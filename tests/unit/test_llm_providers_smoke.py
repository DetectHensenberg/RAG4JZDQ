"""Smoke tests for LLM provider implementations.

This module tests the OpenAI, Azure, and DeepSeek LLM providers
using mocked HTTP responses to avoid real API calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.libs.llm import (
    AzureLLM,
    AzureLLMError,
    BaseLLM,
    DeepSeekLLM,
    DeepSeekLLMError,
    LLMFactory,
    Message,
    OpenAILLM,
    OpenAILLMError,
)


# -----------------------------------------------------------------------------
# Module-level Setup: Ensure providers are registered
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def ensure_providers_registered():
    """Ensure all LLM providers are registered before each test.
    
    This is needed because other tests (e.g., test_llm_factory.py) may
    clear the provider registry during their setup.
    """
    # Re-register providers if they've been cleared
    if "openai" not in LLMFactory._PROVIDERS:
        LLMFactory.register_provider("openai", OpenAILLM)
    if "azure" not in LLMFactory._PROVIDERS:
        LLMFactory.register_provider("azure", AzureLLM)
    if "deepseek" not in LLMFactory._PROVIDERS:
        LLMFactory.register_provider("deepseek", DeepSeekLLM)
    yield


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


@dataclass
class MockLLMSettings:
    """Mock settings for LLM testing."""
    
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1024


@dataclass
class MockSettings:
    """Mock application settings."""
    
    llm: MockLLMSettings = None
    
    def __post_init__(self):
        if self.llm is None:
            self.llm = MockLLMSettings()


def make_mock_response(
    content: str = "Hello! How can I help you?",
    model: str = "gpt-4o-mini",
    status_code: int = 200,
) -> MagicMock:
    """Create a mock HTTP response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1704067200,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }
    return response


def make_error_response(
    status_code: int = 400,
    error_message: str = "Invalid request",
) -> MagicMock:
    """Create a mock error HTTP response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "error": {
            "message": error_message,
            "type": "invalid_request_error",
        }
    }
    response.text = f"Error: {error_message}"
    return response


# -----------------------------------------------------------------------------
# Factory Registration Tests
# -----------------------------------------------------------------------------


class TestLLMFactoryRegistration:
    """Tests for LLM factory provider registration."""
    
    def test_openai_registered(self):
        """OpenAI provider should be registered."""
        assert "openai" in LLMFactory.list_providers()
    
    def test_azure_registered(self):
        """Azure provider should be registered."""
        assert "azure" in LLMFactory.list_providers()
    
    def test_deepseek_registered(self):
        """DeepSeek provider should be registered."""
        assert "deepseek" in LLMFactory.list_providers()
    
    def test_factory_creates_openai(self):
        """Factory should create OpenAI instance when provider=openai."""
        settings = MockSettings(llm=MockLLMSettings(provider="openai"))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            llm = LLMFactory.create(settings)
            assert isinstance(llm, OpenAILLM)
    
    def test_factory_creates_azure(self):
        """Factory should create Azure instance when provider=azure."""
        settings = MockSettings(llm=MockLLMSettings(provider="azure"))
        env_vars = {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        }
        with patch.dict("os.environ", env_vars):
            llm = LLMFactory.create(settings)
            assert isinstance(llm, AzureLLM)
    
    def test_factory_creates_deepseek(self):
        """Factory should create DeepSeek instance when provider=deepseek."""
        settings = MockSettings(llm=MockLLMSettings(provider="deepseek"))
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            llm = LLMFactory.create(settings)
            assert isinstance(llm, DeepSeekLLM)
    
    def test_factory_unknown_provider_error(self):
        """Factory should raise error for unknown provider."""
        settings = MockSettings(llm=MockLLMSettings(provider="unknown"))
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMFactory.create(settings)


# -----------------------------------------------------------------------------
# OpenAI LLM Tests
# -----------------------------------------------------------------------------


class TestOpenAILLM:
    """Tests for OpenAI LLM implementation."""
    
    def test_init_with_api_key(self):
        """Should initialize with provided API key."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key")
        assert llm.api_key == "test-key"
        assert llm.model == "gpt-4o-mini"
    
    def test_init_with_env_var(self):
        """Should initialize with API key from environment."""
        settings = MockSettings()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            llm = OpenAILLM(settings)
            assert llm.api_key == "env-key"
    
    def test_init_missing_api_key(self):
        """Should raise error when API key is missing."""
        settings = MockSettings()
        with patch.dict("os.environ", {}, clear=True):
            # Ensure OPENAI_API_KEY is not in environment
            import os
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            with pytest.raises(ValueError, match="API key not provided"):
                OpenAILLM(settings)
    
    def test_custom_base_url(self):
        """Should use custom base URL when provided."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key", base_url="https://custom.api.com")
        assert llm.base_url == "https://custom.api.com"
    
    def test_chat_success(self):
        """Should return ChatResponse on successful API call."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_mock_response("Test response", "gpt-4o-mini")
            )
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.content == "Test response"
            assert response.model == "gpt-4o-mini"
            assert response.usage["total_tokens"] == 30
    
    def test_chat_empty_messages_error(self):
        """Should raise ValueError for empty messages list."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key")
        
        with pytest.raises(ValueError, match="cannot be empty"):
            llm.chat([])
    
    def test_chat_invalid_role_error(self):
        """Should raise ValueError for invalid message role."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key")
        
        with pytest.raises(ValueError, match="invalid role"):
            llm.chat([Message(role="invalid", content="Hello")])
    
    def test_chat_api_error(self):
        """Should raise OpenAILLMError on API error."""
        settings = MockSettings()
        llm = OpenAILLM(settings, api_key="test-key")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_error_response(400, "Bad request")
            )
            
            with pytest.raises(OpenAILLMError, match="API error"):
                llm.chat([Message(role="user", content="Hello")])


# -----------------------------------------------------------------------------
# Azure LLM Tests
# -----------------------------------------------------------------------------


class TestAzureLLM:
    """Tests for Azure OpenAI LLM implementation."""
    
    def test_init_with_credentials(self):
        """Should initialize with provided credentials."""
        settings = MockSettings()
        llm = AzureLLM(
            settings,
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
        )
        assert llm.api_key == "test-key"
        assert llm.endpoint == "https://test.openai.azure.com"
    
    def test_init_with_env_vars(self):
        """Should initialize with credentials from environment."""
        settings = MockSettings()
        env_vars = {
            "AZURE_OPENAI_API_KEY": "env-key",
            "AZURE_OPENAI_ENDPOINT": "https://env.openai.azure.com",
        }
        with patch.dict("os.environ", env_vars):
            llm = AzureLLM(settings)
            assert llm.api_key == "env-key"
            assert llm.endpoint == "https://env.openai.azure.com"
    
    def test_init_missing_api_key(self):
        """Should raise error when API key is missing."""
        settings = MockSettings()
        with patch.dict("os.environ", {"AZURE_OPENAI_ENDPOINT": "https://test.com"}):
            with pytest.raises(ValueError, match="API key not provided"):
                AzureLLM(settings)
    
    def test_init_missing_endpoint(self):
        """Should raise error when endpoint is missing."""
        settings = MockSettings()
        with patch.dict("os.environ", {"AZURE_OPENAI_API_KEY": "test-key"}):
            with pytest.raises(ValueError, match="endpoint not provided"):
                AzureLLM(settings)
    
    def test_chat_success(self):
        """Should return ChatResponse on successful API call."""
        settings = MockSettings()
        llm = AzureLLM(
            settings,
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
        )
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_mock_response("Azure response", "gpt-4o-mini")
            )
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.content == "Azure response"
            assert response.usage["total_tokens"] == 30
    
    def test_chat_api_error(self):
        """Should raise AzureLLMError on API error."""
        settings = MockSettings()
        llm = AzureLLM(
            settings,
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
        )
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_error_response(401, "Unauthorized")
            )
            
            with pytest.raises(AzureLLMError, match="API error"):
                llm.chat([Message(role="user", content="Hello")])


# -----------------------------------------------------------------------------
# DeepSeek LLM Tests
# -----------------------------------------------------------------------------


class TestDeepSeekLLM:
    """Tests for DeepSeek LLM implementation."""
    
    def test_init_with_api_key(self):
        """Should initialize with provided API key."""
        settings = MockSettings()
        llm = DeepSeekLLM(settings, api_key="test-key")
        assert llm.api_key == "test-key"
        assert llm.base_url == "https://api.deepseek.com"
    
    def test_init_with_env_var(self):
        """Should initialize with API key from environment."""
        settings = MockSettings()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "env-key"}):
            llm = DeepSeekLLM(settings)
            assert llm.api_key == "env-key"
    
    def test_init_missing_api_key(self):
        """Should raise error when API key is missing."""
        settings = MockSettings()
        with patch.dict("os.environ", {}, clear=True):
            import os
            if "DEEPSEEK_API_KEY" in os.environ:
                del os.environ["DEEPSEEK_API_KEY"]
            with pytest.raises(ValueError, match="API key not provided"):
                DeepSeekLLM(settings)
    
    def test_custom_base_url(self):
        """Should use custom base URL when provided."""
        settings = MockSettings()
        llm = DeepSeekLLM(settings, api_key="test-key", base_url="https://custom.deepseek.com")
        assert llm.base_url == "https://custom.deepseek.com"
    
    def test_chat_success(self):
        """Should return ChatResponse on successful API call."""
        settings = MockSettings()
        llm = DeepSeekLLM(settings, api_key="test-key")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_mock_response("DeepSeek response", "deepseek-chat")
            )
            
            response = llm.chat([Message(role="user", content="Hello")])
            
            assert response.content == "DeepSeek response"
            assert response.model == "deepseek-chat"
    
    def test_chat_api_error(self):
        """Should raise DeepSeekLLMError on API error."""
        settings = MockSettings()
        llm = DeepSeekLLM(settings, api_key="test-key")
        
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                make_error_response(500, "Internal server error")
            )
            
            with pytest.raises(DeepSeekLLMError, match="API error"):
                llm.chat([Message(role="user", content="Hello")])


# -----------------------------------------------------------------------------
# Message Validation Tests
# -----------------------------------------------------------------------------


class TestMessageValidation:
    """Tests for message validation across all providers."""
    
    @pytest.mark.parametrize("llm_class,api_key_env", [
        (OpenAILLM, "OPENAI_API_KEY"),
        (DeepSeekLLM, "DEEPSEEK_API_KEY"),
    ])
    def test_empty_content_validation(self, llm_class, api_key_env):
        """Should reject messages with empty content."""
        settings = MockSettings()
        with patch.dict("os.environ", {api_key_env: "test-key"}):
            llm = llm_class(settings)
            with pytest.raises(ValueError, match="empty content"):
                llm.chat([Message(role="user", content="")])
    
    @pytest.mark.parametrize("llm_class,api_key_env", [
        (OpenAILLM, "OPENAI_API_KEY"),
        (DeepSeekLLM, "DEEPSEEK_API_KEY"),
    ])
    def test_valid_roles_accepted(self, llm_class, api_key_env):
        """Should accept valid roles: system, user, assistant."""
        settings = MockSettings()
        with patch.dict("os.environ", {api_key_env: "test-key"}):
            llm = llm_class(settings)
            
            # These should not raise validation errors
            messages = [
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello"),
                Message(role="assistant", content="Hi there"),
            ]
            
            with patch("httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    make_mock_response()
                )
                # Should not raise
                llm.chat(messages)


# -----------------------------------------------------------------------------
# Integration-Style Tests (Still Mocked)
# -----------------------------------------------------------------------------


class TestLLMIntegration:
    """Integration-style tests using the factory pattern."""
    
    def test_factory_to_chat_flow_openai(self):
        """Test complete flow: factory -> create -> chat for OpenAI."""
        settings = MockSettings(llm=MockLLMSettings(provider="openai"))
        
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            llm = LLMFactory.create(settings)
            
            with patch("httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    make_mock_response("Integration test response")
                )
                
                response = llm.chat([Message(role="user", content="Test")])
                assert response.content == "Integration test response"
    
    def test_factory_to_chat_flow_deepseek(self):
        """Test complete flow: factory -> create -> chat for DeepSeek."""
        settings = MockSettings(llm=MockLLMSettings(provider="deepseek"))
        
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            llm = LLMFactory.create(settings)
            
            with patch("httpx.Client") as mock_client:
                mock_client.return_value.__enter__.return_value.post.return_value = (
                    make_mock_response("DeepSeek integration response")
                )
                
                response = llm.chat([Message(role="user", content="Test")])
                assert response.content == "DeepSeek integration response"
