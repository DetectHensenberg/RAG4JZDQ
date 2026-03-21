"""Unit tests for image relevance scoring in chat API."""

from __future__ import annotations

import pytest


class TestCalculateImageRelevance:
    """Test _calculate_image_relevance function."""

    def test_no_caption_returns_rank_score_with_penalty(self):
        """Images without captions should have reduced relevance based on rank."""
        from api.routers.chat import _calculate_image_relevance
        
        # rank_score = 0.8 (default rank=0, total=1)
        # Result = rank_score * 0.7 = 0.56
        result = _calculate_image_relevance("系统架构是什么", None, 0.8)
        assert result == pytest.approx(0.56, rel=0.01)

    def test_exact_keyword_match_high_relevance(self):
        """Exact keyword overlap should result in high relevance."""
        from api.routers.chat import _calculate_image_relevance
        
        # rank_score = 0.8
        # jaccard = 1.0 (assuming keywords match)
        # Result = 0.8 * 0.6 + 1.0 * 0.4 = 0.48 + 0.4 = 0.88
        result = _calculate_image_relevance(
            question="系统架构",
            caption="系统架构",
            chunk_score=0.7,
        )
        assert result == pytest.approx(0.88, rel=0.01)

    def test_no_keyword_overlap_lower_relevance(self):
        """No keyword overlap should rely mostly on rank score."""
        from api.routers.chat import _calculate_image_relevance
        
        # rank_score = 0.8
        # jaccard = 0.0
        # Result = 0.8 * 0.6 + 0.0 * 0.4 = 0.48
        result = _calculate_image_relevance(
            question="部署",
            caption="说明",
            chunk_score=0.6,
        )
        assert result == pytest.approx(0.48, rel=0.01)

    def test_phrase_match_boosts_score(self):
        """Phrase match in caption should boost relevance."""
        from api.routers.chat import _calculate_image_relevance
        
        # Both have rank_score = 0.8
        result_with_phrase = _calculate_image_relevance(
            question="系统架构的设计方案",
            caption="系统架构包含多个模块",
            chunk_score=0.5,
        )
        
        result_no_phrase = _calculate_image_relevance(
            question="部署流程是怎样的",
            caption="系统架构包含多个模块",
            chunk_score=0.5,
        )
        
        assert result_with_phrase > result_no_phrase

    def test_weighted_combination_formula(self):
        """Verify the weighted combination: rank_score * 0.6 + caption_sim * 0.4."""
        from api.routers.chat import _calculate_image_relevance
        
        # Perfect caption match (jaccard = 1.0)
        # rank_score = 0.8
        result = _calculate_image_relevance(
            question="架构图",
            caption="架构图",
            chunk_score=0.5,
        )
        # Expected: 0.8 * 0.6 + 1.0 * 0.4 = 0.48 + 0.4 = 0.88
        assert result == pytest.approx(0.88, rel=0.01)

    def test_empty_strings_handled_gracefully(self):
        """Empty question or caption should not crash."""
        from api.routers.chat import _calculate_image_relevance
        
        result1 = _calculate_image_relevance("", "some caption", 0.5)
        result2 = _calculate_image_relevance("some question", "", 0.5)
        
        assert result1 >= 0
        assert result2 >= 0

    def test_rank_affects_score(self):
        """Higher rank should result in higher score."""
        from api.routers.chat import _calculate_image_relevance
        
        # Rank 0 vs Rank 4 in total 10
        score_rank0 = _calculate_image_relevance("test", "test", 0.5, rank=0, total_results=10)
        score_rank4 = _calculate_image_relevance("test", "test", 0.5, rank=4, total_results=10)
        
        assert score_rank0 > score_rank4

    def test_threshold_boundary(self):
        """Test scores around the threshold boundary."""
        from api.routers.chat import _calculate_image_relevance, IMAGE_RELEVANCE_THRESHOLD
        
        # With very low rank (last item in many results)
        # rank_score = 0.8 - (9/9)*0.5 = 0.3
        # Result = 0.3 * 0.7 = 0.21 (if no caption)
        # This is still above THRESHOLD=0.10 because retrieved images are "good"
        result = _calculate_image_relevance(
            question="完全无关",
            caption=None,
            chunk_score=0.1,
            rank=9,
            total_results=10
        )
        assert result >= IMAGE_RELEVANCE_THRESHOLD
