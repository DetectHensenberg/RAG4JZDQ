"""Overview page – system configuration and data statistics.

Displays:
- Component configuration cards (LLM, Embedding, VectorStore …)
- Collection statistics (document count, chunk count, image count)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from src.observability.dashboard.services.config_service import ConfigService


# ── Icon / colour mapping for component cards ─────────────────────
_CARD_STYLE = {
    "LLM":          {"icon": "🧠", "color": "#6C63FF"},
    "Embedding":    {"icon": "📐", "color": "#00B4D8"},
    "Vector Store": {"icon": "🗄️", "color": "#2EC4B6"},
    "Retrieval":    {"icon": "🔎", "color": "#FF6B6B"},
    "Reranker":     {"icon": "🏅", "color": "#FCA311"},
    "Vision LLM":   {"icon": "👁️", "color": "#9B5DE5"},
    "Ingestion":    {"icon": "📥", "color": "#00F5D4"},
}


def _safe_collection_stats() -> Dict[str, Any]:
    """Attempt to load collection statistics from ChromaDB.

    Returns empty dict on failure so the page still renders.
    """
    try:
        from src.core.settings import load_settings, resolve_path
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        settings = load_settings()
        persist_dir = str(
            resolve_path(settings.vector_store.persist_directory)
        )
        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        stats: Dict[str, Any] = {}
        for col in client.list_collections():
            name = col.name if hasattr(col, "name") else str(col)
            collection = client.get_collection(name)
            stats[name] = {"chunk_count": collection.count()}
        return stats
    except Exception:
        return {}


def _safe_trace_count() -> int:
    """Return trace line count, or -1 on failure."""
    try:
        from src.core.settings import resolve_path
        traces_path = resolve_path("logs/traces.jsonl")
        if traces_path.exists():
            return sum(1 for _ in traces_path.open(encoding="utf-8"))
        return 0
    except Exception:
        return -1


def _component_card_html(icon: str, name: str, provider: str, model: str, color: str) -> str:
    """Return styled HTML for a single component card."""
    return f"""
<div style="
    background: linear-gradient(135deg, {color}18, {color}08);
    border-left: 4px solid {color};
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    margin-bottom: 0.5rem;
    transition: transform 0.15s;
">
    <div style="font-size:1.6rem; margin-bottom:0.3rem;">{icon}</div>
    <div style="font-size:1.05rem; font-weight:700; color:{color}; margin-bottom:0.35rem;">{name}</div>
    <div style="font-size:0.82rem; color:#888; line-height:1.55;">
        提供商 &nbsp;<code style="background:#f0f0f0;padding:1px 6px;border-radius:4px;font-size:0.8rem;">{provider}</code><br/>
        模型 &nbsp;<code style="background:#f0f0f0;padding:1px 6px;border-radius:4px;font-size:0.8rem;">{model}</code>
    </div>
</div>"""


def render() -> None:
    """Render the Overview page."""

    # ── Welcome banner ─────────────────────────────────────────
    st.markdown(
        """
        <div style="
            background: linear-gradient(135deg, #6C63FF 0%, #00B4D8 100%);
            border-radius: 16px;
            padding: 2rem 2.2rem;
            margin-bottom: 1.8rem;
            color: white;
        ">
            <h1 style="margin:0 0 0.3rem 0; font-size:1.75rem; font-weight:800;">
                📊 模块化 RAG 管理平台
            </h1>
            <p style="margin:0; opacity:0.92; font-size:0.95rem;">
                检索增强生成系统 · 知识库管理 · 性能追踪 · 评估分析
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Quick stats row ────────────────────────────────────────
    stats = _safe_collection_stats()
    trace_count = _safe_trace_count()
    total_chunks = sum(v.get("chunk_count", 0) for v in stats.values()) if stats else 0
    collection_count = len(stats)

    qs1, qs2, qs3, qs4 = st.columns(4)
    with qs1:
        st.metric("📁 集合数", collection_count if stats else "—")
    with qs2:
        st.metric("📦 总分块数", f"{total_chunks:,}" if stats else "—")
    with qs3:
        st.metric("📈 追踪记录", f"{trace_count:,}" if trace_count >= 0 else "—")
    with qs4:
        # system health indicator
        health = "🟢 正常" if (stats and trace_count >= 0) else "🟡 待初始化"
        st.metric("⚡ 系统状态", health)

    st.markdown("")  # spacer

    # ── Component configuration cards ──────────────────────────
    st.markdown("### 🔧 组件配置")

    try:
        config_service = ConfigService()
        cards = config_service.get_component_cards()
    except Exception as exc:
        st.error(f"加载配置失败: {exc}")
        return

    # Render cards in a responsive grid (3 per row on wide, 2 on narrow)
    row_size = 3
    for row_start in range(0, len(cards), row_size):
        row_cards = cards[row_start : row_start + row_size]
        cols = st.columns(row_size)
        for i, card in enumerate(row_cards):
            style = _CARD_STYLE.get(card.name, {"icon": "⚙️", "color": "#888"})
            with cols[i]:
                st.markdown(
                    _component_card_html(
                        icon=style["icon"],
                        name=card.name,
                        provider=card.provider,
                        model=card.model,
                        color=style["color"],
                    ),
                    unsafe_allow_html=True,
                )
                with st.expander("详细参数", expanded=False):
                    for k, v in card.extra.items():
                        st.markdown(f"- **{k}:** `{v}`")

    st.markdown("")  # spacer

    # ── Collection statistics ──────────────────────────────────
    st.markdown("### 📁 集合统计")

    if stats:
        stat_cols = st.columns(min(len(stats), 4))
        for idx, (name, info) in enumerate(sorted(stats.items())):
            with stat_cols[idx % len(stat_cols)]:
                count = info.get("chunk_count", 0)
                # colour-coded status
                if count > 0:
                    badge = "🟢"
                else:
                    badge = "🔴"
                st.markdown(
                    f"""
                    <div style="
                        background:#f8f9fa;
                        border-radius:10px;
                        padding:1rem;
                        text-align:center;
                        border:1px solid #e9ecef;
                    ">
                        <div style="font-size:1.8rem; font-weight:800;">{count:,}</div>
                        <div style="font-size:0.85rem; color:#666; margin-top:0.2rem;">
                            {badge} {name}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info(
            "💡 **未找到集合或 ChromaDB 不可用。** "
            "请前往『摄取管理』页面上传文档来初始化知识库。"
        )

    st.markdown("")  # spacer

    # ── Trace statistics ───────────────────────────────────────
    st.markdown("### 📈 追踪统计")

    if trace_count > 0:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, #6C63FF12, #00B4D812);
                border-radius:10px;
                padding:1rem 1.5rem;
                display:flex;
                align-items:center;
                gap:1rem;
                border:1px solid #e9ecef;
            ">
                <div style="font-size:2rem;">📈</div>
                <div>
                    <div style="font-size:1.4rem; font-weight:700;">{trace_count:,} 条追踪记录</div>
                    <div style="font-size:0.82rem; color:#888;">前往『摄取追踪』或『查询追踪』页面查看详情</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif trace_count == 0:
        st.info("暂无追踪记录。执行一次查询或摄取操作后，追踪数据将自动展示在此处。")
    else:
        st.warning("无法读取追踪文件。请检查日志目录权限。")

    st.markdown("")  # spacer

    # ── Quick links / actions ──────────────────────────────────
    st.markdown("### 🚀 快速操作")
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        st.markdown(
            """
            <div style="background:#f8f9fa;border-radius:10px;padding:1.2rem;text-align:center;border:1px solid #e9ecef;">
                <div style="font-size:1.5rem;">📥</div>
                <div style="font-weight:600;margin:0.4rem 0 0.2rem;">摄取管理</div>
                <div style="font-size:0.78rem;color:#888;">上传文件，构建知识库</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with qa2:
        st.markdown(
            """
            <div style="background:#f8f9fa;border-radius:10px;padding:1.2rem;text-align:center;border:1px solid #e9ecef;">
                <div style="font-size:1.5rem;">🔍</div>
                <div style="font-weight:600;margin:0.4rem 0 0.2rem;">数据浏览</div>
                <div style="font-size:0.78rem;color:#888;">查看文档、分块、图片</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with qa3:
        st.markdown(
            """
            <div style="background:#f8f9fa;border-radius:10px;padding:1.2rem;text-align:center;border:1px solid #e9ecef;">
                <div style="font-size:1.5rem;">📏</div>
                <div style="font-weight:600;margin:0.4rem 0 0.2rem;">评估面板</div>
                <div style="font-size:0.78rem;color:#888;">运行 RAG 质量评估</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
