"""Unit tests for Reranker Factory and Base Reranker.

Test Coverage:
- Factory pattern: provider registration, creation, and routing
- Configuration-driven instantiation
- Error handling for unknown/missing providers
- Validation logic in BaseReranker
- NoneReranker fallback behavior
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.libs.reranker.base_reranker import BaseReranker, NoneReranker
from src.libs.reranker.reranker_factory import RerankerFactory


class FakeReranker(BaseReranker):
    """Fake reranker implementation for testing.
    
    Sorts candidates by descending score for deterministic behavior.
    """
    
    def __init__(self, settings: Any = None, **kwargs: Any) -> None:
        self.settings = settings
        self.kwargs = kwargs
        self.call_count = 0
    
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        self.validate_query(query)
        self.validate_candidates(candidates)
        self.call_count += 1
        return sorted(candidates, key=lambda item: item.get("score", 0.0), reverse=True)


class TestBaseReranker:
    """Tests for BaseReranker validation helpers."""
    
    def test_validate_query_success(self):
        reranker = FakeReranker()
        reranker.validate_query("hello")
    
    def test_validate_query_empty(self):
        reranker = FakeReranker()
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.validate_query("   ")
    
    def test_validate_query_non_string(self):
        reranker = FakeReranker()
        with pytest.raises(ValueError, match="must be a string"):
            reranker.validate_query(123)  # type: ignore[arg-type]
    
    def test_validate_candidates_success(self):
        reranker = FakeReranker()
        reranker.validate_candidates([{"id": "1"}, {"id": "2"}])
    
    def test_validate_candidates_empty(self):
        reranker = FakeReranker()
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.validate_candidates([])
    
    def test_validate_candidates_non_list(self):
        reranker = FakeReranker()
        with pytest.raises(ValueError, match="must be a list"):
            reranker.validate_candidates("invalid")  # type: ignore[arg-type]
    
    def test_validate_candidates_non_dict(self):
        reranker = FakeReranker()
        with pytest.raises(ValueError, match="not a dict"):
            reranker.validate_candidates([{"id": "ok"}, "bad"])  # type: ignore[list-item]


class TestNoneReranker:
    """Tests for NoneReranker behavior."""
    
    def test_rerank_preserves_order(self):
        reranker = NoneReranker()
        candidates = [
            {"id": "a", "score": 0.2},
            {"id": "b", "score": 0.9},
            {"id": "c", "score": 0.5},
        ]
        result = reranker.rerank("query", candidates)
        assert result == candidates
        assert result is not candidates


class TestRerankerFactory:
    """Tests for RerankerFactory."""
    
    def setup_method(self) -> None:
        RerankerFactory._PROVIDERS.clear()
    
    def test_register_provider_success(self):
        RerankerFactory.register_provider("fake", FakeReranker)
        assert "fake" in RerankerFactory._PROVIDERS
        assert RerankerFactory._PROVIDERS["fake"] == FakeReranker
    
    def test_register_provider_case_insensitive(self):
        RerankerFactory.register_provider("FAKE", FakeReranker)
        assert "fake" in RerankerFactory._PROVIDERS
    
    def test_register_provider_invalid_class(self):
        class NotAReranker:
            pass
        
        with pytest.raises(ValueError, match="must inherit from BaseReranker"):
            RerankerFactory.register_provider("invalid", NotAReranker)  # type: ignore[arg-type]
    
    def test_list_providers_empty(self):
        assert RerankerFactory.list_providers() == []
    
    def test_list_providers_sorted(self):
        RerankerFactory.register_provider("zebra", FakeReranker)
        RerankerFactory.register_provider("alpha", FakeReranker)
        RerankerFactory.register_provider("beta", FakeReranker)
        assert RerankerFactory.list_providers() == ["alpha", "beta", "zebra"]
    
    def test_create_success(self):
        RerankerFactory.register_provider("fake", FakeReranker)
        settings = MagicMock()
        settings.rerank = MagicMock()
        settings.rerank.enabled = True
        settings.rerank.provider = "fake"
        
        reranker = RerankerFactory.create(settings)
        assert isinstance(reranker, FakeReranker)
        assert reranker.settings == settings
    
    def test_create_case_insensitive(self):
        RerankerFactory.register_provider("fake", FakeReranker)
        settings = MagicMock()
        settings.rerank = MagicMock()
        settings.rerank.enabled = True
        settings.rerank.provider = "FAKE"
        
        reranker = RerankerFactory.create(settings)
        assert isinstance(reranker, FakeReranker)
    
    def test_create_disabled_returns_none(self):
        settings = MagicMock()
        settings.rerank = MagicMock()
        settings.rerank.enabled = False
        settings.rerank.provider = "fake"
        
        reranker = RerankerFactory.create(settings)
        assert isinstance(reranker, NoneReranker)
    
    def test_create_provider_none_returns_none(self):
        settings = MagicMock()
        settings.rerank = MagicMock()
        settings.rerank.enabled = True
        settings.rerank.provider = "none"
        
        reranker = RerankerFactory.create(settings)
        assert isinstance(reranker, NoneReranker)
    
    def test_create_unknown_provider(self):
        settings = MagicMock()
        settings.rerank = MagicMock()
        settings.rerank.enabled = True
        settings.rerank.provider = "unknown"
        
        with pytest.raises(ValueError) as exc_info:
            RerankerFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "Unsupported Reranker provider: 'unknown'" in error_message
        assert "Available providers" in error_message
    
    def test_create_missing_provider_config(self):
        settings = MagicMock()
        settings.rerank = None
        
        with pytest.raises(ValueError) as exc_info:
            RerankerFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "settings.rerank.provider" in error_message


# ── Boundary / Contract tests (I4) ──────────────────────────────────

class TestRerankerContractBoundary:
    """Boundary tests for BaseReranker contract."""

    def test_none_reranker_single_candidate(self):
        """NoneReranker should handle single-element list."""
        reranker = NoneReranker()
        result = reranker.rerank("q", [{"id": "a", "score": 0.9}])
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_none_reranker_validates_inputs(self):
        """NoneReranker should still validate query and candidates."""
        reranker = NoneReranker()
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.rerank("", [{"id": "a"}])
        with pytest.raises(ValueError, match="cannot be empty"):
            reranker.rerank("q", [])

    def test_fake_reranker_sorts_by_score(self):
        """FakeReranker should sort candidates by score descending."""
        reranker = FakeReranker()
        candidates = [
            {"id": "low", "score": 0.1},
            {"id": "high", "score": 0.9},
            {"id": "mid", "score": 0.5},
        ]
        result = reranker.rerank("query", candidates)
        assert [r["id"] for r in result] == ["high", "mid", "low"]

    def test_reranker_returns_new_list(self):
        """Reranker should return a new list, not mutate the input."""
        reranker = NoneReranker()
        candidates = [{"id": "a"}, {"id": "b"}]
        result = reranker.rerank("q", candidates)
        assert result is not candidates

    def test_validate_candidates_with_extra_fields(self):
        """Candidates with extra metadata fields should be accepted."""
        reranker = FakeReranker()
        candidates = [
            {"id": "a", "score": 0.5, "text": "hello", "metadata": {"p": 1}},
        ]
        reranker.validate_candidates(candidates)

    def test_register_duplicate_provider(self):
        """Re-registering same name should overwrite silently."""
        RerankerFactory._PROVIDERS.clear()
        RerankerFactory.register_provider("fake", FakeReranker)
        RerankerFactory.register_provider("fake", NoneReranker)
        assert RerankerFactory._PROVIDERS["fake"] is NoneReranker
