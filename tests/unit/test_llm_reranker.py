"""Tests for LLM-based Reranker implementation."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from src.core.settings import LLMSettings, RerankSettings, Settings
from src.libs.llm.base_llm import BaseLLM, ChatResponse, Message
from src.libs.reranker.llm_reranker import LLMRerankError, LLMReranker


class MockLLM(BaseLLM):
    """Mock LLM for testing."""
    
    def __init__(self, response_content: str = "[]"):
        self.response_content = response_content
        self.call_count = 0
        self.last_messages: Optional[List[Message]] = None
    
    def chat(
        self,
        messages: List[Message],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        self.call_count += 1
        self.last_messages = messages
        return ChatResponse(
            content=self.response_content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        )


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Mock(spec=Settings)


@pytest.fixture
def sample_prompt():
    """Sample rerank prompt template."""
    return """You are an AI assistant specialized in evaluating relevance.
Given a query and passages, score each passage on relevance (0-3).
Output JSON format with passage_id and score."""


@pytest.fixture
def sample_candidates():
    """Sample candidate list for reranking."""
    return [
        {"id": "chunk_1", "text": "Python is a programming language.", "score": 0.8},
        {"id": "chunk_2", "text": "Machine learning uses neural networks.", "score": 0.75},
        {"id": "chunk_3", "text": "RAG combines retrieval and generation.", "score": 0.9},
    ]


class TestLLMRerankerInit:
    """Test LLMReranker initialization."""
    
    def test_init_with_defaults(self, mock_settings, sample_prompt, tmp_path):
        """Test initialization with default parameters."""
        # Create temp prompt file
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        assert reranker.settings == mock_settings
        assert reranker.llm == mock_llm
        assert reranker.prompt_template == sample_prompt
    
    def test_init_missing_prompt_file(self, mock_settings):
        """Test initialization fails with missing prompt file."""
        mock_llm = MockLLM()
        
        with pytest.raises(LLMRerankError, match="Failed to load rerank prompt"):
            LLMReranker(
                settings=mock_settings,
                prompt_path="/nonexistent/path/rerank.txt",
                llm=mock_llm
            )
    
    def test_load_prompt_template(self, mock_settings, sample_prompt, tmp_path):
        """Test prompt template loading."""
        prompt_file = tmp_path / "custom_prompt.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        assert sample_prompt in reranker.prompt_template


class TestLLMRerankerPromptBuilding:
    """Test prompt building functionality."""
    
    def test_build_rerank_prompt(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test prompt construction with query and candidates."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        query = "What is RAG?"
        prompt = reranker._build_rerank_prompt(query, sample_candidates)
        
        # Check that prompt contains expected elements
        assert sample_prompt in prompt
        assert query in prompt
        assert "chunk_1" in prompt
        assert "chunk_2" in prompt
        assert "chunk_3" in prompt
        assert "Python is a programming language" in prompt
    
    def test_build_prompt_with_missing_text(self, mock_settings, sample_prompt, tmp_path):
        """Test prompt building with candidates missing text field."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        candidates = [
            {"id": "chunk_1", "content": "Alternative field name"},
            {"id": "chunk_2"},  # Missing both text and content
        ]
        
        query = "test query"
        prompt = reranker._build_rerank_prompt(query, candidates)
        
        assert "Alternative field name" in prompt
        assert "chunk_1" in prompt
        assert "chunk_2" in prompt


class TestLLMRerankerResponseParsing:
    """Test LLM response parsing and validation."""
    
    def test_parse_valid_json_response(self, mock_settings, sample_prompt, tmp_path):
        """Test parsing valid JSON response."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        response = json.dumps([
            {"passage_id": "chunk_1", "score": 2, "reasoning": "Relevant"},
            {"passage_id": "chunk_2", "score": 1, "reasoning": "Partial match"},
        ])
        
        parsed = reranker._parse_llm_response(response)
        
        assert len(parsed) == 2
        assert parsed[0]["passage_id"] == "chunk_1"
        assert parsed[0]["score"] == 2
        assert parsed[1]["passage_id"] == "chunk_2"
        assert parsed[1]["score"] == 1
    
    def test_parse_json_with_markdown_wrapper(self, mock_settings, sample_prompt, tmp_path):
        """Test parsing JSON wrapped in markdown code blocks."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        response = """```json
[
    {"passage_id": "chunk_1", "score": 3},
    {"passage_id": "chunk_2", "score": 1}
]
```"""
        
        parsed = reranker._parse_llm_response(response)
        
        assert len(parsed) == 2
        assert parsed[0]["score"] == 3
    
    def test_parse_invalid_json(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for invalid JSON."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        with pytest.raises(LLMRerankError, match="not valid JSON"):
            reranker._parse_llm_response("This is not JSON")
    
    def test_parse_non_array_response(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for non-array response."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        with pytest.raises(LLMRerankError, match="Expected JSON array"):
            reranker._parse_llm_response('{"key": "value"}')
    
    def test_parse_missing_passage_id(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for missing passage_id field."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        response = json.dumps([{"score": 2}])
        
        with pytest.raises(LLMRerankError, match="missing required field 'passage_id'"):
            reranker._parse_llm_response(response)
    
    def test_parse_missing_score(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for missing score field."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        response = json.dumps([{"passage_id": "chunk_1"}])
        
        with pytest.raises(LLMRerankError, match="missing required field 'score'"):
            reranker._parse_llm_response(response)
    
    def test_parse_non_numeric_score(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for non-numeric score."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        response = json.dumps([{"passage_id": "chunk_1", "score": "high"}])
        
        with pytest.raises(LLMRerankError, match="score must be numeric"):
            reranker._parse_llm_response(response)


class TestLLMRerankerReranking:
    """Test end-to-end reranking functionality."""
    
    def test_rerank_success(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test successful reranking with valid LLM response."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        # Mock LLM returns reranked scores
        llm_response = json.dumps([
            {"passage_id": "chunk_3", "score": 3, "reasoning": "Most relevant"},
            {"passage_id": "chunk_1", "score": 2, "reasoning": "Partially relevant"},
            {"passage_id": "chunk_2", "score": 1, "reasoning": "Less relevant"},
        ])
        
        mock_llm = MockLLM(response_content=llm_response)
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        query = "What is RAG?"
        reranked = reranker.rerank(query, sample_candidates)
        
        # Check order (should be chunk_3, chunk_1, chunk_2 by score)
        assert len(reranked) == 3
        assert reranked[0]["id"] == "chunk_3"
        assert reranked[0]["rerank_score"] == 3
        assert reranked[1]["id"] == "chunk_1"
        assert reranked[1]["rerank_score"] == 2
        assert reranked[2]["id"] == "chunk_2"
        assert reranked[2]["rerank_score"] == 1
        
        # Check LLM was called
        assert mock_llm.call_count == 1
    
    def test_rerank_single_candidate(self, mock_settings, sample_prompt, tmp_path):
        """Test reranking with single candidate (no-op)."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        candidates = [{"id": "chunk_1", "text": "Only one", "score": 0.9}]
        query = "test"
        
        reranked = reranker.rerank(query, candidates)
        
        # Should return as-is without calling LLM
        assert len(reranked) == 1
        assert reranked[0]["id"] == "chunk_1"
        assert mock_llm.call_count == 0
    
    def test_rerank_invalid_query(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test error handling for invalid query."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            reranker.rerank("   ", sample_candidates)
    
    def test_rerank_invalid_candidates(self, mock_settings, sample_prompt, tmp_path):
        """Test error handling for invalid candidates."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM()
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        with pytest.raises(ValueError, match="Candidates list cannot be empty"):
            reranker.rerank("test query", [])
    
    def test_rerank_llm_failure(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test error handling when LLM call fails."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        # Mock LLM that raises exception
        class FailingLLM(BaseLLM):
            def chat(self, messages, trace=None, **kwargs):
                raise RuntimeError("LLM service unavailable")
        
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=FailingLLM()
        )
        
        with pytest.raises(LLMRerankError, match="LLM call failed"):
            reranker.rerank("test query", sample_candidates)
    
    def test_rerank_malformed_response(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test error handling for malformed LLM response."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        mock_llm = MockLLM(response_content="This is not valid JSON")
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        with pytest.raises(LLMRerankError, match="not valid JSON"):
            reranker.rerank("test query", sample_candidates)
    
    def test_rerank_preserves_original_fields(self, mock_settings, sample_prompt, tmp_path):
        """Test that reranking preserves original candidate fields."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        llm_response = json.dumps([
            {"passage_id": "chunk_1", "score": 3},
            {"passage_id": "chunk_2", "score": 2},
        ])
        
        mock_llm = MockLLM(response_content=llm_response)
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        candidates = [
            {"id": "chunk_1", "text": "Text 1", "score": 0.8, "metadata": {"key": "value"}},
            {"id": "chunk_2", "text": "Text 2", "score": 0.9, "metadata": {"key": "value2"}},
        ]
        
        reranked = reranker.rerank("test", candidates)
        
        # Check original fields preserved
        assert reranked[0]["text"] == "Text 1"
        assert reranked[0]["score"] == 0.8
        assert reranked[0]["metadata"]["key"] == "value"
        assert reranked[0]["rerank_score"] == 3
        
        assert reranked[1]["text"] == "Text 2"
        assert reranked[1]["score"] == 0.9
        assert reranked[1]["metadata"]["key"] == "value2"
        assert reranked[1]["rerank_score"] == 2


class TestLLMRerankerIntegration:
    """Integration tests for LLM Reranker."""
    
    def test_rerank_with_trace_context(self, mock_settings, sample_prompt, sample_candidates, tmp_path):
        """Test reranking with trace context passed through."""
        prompt_file = tmp_path / "rerank.txt"
        prompt_file.write_text(sample_prompt)
        
        llm_response = json.dumps([
            {"passage_id": "chunk_1", "score": 3},
            {"passage_id": "chunk_2", "score": 2},
        ])
        
        mock_llm = MockLLM(response_content=llm_response)
        reranker = LLMReranker(
            settings=mock_settings,
            prompt_path=str(prompt_file),
            llm=mock_llm
        )
        
        mock_trace = Mock()
        candidates = [
            {"id": "chunk_1", "text": "Test 1"},
            {"id": "chunk_2", "text": "Test 2"}
        ]
        
        reranker.rerank("query", candidates, trace=mock_trace)
        
        # Verify LLM was called with multiple candidates
        assert mock_llm.call_count == 1
