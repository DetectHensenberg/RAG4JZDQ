"""Integration tests for F3 – query pipeline trace instrumentation.

Verifies that HybridSearch.search() and CoreReranker.rerank() populate
TraceContext with the expected stages and timing data.
"""

import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.core.types import ProcessedQuery, RetrievalResult
from src.core.trace.trace_context import TraceContext
from src.core.query_engine.hybrid_search import (
    HybridSearch,
    HybridSearchConfig,
)
from src.core.query_engine.reranker import CoreReranker, RerankConfig


# ── Fake components ──────────────────────────────────────────────────


class FakeDenseRetriever:
    provider_name = "openai"

    def retrieve(self, *, query: str, top_k: int, filters=None, trace=None) -> List[RetrievalResult]:
        return [
            RetrievalResult(chunk_id="d1", score=0.9, text="dense result 1", metadata={}),
            RetrievalResult(chunk_id="d2", score=0.8, text="dense result 2", metadata={}),
        ]


class FakeSparseRetriever:
    def retrieve(self, *, keywords: List[str], top_k: int, collection=None, trace=None) -> List[RetrievalResult]:
        return [
            RetrievalResult(chunk_id="s1", score=0.85, text="sparse result 1", metadata={}),
            RetrievalResult(chunk_id="s2", score=0.75, text="sparse result 2", metadata={}),
        ]


class FakeQueryProcessor:
    def process(self, query: str) -> ProcessedQuery:
        return ProcessedQuery(
            original_query=query,
            keywords=query.split(),
            filters={},
        )


class FakeFusion:
    def fuse(self, *, ranking_lists, top_k, trace=None) -> List[RetrievalResult]:
        # Simple dedup + merge
        seen, merged = set(), []
        for rl in ranking_lists:
            for r in rl:
                if r.chunk_id not in seen:
                    seen.add(r.chunk_id)
                    merged.append(r)
        return merged[:top_k]


class FakeBaseReranker:
    """Minimal reranker that adds rerank_score."""

    def rerank(self, *, query, candidates, trace=None, **kw):
        for i, c in enumerate(candidates):
            c["rerank_score"] = 1.0 - i * 0.1
        return candidates


# ── HybridSearch trace tests ────────────────────────────────────────


class TestHybridSearchTrace:
    """Verify HybridSearch populates TraceContext with expected stages."""

    def _build_engine(self) -> HybridSearch:
        return HybridSearch(
            query_processor=FakeQueryProcessor(),
            dense_retriever=FakeDenseRetriever(),
            sparse_retriever=FakeSparseRetriever(),
            fusion=FakeFusion(),
            config=HybridSearchConfig(
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                parallel_retrieval=False,  # deterministic ordering
            ),
        )

    def test_search_records_query_processing_stage(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "query_processing" in stage_names

    def test_search_records_dense_retrieval_stage(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "dense_retrieval" in stage_names

    def test_search_records_sparse_retrieval_stage(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "sparse_retrieval" in stage_names

    def test_search_records_fusion_stage(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "fusion" in stage_names

    def test_all_stages_have_elapsed_ms(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        for entry in trace.stages:
            assert "elapsed_ms" in entry, f"stage '{entry['stage']}' missing elapsed_ms"
            assert entry["elapsed_ms"] >= 0

    def test_all_stages_have_method_field(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        for entry in trace.stages:
            assert "method" in entry["data"], f"stage '{entry['stage']}' missing method"

    def test_trace_type_is_query(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        assert trace.trace_type == "query"

    def test_to_dict_serialises_all_stages(self) -> None:
        engine = self._build_engine()
        trace = TraceContext(trace_type="query")
        engine.search("hello world", trace=trace)
        trace.finish()
        d = trace.to_dict()
        assert d["trace_type"] == "query"
        assert len(d["stages"]) >= 4  # qp, dense, sparse, fusion

    def test_no_trace_no_crash(self) -> None:
        """search() with trace=None must not raise."""
        engine = self._build_engine()
        results = engine.search("hello world", trace=None)
        assert isinstance(results, list)


# ── CoreReranker trace tests ────────────────────────────────────────


class TestCoreRerankerTrace:
    """Verify CoreReranker.rerank() populates trace with rerank stage."""

    def _build_reranker(self) -> CoreReranker:
        settings = MagicMock()
        settings.rerank = None
        return CoreReranker(
            settings=settings,
            reranker=FakeBaseReranker(),
            config=RerankConfig(enabled=True, top_k=5),
        )

    def _sample_results(self) -> List[RetrievalResult]:
        return [
            RetrievalResult(chunk_id=f"c{i}", score=0.9 - i * 0.1, text=f"text {i}", metadata={})
            for i in range(4)
        ]

    def test_rerank_records_stage(self) -> None:
        reranker = self._build_reranker()
        trace = TraceContext(trace_type="query")
        reranker.rerank("query", self._sample_results(), trace=trace)
        stage_names = [s["stage"] for s in trace.stages]
        assert "rerank" in stage_names

    def test_rerank_stage_has_elapsed_ms(self) -> None:
        reranker = self._build_reranker()
        trace = TraceContext(trace_type="query")
        reranker.rerank("query", self._sample_results(), trace=trace)
        rerank_entry = next(s for s in trace.stages if s["stage"] == "rerank")
        assert "elapsed_ms" in rerank_entry
        assert rerank_entry["elapsed_ms"] >= 0

    def test_rerank_stage_has_method(self) -> None:
        reranker = self._build_reranker()
        trace = TraceContext(trace_type="query")
        reranker.rerank("query", self._sample_results(), trace=trace)
        rerank_entry = next(s for s in trace.stages if s["stage"] == "rerank")
        assert "method" in rerank_entry["data"]

    def test_no_trace_no_crash(self) -> None:
        reranker = self._build_reranker()
        result = reranker.rerank("query", self._sample_results(), trace=None)
        assert len(result.results) > 0

    def test_full_pipeline_trace(self) -> None:
        """Combined: HybridSearch + Reranker should produce 5 stages."""
        engine = HybridSearch(
            query_processor=FakeQueryProcessor(),
            dense_retriever=FakeDenseRetriever(),
            sparse_retriever=FakeSparseRetriever(),
            fusion=FakeFusion(),
            config=HybridSearchConfig(parallel_retrieval=False),
        )
        settings = MagicMock()
        settings.rerank = None
        reranker = CoreReranker(
            settings=settings,
            reranker=FakeBaseReranker(),
            config=RerankConfig(enabled=True, top_k=5),
        )
        trace = TraceContext(trace_type="query")
        search_results = engine.search("hello world", trace=trace)
        reranker.rerank("hello world", search_results, trace=trace)
        trace.finish()
        stage_names = [s["stage"] for s in trace.stages]
        expected = {"query_processing", "dense_retrieval", "sparse_retrieval", "fusion", "rerank"}
        assert expected.issubset(set(stage_names))
        assert trace.to_dict()["trace_type"] == "query"
        assert trace.to_dict()["total_elapsed_ms"] > 0
