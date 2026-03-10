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
_MERMAID_PATTERN = re.compile(r"```mermaid\s*(.*?)```", re.DOTALL)
_CHART_PATTERN = re.compile(r"```chart\s*(.*?)```", re.DOTALL)

# Split answer into segments: plain markdown, mermaid blocks, chart blocks
_BLOCK_PATTERN = re.compile(
    r"(```mermaid\s*.*?```|```chart\s*.*?```)", re.DOTALL
)


def _render_mermaid(code: str) -> None:
    """Render a Mermaid diagram using streamlit.components.v1.html."""
    import html as _html
    import streamlit.components.v1 as components

    escaped = _html.escape(code.strip())
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; background: transparent; }}
        .mermaid {{ background: #fff; border-radius: 8px; padding: 16px; }}
      </style>
    </head>
    <body>
      <div class="mermaid">
{escaped}
      </div>
      <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
      </script>
    </body>
    </html>
    """
    components.html(html_content, height=500, scrolling=True)


def _render_rich_answer(answer: str) -> None:
    """Parse LLM answer and render Mermaid diagrams + chart blocks inline."""
    segments = _BLOCK_PATTERN.split(answer)
    logger.debug(f"_render_rich_answer: {len(segments)} segments, has_mermaid={'```mermaid' in answer}")
    for seg in segments:
        seg_stripped = seg.strip()
        if not seg_stripped:
            continue
        if seg_stripped.startswith("```mermaid"):
            # Extract mermaid code and render via mermaid.js
            m = _MERMAID_PATTERN.match(seg_stripped)
            logger.info(f"Mermaid block detected, regex match={'yes' if m else 'no'}, len={len(seg_stripped)}")
            if m:
                _render_mermaid(m.group(1))
            else:
                st.code(seg_stripped, language="mermaid")
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

    ChromaDB flattens complex metadata values to strings, so this function
    handles both native Python objects and string-serialized representations
    (e.g. ``images`` stored as ``str(list_of_dicts)``).
    """
    import ast as _ast

    # Project root for resolving relative image paths
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

    images: List[Dict[str, Any]] = []
    seen_paths: set = set()

    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico"}

    def _resolve(raw_path: str) -> Optional[Path]:
        """Resolve a path to an absolute Path if the file exists."""
        p = Path(raw_path)
        if p.is_file():
            return p
        # Try relative to project root
        p2 = _PROJECT_ROOT / raw_path
        if p2.is_file():
            return p2
        return None

    def _add(path: str, caption: str, source: str) -> None:
        if not path or len(path) <= 1 or path in seen_paths:
            return
        try:
            resolved = _resolve(path)
            if resolved is None:
                return
            if resolved.suffix.lower() not in _IMG_EXTS:
                return
            key = str(resolved)
            if key in seen_paths:
                return
            seen_paths.add(key)
            images.append({"path": str(resolved), "caption": caption, "source": source})
        except (OSError, ValueError):
            pass

    def _parse_field(value) -> list:
        """Parse a metadata field that may be a list, dict, tuple, or string.

        ChromaDB serialises complex metadata as ``str(obj)``, so the value
        may come back as e.g. ``"{'id':...},{'id':...}"`` which
        ``ast.literal_eval`` parses as a *tuple* of dicts.
        """
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str) and value:
            try:
                parsed = _ast.literal_eval(value)
                if isinstance(parsed, (list, tuple)):
                    return list(parsed)
                if isinstance(parsed, dict):
                    return [parsed]
            except (ValueError, SyntaxError):
                pass
        return []

    for r in results:
        try:
            meta = r.metadata or {}
        except Exception:
            continue
        source_name = Path(meta.get("source_path", "")).name if meta.get("source_path") else ""

        for img in _parse_field(meta.get("images")):
            if isinstance(img, str):
                _add(img, "", source_name)
            elif isinstance(img, dict):
                _add(img.get("path", ""), img.get("caption", ""), source_name)

        for cap in _parse_field(meta.get("image_captions")):
            if isinstance(cap, str):
                _add(cap, "", source_name)
            elif isinstance(cap, dict):
                path = cap.get("path", "")
                if not path:
                    img_id = cap.get("id", "")
                    for img in _parse_field(meta.get("images")):
                        if isinstance(img, dict) and img.get("id") == img_id:
                            path = img.get("path", "")
                            break
                _add(path, cap.get("caption", ""), source_name)

    return images


def _generate_ai_image(prompt: str, api_key: str) -> Optional[str]:
    """Generate an image using DashScope ImageSynthesis (wanx) text-to-image API.

    Returns the image URL on success, None on failure.
    """
    try:
        from http import HTTPStatus
        from dashscope import ImageSynthesis

        rsp = ImageSynthesis.call(
            api_key=api_key,
            model="wanx-v1",
            prompt=prompt,
            n=1,
            size="1024*1024",
        )
        if rsp.status_code == HTTPStatus.OK:
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
                    st.image(img_info["path"], width="stretch")
                    cap = img_info.get("caption", "")
                    src = img_info.get("source", "")
                    label = cap if cap else src
                    if label:
                        st.caption(label)

    # AI generated image
    ai_img_url = entry.get("ai_image_url")
    if ai_img_url:
        with st.expander("🎨 AI 生成配图", expanded=True):
            st.image(ai_img_url, width="stretch")

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
            width="stretch",
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

    # ── Chat history ───────────────────────────────────────────
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = []

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

    # ── Prompt template buttons ────────────────────────────────
    _PROMPT_TEMPLATES = {
        "📊 PPT大纲生成": (
            "我正在为准备一个关于______的售前解决方案PPT。\n"
            "客户的核心痛点是______，我希望通过此次方案的汇报达成______的目标。"
            "请基于以上信息和我上传的公司产品资料，为我设计一个完整的PPT大纲。\n"
            "大纲需要逻辑清晰，层层递进，最终能说服客户。"
            "请直接输出一个包含层级关系（例如，第一级为部分标题，第二级为该部分下的核心论点）的提纲。"
        ),
        "🎯 PPT页面标题设计": (
            "当前PPT的整个逻辑主线是：\"______\"。\n"
            "现在我们需要为其中的______页面设计具体的页面标题。\n"
            "请严格遵循以下要求，一次性输出五个备选标题供我挑选：\n"
            "1. 精准性：准确概括该页的核心内容。\n"
            "2. 客户视角：从客户价值与收益出发，具有吸引力。\n"
            "3. 一致性：风格与整个PPT主线保持一致，专业严谨。\n"
            "4. 表达风格：用语精炼、高大上，避免口语化，字数不超过15字。"
        ),
        "📝 单页内容设计": (
            "当前PPT主题是______，现在我要写其中一页，这页的PPT标题是______，"
            "本页需要具体阐述以下3个要点：\n"
            "1. [请填写要点一]\n"
            "2. [请填写要点二]\n"
            "3. [请填写要点三]\n\n"
            "请按以下结构协助我完成本页内容：\n"
            "1. 总起句：为本页内容撰写一句开篇引语，承上启下。\n"
            "2. 内容阐述：围绕上述三个要点，展开具体、有说服力的论述。\n"
            "3. 呈现形式建议：建议本页内容适合的PPT视觉化呈现形式，并简要说明理由。"
        ),
        "💡 销售主张提炼": (
            '我们的______（解决方案名称）与市场上主流方案相比，'
            '核心优势在于______（例如：独特的算法、集成的生态、灵活的订阅模式）。\n'
            '请帮我将这一优势提炼成一句令人印象深刻、客户易懂易记的“独特销售主张”，'
            '并设计在PPT中至少三处不同的强调方式，句子要求是不超过20个字的金句。'
        ),
        "🔬 技术名词翻译": (
            '我们的技术方案中有一个复杂但关键的概念/架构：______'
            '（例如：微服务化部署、嵌入向量、意图理解），'
            '直接向客户业务人员讲解过于晦涩。请帮我完成以下转换：\n'
            '1. 概念比喻：用一个贴切的商业或生活比喻来解释这个技术概念。\n'
            '2. 价值翻译：将技术的特性直接翻译成给客户业务带来的3个具体价值。'
        ),
    }

    # ── Prompt template quick-fill buttons ────────────────────
    _tpl_cols = st.columns(len(_PROMPT_TEMPLATES))
    for idx, (label, tpl_text) in enumerate(_PROMPT_TEMPLATES.items()):
        with _tpl_cols[idx]:
            if st.button(label, key=f"tpl_{idx}", width="stretch"):
                st.session_state["qa_text_area"] = tpl_text
                st.rerun()

    # ── Chat input (text_area + send button) ──────────────────
    # Clear input from previous send (must happen BEFORE widget creation)
    if st.session_state.get("_qa_clear_input"):
        st.session_state["qa_text_area"] = ""
        del st.session_state["_qa_clear_input"]

    question_text = st.text_area(
        "💬 输入你的问题",
        height=150,
        placeholder="输入你的问题，例如：请根据招标文件写一份投标技术方案\n\n点击上方按钮可快速填入提示词模板，编辑后点击发送。",
        key="qa_text_area",
        label_visibility="collapsed",
    )

    send_clicked = st.button("🚀 发送", type="primary", width="stretch")
    question = question_text.strip() if send_clicked and question_text.strip() else None

    # Schedule clearing for next rerun (after widget has been read)
    if question:
        st.session_state["_qa_clear_input"] = True

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

            spinner_text = "正在检索知识库并生成回答…" if do_retrieve else "正在生成回答…"
            with st.spinner(spinner_text):
                answer, references, raw_results = _generate_answer(
                    question=question,
                    collection=collection,
                    top_k=top_k,
                    max_tokens=max_tokens,
                    uploaded_doc_text=uploaded_doc_text,
                    do_retrieve=do_retrieve,
                )

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

        # Save to history
        st.session_state["qa_history"].append(entry)


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
