"""Unit tests for Embedding Factory and Base Embedding.

Test Coverage:
- Factory pattern: provider registration, creation, and routing
- Configuration-driven instantiation
- Error handling for unknown/missing providers
- Validation logic in BaseEmbedding
"""

from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from src.libs.embedding.base_embedding import BaseEmbedding
from src.libs.embedding.embedding_factory import EmbeddingFactory


class FakeEmbedding(BaseEmbedding):
    """Fake embedding provider for testing.
    
    Returns deterministic fake vectors for reproducible testing.
    """
    
    def __init__(self, settings: Any = None, dimension: int = 384, **kwargs: Any):
        """Initialize fake embedding provider.
        
        Args:
            settings: Optional settings (unused in fake).
            dimension: Vector dimension to return.
            **kwargs: Additional parameters (unused).
        """
        self.settings = settings
        self.dimension = dimension
        self.call_count = 0
    
    def embed(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[List[float]]:
        """Generate fake embeddings."""
        self.validate_texts(texts)
        self.call_count += 1
        
        # Return deterministic fake vectors
        return [[float(i + j) for j in range(self.dimension)] for i in range(len(texts))]
    
    def get_dimension(self) -> int:
        """Return configured dimension."""
        return self.dimension


class TestBaseEmbedding:
    """Tests for BaseEmbedding abstract class."""
    
    def test_validate_texts_success(self):
        """Valid text list should pass validation."""
        embedding = FakeEmbedding()
        # Should not raise
        embedding.validate_texts(["hello", "world"])
    
    def test_validate_texts_empty_list(self):
        """Empty list should raise ValueError."""
        embedding = FakeEmbedding()
        with pytest.raises(ValueError, match="cannot be empty"):
            embedding.validate_texts([])
    
    def test_validate_texts_non_string(self):
        """Non-string entries should raise ValueError."""
        embedding = FakeEmbedding()
        with pytest.raises(ValueError, match="not a string"):
            embedding.validate_texts(["valid", 123, "text"])  # type: ignore
    
    def test_validate_texts_empty_string(self):
        """Empty or whitespace-only strings should raise ValueError."""
        embedding = FakeEmbedding()
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            embedding.validate_texts(["valid", "   ", "text"])
    
    def test_get_dimension_implemented(self):
        """FakeEmbedding should return configured dimension."""
        embedding = FakeEmbedding(dimension=512)
        assert embedding.get_dimension() == 512
    
    def test_get_dimension_not_implemented(self):
        """BaseEmbedding without override should raise NotImplementedError."""
        
        class IncompleteEmbedding(BaseEmbedding):
            def embed(self, texts: List[str], trace: Optional[Any] = None, **kwargs: Any) -> List[List[float]]:
                return [[0.0]]
        
        incomplete = IncompleteEmbedding()
        with pytest.raises(NotImplementedError, match="must implement get_dimension"):
            incomplete.get_dimension()


class TestFakeEmbedding:
    """Tests for FakeEmbedding provider implementation."""
    
    def test_embed_single_text(self):
        """Embedding single text should return one vector."""
        embedding = FakeEmbedding(dimension=3)
        result = embedding.embed(["hello"])
        
        assert len(result) == 1
        assert len(result[0]) == 3
        assert result[0] == [0.0, 1.0, 2.0]
    
    def test_embed_multiple_texts(self):
        """Embedding multiple texts should return matching number of vectors."""
        embedding = FakeEmbedding(dimension=2)
        result = embedding.embed(["hello", "world", "test"])
        
        assert len(result) == 3
        assert result[0] == [0.0, 1.0]
        assert result[1] == [1.0, 2.0]
        assert result[2] == [2.0, 3.0]
    
    def test_embed_increments_call_count(self):
        """Each embed call should increment the counter."""
        embedding = FakeEmbedding()
        assert embedding.call_count == 0
        
        embedding.embed(["test1"])
        assert embedding.call_count == 1
        
        embedding.embed(["test2", "test3"])
        assert embedding.call_count == 2
    
    def test_embed_validates_input(self):
        """embed() should call validate_texts and raise on invalid input."""
        embedding = FakeEmbedding()
        
        with pytest.raises(ValueError, match="cannot be empty"):
            embedding.embed([])
        
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            embedding.embed(["  "])


class TestEmbeddingFactory:
    """Tests for EmbeddingFactory."""
    
    def setup_method(self):
        """Reset factory registry before each test."""
        EmbeddingFactory._PROVIDERS.clear()
    
    def test_register_provider_success(self):
        """Registering valid provider should succeed."""
        EmbeddingFactory.register_provider("fake", FakeEmbedding)
        assert "fake" in EmbeddingFactory._PROVIDERS
        assert EmbeddingFactory._PROVIDERS["fake"] == FakeEmbedding
    
    def test_register_provider_case_insensitive(self):
        """Provider names should be normalized to lowercase."""
        EmbeddingFactory.register_provider("OpenAI", FakeEmbedding)
        assert "openai" in EmbeddingFactory._PROVIDERS
    
    def test_register_provider_invalid_class(self):
        """Registering non-BaseEmbedding class should raise ValueError."""
        
        class NotAnEmbedding:
            pass
        
        with pytest.raises(ValueError, match="must inherit from BaseEmbedding"):
            EmbeddingFactory.register_provider("invalid", NotAnEmbedding)  # type: ignore
    
    def test_list_providers_empty(self):
        """list_providers should return empty list when no providers registered."""
        assert EmbeddingFactory.list_providers() == []
    
    def test_list_providers_sorted(self):
        """list_providers should return sorted provider names."""
        EmbeddingFactory.register_provider("zebra", FakeEmbedding)
        EmbeddingFactory.register_provider("alpha", FakeEmbedding)
        EmbeddingFactory.register_provider("beta", FakeEmbedding)
        
        providers = EmbeddingFactory.list_providers()
        assert providers == ["alpha", "beta", "zebra"]
    
    def test_create_success(self):
        """Creating registered provider should succeed."""
        EmbeddingFactory.register_provider("fake", FakeEmbedding)
        
        settings = MagicMock()
        settings.embedding.provider = "fake"
        
        embedding = EmbeddingFactory.create(settings)
        
        assert isinstance(embedding, FakeEmbedding)
        assert embedding.settings == settings
    
    def test_create_case_insensitive(self):
        """Provider lookup should be case-insensitive."""
        EmbeddingFactory.register_provider("fake", FakeEmbedding)
        
        settings = MagicMock()
        settings.embedding.provider = "FAKE"
        
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, FakeEmbedding)
    
    def test_create_with_overrides(self):
        """Factory should pass override kwargs to provider constructor."""
        EmbeddingFactory.register_provider("fake", FakeEmbedding)
        
        settings = MagicMock()
        settings.embedding.provider = "fake"
        
        embedding = EmbeddingFactory.create(settings, dimension=1024)
        assert embedding.dimension == 1024
    
    def test_create_unknown_provider(self):
        """Creating unregistered provider should raise clear error."""
        EmbeddingFactory.register_provider("fake", FakeEmbedding)
        
        settings = MagicMock()
        settings.embedding.provider = "unknown"
        
        with pytest.raises(ValueError) as exc_info:
            EmbeddingFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "Unsupported Embedding provider: 'unknown'" in error_message
        assert "Available providers:" in error_message
    
    def test_create_missing_provider_config(self):
        """Missing provider in settings should raise clear error."""
        settings = MagicMock()
        del settings.embedding  # Simulate missing config
        
        with pytest.raises(ValueError) as exc_info:
            EmbeddingFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "Missing required configuration" in error_message
        assert "settings.embedding.provider" in error_message
        assert "settings.yaml" in error_message
    
    def test_create_provider_instantiation_failure(self):
        """Provider constructor errors should be wrapped in RuntimeError."""
        
        class BrokenEmbedding(BaseEmbedding):
            def __init__(self, settings: Any, **kwargs: Any):
                raise ValueError("Intentional init error")
            
            def embed(self, texts: List[str], trace: Optional[Any] = None, **kwargs: Any) -> List[List[float]]:
                return [[0.0]]
        
        EmbeddingFactory.register_provider("broken", BrokenEmbedding)
        
        settings = MagicMock()
        settings.embedding.provider = "broken"
        
        with pytest.raises(RuntimeError) as exc_info:
            EmbeddingFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "Failed to instantiate Embedding provider 'broken'" in error_message
        assert "Intentional init error" in error_message
    
    def test_create_no_providers_registered(self):
        """Creating provider when registry is empty should show helpful message."""
        settings = MagicMock()
        settings.embedding.provider = "openai"
        
        with pytest.raises(ValueError) as exc_info:
            EmbeddingFactory.create(settings)
        
        error_message = str(exc_info.value)
        assert "Unsupported Embedding provider: 'openai'" in error_message
        assert "Available providers: none" in error_message
