"""E2E smoke tests for the Streamlit Dashboard pages.

Uses Streamlit's ``AppTest`` framework to render each page's ``render()``
function in headless mode and verify that:

1. No Python exception is raised during render.
2. Each page produces at least one expected UI element (header / info / metric).

These tests do **not** require live data – they should pass on a fresh
checkout where the vector store is empty.

Usage::

    pytest tests/e2e/test_dashboard_smoke.py -v
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _mock_settings() -> MagicMock:
    """Return a minimal mock Settings that satisfies all dashboard pages."""
    s = MagicMock()
    s.llm.provider = "azure"
    s.llm.model = "gpt-4o"
    s.llm.temperature = 0.0
    s.llm.max_tokens = 4096

    s.embedding.provider = "azure"
    s.embedding.model = "text-embedding-ada-002"
    s.embedding.dimensions = 1536

    s.vector_store.provider = "chroma"
    s.vector_store.collection_name = "default"
    s.vector_store.persist_directory = "./data/db/chroma"

    s.retrieval.dense_top_k = 20
    s.retrieval.sparse_top_k = 20
    s.retrieval.fusion_top_k = 10

    s.rerank.enabled = False
    s.rerank.provider = "none"
    s.rerank.model = ""
    s.rerank.top_k = 5

    s.vision_llm.enabled = False
    s.vision_llm.provider = "azure"
    s.vision_llm.model = "gpt-4o"
    s.vision_llm.max_image_size = 2048

    s.observability.log_level = "INFO"
    s.observability.trace_enabled = True
    s.observability.trace_file = "./logs/traces.jsonl"
    s.observability.structured_logging = True

    s.ingestion.chunk_size = 1000
    s.ingestion.chunk_overlap = 200
    s.ingestion.splitter = "recursive"
    s.ingestion.batch_size = 100
    return s


def _collect_text(at: Any) -> str:
    """Collect all rendered text from an AppTest run for assertion."""
    parts: List[str] = []
    for attr in ("markdown", "header", "subheader", "info", "error", "title", "text", "success", "warning"):
        for el in getattr(at, attr, []):
            parts.append(str(getattr(el, "value", "")))
    return "\n".join(parts)


# ── Tests ─────────────────────────────────────────────────────────────


class TestDashboardSmoke:
    """Smoke tests: each page renders without uncaught exceptions."""

    # ------------------------------------------------------------------
    # 1. Overview page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_overview_page_renders(self) -> None:
        """Overview page loads and shows system overview header."""
        from streamlit.testing.v1 import AppTest

        def page_script():
            from src.observability.dashboard.pages.overview import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)

        with patch(
            "src.observability.dashboard.services.config_service.load_settings",
            return_value=_mock_settings(),
        ):
            at.run()

        assert not at.exception, (
            f"Overview page raised an exception: {at.exception}"
        )
        text = _collect_text(at)
        assert "overview" in text.lower() or "system" in text.lower()

    # ------------------------------------------------------------------
    # 2. Data Browser page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_data_browser_page_renders(self) -> None:
        """Data Browser page loads (may show 'no documents' info)."""
        from streamlit.testing.v1 import AppTest

        mock_svc = MagicMock()
        mock_svc.list_documents.return_value = []

        def page_script():
            from src.observability.dashboard.pages.data_browser import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)

        with patch(
            "src.observability.dashboard.pages.data_browser.DataService",
            return_value=mock_svc,
        ):
            at.run()

        assert not at.exception, (
            f"Data Browser page raised an exception: {at.exception}"
        )
        text = _collect_text(at)
        assert "data" in text.lower() or "browser" in text.lower() or "document" in text.lower()

    # ------------------------------------------------------------------
    # 3. Ingestion Manager page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_ingestion_manager_page_renders(self) -> None:
        """Ingestion Manager page loads without errors."""
        from streamlit.testing.v1 import AppTest

        mock_svc = MagicMock()
        mock_svc.list_documents.return_value = []

        def page_script():
            from src.observability.dashboard.pages.ingestion_manager import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)

        with patch(
            "src.observability.dashboard.pages.ingestion_manager.DataService",
            return_value=mock_svc,
        ):
            at.run()

        assert not at.exception, (
            f"Ingestion Manager page raised an exception: {at.exception}"
        )

    # ------------------------------------------------------------------
    # 4. Ingestion Traces page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_ingestion_traces_page_renders(self) -> None:
        """Ingestion Traces page loads (empty trace list is OK)."""
        from streamlit.testing.v1 import AppTest

        mock_svc = MagicMock()
        mock_svc.list_traces.return_value = []

        def page_script():
            from src.observability.dashboard.pages.ingestion_traces import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)

        with patch(
            "src.observability.dashboard.pages.ingestion_traces.TraceService",
            return_value=mock_svc,
        ):
            at.run()

        assert not at.exception, (
            f"Ingestion Traces page raised an exception: {at.exception}"
        )
        text = _collect_text(at)
        assert "trace" in text.lower() or "ingestion" in text.lower()

    # ------------------------------------------------------------------
    # 5. Query Traces page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_query_traces_page_renders(self) -> None:
        """Query Traces page loads (empty trace list is OK)."""
        from streamlit.testing.v1 import AppTest

        mock_svc = MagicMock()
        mock_svc.list_traces.return_value = []

        def page_script():
            from src.observability.dashboard.pages.query_traces import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)

        with patch(
            "src.observability.dashboard.pages.query_traces.TraceService",
            return_value=mock_svc,
        ):
            at.run()

        assert not at.exception, (
            f"Query Traces page raised an exception: {at.exception}"
        )
        text = _collect_text(at)
        assert "query" in text.lower() or "trace" in text.lower()

    # ------------------------------------------------------------------
    # 6. Evaluation Panel page
    # ------------------------------------------------------------------

    @pytest.mark.e2e
    def test_evaluation_panel_page_renders(self) -> None:
        """Evaluation Panel page loads without errors."""
        from streamlit.testing.v1 import AppTest

        def page_script():
            from src.observability.dashboard.pages.evaluation_panel import render
            render()

        at = AppTest.from_function(page_script, default_timeout=10)
        at.run()

        assert not at.exception, (
            f"Evaluation Panel page raised an exception: {at.exception}"
        )
        text = _collect_text(at)
        assert "evaluation" in text.lower() or "panel" in text.lower()
