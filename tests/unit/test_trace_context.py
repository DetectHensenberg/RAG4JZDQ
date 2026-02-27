"""Tests for TraceContext (enhanced) and TraceCollector."""

import json
import time

import pytest

from src.core.trace.trace_context import TraceContext
from src.core.trace.trace_collector import TraceCollector


# ── TraceContext basics ──────────────────────────────────────────────

class TestTraceContextInit:
    """Verify constructor defaults and trace_type."""

    def test_default_trace_type_is_query(self) -> None:
        tc = TraceContext()
        assert tc.trace_type == "query"

    def test_ingestion_trace_type(self) -> None:
        tc = TraceContext(trace_type="ingestion")
        assert tc.trace_type == "ingestion"

    def test_trace_id_is_uuid(self) -> None:
        tc = TraceContext()
        assert len(tc.trace_id) == 36  # UUID-4 length with dashes

    def test_started_at_is_iso_string(self) -> None:
        tc = TraceContext()
        assert isinstance(tc.started_at, str)
        assert "T" in tc.started_at  # ISO format

    def test_finished_at_initially_none(self) -> None:
        tc = TraceContext()
        assert tc.finished_at is None

    def test_stages_initially_empty(self) -> None:
        tc = TraceContext()
        assert tc.stages == []


# ── record_stage ────────────────────────────────────────────────────

class TestRecordStage:
    """Verify stage recording and backward compatibility."""

    def test_record_stage_appends(self) -> None:
        tc = TraceContext()
        tc.record_stage("load", {"method": "markitdown"})
        tc.record_stage("split", {"method": "recursive"})
        assert len(tc.stages) == 2

    def test_stage_entry_has_required_keys(self) -> None:
        tc = TraceContext()
        tc.record_stage("embed", {"provider": "openai"})
        entry = tc.stages[0]
        assert entry["stage"] == "embed"
        assert "timestamp" in entry
        assert entry["data"] == {"provider": "openai"}

    def test_record_stage_with_elapsed(self) -> None:
        tc = TraceContext()
        tc.record_stage("rerank", {"backend": "cross_encoder"}, elapsed_ms=42.5)
        entry = tc.stages[0]
        assert entry["elapsed_ms"] == 42.5

    def test_record_stage_without_elapsed(self) -> None:
        tc = TraceContext()
        tc.record_stage("fusion", {"algorithm": "rrf"})
        entry = tc.stages[0]
        assert "elapsed_ms" not in entry

    def test_duplicate_stage_names_appended(self) -> None:
        tc = TraceContext()
        tc.record_stage("transform", {"step": "refine"})
        tc.record_stage("transform", {"step": "enrich"})
        assert len(tc.stages) == 2


# ── get_stage_data (backward-compat) ────────────────────────────────

class TestGetStageData:
    """Backward-compatible helper returns last-written data."""

    def test_returns_data_for_known_stage(self) -> None:
        tc = TraceContext()
        tc.record_stage("load", {"file": "test.pdf"})
        assert tc.get_stage_data("load") == {"file": "test.pdf"}

    def test_returns_none_for_unknown_stage(self) -> None:
        tc = TraceContext()
        assert tc.get_stage_data("nonexistent") is None

    def test_returns_last_data_for_duplicate_stage(self) -> None:
        tc = TraceContext()
        tc.record_stage("x", {"v": 1})
        tc.record_stage("x", {"v": 2})
        assert tc.get_stage_data("x") == {"v": 2}


# ── finish ──────────────────────────────────────────────────────────

class TestFinish:
    """Lifecycle: finish() sets finished_at and freezes elapsed."""

    def test_finish_sets_finished_at(self) -> None:
        tc = TraceContext()
        assert tc.finished_at is None
        tc.finish()
        assert tc.finished_at is not None
        assert "T" in tc.finished_at

    def test_elapsed_after_finish_is_frozen(self) -> None:
        tc = TraceContext()
        time.sleep(0.01)
        tc.finish()
        e1 = tc.elapsed_ms()
        time.sleep(0.01)
        e2 = tc.elapsed_ms()
        assert e1 == e2  # frozen after finish


# ── elapsed_ms ──────────────────────────────────────────────────────

class TestElapsedMs:
    """Timing helpers."""

    def test_total_elapsed_positive(self) -> None:
        tc = TraceContext()
        time.sleep(0.005)
        assert tc.elapsed_ms() > 0

    def test_stage_elapsed(self) -> None:
        tc = TraceContext()
        tc.record_stage("a", {}, elapsed_ms=12.3)
        assert tc.elapsed_ms("a") == 12.3

    def test_stage_elapsed_unknown_raises(self) -> None:
        tc = TraceContext()
        with pytest.raises(KeyError, match="no_such"):
            tc.elapsed_ms("no_such")


# ── to_dict & JSON serialisation ────────────────────────────────────

class TestToDict:
    """to_dict() produces a JSON-serialisable dict."""

    def test_contains_required_keys(self) -> None:
        tc = TraceContext(trace_type="ingestion")
        tc.record_stage("load", {"method": "markitdown"}, elapsed_ms=100)
        tc.finish()
        d = tc.to_dict()
        for key in ("trace_id", "trace_type", "started_at",
                     "finished_at", "total_elapsed_ms", "stages", "metadata"):
            assert key in d, f"missing key: {key}"

    def test_trace_type_in_output(self) -> None:
        tc = TraceContext(trace_type="query")
        tc.finish()
        assert tc.to_dict()["trace_type"] == "query"

    def test_json_serialisable(self) -> None:
        tc = TraceContext(trace_type="ingestion")
        tc.record_stage("embed", {"provider": "openai"}, elapsed_ms=55.5)
        tc.finish()
        text = json.dumps(tc.to_dict())
        assert isinstance(text, str)
        parsed = json.loads(text)
        assert parsed["trace_type"] == "ingestion"

    def test_total_elapsed_ms_is_number(self) -> None:
        tc = TraceContext()
        tc.finish()
        assert isinstance(tc.to_dict()["total_elapsed_ms"], float)


# ── TraceCollector ──────────────────────────────────────────────────

class TestTraceCollector:
    """TraceCollector persists traces to JSON Lines file."""

    def test_collect_creates_file(self, tmp_path) -> None:
        p = tmp_path / "traces.jsonl"
        collector = TraceCollector(traces_path=p)
        tc = TraceContext()
        tc.finish()
        collector.collect(tc)
        assert p.exists()

    def test_collect_appends_json_line(self, tmp_path) -> None:
        p = tmp_path / "traces.jsonl"
        collector = TraceCollector(traces_path=p)
        for i in range(3):
            tc = TraceContext(trace_type="query")
            tc.record_stage(f"stage_{i}", {"i": i})
            tc.finish()
            collector.collect(tc)
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert obj["trace_type"] == "query"

    def test_collect_auto_finishes(self, tmp_path) -> None:
        """If finish() was not called, collect() calls it automatically."""
        p = tmp_path / "traces.jsonl"
        collector = TraceCollector(traces_path=p)
        tc = TraceContext()
        assert tc.finished_at is None
        collector.collect(tc)
        assert tc.finished_at is not None
        obj = json.loads(p.read_text().strip())
        assert obj["finished_at"] is not None

    def test_collect_contains_all_stages(self, tmp_path) -> None:
        p = tmp_path / "traces.jsonl"
        collector = TraceCollector(traces_path=p)
        tc = TraceContext(trace_type="ingestion")
        tc.record_stage("load", {"method": "markitdown"}, elapsed_ms=10)
        tc.record_stage("split", {"method": "recursive"}, elapsed_ms=5)
        tc.finish()
        collector.collect(tc)
        obj = json.loads(p.read_text().strip())
        assert len(obj["stages"]) == 2

    def test_path_property(self, tmp_path) -> None:
        p = tmp_path / "sub" / "traces.jsonl"
        collector = TraceCollector(traces_path=p)
        assert collector.path == p
        assert p.parent.exists()
