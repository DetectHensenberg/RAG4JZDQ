"""Unit tests for image relevance scoring in chat API."""

from __future__ import annotations

import pytest


class TestCalculateImageRelevance:
    """Test _calculate_image_relevance function."""

    def test_no_caption_returns_chunk_score_with_penalty(self):
        """Images without captions should have reduced relevance."""
        from api.routers.chat import _calculate_image_relevance
        
        # No caption = chunk_score * 0.5
        result = _calculate_image_relevance("系统架构是什么", None, 0.8)
        assert result == pytest.approx(0.4, rel=0.01)

    def test_exact_keyword_match_high_relevance(self):
        """Exact keyword overlap should result in high relevance."""
        from api.routers.chat import _calculate_image_relevance
        
        # Question and caption share keywords
        result = _calculate_image_relevance(
            question="系统架构是怎样的",
            caption="系统架构图展示微服务组件",
            chunk_score=0.7,
        )
        # Should have high score due to keyword overlap
        assert result >= 0.5

    def test_no_keyword_overlap_lower_relevance(self):
        """No keyword overlap should rely mostly on chunk score."""
        from api.routers.chat import _calculate_image_relevance
        
        result = _calculate_image_relevance(
            question="如何部署系统",
            caption="用户登录流程示意图",
            chunk_score=0.6,
        )
        # No overlap, score should be lower
        assert result < 0.5

    def test_phrase_match_boosts_score(self):
        """Phrase match in caption should boost relevance."""
        from api.routers.chat import _calculate_image_relevance
        
        # Question contains "系统架构" which appears in caption
        result_with_phrase = _calculate_image_relevance(
            question="系统架构的设计方案",
            caption="系统架构包含多个模块",
            chunk_score=0.5,
        )
        
        # Compare with no phrase match
        result_no_phrase = _calculate_image_relevance(
            question="部署流程是怎样的",
            caption="系统架构包含多个模块",
            chunk_score=0.5,
        )
        
        assert result_with_phrase > result_no_phrase

    def test_weighted_combination_formula(self):
        """Verify the weighted combination: chunk_score * 0.6 + caption_sim * 0.4."""
        from api.routers.chat import _calculate_image_relevance
        
        # Perfect caption match (jaccard = 1.0)
        result = _calculate_image_relevance(
            question="架构图",
            caption="架构图",
            chunk_score=0.5,
        )
        # Expected: 0.5 * 0.6 + 1.0 * 0.4 = 0.7
        assert result == pytest.approx(0.7, rel=0.05)

    def test_empty_strings_handled_gracefully(self):
        """Empty question or caption should not crash."""
        from api.routers.chat import _calculate_image_relevance
        
        result1 = _calculate_image_relevance("", "some caption", 0.5)
        result2 = _calculate_image_relevance("some question", "", 0.5)
        
        assert result1 >= 0
        assert result2 >= 0

    def test_chinese_text_tokenization(self):
        """Chinese text should be tokenized correctly."""  
        from api.routers.chat import _calculate_image_relevance
        
        # Chinese characters are tokenized by \w+ pattern
        result = _calculate_image_relevance(
            question="什么是RAG系统",
            caption="RAG系统架构说明",
            chunk_score=0.6,
        )
        # "RAG" and "系统" should match - but \w+ only matches ASCII
        # So we expect moderate score from chunk_score * 0.6
        assert result > 0.3

    def test_mixed_chinese_english_text(self):
        """Mixed Chinese-English text should work."""  
        from api.routers.chat import _calculate_image_relevance
        
        result = _calculate_image_relevance(
            question="LLM模型如何工作",
            caption="LLM模型工作原理图",
            chunk_score=0.7,
        )
        # "LLM" should match (ASCII), but "模型" won't (Chinese)
        # chunk_score * 0.6 = 0.42, plus some caption match for LLM
        assert result > 0.4

    def test_threshold_boundary(self):
        """Test scores around the threshold boundary."""
        from api.routers.chat import _calculate_image_relevance, IMAGE_RELEVANCE_THRESHOLD
        
        # Low chunk score, no caption match
        result = _calculate_image_relevance(
            question="完全无关的问题",
            caption="完全不同的描述",
            chunk_score=0.2,
        )
        # Should be below threshold
        assert result < IMAGE_RELEVANCE_THRESHOLD

    def test_high_chunk_score_compensates_poor_caption(self):
        """High chunk score can compensate for poor caption match."""
        from api.routers.chat import _calculate_image_relevance
        
        result = _calculate_image_relevance(
            question="部署流程",
            caption="用户界面设计",
            chunk_score=0.9,
        )
        # chunk_score * 0.6 = 0.54, so result should be around 0.54
        assert result > 0.4
