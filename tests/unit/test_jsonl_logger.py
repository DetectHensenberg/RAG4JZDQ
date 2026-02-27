"""Tests for structured JSON Lines logger (F2).

Covers:
- JSONFormatter output structure
- get_trace_logger file handler setup
- write_trace convenience function
"""

import json
import logging
from pathlib import Path

import pytest

from src.observability.logger import JSONFormatter, get_trace_logger, write_trace


# ── JSONFormatter ────────────────────────────────────────────────────


class TestJSONFormatter:
    """Verify JSONFormatter produces valid JSON with required fields."""

    def _make_record(
        self, msg: str = "hello", level: int = logging.INFO, **extra: object
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self) -> None:
        fmt = JSONFormatter()
        record = self._make_record("test message")
        line = fmt.format(record)
        obj = json.loads(line)
        assert isinstance(obj, dict)

    def test_required_keys(self) -> None:
        fmt = JSONFormatter()
        obj = json.loads(fmt.format(self._make_record()))
        for key in ("timestamp", "level", "logger", "message"):
            assert key in obj, f"missing key: {key}"

    def test_message_value(self) -> None:
        fmt = JSONFormatter()
        obj = json.loads(fmt.format(self._make_record("hello world")))
        assert obj["message"] == "hello world"

    def test_level_value(self) -> None:
        fmt = JSONFormatter()
        obj = json.loads(fmt.format(self._make_record(level=logging.WARNING)))
        assert obj["level"] == "WARNING"

    def test_extra_fields_merged(self) -> None:
        fmt = JSONFormatter()
        record = self._make_record(trace_type="query", score=0.95)
        obj = json.loads(fmt.format(record))
        assert obj["trace_type"] == "query"
        assert obj["score"] == 0.95

    def test_non_serialisable_extra_converted(self) -> None:
        fmt = JSONFormatter()
        record = self._make_record(custom_obj=object())
        line = fmt.format(record)
        obj = json.loads(line)
        assert "custom_obj" in obj  # converted to str

    def test_single_line_output(self) -> None:
        fmt = JSONFormatter()
        line = fmt.format(self._make_record("no\nnewlines\nplease"))
        # json.dumps by default escapes newlines as \\n
        assert "\n" not in line


# ── get_trace_logger ────────────────────────────────────────────────


class TestGetTraceLogger:
    """Verify get_trace_logger sets up JSON Lines file handler."""

    def test_returns_logger(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        lgr = get_trace_logger(p, name="test.trace.1")
        assert isinstance(lgr, logging.Logger)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "deep" / "traces.jsonl"
        get_trace_logger(p, name="test.trace.2")
        assert p.parent.exists()

    def test_writes_json_line(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        lgr = get_trace_logger(p, name="test.trace.3")
        lgr.info("test event", extra={"trace_type": "query"})
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["message"] == "test event"
        assert obj["trace_type"] == "query"

    def test_no_duplicate_handlers_on_repeated_call(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        lgr1 = get_trace_logger(p, name="test.trace.4")
        lgr2 = get_trace_logger(p, name="test.trace.4")
        assert lgr1 is lgr2
        assert len(lgr2.handlers) == 1


# ── write_trace ─────────────────────────────────────────────────────


class TestWriteTrace:
    """Verify write_trace convenience function."""

    def test_creates_file(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        write_trace({"trace_type": "ingestion", "stages": []}, p)
        assert p.exists()

    def test_appends_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        write_trace({"trace_type": "query", "id": 1}, p)
        write_trace({"trace_type": "ingestion", "id": 2}, p)
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
        assert json.loads(lines[1])["id"] == 2

    def test_trace_type_field_preserved(self, tmp_path: Path) -> None:
        p = tmp_path / "traces.jsonl"
        write_trace({"trace_type": "ingestion", "stages": [{"stage": "load"}]}, p)
        obj = json.loads(p.read_text().strip())
        assert obj["trace_type"] == "ingestion"
        assert len(obj["stages"]) == 1

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "a" / "b" / "traces.jsonl"
        write_trace({"ok": True}, p)
        assert p.exists()

    def test_round_trip_with_trace_context(self, tmp_path: Path) -> None:
        """write_trace + TraceContext.to_dict() round-trip."""
        from src.core.trace.trace_context import TraceContext

        tc = TraceContext(trace_type="query")
        tc.record_stage("dense", {"provider": "openai"}, elapsed_ms=12.0)
        tc.finish()
        p = tmp_path / "traces.jsonl"
        write_trace(tc.to_dict(), p)
        obj = json.loads(p.read_text().strip())
        assert obj["trace_type"] == "query"
        assert obj["stages"][0]["stage"] == "dense"
