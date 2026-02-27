"""Unit tests for the Evaluation Panel dashboard page."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


class TestEvaluationPanelHelpers:
    """Test helper functions in evaluation_panel module."""

    def test_save_and_load_history(self, tmp_path: Path) -> None:
        """History round-trip: save then load."""
        from src.observability.dashboard.pages import evaluation_panel as ep

        # Temporarily override history path
        original = ep.EVAL_HISTORY_PATH
        ep.EVAL_HISTORY_PATH = tmp_path / "eval_history.jsonl"

        try:
            report = {
                "evaluator_name": "custom",
                "query_count": 2,
                "total_elapsed_ms": 123.4,
                "aggregate_metrics": {"hit_rate": 0.8},
            }

            ep._save_to_history(report)
            history = ep._load_history()

            assert len(history) == 1
            assert history[0]["evaluator_name"] == "custom"
            assert history[0]["aggregate_metrics"]["hit_rate"] == 0.8
            assert "timestamp" in history[0]
        finally:
            ep.EVAL_HISTORY_PATH = original

    def test_load_history_empty(self, tmp_path: Path) -> None:
        """Load returns empty list when no history file exists."""
        from src.observability.dashboard.pages import evaluation_panel as ep

        original = ep.EVAL_HISTORY_PATH
        ep.EVAL_HISTORY_PATH = tmp_path / "nonexistent.jsonl"

        try:
            assert ep._load_history() == []
        finally:
            ep.EVAL_HISTORY_PATH = original

    def test_load_history_tolerates_bad_lines(self, tmp_path: Path) -> None:
        """Malformed lines are skipped."""
        from src.observability.dashboard.pages import evaluation_panel as ep

        original = ep.EVAL_HISTORY_PATH
        hist_file = tmp_path / "eval_history.jsonl"
        hist_file.write_text(
            '{"ok": true}\nBAD LINE\n{"ok": false}\n',
            encoding="utf-8",
        )
        ep.EVAL_HISTORY_PATH = hist_file

        try:
            history = ep._load_history()
            assert len(history) == 2
            assert history[0]["ok"] is True
            assert history[1]["ok"] is False
        finally:
            ep.EVAL_HISTORY_PATH = original

    def test_save_history_creates_parent_dir(self, tmp_path: Path) -> None:
        """_save_to_history creates missing parent directories."""
        from src.observability.dashboard.pages import evaluation_panel as ep

        original = ep.EVAL_HISTORY_PATH
        ep.EVAL_HISTORY_PATH = tmp_path / "subdir" / "eval.jsonl"

        try:
            ep._save_to_history({"test": True})
            assert ep.EVAL_HISTORY_PATH.exists()
        finally:
            ep.EVAL_HISTORY_PATH = original


class TestEvaluationPanelImport:
    """Verify the module can be imported without side effects."""

    def test_module_imports(self) -> None:
        from src.observability.dashboard.pages import evaluation_panel

        assert hasattr(evaluation_panel, "render")
        assert callable(evaluation_panel.render)

    def test_default_golden_path(self) -> None:
        from src.observability.dashboard.pages.evaluation_panel import (
            DEFAULT_GOLDEN_SET,
        )

        assert DEFAULT_GOLDEN_SET == Path("tests/fixtures/golden_test_set.json")
