"""Unit tests for Ollama Embedding provider implementation.

This test suite validates the Ollama Embedding implementation using
mocked HTTP responses to ensure reliable, fast, and offline testing.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.libs.embedding.ollama_embedding import OllamaEmbedding, OllamaEmbeddingError
from src.libs.embedding.embedding_factory import EmbeddingFactory


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_settings_ollama() -> Any:
    """Create mock settings for Ollama embedding."""
    settings = Mock()
    settings.embedding = Mock()
    settings.embedding.provider = "ollama"
    settings.embedding.model = "nomic-embed-text"
    settings.embedding.dimensions = 768
    return settings


@pytest.fixture
def mock_ollama_response() -> dict[str, Any]:
    """Create a mock Ollama embeddings response."""
    return {
        "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]  # Truncated for testing
    }


# =============================================================================
# Ollama Embedding Tests
# =============================================================================

class TestOllamaEmbedding:
    """Test suite for OllamaEmbedding implementation."""
    
    def test_initialization_default(self, mock_settings_ollama: Any) -> None:
        """Test successful initialization with default base_url."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        assert embedding.model == "nomic-embed-text"
        assert embedding.dimension == 768
        assert embedding.base_url == OllamaEmbedding.DEFAULT_BASE_URL
        assert embedding.timeout == OllamaEmbedding.DEFAULT_TIMEOUT
    
    def test_initialization_with_custom_base_url(self, mock_settings_ollama: Any) -> None:
        """Test initialization with custom base URL."""
        custom_url = "http://custom-ollama:11434"
        embedding = OllamaEmbedding(mock_settings_ollama, base_url=custom_url)
        
        assert embedding.base_url == custom_url
    
    def test_initialization_with_env_var(
        self, mock_settings_ollama: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test initialization with base URL from environment variable."""
        env_url = "http://env-ollama:11434"
        monkeypatch.setenv("OLLAMA_BASE_URL", env_url)
        
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        assert embedding.base_url == env_url
    
    def test_initialization_with_custom_timeout(self, mock_settings_ollama: Any) -> None:
        """Test initialization with custom timeout."""
        custom_timeout = 60.0
        embedding = OllamaEmbedding(mock_settings_ollama, timeout=custom_timeout)
        
        assert embedding.timeout == custom_timeout
    
    def test_initialization_without_dimensions_setting(self, mock_settings_ollama: Any) -> None:
        """Test initialization when dimensions not in settings (uses default)."""
        delattr(mock_settings_ollama.embedding, 'dimensions')
        
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        assert embedding.dimension == OllamaEmbedding.DEFAULT_DIMENSION
    
    @patch('httpx.Client')
    def test_embed_single_text(
        self, 
        mock_client_class: Mock,
        mock_settings_ollama: Any,
        mock_ollama_response: dict[str, Any],
    ) -> None:
        """Test embedding a single text."""
        # Setup mock HTTP response
        mock_response = Mock()
        mock_response.json.return_value = mock_ollama_response
        mock_response.raise_for_status.return_value = None
        
        # Setup mock client
        mock_client_class.return_value.__enter__.return_value.post.return_value = mock_response
        
        # Execute
        embedding = OllamaEmbedding(mock_settings_ollama)
        result = embedding.embed(["hello world"])
        
        # Assert
        assert len(result) == 1
        assert result[0] == mock_ollama_response["embedding"]
        
        # Verify API call
        mock_client_class.return_value.__enter__.return_value.post.assert_called_once()
        call_args = mock_client_class.return_value.__enter__.return_value.post.call_args
        assert call_args[0][0] == f"{embedding.base_url}/api/embeddings"
        assert call_args[1]["json"]["model"] == "nomic-embed-text"
        assert call_args[1]["json"]["prompt"] == "hello world"
    
    @patch('httpx.Client')
    def test_embed_multiple_texts(
        self, 
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test embedding multiple texts (batch processing)."""
        # Setup mock HTTP client with different embeddings for each text
        def create_response(url, json) -> Mock:
            response = Mock()
            # Return different embeddings based on prompt
            if "hello" in json["prompt"]:
                response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
            else:
                response.json.return_value = {"embedding": [0.4, 0.5, 0.6]}
            response.raise_for_status.return_value = None
            return response
        
        mock_client_class.return_value.__enter__.return_value.post.side_effect = create_response
        
        # Execute
        embedding = OllamaEmbedding(mock_settings_ollama)
        result = embedding.embed(["hello world", "test"])
        
        # Assert
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]
        
        # Verify API called twice (once per text)
        assert mock_client_class.return_value.__enter__.return_value.post.call_count == 2
    
    def test_embed_empty_list(self, mock_settings_ollama: Any) -> None:
        """Test that embedding empty list raises ValueError."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(ValueError, match="Texts list cannot be empty"):
            embedding.embed([])
    
    def test_embed_with_empty_string(self, mock_settings_ollama: Any) -> None:
        """Test that embedding empty string raises ValueError."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            embedding.embed([""])
    
    def test_embed_with_non_string(self, mock_settings_ollama: Any) -> None:
        """Test that embedding non-string raises ValueError."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(ValueError, match="not a string"):
            embedding.embed([123])  # type: ignore
    
    @patch('httpx.Client')
    def test_embed_http_status_error(
        self,
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test handling of HTTP status errors (4xx, 5xx)."""
        # Setup mock to raise HTTPStatusError
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = __import__('httpx').HTTPStatusError(
            "Not Found", request=Mock(), response=mock_response
        )
        
        mock_client_class.return_value.__enter__.return_value.post.return_value = mock_response
        
        # Execute and assert
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="Ollama API request failed with status 404"):
            embedding.embed(["test"])
    
    @patch('httpx.Client')
    def test_embed_connection_error(
        self,
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test handling of connection errors (server not reachable)."""
        # Setup mock to raise ConnectError
        mock_client_class.return_value.__enter__.return_value.post.side_effect = __import__('httpx').ConnectError(
            "Connection refused"
        )
        
        # Execute and assert
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="Failed to connect to Ollama server"):
            embedding.embed(["test"])
    
    @patch('httpx.Client')
    def test_embed_timeout_error(
        self,
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test handling of timeout errors."""
        # Setup mock to raise TimeoutException
        mock_client_class.return_value.__enter__.return_value.post.side_effect = __import__('httpx').TimeoutException(
            "Request timed out"
        )
        
        # Execute and assert
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="Ollama API request timed out"):
            embedding.embed(["test"])
    
    @patch('httpx.Client')
    def test_embed_missing_embedding_field(
        self,
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test handling of response missing 'embedding' field."""
        # Setup mock with invalid response format
        mock_response = Mock()
        mock_response.json.return_value = {"wrong_field": "data"}
        mock_response.raise_for_status.return_value = None
        
        mock_client_class.return_value.__enter__.return_value.post.return_value = mock_response
        
        # Execute and assert
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="Unexpected response format"):
            embedding.embed(["test"])
    
    @patch('httpx.Client')
    def test_embed_json_parse_error(
        self,
        mock_client_class: Mock,
        mock_settings_ollama: Any,
    ) -> None:
        """Test handling of JSON parsing errors."""
        # Setup mock with response that fails JSON parsing
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status.return_value = None
        
        mock_client_class.return_value.__enter__.return_value.post.return_value = mock_response
        
        # Execute and assert
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="Failed to parse Ollama API response"):
            embedding.embed(["test"])
    
    @patch.dict('sys.modules', {'httpx': None})
    def test_embed_missing_httpx_dependency(
        self,
        mock_settings_ollama: Any,
    ) -> None:
        """Test that missing httpx library raises clear error."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        with pytest.raises(OllamaEmbeddingError, match="httpx library is required"):
            embedding.embed(["test"])
    
    def test_get_dimension(self, mock_settings_ollama: Any) -> None:
        """Test get_dimension method returns configured dimension."""
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        assert embedding.get_dimension() == 768
    
    def test_get_dimension_default(self, mock_settings_ollama: Any) -> None:
        """Test get_dimension returns default when not configured."""
        delattr(mock_settings_ollama.embedding, 'dimensions')
        
        embedding = OllamaEmbedding(mock_settings_ollama)
        
        assert embedding.get_dimension() == OllamaEmbedding.DEFAULT_DIMENSION


# =============================================================================
# Factory Integration Tests
# =============================================================================

class TestOllamaEmbeddingFactoryIntegration:
    """Test suite for Ollama Embedding factory integration."""
    
    def test_factory_creates_ollama_embedding(self, mock_settings_ollama: Any) -> None:
        """Test that factory correctly creates Ollama embedding instance."""
        # Register Ollama provider
        EmbeddingFactory.register_provider("ollama", OllamaEmbedding)
        
        # Create via factory
        embedding = EmbeddingFactory.create(mock_settings_ollama)
        
        # Assert correct type
        assert isinstance(embedding, OllamaEmbedding)
        assert embedding.model == "nomic-embed-text"
    
    def test_factory_with_override_kwargs(self, mock_settings_ollama: Any) -> None:
        """Test factory with parameter overrides."""
        EmbeddingFactory.register_provider("ollama", OllamaEmbedding)
        
        # Create with overrides
        embedding = EmbeddingFactory.create(
            mock_settings_ollama,
            base_url="http://override:11434",
            timeout=30.0,
        )
        
        assert isinstance(embedding, OllamaEmbedding)
        assert embedding.base_url == "http://override:11434"
        assert embedding.timeout == 30.0
