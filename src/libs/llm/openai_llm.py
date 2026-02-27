"""OpenAI-compatible LLM implementation.

This module provides the OpenAI LLM implementation that works with
the standard OpenAI API. It can also be used with other OpenAI-compatible
endpoints by configuring the base_url.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, ChatResponse, Message


class OpenAILLMError(RuntimeError):
    """Raised when OpenAI API call fails."""


class OpenAILLM(BaseLLM):
    """OpenAI LLM provider implementation.
    
    This class implements the BaseLLM interface for OpenAI's chat completion API.
    It supports the standard OpenAI API and any OpenAI-compatible endpoints.
    
    Attributes:
        api_key: The API key for authentication.
        base_url: The base URL for the API (default: OpenAI's endpoint).
        model: The model identifier to use.
        default_temperature: Default temperature for generation.
        default_max_tokens: Default max tokens for generation.
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> llm = OpenAILLM(settings)
        >>> response = llm.chat([Message(role='user', content='Hello')])
    """
    
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    
    def __init__(
        self,
        settings: Any,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the OpenAI LLM provider.
        
        Args:
            settings: Application settings containing LLM configuration.
            api_key: Optional API key override (falls back to settings.llm.api_key or env var).
            base_url: Optional base URL override.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If API key is not provided and not found in environment.
        
        Note:
            When azure_endpoint is present in settings, the provider automatically
            constructs the Azure-compatible OpenAI URL and uses api-key auth header.
        """
        self.model = settings.llm.model
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        
        # API key: explicit > settings > env var
        self.api_key = (
            api_key
            or getattr(settings.llm, 'api_key', None)
            or os.environ.get("OPENAI_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set in settings.yaml (llm.api_key), "
                "OPENAI_API_KEY environment variable, or pass api_key parameter."
            )
        
        # Azure-compatible mode detection
        azure_endpoint = getattr(settings.llm, 'azure_endpoint', None)
        self.api_version = getattr(settings.llm, 'api_version', None)
        
        effective_base_url = base_url or getattr(settings.llm, 'base_url', None)
        if effective_base_url:
            self.base_url = effective_base_url
            self._use_azure_auth = False
        elif azure_endpoint:
            # Azure-compatible mode: construct deployment-based URL
            deployment = getattr(settings.llm, 'deployment_name', None) or self.model
            self.base_url = f"{azure_endpoint.rstrip('/')}/openai/deployments/{deployment}"
            self._use_azure_auth = True
            if not self.api_version:
                self.api_version = "2024-02-15-preview"
        else:
            self.base_url = self.DEFAULT_BASE_URL
            self._use_azure_auth = False
        
        # Proxy configuration: settings > env var
        self._proxy = (
            getattr(settings.llm, 'proxy', None)
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
            or None
        )

        # Store any additional kwargs for future use
        self._extra_config = kwargs
    
    def chat(
        self,
        messages: List[Message],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate a chat completion using OpenAI API.
        
        Args:
            messages: List of conversation messages.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse with generated content and metadata.
        
        Raises:
            ValueError: If messages are invalid.
            OpenAILLMError: If API call fails.
        """
        # Validate input
        self.validate_messages(messages)
        
        # Prepare request parameters
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        model = kwargs.get("model", self.model)
        
        # Convert messages to API format
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        # Make API call
        try:
            response_data = self._call_api(
                messages=api_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # Parse response
            content = response_data["choices"][0]["message"]["content"]
            usage = response_data.get("usage")
            
            return ChatResponse(
                content=content,
                model=response_data.get("model", model),
                usage=usage,
                raw_response=response_data,
            )
        except KeyError as e:
            raise OpenAILLMError(
                f"[OpenAI] Unexpected response format: missing key {e}"
            ) from e
        except Exception as e:
            if isinstance(e, OpenAILLMError):
                raise
            raise OpenAILLMError(
                f"[OpenAI] API call failed: {type(e).__name__}: {e}"
            ) from e
    
    def _call_api(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Make the actual API call to OpenAI.
        
        This method is separated to allow easy mocking in tests.
        
        Args:
            messages: Messages in API format.
            model: Model identifier.
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate.
        
        Returns:
            Raw API response as dictionary.
        
        Raises:
            OpenAILLMError: If the API call fails.
        """
        import requests as _requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        if self.api_version:
            url += f"?api-version={self.api_version}"

        if self._use_azure_auth:
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        else:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Build request kwargs
        req_kwargs: dict = {"timeout": 180}
        if self._proxy:
            req_kwargs["proxies"] = {"https": self._proxy, "http": self._proxy}
            req_kwargs["verify"] = False

        try:
            response = _requests.post(url, json=payload, headers=headers, **req_kwargs)

            if response.status_code != 200:
                error_detail = self._parse_error_response(response)
                raise OpenAILLMError(
                    f"[OpenAI] API error (HTTP {response.status_code}): {error_detail}"
                )

            return response.json()
        except _requests.exceptions.Timeout as e:
            raise OpenAILLMError(
                f"[OpenAI] Request timed out after 180 seconds"
            ) from e
        except _requests.exceptions.RequestException as e:
            raise OpenAILLMError(
                f"[OpenAI] Connection failed: {type(e).__name__}: {e}"
            ) from e
    
    def _parse_error_response(self, response: Any) -> str:
        """Parse error details from API response.
        
        Args:
            response: The HTTP response object.
        
        Returns:
            Human-readable error message.
        """
        try:
            error_data = response.json()
            if "error" in error_data:
                error = error_data["error"]
                if isinstance(error, dict):
                    return error.get("message", str(error))
                return str(error)
            return response.text
        except Exception:
            return response.text or "Unknown error"
