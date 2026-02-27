"""Tests for Cross-Encoder based Reranker implementation."""

from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest

from src.core.settings import RerankSettings, Settings
from src.libs.reranker.cross_encoder_reranker import (
    CrossEncoderRerankError,
    CrossEncoderReranker,
)


class MockCrossEncoder:
    """Mock Cross-Encoder model for deterministic testing."""
    
    def __init__(self, model_name: str = "mock-model"):
        self.model_name = model_name
        self.call_count = 0
        self.last_pairs = None
    
    def predict(self, pairs: List[tuple[str, str]]) -> List[float]:
        """Return deterministic scores for testing.
        
        Scoring strategy: score based on presence of keywords in passage.
        """
        self.call_count += 1
        self.last_pairs = pairs
        
        scores = []
        for query, passage in pairs:
            # Simple scoring: count keyword matches
            score = 0.0
            query_words = query.lower().split()
            passage_lower = passage.lower()
            
            for word in query_words:
                if word in passage_lower:
                    score += 0.3
            
            scores.append(score)
        
        return scores


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.rerank = Mock(spec=RerankSettings)
    settings.rerank.model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    settings.rerank.enabled = True
    settings.rerank.provider = "cross_encoder"
    return settings


@pytest.fixture
def sample_candidates():
    """Sample candidate list for reranking."""
    return [
        {"id": "chunk_1", "text": "Python is a programming language.", "score": 0.8},
        {"id": "chunk_2", "text": "Machine learning uses neural networks.", "score": 0.75},
        {"id": "chunk_3", "text": "RAG combines retrieval and generation.", "score": 0.9},
        {"id": "chunk_4", "text": "Embeddings represent text as vectors.", "score": 0.7},
    ]


class TestCrossEncoderRerankerInit:
    """Test CrossEncoderReranker initialization."""
    
    def test_init_with_mock_model(self, mock_settings):
        """Test initialization with injected mock model."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model,
            timeout=5.0
        )
        
        assert reranker.settings == mock_settings
        assert reranker.model == mock_model
        assert reranker.timeout == 5.0
    
    def test_init_missing_model_config(self):
        """Test initialization fails when model config is missing."""
        settings = Mock(spec=Settings)
        settings.rerank = Mock(spec=RerankSettings)
        settings.rerank.model = None
        
        with pytest.raises(CrossEncoderRerankError, match="Failed to initialize"):
            CrossEncoderReranker(settings=settings)
    
    def test_init_invalid_model_type(self):
        """Test initialization fails with invalid model type."""
        settings = Mock(spec=Settings)
        settings.rerank = Mock(spec=RerankSettings)
        settings.rerank.model = 123  # Not a string
        
        with pytest.raises(CrossEncoderRerankError, match="Failed to initialize"):
            CrossEncoderReranker(settings=settings)
    
    def test_get_model_name_from_settings(self, mock_settings):
        """Test extracting model name from settings."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        model_name = reranker._get_model_name_from_settings(mock_settings)
        assert model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    @patch('src.libs.reranker.cross_encoder_reranker.CrossEncoderReranker._load_cross_encoder_model')
    def test_init_loads_model_from_settings(self, mock_load, mock_settings):
        """Test that init loads model from settings when not injected."""
        mock_load.return_value = MockCrossEncoder()
        
        reranker = CrossEncoderReranker(settings=mock_settings)
        
        mock_load.assert_called_once_with("cross-encoder/ms-marco-MiniLM-L-6-v2")
        assert reranker.model is not None


class TestCrossEncoderRerankerValidation:
    """Test input validation."""
    
    def test_validate_query_success(self, mock_settings):
        """Test query validation passes for valid query."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        # Should not raise
        reranker.validate_query("What is RAG?")
    
    def test_validate_query_empty(self, mock_settings):
        """Test query validation fails for empty query."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.validate_query("")
    
    def test_validate_candidates_success(self, mock_settings, sample_candidates):
        """Test candidates validation passes for valid list."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        # Should not raise
        reranker.validate_candidates(sample_candidates)
    
    def test_validate_candidates_empty_list(self, mock_settings):
        """Test candidates validation fails for empty list."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.validate_candidates([])


class TestCrossEncoderRerankerPairPreparation:
    """Test query-passage pair preparation."""
    
    def test_prepare_pairs_with_text_field(self, mock_settings):
        """Test pair preparation with 'text' field."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "text": "First passage"},
            {"id": "2", "text": "Second passage"},
        ]
        
        pairs = reranker._prepare_pairs("query", candidates)
        
        assert len(pairs) == 2
        assert pairs[0] == ("query", "First passage")
        assert pairs[1] == ("query", "Second passage")
    
    def test_prepare_pairs_with_content_field(self, mock_settings):
        """Test pair preparation with 'content' field as fallback."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "content": "First passage"},
            {"id": "2", "content": "Second passage"},
        ]
        
        pairs = reranker._prepare_pairs("query", candidates)
        
        assert len(pairs) == 2
        assert pairs[0] == ("query", "First passage")
        assert pairs[1] == ("query", "Second passage")
    
    def test_prepare_pairs_missing_text(self, mock_settings):
        """Test pair preparation with missing text field."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1"},  # No text or content
        ]
        
        pairs = reranker._prepare_pairs("query", candidates)
        
        assert len(pairs) == 1
        assert pairs[0] == ("query", "")  # Empty string fallback


class TestCrossEncoderRerankerScoring:
    """Test scoring functionality."""
    
    def test_score_pairs_success(self, mock_settings):
        """Test successful scoring of pairs."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        pairs = [
            ("machine learning", "Machine learning is a field of AI"),
            ("machine learning", "Python is a programming language"),
        ]
        
        scores = reranker._score_pairs(pairs)
        
        assert len(scores) == 2
        assert isinstance(scores[0], float)
        assert isinstance(scores[1], float)
        # First passage should score higher (contains both keywords)
        assert scores[0] > scores[1]
    
    def test_score_pairs_model_called(self, mock_settings):
        """Test that model.predict is called with correct pairs."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        pairs = [("query", "passage")]
        
        reranker._score_pairs(pairs)
        
        assert mock_model.call_count == 1
        assert mock_model.last_pairs == pairs


class TestCrossEncoderRerankerSorting:
    """Test score attachment and sorting."""
    
    def test_attach_scores_and_sort(self, mock_settings):
        """Test attaching scores and sorting by relevance."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "text": "Low"},
            {"id": "2", "text": "High"},
            {"id": "3", "text": "Medium"},
        ]
        scores = [0.1, 0.9, 0.5]
        
        result = reranker._attach_scores_and_sort(candidates, scores, top_k=3)
        
        assert len(result) == 3
        assert result[0]["id"] == "2"
        assert result[0]["rerank_score"] == 0.9
        assert result[1]["id"] == "3"
        assert result[1]["rerank_score"] == 0.5
        assert result[2]["id"] == "1"
        assert result[2]["rerank_score"] == 0.1
    
    def test_attach_scores_top_k_limit(self, mock_settings):
        """Test top_k limits output size."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "text": "A"},
            {"id": "2", "text": "B"},
            {"id": "3", "text": "C"},
        ]
        scores = [0.3, 0.9, 0.6]
        
        result = reranker._attach_scores_and_sort(candidates, scores, top_k=2)
        
        assert len(result) == 2
        assert result[0]["id"] == "2"
        assert result[1]["id"] == "3"
    
    def test_attach_scores_preserves_original(self, mock_settings):
        """Test that original candidates are not modified."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "text": "Test", "metadata": {"key": "value"}},
        ]
        scores = [0.5]
        
        result = reranker._attach_scores_and_sort(candidates, scores, top_k=1)
        
        # Original should not have rerank_score
        assert "rerank_score" not in candidates[0]
        # Result should have rerank_score
        assert "rerank_score" in result[0]
        # Other fields preserved
        assert result[0]["metadata"] == {"key": "value"}


class TestCrossEncoderRerankerEndToEnd:
    """Test end-to-end reranking."""
    
    def test_rerank_success(self, mock_settings, sample_candidates):
        """Test successful end-to-end reranking."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        query = "machine learning neural networks"
        result = reranker.rerank(query, sample_candidates)
        
        # Should return reranked candidates
        assert len(result) == 4
        assert all("rerank_score" in c for c in result)
        
        # Candidate 2 should rank highest (contains both keywords)
        assert result[0]["id"] == "chunk_2"
        assert result[0]["text"] == "Machine learning uses neural networks."
    
    def test_rerank_with_top_k(self, mock_settings, sample_candidates):
        """Test reranking with top_k parameter."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        query = "machine learning"
        result = reranker.rerank(query, sample_candidates, top_k=2)
        
        assert len(result) == 2
        # Should return top 2 by relevance
        assert result[0]["id"] == "chunk_2"
    
    def test_rerank_invalid_query(self, mock_settings, sample_candidates):
        """Test reranking with invalid query."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        with pytest.raises(ValueError, match="Query"):
            reranker.rerank("", sample_candidates)
    
    def test_rerank_invalid_candidates(self, mock_settings):
        """Test reranking with invalid candidates."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        with pytest.raises(ValueError, match="Candidates"):
            reranker.rerank("query", [])
    
    def test_rerank_invalid_top_k(self, mock_settings, sample_candidates):
        """Test reranking with invalid top_k parameter."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        with pytest.raises(ValueError, match="top_k"):
            reranker.rerank("query", sample_candidates, top_k=0)
    
    def test_rerank_single_candidate(self, mock_settings):
        """Test reranking with single candidate."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [{"id": "1", "text": "Single passage"}]
        result = reranker.rerank("query", candidates)
        
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert "rerank_score" in result[0]


class TestCrossEncoderRerankerIntegration:
    """Test integration scenarios."""
    
    def test_rerank_with_trace_context(self, mock_settings, sample_candidates):
        """Test reranking with trace context."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        mock_trace = Mock()
        query = "machine learning"
        
        result = reranker.rerank(query, sample_candidates, trace=mock_trace)
        
        # Should complete successfully and pass trace through
        assert len(result) == 4
        assert all("rerank_score" in c for c in result)
    
    def test_rerank_preserves_all_fields(self, mock_settings):
        """Test that reranking preserves all original candidate fields."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {
                "id": "1",
                "text": "Machine learning text",
                "score": 0.8,
                "metadata": {"source": "doc1", "page": 5},
                "custom_field": "custom_value"
            }
        ]
        
        result = reranker.rerank("machine learning", candidates)
        
        assert result[0]["id"] == "1"
        assert result[0]["score"] == 0.8
        assert result[0]["metadata"] == {"source": "doc1", "page": 5}
        assert result[0]["custom_field"] == "custom_value"
        assert result[0]["rerank_score"] > 0
    
    def test_rerank_deterministic(self, mock_settings):
        """Test that reranking produces deterministic results with mock."""
        mock_model = MockCrossEncoder()
        reranker = CrossEncoderReranker(
            settings=mock_settings,
            model=mock_model
        )
        
        candidates = [
            {"id": "1", "text": "First"},
            {"id": "2", "text": "Second"},
        ]
        
        result1 = reranker.rerank("query", candidates)
        result2 = reranker.rerank("query", candidates)
        
        # Should produce identical results
        assert result1[0]["id"] == result2[0]["id"]
        assert result1[0]["rerank_score"] == result2[0]["rerank_score"]
