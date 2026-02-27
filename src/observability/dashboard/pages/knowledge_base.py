"""Knowledge Base Builder page – scan a local directory and batch-ingest all documents.

Layout:
1. Directory path input
2. File type filter & collection name
3. Preview scanned files
4. Start button → batch ingestion with per-file progress
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

import streamlit as st

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


def _open_folder_dialog() -> str:
    """Open a native OS folder picker dialog in a subprocess.

    Running tkinter in a separate process avoids threading conflicts
    with Streamlit's execution model.
    """
    try:
        import subprocess
        import sys

        script = (
            "import tkinter as tk; "
            "from tkinter import filedialog; "
            "root = tk.Tk(); "
            "root.withdraw(); "
            "root.wm_attributes('-topmost', 1); "
            "folder = filedialog.askdirectory(title='选择知识库文件夹', mustexist=True); "
            "root.destroy(); "
            "print(folder or '')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _scan_directory(directory: Path) -> List[Path]:
    """Recursively scan a directory for supported document files."""
    files: List[Path] = []
    for root, _dirs, filenames in os.walk(directory):
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.suffix.lower() in SUPPORTED_EXTENSIONS and not fname.startswith("."):
                files.append(fpath)
    return files


def _run_batch_ingestion(
    files: List[Path],
    collection: str,
    progress_bar: "st.delta_generator.DeltaGenerator",
    status_text: "st.delta_generator.DeltaGenerator",
    file_status_container: "st.delta_generator.DeltaGenerator",
) -> dict:
    """Run ingestion pipeline on each file sequentially."""
    from src.core.settings import load_settings
    from src.core.trace import TraceContext, TraceCollector
    from src.ingestion.pipeline import IngestionPipeline

    settings = load_settings()
    collector = TraceCollector()

    results = {"success": 0, "skipped": 0, "failed": 0, "errors": []}
    total = len(files)

    for idx, fpath in enumerate(files):
        file_label = fpath.name
        progress_frac = idx / total
        progress_bar.progress(progress_frac, text=f"[{idx + 1}/{total}] 正在处理: {file_label}")
        status_text.caption(f"📄 {fpath}")

        trace = TraceContext(trace_type="ingestion")
        trace.metadata["source_path"] = str(fpath)
        trace.metadata["collection"] = collection
        trace.metadata["source"] = "knowledge_base_builder"

        try:
            pipeline = IngestionPipeline(settings, collection=collection)
            result = pipeline.run(file_path=str(fpath), trace=trace)

            # Check if file was skipped (already processed)
            integrity_stage = result.stages.get("integrity", {})
            if integrity_stage.get("skipped"):
                results["skipped"] += 1
                file_status_container.markdown(
                    f"⏭️ `{file_label}` — 已存在，跳过"
                )
            elif result.success:
                results["success"] += 1
                file_status_container.markdown(
                    f"✅ `{file_label}` — 成功"
                )
            else:
                err_msg = result.error or "未知错误"
                results["failed"] += 1
                results["errors"].append(f"{file_label}: {err_msg}")
                file_status_container.markdown(
                    f"❌ `{file_label}` — {err_msg}"
                )
        except Exception as exc:
            results["failed"] += 1
            results["errors"].append(f"{file_label}: {exc}")
            file_status_container.markdown(
                f"❌ `{file_label}` — {exc}"
            )
        finally:
            collector.collect(trace)

    progress_bar.progress(1.0, text="✅ 全部完成")
    return results


def render() -> None:
    """Render the Knowledge Base Builder page."""
    st.header("📂 知识库构建")
    st.markdown("指定本机的一个文件夹，自动扫描其中所有文档并批量摄取到向量数据库中，一键构建知识库。")

    st.markdown("")

    # ── Directory input ────────────────────────────────────────
    st.markdown("### 📁 选择目录")

    # 浏览按钮通过 on_click 回调在 rerun 前同步弹出 tkinter 对话框
    if "kb_dir_input" not in st.session_state:
        st.session_state["kb_dir_input"] = ""

    def _browse_callback() -> None:
        """on_click callback – runs synchronously BEFORE the rerun."""
        selected = _open_folder_dialog()
        if selected:
            st.session_state["kb_dir_input"] = selected

    col_input, col_browse = st.columns([5, 1])
    with col_input:
        dir_path_str = st.text_input(
            "本地文件夹路径",
            key="kb_dir_input",
            placeholder=r"例如: D:\Documents\MyKnowledgeBase",
            help="输入要作为知识库的本地文件夹完整路径，支持子目录递归扫描。",
        )
    with col_browse:
        st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
        st.button(
            "\U0001F4C1 浏览…",
            key="kb_browse_btn",
            use_container_width=True,
            on_click=_browse_callback,
        )

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        collection = st.text_input(
            "集合名称",
            value="default",
            key="kb_collection",
            help="文档将被存储到此向量数据库集合中。",
        )
    with col_cfg2:
        ext_filter = st.multiselect(
            "文件类型筛选",
            options=["PDF", "TXT", "MD", "DOCX"],
            default=["PDF", "TXT", "MD", "DOCX"],
            key="kb_ext_filter",
            help="选择要扫描的文件类型。",
        )

    # Convert filter to extensions set
    active_extensions = {f".{e.lower()}" for e in ext_filter} if ext_filter else SUPPORTED_EXTENSIONS

    st.markdown("")

    # ── Scan & Preview ─────────────────────────────────────────
    dir_path = Path(dir_path_str.strip()) if dir_path_str.strip() else None
    scanned_files: List[Path] = []

    if dir_path and dir_path.is_dir():
        all_files = _scan_directory(dir_path)
        scanned_files = [f for f in all_files if f.suffix.lower() in active_extensions]

        st.markdown("### 📋 扫描结果")

        if scanned_files:
            # Summary metrics
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.metric("📄 文件总数", len(scanned_files))
            with mc2:
                # Group by extension
                ext_counts = {}
                for f in scanned_files:
                    ext = f.suffix.lower()
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                ext_summary = " · ".join(f"{ext}: {cnt}" for ext, cnt in sorted(ext_counts.items()))
                st.metric("📊 类型分布", ext_summary)
            with mc3:
                total_size = sum(f.stat().st_size for f in scanned_files)
                if total_size >= 1024 * 1024:
                    size_label = f"{total_size / (1024 * 1024):.1f} MB"
                elif total_size >= 1024:
                    size_label = f"{total_size / 1024:.1f} KB"
                else:
                    size_label = f"{total_size} B"
                st.metric("💾 总大小", size_label)

            # File list in an expander
            with st.expander(f"查看文件列表 ({len(scanned_files)} 个文件)", expanded=False):
                for i, f in enumerate(scanned_files):
                    rel = f.relative_to(dir_path) if f.is_relative_to(dir_path) else f
                    size_kb = f.stat().st_size / 1024
                    st.markdown(f"`{i+1}.` 📄 `{rel}` — {size_kb:.1f} KB")

            st.markdown("")

            # ── Start button ───────────────────────────────────
            st.markdown("### 🚀 开始构建")
            st.info(
                f"将把 **{len(scanned_files)}** 个文件摄取到集合 **{collection.strip() or 'default'}** 中。"
                "已处理过的文件会自动跳过（基于文件哈希判断）。"
            )

            if st.button("🚀 开始构建知识库", type="primary", key="kb_start_btn"):
                st.markdown("---")
                progress_bar = st.progress(0, text="准备中…")
                status_text = st.empty()
                file_status_container = st.container()

                results = _run_batch_ingestion(
                    files=scanned_files,
                    collection=collection.strip() or "default",
                    progress_bar=progress_bar,
                    status_text=status_text,
                    file_status_container=file_status_container,
                )

                # ── Final summary ──────────────────────────────
                st.markdown("---")
                st.markdown("### 📊 构建结果")
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.metric("✅ 成功", results["success"])
                with rc2:
                    st.metric("⏭️ 跳过", results["skipped"])
                with rc3:
                    st.metric("❌ 失败", results["failed"])

                if results["failed"] == 0:
                    st.success(
                        f"🎉 知识库构建完成！成功摄取 {results['success']} 个文件，"
                        f"跳过 {results['skipped']} 个已存在文件。"
                    )
                else:
                    st.warning(
                        f"构建完成，但有 {results['failed']} 个文件失败。"
                    )
                    with st.expander("查看错误详情"):
                        for err in results["errors"]:
                            st.error(err)
        else:
            st.warning(f"该目录下未找到支持的文档文件（{', '.join(sorted(active_extensions))}）。")

    elif dir_path_str.strip():
        st.error(f"❌ 路径不存在或不是有效目录: `{dir_path_str}`")
    else:
        # Empty state – guide user
        st.markdown(
            """
            <div style="
                background: #f8f9fa;
                border: 2px dashed #dee2e6;
                border-radius: 12px;
                padding: 3rem 2rem;
                text-align: center;
                color: #888;
            ">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📂</div>
                <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 0.3rem;">
                    在上方输入本地文件夹路径
                </div>
                <div style="font-size: 0.85rem;">
                    支持 PDF、TXT、Markdown、DOCX 格式 · 自动递归扫描子目录
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
