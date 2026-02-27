"""Tests for F5 – Pipeline on_progress callback.

Verifies that IngestionPipeline.run() fires the optional on_progress
callback at each pipeline stage with (stage_name, current, total).
"""

from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

from src.core.trace.trace_context import TraceContext
from src.core.types import Document, Chunk
from src.ingestion.pipeline import IngestionPipeline


# ── Helpers ──────────────────────────────────────────────────────────


def _make_fake_pipeline() -> object:
    """Build a fake IngestionPipeline that doesn't require real settings."""

    class FP:
        collection = "test"
        force = False

    fp = FP()

    # Stage 1: integrity
    fp.integrity_checker = MagicMock()
    fp.integrity_checker.compute_sha256.return_value = "hash123"
    fp.integrity_checker.should_skip.return_value = False

    # Stage 2: loader
    fp.loader = MagicMock()
    fp.loader.load.return_value = Document(
        id="doc1", text="Hello world. " * 50, metadata={"source_path": "test.pdf", "images": []}
    )

    # Stage 3: chunker
    chunks = [
        Chunk(id=f"c{i}", text=f"Chunk {i} text. " * 5, metadata={"source_path": "test.pdf"})
        for i in range(3)
    ]
    fp.chunker = MagicMock()
    fp.chunker.split_document.return_value = chunks

    # Stage 4: transforms
    fp.chunk_refiner = MagicMock()
    fp.chunk_refiner.transform.return_value = chunks
    fp.metadata_enricher = MagicMock()
    fp.metadata_enricher.transform.return_value = chunks
    fp.image_captioner = MagicMock()
    fp.image_captioner.transform.return_value = chunks

    # Stage 5: encoding
    batch_result = MagicMock()
    batch_result.dense_vectors = [[0.1, 0.2]] * 3
    batch_result.sparse_stats = [{"doc_id": f"c{i}"} for i in range(3)]
    fp.batch_processor = MagicMock()
    fp.batch_processor.process.return_value = batch_result

    # Stage 6: storage
    fp.vector_upserter = MagicMock()
    fp.vector_upserter.upsert.return_value = ["v0", "v1", "v2"]
    fp.bm25_indexer = MagicMock()
    fp.image_storage = MagicMock()

    return fp


def _collect_progress(fp) -> List[Tuple[str, int, int]]:
    """Run pipeline with a callback and return collected calls."""
    calls: List[Tuple[str, int, int]] = []

    def on_progress(stage: str, current: int, total: int) -> None:
        calls.append((stage, current, total))

    IngestionPipeline.run(fp, "test.pdf", on_progress=on_progress)
    return calls


# ── Tests ────────────────────────────────────────────────────────────


class TestPipelineProgressCallback:
    """Verify on_progress is called correctly."""

    def test_callback_called_for_all_stages(self) -> None:
        fp = _make_fake_pipeline()
        calls = _collect_progress(fp)
        stage_names = [c[0] for c in calls]
        assert "integrity" in stage_names
        assert "load" in stage_names
        assert "split" in stage_names
        assert "transform" in stage_names
        assert "embed" in stage_names
        assert "upsert" in stage_names

    def test_total_is_six(self) -> None:
        fp = _make_fake_pipeline()
        calls = _collect_progress(fp)
        for _, _, total in calls:
            assert total == 6

    def test_current_is_monotonically_increasing(self) -> None:
        fp = _make_fake_pipeline()
        calls = _collect_progress(fp)
        currents = [c[1] for c in calls]
        assert currents == sorted(currents)
        assert currents == list(range(1, 7))

    def test_no_callback_no_crash(self) -> None:
        """on_progress=None should not break anything."""
        fp = _make_fake_pipeline()
        result = IngestionPipeline.run(fp, "test.pdf", on_progress=None)
        assert result.success

    def test_callback_with_trace(self) -> None:
        """on_progress + trace both work together."""
        fp = _make_fake_pipeline()
        calls: List[Tuple[str, int, int]] = []
        trace = TraceContext(trace_type="ingestion")

        def on_progress(stage: str, current: int, total: int) -> None:
            calls.append((stage, current, total))

        IngestionPipeline.run(fp, "test.pdf", trace=trace, on_progress=on_progress)
        assert len(calls) == 6
        assert len(trace.stages) >= 5  # trace records from F4

    def test_ordering(self) -> None:
        fp = _make_fake_pipeline()
        calls = _collect_progress(fp)
        stage_names = [c[0] for c in calls]
        expected_order = ["integrity", "load", "split", "transform", "embed", "upsert"]
        assert stage_names == expected_order
