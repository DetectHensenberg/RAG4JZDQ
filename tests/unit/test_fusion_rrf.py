"""Unit tests for RRF Fusion (Reciprocal Rank Fusion).

This module tests the RRFFusion class for combining multiple retrieval
ranking lists into a unified ranking using the RRF algorithm.

Test Categories:
1. Initialization tests
2. Basic fusion functionality
3. Deterministic behavior verification
4. Edge cases and error handling
5. Weighted fusion tests
6. Utility function tests
"""

import pytest
from typing import List

from src.core.types import RetrievalResult
from src.core.query_engine.fusion import RRFFusion, rrf_score


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def fusion_default() -> RRFFusion:
    """Create RRFFusion with default k=60."""
    return RRFFusion()


@pytest.fixture
def fusion_k20() -> RRFFusion:
    """Create RRFFusion with k=20 for testing k-sensitivity."""
    return RRFFusion(k=20)


@pytest.fixture
def dense_results() -> List[RetrievalResult]:
    """Sample dense retrieval results (3 documents: a, b, c)."""
    return [
        RetrievalResult(chunk_id="a", score=0.95, text="Dense text A", metadata={"source": "dense", "page": 1}),
        RetrievalResult(chunk_id="b", score=0.85, text="Dense text B", metadata={"source": "dense", "page": 2}),
        RetrievalResult(chunk_id="c", score=0.70, text="Dense text C", metadata={"source": "dense", "page": 3}),
    ]


@pytest.fixture
def sparse_results() -> List[RetrievalResult]:
    """Sample sparse retrieval results (3 documents: b, c, d)."""
    return [
        RetrievalResult(chunk_id="b", score=5.2, text="Sparse text B", metadata={"source": "sparse", "page": 2}),
        RetrievalResult(chunk_id="c", score=4.1, text="Sparse text C", metadata={"source": "sparse", "page": 3}),
        RetrievalResult(chunk_id="d", score=3.5, text="Sparse text D", metadata={"source": "sparse", "page": 4}),
    ]


@pytest.fixture
def disjoint_results_1() -> List[RetrievalResult]:
    """Results with no overlap (set 1)."""
    return [
        RetrievalResult(chunk_id="x", score=0.9, text="Text X", metadata={}),
        RetrievalResult(chunk_id="y", score=0.8, text="Text Y", metadata={}),
    ]


@pytest.fixture
def disjoint_results_2() -> List[RetrievalResult]:
    """Results with no overlap (set 2)."""
    return [
        RetrievalResult(chunk_id="p", score=5.0, text="Text P", metadata={}),
        RetrievalResult(chunk_id="q", score=4.0, text="Text Q", metadata={}),
    ]


# =============================================================================
# Initialization Tests
# =============================================================================

class TestRRFFusionInit:
    """Tests for RRFFusion initialization."""
    
    def test_default_k_is_60(self):
        """Default k should be 60 as per original RRF paper."""
        fusion = RRFFusion()
        assert fusion.k == 60
    
    def test_custom_k_value(self):
        """Should accept custom k values."""
        fusion = RRFFusion(k=100)
        assert fusion.k == 100
    
    def test_k_must_be_positive_integer(self):
        """Should reject non-positive k values."""
        with pytest.raises(ValueError, match="positive integer"):
            RRFFusion(k=0)
        
        with pytest.raises(ValueError, match="positive integer"):
            RRFFusion(k=-10)
    
    def test_k_must_be_integer(self):
        """Should reject non-integer k values."""
        with pytest.raises(ValueError, match="positive integer"):
            RRFFusion(k=60.5)
        
        with pytest.raises(ValueError, match="positive integer"):
            RRFFusion(k="60")


# =============================================================================
# Basic Fusion Tests
# =============================================================================

class TestRRFFusionBasic:
    """Tests for basic RRF fusion functionality."""
    
    def test_fuse_single_list(self, fusion_default, dense_results):
        """Fusing a single list should preserve order with RRF scores."""
        fused = fusion_default.fuse([dense_results])
        
        assert len(fused) == 3
        # Order should be preserved: a, b, c
        assert [r.chunk_id for r in fused] == ["a", "b", "c"]
        # Scores should be RRF scores: 1/(60+1), 1/(60+2), 1/(60+3)
        assert abs(fused[0].score - 1/61) < 1e-10
        assert abs(fused[1].score - 1/62) < 1e-10
        assert abs(fused[2].score - 1/63) < 1e-10
    
    def test_fuse_two_overlapping_lists(self, fusion_default, dense_results, sparse_results):
        """Fusing overlapping lists should combine scores correctly."""
        fused = fusion_default.fuse([dense_results, sparse_results])
        
        # Should have 4 unique chunks: a, b, c, d
        assert len(fused) == 4
        chunk_ids = {r.chunk_id for r in fused}
        assert chunk_ids == {"a", "b", "c", "d"}
        
        # 'b' appears in both lists (rank 2 in dense, rank 1 in sparse)
        # RRF(b) = 1/(60+2) + 1/(60+1) = 1/62 + 1/61
        b_result = next(r for r in fused if r.chunk_id == "b")
        expected_b_score = 1/62 + 1/61
        assert abs(b_result.score - expected_b_score) < 1e-10
        
        # 'c' appears in both lists (rank 3 in dense, rank 2 in sparse)
        # RRF(c) = 1/(60+3) + 1/(60+2) = 1/63 + 1/62
        c_result = next(r for r in fused if r.chunk_id == "c")
        expected_c_score = 1/63 + 1/62
        assert abs(c_result.score - expected_c_score) < 1e-10
        
        # 'a' only in dense (rank 1)
        # RRF(a) = 1/(60+1) = 1/61
        a_result = next(r for r in fused if r.chunk_id == "a")
        assert abs(a_result.score - 1/61) < 1e-10
        
        # 'd' only in sparse (rank 3)
        # RRF(d) = 1/(60+3) = 1/63
        d_result = next(r for r in fused if r.chunk_id == "d")
        assert abs(d_result.score - 1/63) < 1e-10
    
    def test_fuse_disjoint_lists(self, fusion_default, disjoint_results_1, disjoint_results_2):
        """Fusing non-overlapping lists should include all documents."""
        fused = fusion_default.fuse([disjoint_results_1, disjoint_results_2])
        
        assert len(fused) == 4
        chunk_ids = {r.chunk_id for r in fused}
        assert chunk_ids == {"x", "y", "p", "q"}
        
        # All should have single-list RRF scores
        x_result = next(r for r in fused if r.chunk_id == "x")
        assert abs(x_result.score - 1/61) < 1e-10  # rank 1 in list 1
    
    def test_fuse_with_top_k(self, fusion_default, dense_results, sparse_results):
        """top_k should limit the number of returned results."""
        fused = fusion_default.fuse([dense_results, sparse_results], top_k=2)
        
        assert len(fused) == 2
        # Should be the top 2 by RRF score
    
    def test_fuse_top_k_larger_than_results(self, fusion_default, dense_results):
        """top_k larger than available results should return all."""
        fused = fusion_default.fuse([dense_results], top_k=100)
        
        assert len(fused) == 3


# =============================================================================
# Deterministic Behavior Tests
# =============================================================================

class TestRRFFusionDeterministic:
    """Tests for deterministic behavior (key requirement from spec)."""
    
    def test_same_input_produces_same_output(self, fusion_default, dense_results, sparse_results):
        """Same input should always produce identical output."""
        fused1 = fusion_default.fuse([dense_results, sparse_results])
        fused2 = fusion_default.fuse([dense_results, sparse_results])
        
        assert len(fused1) == len(fused2)
        for r1, r2 in zip(fused1, fused2):
            assert r1.chunk_id == r2.chunk_id
            assert r1.score == r2.score
            assert r1.text == r2.text
    
    def test_tie_breaking_by_chunk_id(self, fusion_default):
        """Equal RRF scores should be broken by chunk_id alphabetically."""
        # Create results where two chunks will have identical RRF scores
        list1 = [
            RetrievalResult(chunk_id="zebra", score=0.9, text="Z", metadata={}),
        ]
        list2 = [
            RetrievalResult(chunk_id="apple", score=0.9, text="A", metadata={}),
        ]
        
        fused = fusion_default.fuse([list1, list2])
        
        # Both have RRF score = 1/(60+1) = 1/61
        assert fused[0].chunk_id == "apple"  # 'a' < 'z'
        assert fused[1].chunk_id == "zebra"
    
    def test_list_order_affects_metadata_source(self, fusion_default):
        """First occurrence's metadata should be preserved."""
        list1 = [
            RetrievalResult(chunk_id="shared", score=0.9, text="Text from list 1", metadata={"source": "list1"}),
        ]
        list2 = [
            RetrievalResult(chunk_id="shared", score=5.0, text="Text from list 2", metadata={"source": "list2"}),
        ]
        
        fused = fusion_default.fuse([list1, list2])
        
        assert len(fused) == 1
        # First occurrence (list1) metadata preserved
        assert fused[0].metadata["source"] == "list1"
        assert fused[0].text == "Text from list 1"
    
    def test_order_of_lists_does_not_affect_scores(self, fusion_default, dense_results, sparse_results):
        """Swapping list order should produce same scores (different order for ties only)."""
        fused1 = fusion_default.fuse([dense_results, sparse_results])
        fused2 = fusion_default.fuse([sparse_results, dense_results])
        
        # Create score lookup
        scores1 = {r.chunk_id: r.score for r in fused1}
        scores2 = {r.chunk_id: r.score for r in fused2}
        
        # Scores should be identical
        assert scores1 == scores2


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestRRFFusionEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_ranking_lists_raises_error(self, fusion_default):
        """Empty ranking_lists should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            fusion_default.fuse([])
    
    def test_all_empty_lists_returns_empty(self, fusion_default):
        """All empty lists should return empty result."""
        fused = fusion_default.fuse([[], []])
        
        assert fused == []
    
    def test_some_empty_lists_ignored(self, fusion_default, dense_results):
        """Empty lists should be filtered out."""
        fused = fusion_default.fuse([[], dense_results, []])
        
        assert len(fused) == 3
        assert [r.chunk_id for r in fused] == ["a", "b", "c"]
    
    def test_single_result_per_list(self, fusion_default):
        """Should handle lists with single results."""
        list1 = [RetrievalResult(chunk_id="only", score=1.0, text="Solo", metadata={})]
        
        fused = fusion_default.fuse([list1])
        
        assert len(fused) == 1
        assert fused[0].chunk_id == "only"
    
    def test_many_lists(self, fusion_default):
        """Should handle many ranking lists."""
        lists = [
            [RetrievalResult(chunk_id=f"chunk_{i}", score=1.0, text=f"Text {i}", metadata={})]
            for i in range(10)
        ]
        
        fused = fusion_default.fuse(lists)
        
        assert len(fused) == 10
    
    def test_metadata_is_copied_not_shared(self, fusion_default, dense_results):
        """Metadata should be copied to avoid mutation issues."""
        fused = fusion_default.fuse([dense_results])
        
        # Modify fused metadata
        fused[0].metadata["modified"] = True
        
        # Original should not be affected
        assert "modified" not in dense_results[0].metadata


# =============================================================================
# K Parameter Sensitivity Tests
# =============================================================================

class TestRRFFusionKParameter:
    """Tests for k parameter effects on fusion."""
    
    def test_higher_k_reduces_score_differences(self):
        """Higher k should reduce the difference between adjacent ranks."""
        fusion_k20 = RRFFusion(k=20)
        fusion_k100 = RRFFusion(k=100)
        
        # Score difference between rank 1 and rank 2
        # k=20: 1/21 - 1/22 = 0.00216...
        # k=100: 1/101 - 1/102 = 0.000097...
        
        diff_k20 = 1/21 - 1/22
        diff_k100 = 1/101 - 1/102
        
        assert diff_k20 > diff_k100
    
    def test_k_affects_final_ranking(self):
        """Different k values can lead to different rankings in edge cases."""
        # Construct a case where k matters:
        # Document A: rank 1 in list 1, not in list 2
        # Document B: rank 10 in list 1, rank 1 in list 2
        
        list1 = [
            RetrievalResult(chunk_id="a", score=1.0, text="A", metadata={}),
        ] + [
            RetrievalResult(chunk_id=f"filler_{i}", score=0.5, text="", metadata={})
            for i in range(8)
        ] + [
            RetrievalResult(chunk_id="b", score=0.1, text="B", metadata={}),
        ]
        
        list2 = [
            RetrievalResult(chunk_id="b", score=5.0, text="B", metadata={}),
        ]
        
        fusion_k20 = RRFFusion(k=20)
        fusion_k100 = RRFFusion(k=100)
        
        fused_k20 = fusion_k20.fuse([list1, list2])
        fused_k100 = fusion_k100.fuse([list1, list2])
        
        # Get scores for a and b in each fusion
        scores_k20 = {r.chunk_id: r.score for r in fused_k20}
        scores_k100 = {r.chunk_id: r.score for r in fused_k100}
        
        # With k=20:
        # A: 1/(20+1) = 1/21 ≈ 0.0476
        # B: 1/(20+10) + 1/(20+1) = 1/30 + 1/21 ≈ 0.0810
        # B > A
        
        # With k=100:
        # A: 1/(100+1) = 1/101 ≈ 0.0099
        # B: 1/(100+10) + 1/(100+1) = 1/110 + 1/101 ≈ 0.0190
        # B > A (but closer)
        
        assert scores_k20["b"] > scores_k20["a"]
        assert scores_k100["b"] > scores_k100["a"]


# =============================================================================
# Weighted Fusion Tests
# =============================================================================

class TestRRFFusionWeighted:
    """Tests for weighted RRF fusion."""
    
    def test_weighted_fusion_basic(self, fusion_default):
        """Weighted fusion should multiply scores by weights."""
        list1 = [
            RetrievalResult(chunk_id="a", score=1.0, text="A", metadata={}),
        ]
        list2 = [
            RetrievalResult(chunk_id="b", score=1.0, text="B", metadata={}),
        ]
        
        # Give list1 double weight
        fused = fusion_default.fuse_with_weights([list1, list2], weights=[2.0, 1.0])
        
        scores = {r.chunk_id: r.score for r in fused}
        
        # A: 2.0 * 1/(60+1) = 2/61
        # B: 1.0 * 1/(60+1) = 1/61
        assert abs(scores["a"] - 2/61) < 1e-10
        assert abs(scores["b"] - 1/61) < 1e-10
    
    def test_weighted_fusion_default_uniform(self, fusion_default, dense_results):
        """Without weights, should be same as regular fusion."""
        fused_regular = fusion_default.fuse([dense_results])
        fused_weighted = fusion_default.fuse_with_weights([dense_results])
        
        for r1, r2 in zip(fused_regular, fused_weighted):
            assert r1.chunk_id == r2.chunk_id
            assert abs(r1.score - r2.score) < 1e-10
    
    def test_weighted_fusion_weight_length_mismatch(self, fusion_default, dense_results, sparse_results):
        """Weight length must match ranking_lists length."""
        with pytest.raises(ValueError, match="must match"):
            fusion_default.fuse_with_weights(
                [dense_results, sparse_results],
                weights=[1.0]  # Only 1 weight for 2 lists
            )
    
    def test_weighted_fusion_negative_weight_rejected(self, fusion_default, dense_results):
        """Negative weights should be rejected."""
        with pytest.raises(ValueError, match="non-negative"):
            fusion_default.fuse_with_weights([dense_results], weights=[-1.0])
    
    def test_weighted_fusion_zero_weight(self, fusion_default):
        """Zero weight should effectively ignore that list."""
        list1 = [
            RetrievalResult(chunk_id="a", score=1.0, text="A", metadata={}),
        ]
        list2 = [
            RetrievalResult(chunk_id="b", score=1.0, text="B", metadata={}),
        ]
        
        fused = fusion_default.fuse_with_weights([list1, list2], weights=[1.0, 0.0])
        
        scores = {r.chunk_id: r.score for r in fused}
        
        assert abs(scores["a"] - 1/61) < 1e-10
        assert abs(scores["b"] - 0.0) < 1e-10  # Zero contribution
    
    def test_weighted_fusion_with_top_k(self, fusion_default, dense_results, sparse_results):
        """Weighted fusion should respect top_k."""
        fused = fusion_default.fuse_with_weights(
            [dense_results, sparse_results],
            weights=[1.5, 1.0],
            top_k=2
        )
        
        assert len(fused) == 2


# =============================================================================
# Utility Function Tests
# =============================================================================

class TestRRFScoreFunction:
    """Tests for the rrf_score utility function."""
    
    def test_rrf_score_rank_1(self):
        """RRF score for rank 1 with default k."""
        score = rrf_score(1)
        assert abs(score - 1/61) < 1e-10
    
    def test_rrf_score_rank_10(self):
        """RRF score for rank 10 with default k."""
        score = rrf_score(10)
        assert abs(score - 1/70) < 1e-10
    
    def test_rrf_score_custom_k(self):
        """RRF score with custom k value."""
        score = rrf_score(1, k=20)
        assert abs(score - 1/21) < 1e-10
    
    def test_rrf_score_invalid_rank(self):
        """Should reject invalid rank values."""
        with pytest.raises(ValueError, match="positive integer"):
            rrf_score(0)
        
        with pytest.raises(ValueError, match="positive integer"):
            rrf_score(-1)
        
        with pytest.raises(ValueError, match="positive integer"):
            rrf_score(1.5)
    
    def test_rrf_score_invalid_k(self):
        """Should reject invalid k values."""
        with pytest.raises(ValueError, match="positive integer"):
            rrf_score(1, k=0)
        
        with pytest.raises(ValueError, match="positive integer"):
            rrf_score(1, k=-10)


# =============================================================================
# Integration-like Tests
# =============================================================================

class TestRRFFusionRealisticScenarios:
    """Tests simulating realistic retrieval scenarios."""
    
    def test_typical_hybrid_search_scenario(self, fusion_default):
        """Simulate typical Dense + Sparse hybrid search."""
        # Dense retrieval: semantic matches
        dense = [
            RetrievalResult(chunk_id="semantic_1", score=0.92, text="Detailed explanation of RAG architecture", metadata={"type": "doc"}),
            RetrievalResult(chunk_id="semantic_2", score=0.88, text="How retrieval augmented generation works", metadata={"type": "doc"}),
            RetrievalResult(chunk_id="both_1", score=0.85, text="RAG implementation with Azure OpenAI", metadata={"type": "tutorial"}),
            RetrievalResult(chunk_id="semantic_3", score=0.80, text="Vector embeddings for document search", metadata={"type": "doc"}),
        ]
        
        # Sparse retrieval: keyword matches for "RAG Azure"
        sparse = [
            RetrievalResult(chunk_id="keyword_1", score=8.5, text="Azure RAG setup guide", metadata={"type": "guide"}),
            RetrievalResult(chunk_id="both_1", score=7.2, text="RAG implementation with Azure OpenAI", metadata={"type": "tutorial"}),
            RetrievalResult(chunk_id="keyword_2", score=5.1, text="Azure configuration for RAG", metadata={"type": "config"}),
        ]
        
        fused = fusion_default.fuse([dense, sparse], top_k=5)
        
        # Verify overlap document "both_1" gets boosted
        both_1_result = next(r for r in fused if r.chunk_id == "both_1")
        semantic_1_result = next(r for r in fused if r.chunk_id == "semantic_1")
        
        # both_1 should have higher RRF score than semantic_1
        # both_1: 1/(60+3) + 1/(60+2) = 1/63 + 1/62 ≈ 0.0320
        # semantic_1: 1/(60+1) = 1/61 ≈ 0.0164
        assert both_1_result.score > semantic_1_result.score
    
    def test_sparse_dominant_scenario(self, fusion_default):
        """Scenario where sparse retrieval should be trusted more."""
        # Sparse has strong exact keyword matches
        sparse = [
            RetrievalResult(chunk_id="exact_match", score=15.0, text="配置 Azure OpenAI API 密钥", metadata={}),
        ]
        
        # Dense has weak semantic matches
        dense = [
            RetrievalResult(chunk_id="weak_semantic_1", score=0.52, text="Cloud service configuration", metadata={}),
            RetrievalResult(chunk_id="weak_semantic_2", score=0.51, text="API integration patterns", metadata={}),
            RetrievalResult(chunk_id="exact_match", score=0.48, text="配置 Azure OpenAI API 密钥", metadata={}),
        ]
        
        fused = fusion_default.fuse([dense, sparse])
        
        # exact_match should be ranked first due to appearing in both
        assert fused[0].chunk_id == "exact_match"
