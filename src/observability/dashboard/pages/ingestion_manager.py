"""Ingestion Manager page – upload files, trigger ingestion, delete documents.

Layout:
1. File uploader + collection selector
2. Ingest button → progress bar (using on_progress callback)
3. Document list with delete buttons
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import streamlit as st

from src.observability.dashboard.services.data_service import DataService


def _run_ingestion(
    uploaded_file: "st.runtime.uploaded_file_manager.UploadedFile",
    collection: str,
    progress_bar: "st.delta_generator.DeltaGenerator",
    status_text: "st.delta_generator.DeltaGenerator",
) -> None:
    """Save the uploaded file to a temp location and run the pipeline."""
    from src.core.settings import load_settings
    from src.core.trace import TraceContext, TraceCollector
    from src.ingestion.pipeline import IngestionPipeline

    settings = load_settings()

    # Write uploaded file to a temp location
    suffix = Path(uploaded_file.name).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    _STAGE_LABELS = {
        "integrity": "🔍 检查文件完整性…",
        "load": "📄 加载文档…",
        "split": "✂️ 文档分块…",
        "transform": "🔄 转换分块 (LLM 优化 + 元数据增强)…",
        "embed": "🔢 向量编码…",
        "upsert": "💾 存储到数据库…",
    }

    def on_progress(stage: str, current: int, total: int) -> None:
        frac = (current - 1) / total  # stage just started, show partial progress
        label = _STAGE_LABELS.get(stage, stage)
        progress_bar.progress(frac, text=f"[{current}/{total}] {label}")
        status_text.caption(label)

    trace = TraceContext(trace_type="ingestion")
    trace.metadata["source_path"] = uploaded_file.name
    trace.metadata["collection"] = collection
    trace.metadata["source"] = "dashboard"

    try:
        pipeline = IngestionPipeline(settings, collection=collection)
        pipeline.run(
            file_path=tmp_path,
            trace=trace,
            on_progress=on_progress,
        )
        progress_bar.progress(1.0, text="✅ 完成")
        status_text.success(f"成功将 **{uploaded_file.name}** 摄取到集合 **{collection}** 中。")
    except Exception as exc:
        status_text.error(f"摄取失败: {exc}")
    finally:
        TraceCollector().collect(trace)
        # Clean up temp file
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


def render() -> None:
    """Render the Ingestion Manager page."""
    st.header("📥 摄取管理")

    # ── Upload section ─────────────────────────────────────────────
    st.subheader("📤 上传与摄取")

    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded = st.file_uploader(
            "选择要摄取的文件",
            type=["pdf", "txt", "md", "docx"],
            key="ingest_uploader",
        )
    with col2:
        collection = st.text_input("集合", value="default", key="ingest_collection")

    if uploaded is not None:
        if st.button("🚀 开始摄取", key="btn_ingest"):
            progress_bar = st.progress(0, text="准备中…")
            status_text = st.empty()
            _run_ingestion(uploaded, collection.strip() or "default", progress_bar, status_text)

    st.divider()

    # ── Document management section ────────────────────────────────
    st.subheader("🗑️ 文档管理")

    try:
        svc = DataService()
        docs = svc.list_documents()
    except Exception as exc:
        st.error(f"加载文档失败: {exc}")
        return

    if not docs:
        st.info(
            "**尚未摄取任何文档。** "
            "请在上方上传 PDF、TXT、MD 或 DOCX 文件，然后点击『开始摄取』。"
        )
        return

    for idx, doc in enumerate(docs):
        col_info, col_btn = st.columns([4, 1])
        with col_info:
            st.markdown(
                f"**{doc['source_path']}** — "
                f"集合: `{doc.get('collection', '—')}` | "
                f"分块: {doc['chunk_count']} | "
                f"图片: {doc['image_count']}"
            )
        with col_btn:
            if st.button("🗑️ 删除", key=f"del_{idx}"):
                try:
                    result = svc.delete_document(
                        source_path=doc["source_path"],
                        collection=doc.get("collection", "default"),
                        source_hash=doc.get("source_hash"),
                    )
                    if result.success:
                        st.success(
                            f"已删除: {result.chunks_deleted} 个分块, "
                            f"{result.images_deleted} 张图片。"
                        )
                        st.rerun()
                    else:
                        st.warning(f"部分删除。错误: {result.errors}")
                except Exception as exc:
                    st.error(f"删除失败: {exc}")
