"""Integration tests for F4 – ingestion pipeline trace instrumentation.

Verifies that IngestionPipeline.run() populates TraceContext with the
expected stages (load/split/transform/embed/upsert) and timing data.

We monkey-patch the heavy external components so the test runs without
real Azure / ChromaDB / LLM dependencies.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.core.trace.trace_context import TraceContext
from src.core.types import Document, Chunk


# ── Fake heavy components ────────────────────────────────────────────

def _fake_document(path: str = "test.pdf") -> Document:
    return Document(
        id="doc_hash_abc123",
        text="Hello world. " * 50,
        metadata={"source_path": path, "images": []},
    )


def _fake_chunks(n: int = 3) -> List[Chunk]:
    return [
        Chunk(
            id=f"chunk_{i}",
            text=f"Chunk text {i}. " * 10,
            metadata={"source_doc_id": "doc_hash_abc123", "source_path": "test.pdf"},
        )
        for i in range(n)
    ]


@dataclass
class FakeBatchResult:
    dense_vectors: List[List[float]] = field(default_factory=lambda: [[0.1, 0.2]] * 3)
    sparse_stats: List[Dict[str, Any]] = field(default_factory=lambda: [{"doc_id": f"chunk_{i}"} for i in range(3)])


class FakePipeline:
    """Mimics IngestionPipeline but with all heavy components replaced."""

    def __init__(self):
        self.collection = "test_collection"
        self.force = False

        # Mock each component
        self.integrity_checker = MagicMock()
        self.integrity_checker.compute_sha256.return_value = "abc123"
        self.integrity_checker.should_skip.return_value = False

        self.loader = MagicMock()
        self.loader.load.return_value = _fake_document()

        self.chunker = MagicMock()
        chunks = _fake_chunks()
        self.chunker.split_document.return_value = chunks

        self.chunk_refiner = MagicMock()
        self.chunk_refiner.transform.return_value = chunks

        self.metadata_enricher = MagicMock()
        self.metadata_enricher.transform.return_value = chunks

        self.image_captioner = MagicMock()
        self.image_captioner.transform.return_value = chunks

        self.batch_processor = MagicMock()
        self.batch_processor.process.return_value = FakeBatchResult()

        self.vector_upserter = MagicMock()
        self.vector_upserter.upsert.return_value = ["vid_0", "vid_1", "vid_2"]

        self.bm25_indexer = MagicMock()
        self.image_storage = MagicMock()


def _run_fake_pipeline(trace: Optional[TraceContext] = None):
    """Import the real run() logic but wire it to FakePipeline."""
    from src.ingestion.pipeline import IngestionPipeline

    fp = FakePipeline()
    # Borrow the real `run` method but bind it to our fake instance
    return IngestionPipeline.run(fp, "test.pdf", trace=trace)


# ── Tests ────────────────────────────────────────────────────────────


class TestIngestionPipelineTrace:
    """Verify IngestionPipeline.run() records the 5 required stages."""

    def test_records_load_stage(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "load" in stage_names

    def test_records_split_stage(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "split" in stage_names

    def test_records_transform_stage(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "transform" in stage_names

    def test_records_embed_stage(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "embed" in stage_names

    def test_records_upsert_stage(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "upsert" in stage_names

    def test_all_stages_have_elapsed_ms(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        for entry in trace.stages:
            assert "elapsed_ms" in entry, f"stage '{entry['stage']}' missing elapsed_ms"
            assert entry["elapsed_ms"] >= 0

    def test_all_stages_have_method_field(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        for entry in trace.stages:
            assert "method" in entry["data"], f"stage '{entry['stage']}' missing method"

    def test_trace_type_is_ingestion(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        assert trace.trace_type == "ingestion"

    def test_to_dict_contains_all_stages(self) -> None:
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        trace.finish()
        d = trace.to_dict()
        assert d["trace_type"] == "ingestion"
        assert len(d["stages"]) >= 5  # load, split, transform, embed, upsert

    def test_no_trace_no_crash(self) -> None:
        """run() with trace=None must not raise."""
        result = _run_fake_pipeline(trace=None)
        assert result.success

    def test_stage_ordering(self) -> None:
        """Stages should appear in pipeline order."""
        trace = TraceContext(trace_type="ingestion")
        _run_fake_pipeline(trace)
        stage_names = [s["stage"] for s in trace.stages]
        expected_order = ["load", "split", "transform", "embed", "upsert"]
        # All expected stages present and in order
        positions = [stage_names.index(s) for s in expected_order]
        assert positions == sorted(positions)
