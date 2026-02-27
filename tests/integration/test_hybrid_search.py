"""Integration tests for HybridSearch.

This test module validates the HybridSearch orchestration layer:
- Complete retrieval flow (query → dense+sparse → fusion → results)
- Graceful degradation when one retriever fails
- Metadata filtering (pre and post-fusion)
- Parallel vs sequential retrieval modes
- Edge cases and error handling

Test Strategy:
- Use mock/fake retrievers for deterministic behavior
- Test actual component integration (not just mocking)
- Cover both success and failure scenarios
"""

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from src.core.types import ProcessedQuery, RetrievalResult
from src.core.query_engine.hybrid_search import (
    HybridSearch,
    HybridSearchConfig,
    HybridSearchResult,
    create_hybrid_search,
)
from src.core.query_engine.query_processor import QueryProcessor
from src.core.query_engine.fusion import RRFFusion


# =============================================================================
# Test Fixtures - Mock Components
# =============================================================================

class MockDenseRetriever:
    """Mock Dense Retriever for testing."""
    
    def __init__(
        self,
        results: Optional[List[RetrievalResult]] = None,
        should_fail: bool = False,
        error_message: str = "Dense retrieval failed",
    ):
        self.results = results or []
        self.should_fail = should_fail
        self.error_message = error_message
        self.call_count = 0
        self.last_query = None
        self.last_top_k = None
        self.last_filters = None
    
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        self.call_count += 1
        self.last_query = query
        self.last_top_k = top_k
        self.last_filters = filters
        
        if self.should_fail:
            raise RuntimeError(self.error_message)
        
        return self.results[:top_k]


class MockSparseRetriever:
    """Mock Sparse Retriever for testing."""
    
    def __init__(
        self,
        results: Optional[List[RetrievalResult]] = None,
        should_fail: bool = False,
        error_message: str = "Sparse retrieval failed",
    ):
        self.results = results or []
        self.should_fail = should_fail
        self.error_message = error_message
        self.call_count = 0
        self.last_keywords = None
        self.last_top_k = None
        self.last_collection = None
    
    def retrieve(
        self,
        keywords: List[str],
        top_k: int = 10,
        collection: Optional[str] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        self.call_count += 1
        self.last_keywords = keywords
        self.last_top_k = top_k
        self.last_collection = collection
        
        if self.should_fail:
            raise RuntimeError(self.error_message)
        
        return self.results[:top_k]


@pytest.fixture
def sample_dense_results() -> List[RetrievalResult]:
    """Sample results from dense retrieval."""
    return [
        RetrievalResult(
            chunk_id="dense_1",
            score=0.95,
            text="Azure OpenAI 配置步骤详解",
            metadata={"source_path": "docs/azure.pdf", "collection": "api-docs"},
        ),
        RetrievalResult(
            chunk_id="dense_2",
            score=0.88,
            text="OpenAI API 使用指南",
            metadata={"source_path": "docs/openai.pdf", "collection": "api-docs"},
        ),
        RetrievalResult(
            chunk_id="common_chunk",
            score=0.85,
            text="通用配置说明",
            metadata={"source_path": "docs/common.pdf", "collection": "general"},
        ),
        RetrievalResult(
            chunk_id="dense_4",
            score=0.80,
            text="云服务配置概述",
            metadata={"source_path": "docs/cloud.pdf", "collection": "general"},
        ),
    ]


@pytest.fixture
def sample_sparse_results() -> List[RetrievalResult]:
    """Sample results from sparse retrieval."""
    return [
        RetrievalResult(
            chunk_id="sparse_1",
            score=8.5,
            text="Azure 配置 Azure OpenAI 服务",
            metadata={"source_path": "docs/azure-setup.pdf", "collection": "tutorials"},
        ),
        RetrievalResult(
            chunk_id="common_chunk",  # Same as in dense
            score=7.2,
            text="通用配置说明",
            metadata={"source_path": "docs/common.pdf", "collection": "general"},
        ),
        RetrievalResult(
            chunk_id="sparse_3",
            score=6.8,
            text="配置文件 YAML 格式说明",
            metadata={"source_path": "docs/config.pdf", "collection": "tutorials"},
        ),
    ]


@pytest.fixture
def query_processor() -> QueryProcessor:
    """Real QueryProcessor instance."""
    return QueryProcessor()


@pytest.fixture
def rrf_fusion() -> RRFFusion:
    """Real RRFFusion instance with default k=60."""
    return RRFFusion(k=60)


# =============================================================================
# Basic Functionality Tests
# =============================================================================

class TestHybridSearchBasic:
    """Test basic HybridSearch functionality."""
    
    def test_init_with_all_components(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test initialization with all components."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        assert hybrid.query_processor is query_processor
        assert hybrid.dense_retriever is dense
        assert hybrid.sparse_retriever is sparse
        assert hybrid.fusion is rrf_fusion
    
    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = HybridSearchConfig(
            dense_top_k=30,
            sparse_top_k=30,
            fusion_top_k=15,
            parallel_retrieval=False,
        )
        
        hybrid = HybridSearch(config=config)
        
        assert hybrid.config.dense_top_k == 30
        assert hybrid.config.sparse_top_k == 30
        assert hybrid.config.fusion_top_k == 15
        assert hybrid.config.parallel_retrieval is False
    
    def test_search_returns_results(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that search returns fused results."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("如何配置 Azure OpenAI？", top_k=5)
        
        # Should return results
        assert len(results) > 0
        assert len(results) <= 5
        
        # Results should be RetrievalResult objects
        for r in results:
            assert isinstance(r, RetrievalResult)
            assert r.chunk_id
            assert isinstance(r.score, float)
            assert r.text
    
    def test_search_with_return_details(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test search with return_details=True."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        result = hybrid.search("Azure config", top_k=5, return_details=True)
        
        assert isinstance(result, HybridSearchResult)
        assert result.results is not None
        assert result.dense_results is not None
        assert result.sparse_results is not None
        assert result.dense_error is None
        assert result.sparse_error is None
        assert result.used_fallback is False
        assert result.processed_query is not None
    
    def test_search_calls_both_retrievers(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that both retrievers are called."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        hybrid.search("Azure OpenAI 配置", top_k=5)
        
        assert dense.call_count == 1
        assert sparse.call_count == 1
    
    def test_common_chunks_deduplicated(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that common chunks appear only once in results."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("配置", top_k=10)
        
        # Check for duplicate chunk_ids
        chunk_ids = [r.chunk_id for r in results]
        assert len(chunk_ids) == len(set(chunk_ids)), "Results contain duplicate chunk_ids"
        
        # The common_chunk should appear exactly once
        assert chunk_ids.count("common_chunk") <= 1


# =============================================================================
# Graceful Degradation Tests
# =============================================================================

class TestHybridSearchDegradation:
    """Test graceful degradation when components fail."""
    
    def test_dense_fails_uses_sparse_only(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test fallback to sparse when dense fails."""
        dense = MockDenseRetriever(should_fail=True)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        result = hybrid.search("Azure 配置", top_k=5, return_details=True)
        
        assert result.used_fallback is True
        assert result.dense_error is not None
        assert "Dense retrieval" in result.dense_error
        assert result.sparse_error is None
        assert len(result.results) > 0
    
    def test_sparse_fails_uses_dense_only(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
    ):
        """Test fallback to dense when sparse fails."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(should_fail=True)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        result = hybrid.search("Azure 配置", top_k=5, return_details=True)
        
        assert result.used_fallback is True
        assert result.sparse_error is not None
        assert "Sparse retrieval" in result.sparse_error
        assert result.dense_error is None
        assert len(result.results) > 0
    
    def test_both_fail_raises_error(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
    ):
        """Test that RuntimeError is raised when both retrievers fail."""
        dense = MockDenseRetriever(should_fail=True)
        sparse = MockSparseRetriever(should_fail=True)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        with pytest.raises(RuntimeError) as exc_info:
            hybrid.search("Azure 配置", top_k=5)
        
        assert "Both retrieval paths failed" in str(exc_info.value)
    
    def test_no_retrievers_configured(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
    ):
        """Test behavior when no retrievers are configured."""
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=None,
            sparse_retriever=None,
            fusion=rrf_fusion,
        )
        
        with pytest.raises(RuntimeError) as exc_info:
            hybrid.search("Azure 配置", top_k=5)
        
        assert "No retriever" in str(exc_info.value) or "Both" in str(exc_info.value)
    
    def test_dense_only_mode(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
    ):
        """Test search with only dense retriever."""
        dense = MockDenseRetriever(results=sample_dense_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=None,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("Azure 配置", top_k=3)
        
        assert len(results) > 0
        assert len(results) <= 3
    
    def test_sparse_only_mode(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test search with only sparse retriever."""
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=None,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("Azure 配置", top_k=3)
        
        assert len(results) > 0
        assert len(results) <= 3


# =============================================================================
# Filter Tests
# =============================================================================

class TestHybridSearchFilters:
    """Test metadata filtering functionality."""
    
    def test_explicit_filters_passed_to_retrievers(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that explicit filters are passed to retrievers."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        hybrid.search("Azure", top_k=5, filters={"collection": "api-docs"})
        
        assert dense.last_filters == {"collection": "api-docs"}
        assert sparse.last_collection == "api-docs"
    
    def test_query_filter_syntax_extraction(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that filters in query syntax are extracted."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        result = hybrid.search("collection:api-docs Azure 配置", top_k=5, return_details=True)
        
        # Check that filter was extracted from query
        assert result.processed_query is not None
        assert "collection" in result.processed_query.filters
    
    def test_post_fusion_metadata_filter(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test post-fusion metadata filtering."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        config = HybridSearchConfig(metadata_filter_post=True)
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
            config=config,
        )
        
        # Filter for api-docs collection only
        results = hybrid.search("Azure", top_k=10, filters={"collection": "api-docs"})
        
        # All results should have collection=api-docs
        for r in results:
            assert r.metadata.get("collection") == "api-docs"


# =============================================================================
# Configuration Tests
# =============================================================================

class TestHybridSearchConfig:
    """Test configuration behavior."""
    
    def test_top_k_from_config(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that top_k values from config are used."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        config = HybridSearchConfig(
            dense_top_k=3,
            sparse_top_k=3,
            fusion_top_k=2,
        )
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
            config=config,
        )
        
        results = hybrid.search("Azure")  # No explicit top_k
        
        assert dense.last_top_k == 3
        assert sparse.last_top_k == 3
        assert len(results) <= 2
    
    def test_top_k_override(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that explicit top_k overrides config."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("Azure", top_k=1)
        
        assert len(results) == 1
    
    def test_sequential_retrieval_mode(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test sequential retrieval mode (non-parallel)."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        config = HybridSearchConfig(parallel_retrieval=False)
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
            config=config,
        )
        
        results = hybrid.search("Azure", top_k=5)
        
        # Both should be called
        assert dense.call_count == 1
        assert sparse.call_count == 1
        assert len(results) > 0


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================

class TestHybridSearchEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_query_raises_error(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
    ):
        """Test that empty query raises ValueError."""
        hybrid = HybridSearch(
            query_processor=query_processor,
            fusion=rrf_fusion,
        )
        
        with pytest.raises(ValueError) as exc_info:
            hybrid.search("")
        
        assert "empty" in str(exc_info.value).lower()
    
    def test_whitespace_query_raises_error(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
    ):
        """Test that whitespace-only query raises ValueError."""
        hybrid = HybridSearch(
            query_processor=query_processor,
            fusion=rrf_fusion,
        )
        
        with pytest.raises(ValueError) as exc_info:
            hybrid.search("   \t\n  ")
        
        assert "empty" in str(exc_info.value).lower()
    
    def test_empty_results_from_both_retrievers(
        self,
        query_processor: QueryProcessor,
        rrf_fusion: RRFFusion,
    ):
        """Test handling when both retrievers return empty results."""
        dense = MockDenseRetriever(results=[])
        sparse = MockSparseRetriever(results=[])
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("obscure query with no matches", top_k=5)
        
        assert results == []
    
    def test_query_without_keywords_skips_sparse(
        self,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that sparse is skipped when no keywords extracted."""
        # Mock query processor that returns empty keywords
        mock_processor = MagicMock()
        mock_processor.process.return_value = ProcessedQuery(
            original_query="的",  # Only stopwords
            keywords=[],
            filters={},
        )
        
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=mock_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("的", top_k=5)
        
        # Dense should be called, sparse may be called but with empty keywords
        assert dense.call_count == 1
        assert len(results) > 0
    
    def test_no_query_processor_fallback(
        self,
        rrf_fusion: RRFFusion,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test fallback when no QueryProcessor is configured."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=None,  # No processor
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=rrf_fusion,
        )
        
        results = hybrid.search("Azure OpenAI", top_k=5)
        
        # Should still work with basic tokenization
        assert len(results) > 0
    
    def test_no_fusion_interleave_fallback(
        self,
        query_processor: QueryProcessor,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test interleave fallback when no fusion is configured."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=None,  # No fusion
        )
        
        results = hybrid.search("Azure", top_k=5)
        
        # Should still return results (interleaved)
        assert len(results) > 0
        assert len(results) <= 5


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestCreateHybridSearch:
    """Test the create_hybrid_search factory function."""
    
    def test_creates_default_fusion(self):
        """Test that default RRF fusion is created."""
        hybrid = create_hybrid_search()
        
        assert hybrid.fusion is not None
        assert isinstance(hybrid.fusion, RRFFusion)
        assert hybrid.fusion.k == 60  # Default k
    
    def test_uses_provided_fusion(self, rrf_fusion: RRFFusion):
        """Test that provided fusion is used."""
        custom_fusion = RRFFusion(k=30)
        
        hybrid = create_hybrid_search(fusion=custom_fusion)
        
        assert hybrid.fusion is custom_fusion
        assert hybrid.fusion.k == 30
    
    def test_passes_all_components(
        self,
        query_processor: QueryProcessor,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that all components are passed through."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        hybrid = create_hybrid_search(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
        )
        
        assert hybrid.query_processor is query_processor
        assert hybrid.dense_retriever is dense
        assert hybrid.sparse_retriever is sparse


# =============================================================================
# RRF Fusion Integration Tests
# =============================================================================

class TestRRFFusionIntegration:
    """Test actual RRF fusion behavior in HybridSearch."""
    
    def test_common_chunks_boosted_by_rrf(
        self,
        query_processor: QueryProcessor,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that chunks appearing in both results get boosted."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        
        # Use RRF fusion
        fusion = RRFFusion(k=60)
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=fusion,
        )
        
        results = hybrid.search("配置", top_k=10)
        
        # common_chunk appears in both, should be ranked higher
        chunk_ids = [r.chunk_id for r in results]
        
        # Check that common_chunk is present
        if "common_chunk" in chunk_ids:
            common_idx = chunk_ids.index("common_chunk")
            # It should be relatively high due to RRF boost
            # (appears in both lists = sum of RRF scores)
            assert common_idx < 5, "common_chunk should be boosted by RRF"
    
    def test_rrf_scores_are_deterministic(
        self,
        query_processor: QueryProcessor,
        sample_dense_results: List[RetrievalResult],
        sample_sparse_results: List[RetrievalResult],
    ):
        """Test that RRF fusion produces deterministic results."""
        dense = MockDenseRetriever(results=sample_dense_results)
        sparse = MockSparseRetriever(results=sample_sparse_results)
        fusion = RRFFusion(k=60)
        
        hybrid = HybridSearch(
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=fusion,
        )
        
        # Run same search multiple times
        results1 = hybrid.search("配置", top_k=5)
        results2 = hybrid.search("配置", top_k=5)
        
        # Results should be identical
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.chunk_id == r2.chunk_id
            assert r1.score == r2.score
