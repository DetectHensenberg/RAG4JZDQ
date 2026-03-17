"""Unit tests for QueryRewriter.

Tests for:
- #11: Query Rewriting and HyDE
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.query_engine.query_rewriter import QueryRewriter, RewriteResult


@pytest.fixture
def mock_settings_disabled():
    """Settings with rewriting disabled."""
    settings = MagicMock()
    settings.retrieval = MagicMock()
    settings.retrieval.query_rewrite = False
    settings.retrieval.hyde_enabled = False
    return settings


@pytest.fixture
def mock_settings_enabled():
    """Settings with rewriting enabled."""
    settings = MagicMock()
    settings.retrieval = MagicMock()
    settings.retrieval.query_rewrite = True
    settings.retrieval.hyde_enabled = True
    return settings


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = MagicMock()
    return llm


class TestQueryRewriterDisabled:
    """Test QueryRewriter when disabled."""
    
    def test_rewrite_disabled_returns_original(self, mock_settings_disabled):
        """When disabled, should return original query only."""
        rewriter = QueryRewriter(mock_settings_disabled)
        result = rewriter.rewrite("九洲搞什么的")
        
        assert result.original_query == "九洲搞什么的"
        assert result.rewritten_queries == ["九洲搞什么的"]
        assert result.hyde_document is None
        assert result.rewrite_used is False
        assert result.hyde_used is False
    
    def test_empty_query(self, mock_settings_disabled):
        """Empty query should return empty result."""
        rewriter = QueryRewriter(mock_settings_disabled)
        result = rewriter.rewrite("")
        
        assert result.original_query == ""
        assert result.rewritten_queries == [""]
        assert result.rewrite_used is False


class TestQueryRewriterEnabled:
    """Test QueryRewriter when enabled."""
    
    def test_rewrite_enabled(self, mock_settings_enabled, mock_llm):
        """When enabled, should call LLM for rewriting."""
        mock_llm.generate.return_value = "九洲公司的主营业务是什么\n九洲集团的业务范围"
        
        rewriter = QueryRewriter(mock_settings_enabled, llm=mock_llm)
        result = rewriter.rewrite("九洲搞什么的")
        
        assert result.original_query == "九洲搞什么的"
        assert "九洲搞什么的" in result.rewritten_queries  # Original included
        assert "九洲公司的主营业务是什么" in result.rewritten_queries
        assert "九洲集团的业务范围" in result.rewritten_queries
        assert result.rewrite_used is True
    
    def test_hyde_enabled(self, mock_settings_enabled, mock_llm):
        """When HyDE enabled, should generate hypothetical document."""
        mock_llm.generate.side_effect = [
            "改写后的问题1\n改写后的问题2",  # First call for rewrite
            "九洲集团是一家专注于电子信息产业的高科技企业...",  # Second call for HyDE
        ]
        
        rewriter = QueryRewriter(mock_settings_enabled, llm=mock_llm)
        result = rewriter.rewrite("九洲搞什么的")
        
        assert result.hyde_document is not None
        assert "九洲集团" in result.hyde_document
        assert result.hyde_used is True
    
    def test_rewrite_with_numbered_lines(self, mock_settings_enabled, mock_llm):
        """Should handle numbered response format."""
        mock_llm.generate.return_value = "1. 九洲公司的主营业务\n2. 九洲集团业务范围\n3. 九洲的核心产品"
        
        rewriter = QueryRewriter(mock_settings_enabled, llm=mock_llm)
        result = rewriter.rewrite("九洲搞什么的")
        
        # Should strip numbering
        assert "九洲公司的主营业务" in result.rewritten_queries
        assert result.rewrite_used is True
    
    def test_llm_error_fallback(self, mock_settings_enabled, mock_llm):
        """Should fallback to original on LLM error."""
        mock_llm.generate.side_effect = Exception("LLM error")
        
        rewriter = QueryRewriter(mock_settings_enabled, llm=mock_llm)
        result = rewriter.rewrite("测试问题")
        
        # Should still have original query
        assert result.original_query == "测试问题"
        assert "测试问题" in result.rewritten_queries
        # Rewrite failed, so rewrite_used should be False
        assert result.rewrite_used is False


class TestRewriteResult:
    """Test RewriteResult dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        result = RewriteResult(
            original_query="test",
            rewritten_queries=["test"],
        )
        
        assert result.hyde_document is None
        assert result.rewrite_used is False
        assert result.hyde_used is False
    
    def test_full_result(self):
        """Test full result with all fields."""
        result = RewriteResult(
            original_query="original",
            rewritten_queries=["original", "rewritten1", "rewritten2"],
            hyde_document="hypothetical doc",
            rewrite_used=True,
            hyde_used=True,
        )
        
        assert len(result.rewritten_queries) == 3
        assert result.hyde_document == "hypothetical doc"


class TestQueryRewriterProperties:
    """Test QueryRewriter properties."""
    
    def test_rewrite_enabled_property(self, mock_settings_enabled):
        """Test rewrite_enabled property."""
        rewriter = QueryRewriter(mock_settings_enabled)
        assert rewriter.rewrite_enabled is True
    
    def test_hyde_enabled_property(self, mock_settings_enabled):
        """Test hyde_enabled property."""
        rewriter = QueryRewriter(mock_settings_enabled)
        assert rewriter.hyde_enabled is True
    
    def test_disabled_properties(self, mock_settings_disabled):
        """Test properties when disabled."""
        rewriter = QueryRewriter(mock_settings_disabled)
        assert rewriter.rewrite_enabled is False
        assert rewriter.hyde_enabled is False
