"""Modular RAG Dashboard – multi-page Streamlit application.

Entry-point: ``streamlit run src/observability/dashboard/app.py``

Pages are registered via ``st.navigation()`` and rendered by their
respective modules under ``pages/``.  Pages not yet implemented show
a placeholder message.
"""

from __future__ import annotations

import streamlit as st


# ── Page definitions ─────────────────────────────────────────────────

def _page_knowledge_qa() -> None:
    from src.observability.dashboard.pages.knowledge_qa import render
    render()


def _page_knowledge_base() -> None:
    from src.observability.dashboard.pages.knowledge_base import render
    render()


def _page_overview() -> None:
    from src.observability.dashboard.pages.overview import render
    render()


def _page_data_browser() -> None:
    from src.observability.dashboard.pages.data_browser import render
    render()


def _page_ingestion_manager() -> None:
    from src.observability.dashboard.pages.ingestion_manager import render
    render()


def _page_ingestion_traces() -> None:
    from src.observability.dashboard.pages.ingestion_traces import render
    render()


def _page_query_traces() -> None:
    from src.observability.dashboard.pages.query_traces import render
    render()


def _page_evaluation_panel() -> None:
    from src.observability.dashboard.pages.evaluation_panel import render
    render()


# ── Navigation ───────────────────────────────────────────────────────

pages = [
    st.Page(_page_knowledge_qa, title="知识库问答", icon="\U0001F4AC", default=True),
    st.Page(_page_knowledge_base, title="知识库构建", icon="\U0001F4C2"),
    st.Page(_page_overview, title="系统总览", icon="📊"),
    st.Page(_page_data_browser, title="数据浏览", icon="🔍"),
    st.Page(_page_ingestion_manager, title="摄取管理", icon="📥"),
    st.Page(_page_ingestion_traces, title="摄取追踪", icon="🔬"),
    st.Page(_page_query_traces, title="查询追踪", icon="🔎"),
    st.Page(_page_evaluation_panel, title="评估面板", icon="📏"),
]


def main() -> None:
    st.set_page_config(
        page_title="模块化 RAG 管理平台",
        page_icon="📊",
        layout="wide",
    )

    # 缩窄侧边栏宽度
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] { min-width: 180px !important; max-width: 200px !important; }
            [data-testid="stSidebarContent"] { padding-top: 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    nav = st.navigation(pages)
    nav.run()


if __name__ == "__main__":
    main()
else:
    # When run directly via `streamlit run app.py`
    main()
