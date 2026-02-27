"""Unit tests for Ollama LLM implementation.

This module tests the Ollama LLM provider using mocked HTTP responses
to avoid requiring a running Ollama instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.libs.llm import LLMFactory, Message, OllamaLLM, OllamaLLMError


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@dataclass
class MockLLMSettings:
    """Mock settings for LLM testing."""
    
    provider: str = "ollama"
    model: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass
class MockSettings:
    """Mock application settings."""
    
    llm: MockLLMSettings = None
    
    def __post_init__(self):
        if self.llm is None:
            self.llm = MockLLMSettings()


def make_ollama_response(
    content: str = "Hello! I'm running locally via Ollama.",
    model: str = "llama3",
    status_code: int = 200,
    prompt_eval_count: int = 15,
    eval_count: int = 25,
) -> MagicMock:
    """Create a mock Ollama HTTP response.
    
    Ollama's /api/chat endpoint returns a different format than OpenAI:
    - Uses 'message' object with 'role' and 'content'
    - Uses 'eval_count' and 'prompt_eval_count' for token counts
    """
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "model": model,
        "created_at": "2026-01-28T12:00:00.000000Z",
        "message": {
            "role": "assistant",
            "content": content,
        },
        "done": True,
        "done_reason": "stop",
        "total_duration": 1234567890,
        "load_duration": 12345678,
        "prompt_eval_count": prompt_eval_count,
        "prompt_eval_duration": 123456789,
        "eval_count": eval_count,
        "eval_duration": 987654321,
    }
    return response


def make_error_response(
    status_code: int = 400,
    error_message: str = "model not found",
) -> MagicMock:
    """Create a mock error HTTP response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"error": error_message}
    response.text = f"Error: {error_message}"
    return response


# -----------------------------------------------------------------------------
# Factory Registration Tests
# -----------------------------------------------------------------------------


class TestOllamaFactoryRegistration:
    """Tests for Ollama provider factory registration."""
    
    @pytest.fixture(autouse=True)
    def ensure_provider_registered(self):
        """Ensure Ollama provider is registered before each test."""
        if "ollama" not in LLMFactory._PROVIDERS:
            LLMFactory.register_provider("ollama", OllamaLLM)
        yield
    
    def test_ollama_registered(self):
        """Ollama provider should be registered with factory."""
        assert "ollama" in LLMFactory.list_providers()
    
    def test_factory_creates_ollama(self):
        """Factory should create OllamaLLM instance when provider=ollama."""
        settings = MockSettings(llm=MockLLMSettings(provider="ollama"))
        llm = LLMFactory.create(settings)
        assert isinstance(llm, OllamaLLM)
    
    def test_factory_creates_ollama_case_insensitive(self):
        """Factory should handle case-insensitive provider name."""
        settings = MockSettings(llm=MockLLMSettings(provider="OLLAMA"))
        llm = LLMFactory.create(settings)
        assert isinstance(llm, OllamaLLM)


# -----------------------------------------------------------------------------
# Initialization Tests
# -----------------------------------------------------------------------------


class TestOllamaInit:
    """Tests for OllamaLLM initialization."""
    
    def test_init_default_base_url(self):
        """Should use default localhost URL when none specified."""
        settings = MockSettings()
        llm = OllamaLLM(settings)
        assert llm.base_url == "http://localhost:11434"
    
    def test_init_custom_base_url(self):
        """Should use provided base URL."""
        settings = MockSettings()
        llm = OllamaLLM(settings, base_url="http://192.168.1.100:11434")
        assert llm.base_url == "http://192.168.1.100:11434"
    
    def test_init_base_url_from_env(self):
        """Should read base URL from environment variable."""
        settings = MockSettings()
        with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://remote:11434"}):
            llm = OllamaLLM(settings)
            assert llm.base_url == "http://remote:11434"
    
    def test_init_explicit_base_url_overrides_env(self):
        """Explicit base URL should override environment variable."""
        settings = MockSettings()
        with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://env:11434"}):
            llm = OllamaLLM(settings, base_url="http://explicit:11434")
            assert llm.base_url == "http://explicit:11434"
    
    def test_init_model_from_settings(self):
        """Should read model from settings."""
        settings = MockSettings(llm=MockLLMSettings(model="mistral"))
        llm = OllamaLLM(settings)
        assert llm.model == "mistral"
    
    def test_init_temperature_from_settings(self):
        """Should read temperature from settings."""
        settings = MockSettings(llm=MockLLMSettings(temperature=0.5))
        llm = OllamaLLM(settings)
        assert llm.default_temperature == 0.5
    
    def test_init_max_tokens_from_settings(self):
        """Should read max_tokens from settings."""
        settings = MockSettings(llm=MockLLMSettings(max_tokens=4096))
        llm = OllamaLLM(settings)
        assert llm.default_max_tokens == 4096
    
    def test_init_custom_timeout(self):
        """Should accept custom timeout."""
        settings = MockSettings()
        llm = OllamaLLM(settings, timeout=300.0)
        assert llm.timeout == 300.0
    
    def test_init_default_timeout(self):
        """Should use default timeout when none specified."""
        settings = MockSettings()
        llm = OllamaLLM(settings)
        assert llm.timeout == 120.0  # Longer default for local inference


# -----------------------------------------------------------------------------
# Chat Tests with Mocked HTTP
# -----------------------------------------------------------------------------


class TestOllamaChat:
    """Tests for OllamaLLM chat functionality with mocked HTTP."""
    
    @pytest.fixture
    def llm(self):
        """Create an OllamaLLM instance for testing."""
        settings = MockSettings()
        return OllamaLLM(settings)
    
    def test_chat_success(self, llm):
        """Should successfully process a chat request."""
        mock_response = make_ollama_response(content="Hello from Ollama!")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.content == "Hello from Ollama!"
            assert response.model == "llama3"
    
    def test_chat_returns_usage_stats(self, llm):
        """Should include usage statistics in response."""
        mock_response = make_ollama_response(
            prompt_eval_count=20,
            eval_count=50,
        )
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.usage is not None
            assert response.usage["prompt_tokens"] == 20
            assert response.usage["completion_tokens"] == 50
            assert response.usage["total_tokens"] == 70
    
    def test_chat_preserves_raw_response(self, llm):
        """Should preserve raw response for debugging."""
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.raw_response is not None
            assert "model" in response.raw_response
    
    def test_chat_with_system_message(self, llm):
        """Should handle system messages correctly."""
        mock_response = make_ollama_response(content="I understand the context.")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            messages = [
                Message(role="system", content="You are a helpful assistant."),
                Message(role="user", content="Hello"),
            ]
            response = llm.chat(messages)
            
            assert response.content == "I understand the context."
            
            # Verify API was called with both messages
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert len(payload["messages"]) == 2
            assert payload["messages"][0]["role"] == "system"
    
    def test_chat_with_conversation(self, llm):
        """Should handle multi-turn conversations."""
        mock_response = make_ollama_response(content="The capital is Paris.")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            messages = [
                Message(role="user", content="What is the capital of France?"),
                Message(role="assistant", content="Paris is the capital of France."),
                Message(role="user", content="Tell me more about it."),
            ]
            response = llm.chat(messages)
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert len(payload["messages"]) == 3
    
    def test_chat_with_temperature_override(self, llm):
        """Should allow temperature override in chat call."""
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            llm.chat([Message(role="user", content="Hello")], temperature=0.1)
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["options"]["temperature"] == 0.1
    
    def test_chat_with_max_tokens_override(self, llm):
        """Should allow max_tokens override in chat call."""
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            llm.chat([Message(role="user", content="Hello")], max_tokens=500)
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["options"]["num_predict"] == 500  # Ollama uses num_predict
    
    def test_chat_uses_stream_false(self, llm):
        """Should disable streaming for synchronous response."""
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            llm.chat([Message(role="user", content="Hello")])
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["stream"] is False


# -----------------------------------------------------------------------------
# Validation Tests
# -----------------------------------------------------------------------------


class TestOllamaValidation:
    """Tests for input validation."""
    
    @pytest.fixture
    def llm(self):
        """Create an OllamaLLM instance for testing."""
        settings = MockSettings()
        return OllamaLLM(settings)
    
    def test_chat_empty_messages_raises(self, llm):
        """Should raise ValueError for empty messages list."""
        with pytest.raises(ValueError, match="Messages list cannot be empty"):
            llm.chat([])
    
    def test_chat_invalid_role_raises(self, llm):
        """Should raise ValueError for invalid message role."""
        with pytest.raises(ValueError, match="invalid role"):
            llm.chat([Message(role="invalid", content="Hello")])
    
    def test_chat_empty_content_raises(self, llm):
        """Should raise ValueError for empty message content."""
        with pytest.raises(ValueError, match="empty content"):
            llm.chat([Message(role="user", content="")])


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


class TestOllamaErrorHandling:
    """Tests for error handling scenarios."""
    
    @pytest.fixture
    def llm(self):
        """Create an OllamaLLM instance for testing."""
        settings = MockSettings()
        return OllamaLLM(settings)
    
    def test_api_error_response(self, llm):
        """Should raise OllamaLLMError on API error response."""
        mock_response = make_error_response(status_code=404, error_message="model not found")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            assert "HTTP 404" in str(exc_info.value)
            assert "model not found" in str(exc_info.value)
    
    def test_timeout_error(self, llm):
        """Should raise OllamaLLMError on timeout with helpful message."""
        import httpx
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = httpx.TimeoutException("timeout")
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            assert "timed out" in str(exc_info.value).lower()
            assert "120" in str(exc_info.value)  # Default timeout value
    
    def test_connection_error(self, llm):
        """Should raise OllamaLLMError on connection failure with helpful message."""
        import httpx
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = httpx.ConnectError("Connection refused")
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            error_msg = str(exc_info.value)
            assert "Connection failed" in error_msg
            assert "ollama serve" in error_msg.lower()  # Helpful hint
    
    def test_request_error(self, llm):
        """Should raise OllamaLLMError on general request failure."""
        import httpx
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = httpx.RequestError("Network error")
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            assert "[Ollama]" in str(exc_info.value)
    
    def test_error_does_not_leak_sensitive_info(self, llm):
        """Error messages should not expose internal URLs or config details."""
        mock_response = make_error_response(status_code=500, error_message="internal error")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            error_msg = str(exc_info.value)
            # Should not contain the full internal URL
            assert "localhost:11434" not in error_msg
    
    def test_unexpected_response_format(self, llm):
        """Should handle unexpected response format gracefully."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"unexpected": "format"}
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = response
            
            with pytest.raises(OllamaLLMError) as exc_info:
                llm.chat([Message(role="user", content="Hello")])
            
            assert "Unexpected response format" in str(exc_info.value)


# -----------------------------------------------------------------------------
# API URL Construction Tests
# -----------------------------------------------------------------------------


class TestOllamaAPIEndpoint:
    """Tests for API endpoint URL construction."""
    
    def test_api_url_construction(self):
        """Should construct correct API URL."""
        settings = MockSettings()
        llm = OllamaLLM(settings, base_url="http://localhost:11434")
        
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            llm.chat([Message(role="user", content="Hello")])
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            assert call_args.args[0] == "http://localhost:11434/api/chat"
    
    def test_api_url_strips_trailing_slash(self):
        """Should handle base URL with trailing slash."""
        settings = MockSettings()
        llm = OllamaLLM(settings, base_url="http://localhost:11434/")
        
        mock_response = make_ollama_response()
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            llm.chat([Message(role="user", content="Hello")])
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            assert call_args.args[0] == "http://localhost:11434/api/chat"


# -----------------------------------------------------------------------------
# Model Override Tests
# -----------------------------------------------------------------------------


class TestOllamaModelOverride:
    """Tests for model override functionality."""
    
    def test_model_override_in_chat(self):
        """Should allow model override per chat call."""
        settings = MockSettings(llm=MockLLMSettings(model="llama3"))
        llm = OllamaLLM(settings)
        
        mock_response = make_ollama_response(model="mistral")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = llm.chat(
                [Message(role="user", content="Hello")],
                model="mistral",
            )
            
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["model"] == "mistral"
            assert response.model == "mistral"
