"""Knowledge Q&A page – ask questions against the knowledge base.

Flow:
1. User enters a question
2. System retrieves relevant chunks from vector DB (HybridSearch)
3. LLM generates an answer grounded in retrieved context
4. User can export the answer as a Markdown/Word document
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

logger = logging.getLogger(__name__)

# ── System prompt for document generation ──────────────────────
SYSTEM_PROMPT = """你是一位专业的系统方案架构师。你的任务是基于提供的参考资料，撰写专业、结构清晰的系统方案文档。

要求：
1. 回答必须基于提供的参考资料，不要编造信息
2. 使用专业的中文技术文档风格
3. 结构清晰，使用 Markdown 格式（标题、列表、表格等）
4. 如果参考资料不足以回答问题，请明确说明哪些部分需要补充
5. 在回答末尾标注参考了哪些来源文档"""


def _build_context(results: list) -> str:
    """Build context string from retrieval results."""
    context_parts = []
    for i, r in enumerate(results):
        source = r.metadata.get("source_path", "未知来源")
        source_name = Path(source).name if source != "未知来源" else source
        context_parts.append(
            f"【参考资料 {i + 1}】(来源: {source_name})\n{r.text}"
        )
    return "\n\n---\n\n".join(context_parts)


def _build_messages(question: str, context: str) -> list:
    """Build LLM message list for RAG generation."""
    from src.libs.llm.base_llm import Message

    user_content = f"""请基于以下参考资料回答用户的问题。

## 参考资料

{context}

## 用户问题

{question}

请给出详细、专业的回答："""

    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]


def _create_hybrid_search(settings: Any, collection: str) -> Any:
    """Create HybridSearch instance for retrieval."""
    from src.core.query_engine.query_processor import QueryProcessor
    from src.core.query_engine.hybrid_search import create_hybrid_search
    from src.core.query_engine.dense_retriever import create_dense_retriever
    from src.core.query_engine.sparse_retriever import create_sparse_retriever
    from src.ingestion.storage.bm25_indexer import BM25Indexer
    from src.libs.embedding.embedding_factory import EmbeddingFactory
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory
    from src.core.settings import resolve_path

    vector_store = VectorStoreFactory.create(settings, collection_name=collection)
    embedding_client = EmbeddingFactory.create(settings)
    dense_retriever = create_dense_retriever(
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    bm25_indexer = BM25Indexer(
        index_dir=str(resolve_path(f"data/db/bm25/{collection}"))
    )
    sparse_retriever = create_sparse_retriever(
        settings=settings,
        bm25_indexer=bm25_indexer,
        vector_store=vector_store,
    )
    sparse_retriever.default_collection = collection

    query_processor = QueryProcessor()
    return create_hybrid_search(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
    )


def _export_markdown(question: str, answer: str) -> str:
    """Generate a Markdown document from Q&A."""
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    return f"""# 系统方案文档

> 生成时间: {timestamp}

## 需求描述

{question}

## 方案内容

{answer}
"""


def render() -> None:
    """Render the Knowledge Q&A page."""
    st.header("\U0001F4AC 知识库问答")
    st.markdown("基于已构建的知识库，输入问题即可检索相关内容并由大模型生成专业回答，支持导出为文档。")

    # ── Settings ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### \u2699\ufe0f 问答设置")
        collection = st.text_input(
            "集合名称", value="default", key="qa_collection",
            help="从哪个集合检索"
        )
        top_k = st.slider(
            "检索数量 (Top-K)", min_value=1, max_value=20, value=5,
            key="qa_top_k", help="每次检索返回的分块数量"
        )
        max_tokens = st.slider(
            "最大生成长度", min_value=512, max_value=8192, value=4096,
            step=512, key="qa_max_tokens"
        )

    # ── Chat history ───────────────────────────────────────────
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = []

    # Display chat history
    for entry in st.session_state["qa_history"]:
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            st.markdown(entry["answer"])
            # Export buttons for each answer
            col_md, col_copy = st.columns([1, 1])
            with col_md:
                doc_content = _export_markdown(entry["question"], entry["answer"])
                st.download_button(
                    "\u2B07\ufe0f 导出 Markdown",
                    data=doc_content,
                    file_name="系统方案.md",
                    mime="text/markdown",
                    key=f"dl_md_{entry['id']}",
                    width='stretch',
                )
            with col_copy:
                if st.button("\U0001F50D 查看参考资料", key=f"ref_{entry['id']}"):
                    with st.expander("参考资料详情", expanded=True):
                        for i, ref in enumerate(entry.get("references", [])):
                            source = Path(ref.get("source", "未知")).name
                            score = ref.get("score", 0)
                            text = ref.get("text", "")
                            st.markdown(
                                f"**[{i+1}] {source}** (相关度: {score:.3f})"
                            )
                            st.text(text[:300] + ("..." if len(text) > 300 else ""))
                            st.divider()

    # ── Chat input ─────────────────────────────────────────────
    question = st.chat_input("输入你的问题，例如：请帮我写一份数据仓库架构设计方案")

    if question:
        # Show user message
        with st.chat_message("user"):
            st.markdown(question)

        # Generate answer
        with st.chat_message("assistant"):
            with st.spinner("正在检索知识库并生成回答…"):
                answer, references = _generate_answer(
                    question=question,
                    collection=collection,
                    top_k=top_k,
                    max_tokens=max_tokens,
                )
            st.markdown(answer)

            # Export buttons
            col_md, col_ref = st.columns([1, 1])
            with col_md:
                doc_content = _export_markdown(question, answer)
                st.download_button(
                    "\u2B07\ufe0f 导出 Markdown",
                    data=doc_content,
                    file_name="系统方案.md",
                    mime="text/markdown",
                    key=f"dl_md_latest",
                )

        # Save to history
        entry_id = int(time.time() * 1000)
        st.session_state["qa_history"].append({
            "id": entry_id,
            "question": question,
            "answer": answer,
            "references": references,
        })


def _generate_answer(
    question: str,
    collection: str,
    top_k: int,
    max_tokens: int,
) -> tuple:
    """Retrieve context and generate LLM answer.

    Returns (answer_text, references_list).
    """
    from src.core.settings import load_settings
    from src.libs.llm.llm_factory import LLMFactory

    settings = load_settings()
    references = []

    # Step 1: Retrieve relevant chunks
    try:
        hybrid_search = _create_hybrid_search(settings, collection)
        results = hybrid_search.search(query=question, top_k=top_k)

        if not results:
            return "⚠️ 未在知识库中找到相关内容。请确认知识库已构建且集合名称正确。", []

        references = [
            {
                "source": r.metadata.get("source_path", "未知"),
                "score": r.score,
                "text": r.text,
            }
            for r in results
        ]

        context = _build_context(results)
    except Exception as exc:
        logger.exception("Retrieval failed")
        return f"❌ 知识库检索失败: {exc}", []

    # Step 2: Generate answer with LLM
    try:
        llm = LLMFactory.create(settings)
        messages = _build_messages(question, context)
        response = llm.chat(messages, max_tokens=max_tokens)
        return response.content, references
    except Exception as exc:
        logger.exception("LLM generation failed")
        return f"❌ 大模型生成失败: {exc}", references
