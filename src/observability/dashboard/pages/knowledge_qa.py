"""Knowledge Q&A page – ask questions against the knowledge base.

Flow:
1. User enters a question
2. System retrieves relevant chunks from vector DB (HybridSearch)
3. LLM generates an answer grounded in retrieved context
4. User can export the answer as a Markdown/Word document
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

logger = logging.getLogger(__name__)

# ── System prompt for document generation ──────────────────────
SYSTEM_PROMPT = """你是一位专业的系统方案架构师。你的任务是基于提供的参考资料，撰写专业、结构清晰的系统方案文档。

你可能收到两类输入：
- 知识库参考资料：从向量数据库检索到的相关文档片段
- 用户上传文档：用户直接上传的招标文件、需求文档或目录模板等

要求：
1. 回答必须基于提供的参考资料和用户上传文档，不要编造信息
2. 如果用户上传了目录模板或大纲，请严格按照该目录结构组织回答
3. 如果用户上传了招标文件或需求文档，请针对其中的具体需求逐一响应
4. 使用专业的中文技术文档风格
5. 结构清晰，使用 Markdown 格式（标题、列表、表格等）
6. 如果参考资料不足以回答问题，请明确说明哪些部分需要补充
7. 在回答末尾标注参考了哪些来源文档
8. 当方案涉及架构、流程、关系等内容时，使用 Mermaid 语法生成图表，用 ```mermaid 代码块包裹
9. 当方案涉及数据对比、占比、统计等内容时，使用以下 JSON 格式生成图表数据：
   ```chart
   {"type": "bar", "title": "图表标题", "labels": ["A", "B", "C"], "values": [10, 20, 30]}
   ```
   type 可选: bar（柱状图）, pie（饼图）, line（折线图）
"""


def _build_context(results: list, max_chars: int = 8000) -> str:
    """Build context string from retrieval results.
    
    Args:
        results: List of retrieval results
        max_chars: Maximum context length in characters (default 8000)
    
    Returns:
        Context string with truncated chunks if needed
    """
    context_parts = []
    total_chars = 0
    
    for i, r in enumerate(results):
        source = r.metadata.get("source_path", "未知来源")
        source_name = Path(source).name if source != "未知来源" else source
        
        # Truncate chunk if it would exceed max_chars
        chunk_text = r.text
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        if len(chunk_text) > remaining:
            chunk_text = chunk_text[:remaining] + "…"
        
        context_parts.append(
            f"【参考资料 {i + 1}】(来源: {source_name})\n{chunk_text}"
        )
        total_chars += len(chunk_text)
        
        if total_chars >= max_chars:
            break
    
    return "\n\n---\n\n".join(context_parts)


def _parse_uploaded_file(uploaded_file) -> str:
    """Parse an uploaded file and return its text content.

    Uses MarkItDown for rich document formats (PDF, DOCX, PPTX, XLSX)
    and direct read for plain text files (TXT, MD, CSV).
    """
    name = uploaded_file.name.lower()
    plain_exts = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}
    suffix = Path(name).suffix

    if suffix in plain_exts:
        raw = uploaded_file.getvalue()
        for enc in ("utf-8", "gbk", "gb2312", "utf-16"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    # Use MarkItDown for PDF, DOCX, PPTX, XLSX, etc.
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix
        ) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        result = md.convert(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        return result.text_content if result.text_content else ""
    except Exception as e:
        logger.warning(f"MarkItDown failed for {uploaded_file.name}: {e}")
        # Fallback: try reading as text
        try:
            return uploaded_file.getvalue().decode("utf-8", errors="replace")
        except Exception:
            return ""


def _build_messages(
    question: str,
    context: str,
    uploaded_doc_text: str = "",
) -> list:
    """Build LLM message list for RAG generation."""
    from src.libs.llm.base_llm import Message

    parts = []
    if uploaded_doc_text:
        parts.append(f"## 用户上传文档\n\n{uploaded_doc_text}")
    if context:
        parts.append(f"## 知识库参考资料\n\n{context}")

    materials = "\n\n---\n\n".join(parts) if parts else "（无参考资料）"

    user_content = f"""请基于以下材料回答用户的问题。

{materials}

## 用户问题

{question}

请给出详细、专业的回答："""

    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]


# ── Retrieval mode constants ─────────────────────────────────
RETRIEVAL_ALWAYS = "📚 每次都检索"
RETRIEVAL_NEVER = "🚫 不检索"
RETRIEVAL_AUTO = "🤖 模型自动判断"

_JUDGE_PROMPT = """你是一个判断助手。用户将提出一个问题，你需要判断是否需要从知识库中检索参考资料来回答这个问题。

需要检索的情况：
- 问题涉及特定的项目、产品、公司、技术方案等专有知识
- 问题需要引用具体的文档、规范、标准
- 问题涉及特定领域的专业细节

不需要检索的情况：
- 通用的写作、翻译、总结、格式化请求
- 用户已上传了文档，问题完全基于上传文档
- 简单的对话、问候、闲聊
- 通用常识性问题

请只回答一个字："是"（需要检索）或 "否"（不需要检索）。"""


def _should_retrieve_kb(question: str, has_uploaded_doc: bool) -> bool:
    """Use a lightweight LLM call to decide if KB retrieval is needed."""
    from src.libs.llm.base_llm import Message

    # If user uploaded docs and the question seems to reference them, skip KB
    try:
        llm = st.session_state.get("_qa_llm")
        if llm is None:
            return True  # default to retrieval if LLM not ready

        context_hint = ""
        if has_uploaded_doc:
            context_hint = "\n注意：用户已经上传了文档作为参考。"

        messages = [
            Message(role="system", content=_JUDGE_PROMPT),
            Message(role="user", content=f"用户问题：{question}{context_hint}"),
        ]
        response = llm.chat(messages, max_tokens=8)
        answer = response.content.strip()
        return "否" not in answer
    except Exception:
        return True  # default to retrieval on error


# ── Regex patterns for parsing LLM output ────────────────────
_MERMAID_PATTERN = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_CHART_PATTERN = re.compile(r"```chart\s*\n(.*?)```", re.DOTALL)

# Split answer into segments: plain markdown, mermaid blocks, chart blocks
_BLOCK_PATTERN = re.compile(
    r"(```mermaid\s*\n.*?```|```chart\s*\n.*?```)", re.DOTALL
)


def _render_rich_answer(answer: str) -> None:
    """Parse LLM answer and render Mermaid diagrams + chart blocks inline."""
    segments = _BLOCK_PATTERN.split(answer)
    for seg in segments:
        seg_stripped = seg.strip()
        if not seg_stripped:
            continue
        if seg_stripped.startswith("```mermaid"):
            # Extract mermaid code and render
            m = _MERMAID_PATTERN.match(seg_stripped)
            if m:
                mermaid_code = m.group(1).strip()
                st.mermaid(mermaid_code)  # Use st.mermaid() for proper rendering
            else:
                st.markdown(seg_stripped)
        elif seg_stripped.startswith("```chart"):
            m = _CHART_PATTERN.match(seg_stripped)
            if m:
                _render_chart(m.group(1).strip())
            else:
                st.markdown(seg_stripped)
        else:
            st.markdown(seg_stripped)


def _render_chart(json_str: str) -> None:
    """Parse a chart JSON block and render with matplotlib."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False

        data = json.loads(json_str)
        chart_type = data.get("type", "bar")
        title = data.get("title", "")
        labels = data.get("labels", [])
        values = data.get("values", [])

        if not labels or not values:
            st.warning("图表数据为空")
            return

        fig, ax = plt.subplots(figsize=(8, 4))

        if chart_type == "pie":
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.set_title(title)
        elif chart_type == "line":
            ax.plot(labels, values, marker='o', linewidth=2)
            ax.set_title(title)
            ax.grid(True, alpha=0.3)
        else:  # bar
            colors = plt.cm.Set3([i / max(len(labels), 1) for i in range(len(labels))])
            ax.bar(labels, values, color=colors)
            ax.set_title(title)
            ax.grid(True, axis='y', alpha=0.3)

        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    except Exception as e:
        logger.warning(f"Failed to render chart: {e}")
        st.code(json_str, language="json")


def _collect_kb_images(results: list) -> List[Dict[str, Any]]:
    """Extract image paths from retrieval results metadata.

    Returns a list of dicts with 'path', 'caption', 'source' keys.
    Handles various metadata formats: images can be strings, dicts, or lists.
    """
    images = []
    seen_paths = set()

    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico"}

    def _add(path: str, caption: str, source: str) -> None:
        if not path or len(path) <= 1 or path in seen_paths:
            return
        try:
            p = Path(path)
            if p.suffix.lower() not in _IMG_EXTS:
                return
            if p.is_file():
                seen_paths.add(path)
                images.append({"path": path, "caption": caption, "source": source})
        except (OSError, ValueError):
            pass

    for r in results:
        try:
            meta = r.metadata or {}
        except Exception:
            continue
        source_name = Path(meta.get("source_path", "")).name if meta.get("source_path") else ""

        for img in meta.get("images", []):
            if isinstance(img, str):
                _add(img, "", source_name)
            elif isinstance(img, dict):
                _add(img.get("path", ""), img.get("caption", ""), source_name)

        for cap in meta.get("image_captions", []):
            if isinstance(cap, str):
                _add(cap, "", source_name)
            elif isinstance(cap, dict):
                path = cap.get("path", "")
                if not path:
                    img_id = cap.get("id", "")
                    for img in meta.get("images", []):
                        if isinstance(img, dict) and img.get("id") == img_id:
                            path = img.get("path", "")
                            break
                _add(path, cap.get("caption", ""), source_name)

    return images


def _generate_ai_image(prompt: str, api_key: str) -> Optional[str]:
    """Generate an image using DashScope wanx text-to-image API.

    Returns the image URL on success, None on failure.
    """
    try:
        import dashscope
        from dashscope.aigc.image_generation import ImageGeneration
        from dashscope.api_entities.dashscope_response import Message as DSMessage

        dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
        message = DSMessage(
            role="user",
            content=[{"text": prompt}],
        )
        rsp = ImageGeneration.call(
            model="wanx-v1",
            api_key=api_key,
            messages=[message],
            n=1,
            size="1024*1024",
        )
        if rsp.status_code == 200:
            choices = rsp.output.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", [])
                for item in content:
                    if item.get("type") == "image":
                        return item.get("image")
            # Fallback: older API response format
            results = rsp.output.get("results", [])
            if results:
                return results[0].get("url")
        logger.warning(f"AI image generation failed: {rsp}")
        return None
    except Exception as e:
        logger.warning(f"AI image generation error: {e}")
        return None


def _get_hybrid_search(settings: Any, collection: str) -> Any:
    """Get or create a cached HybridSearch instance.

    Components are cached in ``st.session_state`` and only rebuilt when
    *collection* changes, avoiding expensive ChromaDB / Embedding client
    re-initialisation on every query.
    """
    cache_key = "_qa_hybrid_search"
    col_key = "_qa_hybrid_collection"

    cached = st.session_state.get(cache_key)
    cached_col = st.session_state.get(col_key)
    if cached is not None and cached_col == collection:
        return cached

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
    hybrid_search = create_hybrid_search(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
    )

    st.session_state[cache_key] = hybrid_search
    st.session_state[col_key] = collection
    return hybrid_search


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


def _render_entry(entry: Dict[str, Any], key_suffix: str) -> None:
    """Render a single Q&A entry (answer + images + buttons)."""
    # Rich answer rendering (Mermaid + charts inline)
    _render_rich_answer(entry["answer"])

    # Knowledge base images
    kb_images = entry.get("kb_images", [])
    if kb_images:
        with st.expander(f"📷 知识库相关图片 ({len(kb_images)})", expanded=False):
            cols = st.columns(min(len(kb_images), 3))
            for i, img_info in enumerate(kb_images):
                with cols[i % 3]:
                    st.image(img_info["path"], use_container_width=True)
                    cap = img_info.get("caption", "")
                    src = img_info.get("source", "")
                    label = cap if cap else src
                    if label:
                        st.caption(label)

    # AI generated image
    ai_img_url = entry.get("ai_image_url")
    if ai_img_url:
        with st.expander("🎨 AI 生成配图", expanded=True):
            st.image(ai_img_url, use_container_width=True)

    # Export + reference buttons
    col_md, col_ref = st.columns([1, 1])
    with col_md:
        doc_content = _export_markdown(entry["question"], entry["answer"])
        st.download_button(
            "\u2B07\ufe0f 导出 Markdown",
            data=doc_content,
            file_name="系统方案.md",
            mime="text/markdown",
            key=f"dl_md_{key_suffix}",
            use_container_width=True,
        )
    with col_ref:
        if st.button("\U0001F50D 查看参考资料", key=f"ref_{key_suffix}"):
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
            "单次生成长度", min_value=512, max_value=8192, value=4096,
            step=512, key="qa_max_tokens",
            help="每轮生成的最大 token 数。超长文档会自动分段续写（最多 6 轮）"
        )

        st.markdown("### ️ 图片与图表")
        enable_kb_images = st.checkbox(
            "显示知识库图片", value=True, key="qa_kb_images",
            help="从检索到的文档中提取相关图片"
        )
        enable_ai_image = st.checkbox(
            "AI 生成配图", value=False, key="qa_ai_image",
            help="根据方案内容自动生成 AI 配图（需消耗通义万相额度）"
        )

    # ── Chat history (persisted to SQLite) ───────────────────────
    import sqlite3 as _sqlite3
    _history_db = Path("data/qa_history.db")
    _history_db.parent.mkdir(parents=True, exist_ok=True)
    
    def _init_history_db() -> None:
        conn = _sqlite3.connect(str(_history_db))
        conn.execute("""CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            references_json TEXT DEFAULT '[]',
            kb_images_json TEXT DEFAULT '[]',
            ai_image_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.commit()
        conn.close()
    
    def _load_history() -> List[Dict]:
        try:
            _init_history_db()
            conn = _sqlite3.connect(str(_history_db))
            rows = conn.execute(
                "SELECT id, question, answer, references_json, kb_images_json, ai_image_url FROM qa_history ORDER BY id"
            ).fetchall()
            conn.close()
            history = []
            for row in rows:
                history.append({
                    "id": row[0],
                    "question": row[1],
                    "answer": row[2],
                    "references": json.loads(row[3]) if row[3] else [],
                    "kb_images": json.loads(row[4]) if row[4] else [],
                    "ai_image_url": row[5] or None,
                })
            return history
        except Exception as e:
            logger.warning(f"Failed to load QA history: {e}")
            return []
    
    def _save_entry(entry: Dict) -> None:
        try:
            _init_history_db()
            conn = _sqlite3.connect(str(_history_db))
            conn.execute(
                "INSERT OR REPLACE INTO qa_history (id, question, answer, references_json, kb_images_json, ai_image_url) VALUES (?,?,?,?,?,?)",
                (entry["id"], entry["question"], entry["answer"],
                 json.dumps(entry.get("references", []), ensure_ascii=False),
                 json.dumps(entry.get("kb_images", []), ensure_ascii=False),
                 entry.get("ai_image_url", ""))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save QA entry: {e}")
    
    def _clear_history() -> None:
        try:
            conn = _sqlite3.connect(str(_history_db))
            conn.execute("DELETE FROM qa_history")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to clear QA history: {e}")
    
    # Migrate from old JSON if exists
    _old_json = Path("data/qa_history.json")
    if _old_json.exists() and (not _history_db.exists() or os.path.getsize(str(_history_db)) == 0):
        try:
            _init_history_db()
            with open(_old_json, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for entry in old_data:
                _save_entry(entry)
            _old_json.rename(_old_json.with_suffix(".json.migrated"))
            logger.info(f"Migrated {len(old_data)} QA entries from JSON to SQLite")
        except Exception:
            pass
    
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = _load_history()

    # Clear history button in sidebar
    with st.sidebar:
        if st.button("🗑️ 清空对话历史", key="qa_clear_history"):
            _clear_history()
            st.session_state["qa_history"] = []
            st.rerun()

    # Display chat history
    for entry in st.session_state["qa_history"]:
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            _render_entry(entry, key_suffix=str(entry["id"]))

    # ── File upload ────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "📎 上传文档（招标文件、需求文档、目录模板等）",
        type=["pdf", "docx", "doc", "pptx", "xlsx", "txt", "md", "csv"],
        accept_multiple_files=True,
        key="qa_file_upload",
        help="上传后，AI 将结合文档内容与知识库一起生成方案",
    )

    # Parse uploaded files and cache in session_state
    uploaded_doc_text = ""
    if uploaded_files:
        file_texts = []
        for uf in uploaded_files:
            cache_key = f"_parsed_{uf.name}_{uf.size}"
            if cache_key not in st.session_state:
                with st.spinner(f"正在解析 {uf.name}…"):
                    st.session_state[cache_key] = _parse_uploaded_file(uf)
            file_texts.append(
                f"### 文件: {uf.name}\n\n{st.session_state[cache_key]}"
            )
        uploaded_doc_text = "\n\n---\n\n".join(file_texts)
        st.caption(
            f"已加载 {len(uploaded_files)} 个文档："
            + "、".join(uf.name for uf in uploaded_files)
        )

    # ── Retrieval mode (above chat input, horizontal) ─────────
    retrieval_mode = st.radio(
        "🔍 检索方式",
        options=[RETRIEVAL_AUTO, RETRIEVAL_ALWAYS, RETRIEVAL_NEVER],
        index=0,
        key="qa_retrieval_mode",
        horizontal=True,
    )

    # ── Chat input ─────────────────────────────────────────────
    question = st.chat_input("输入你的问题，例如：请根据招标文件写一份投标技术方案")

    if question:
        from src.core.settings import load_settings
        settings = load_settings()

        # Show user message
        with st.chat_message("user"):
            st.markdown(question)
            if uploaded_files:
                st.caption(
                    "📎 附件：" + "、".join(uf.name for uf in uploaded_files)
                )

        # Generate answer
        with st.chat_message("assistant"):
            # Determine whether to retrieve from KB
            do_retrieve = True
            if retrieval_mode == RETRIEVAL_NEVER:
                do_retrieve = False
            elif retrieval_mode == RETRIEVAL_AUTO:
                with st.spinner("🤖 正在判断是否需要检索知识库…"):
                    do_retrieve = _should_retrieve_kb(
                        question, bool(uploaded_doc_text)
                    )
                if not do_retrieve:
                    st.caption("💡 模型判断本次无需检索知识库")

            # Step 1: Retrieve context
            references = []
            raw_results = []
            context = ""
            if do_retrieve:
                with st.spinner("正在检索知识库…"):
                    try:
                        hybrid_search = _get_hybrid_search(settings, collection)
                        raw_results = hybrid_search.search(query=question, top_k=top_k)
                        references = [
                            {"source": r.metadata.get("source_path", "未知"), "score": r.score, "text": r.text}
                            for r in raw_results
                        ]
                        context = _build_context(raw_results)
                    except Exception as exc:
                        logger.exception("Retrieval failed")
                        st.error(f"❌ 知识库检索失败: {exc}")

            # Step 2: Stream LLM answer
            llm_key = "_qa_llm"
            llm = st.session_state.get(llm_key)
            if llm is None:
                from src.libs.llm.llm_factory import LLMFactory
                llm = LLMFactory.create(settings)
                st.session_state[llm_key] = llm

            messages = _build_messages(question, context, uploaded_doc_text)
            
            # Try streaming, fall back to non-streaming
            try:
                stream = llm.chat_stream(messages, max_tokens=max_tokens)
                answer = st.write_stream(stream)
            except Exception:
                # Fallback: non-streaming
                with st.spinner("正在生成回答…"):
                    response = llm.chat(messages, max_tokens=max_tokens)
                    answer = response.content
                    st.markdown(answer)

            # Collect KB images from retrieval results
            kb_images: List[Dict[str, Any]] = []
            if enable_kb_images and raw_results:
                kb_images = _collect_kb_images(raw_results)

            # AI image generation
            ai_image_url: Optional[str] = None
            if enable_ai_image and not answer.startswith("❌") and not answer.startswith("⚠"):
                with st.spinner("🎨 正在生成 AI 配图…"):
                    # Build a short prompt from the question
                    img_prompt = f"专业技术方案配图，简洁现代风格：{question[:80]}"
                    api_key = getattr(settings, 'vision_llm', None)
                    api_key = getattr(api_key, 'api_key', '') if api_key else ''
                    if not api_key:
                        api_key = getattr(settings.llm, 'api_key', '')
                    if api_key:
                        ai_image_url = _generate_ai_image(img_prompt, api_key)

            entry_id = int(time.time() * 1000)
            entry = {
                "id": entry_id,
                "question": question,
                "answer": answer,
                "references": references,
                "kb_images": kb_images,
                "ai_image_url": ai_image_url,
            }

            _render_entry(entry, key_suffix="latest")

        # Save to history (persisted to SQLite)
        st.session_state["qa_history"].append(entry)
        _save_entry(entry)


def _generate_answer(
    question: str,
    collection: str,
    top_k: int,
    max_tokens: int,
    uploaded_doc_text: str = "",
    do_retrieve: bool = True,
) -> tuple:
    """Retrieve context and generate LLM answer.

    Returns (answer_text, references_list, raw_results).
    raw_results is the list of RetrievalResult objects (for KB image extraction).
    """
    from src.core.settings import load_settings
    from src.libs.llm.llm_factory import LLMFactory
    from src.libs.llm.base_llm import Message

    settings = load_settings()
    references: list = []
    raw_results: list = []
    context: str = ""

    # Step 1: Retrieve relevant chunks (if needed)
    if do_retrieve:
        try:
            hybrid_search = _get_hybrid_search(settings, collection)
            raw_results = hybrid_search.search(query=question, top_k=top_k)

            if not raw_results and not uploaded_doc_text:
                return "⚠️ 未在知识库中找到相关内容。请确认知识库已构建且集合名称正确，或上传文档后重试。", [], []

            references = [
                {
                    "source": r.metadata.get("source_path", "未知"),
                    "score": r.score,
                    "text": r.text,
                }
                for r in raw_results
            ]

            context = _build_context(raw_results)
        except Exception as exc:
            logger.exception("Retrieval failed")
            return f"❌ 知识库检索失败: {exc}", [], []
    elif not uploaded_doc_text:
        # No retrieval and no uploaded doc — use LLM's own knowledge
        pass

    # Step 2: Generate answer with LLM (multi-turn continuation)
    # If the model stops due to max_tokens (finish_reason='length'),
    # automatically continue generating until the answer is complete.
    MAX_CONTINUATIONS = 5  # safety limit to avoid infinite loops
    CONTINUE_PROMPT = "请继续，从你上次中断的地方接着写，不要重复已有内容。"

    try:
        llm_key = "_qa_llm"
        llm = st.session_state.get(llm_key)
        if llm is None:
            llm = LLMFactory.create(settings)
            st.session_state[llm_key] = llm

        messages = _build_messages(question, context, uploaded_doc_text)
        segments: list = []

        for turn in range(MAX_CONTINUATIONS + 1):
            response = llm.chat(messages, max_tokens=max_tokens)
            segments.append(response.content)

            # If the model finished naturally, we're done
            if getattr(response, 'finish_reason', 'stop') != 'length':
                break

            logger.info(f"LLM output truncated (turn {turn + 1}), auto-continuing…")

            # Append assistant's partial answer + user continuation request
            messages.append(Message(role="assistant", content=response.content))
            messages.append(Message(role="user", content=CONTINUE_PROMPT))

        full_answer = "".join(segments)
        return full_answer, references, raw_results
    except Exception as exc:
        logger.exception("LLM generation failed")
        return f"❌ 大模型生成失败: {exc}", references, raw_results
