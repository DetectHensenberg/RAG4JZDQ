"""OpenAI-compatible LLM implementation.

This module provides the OpenAI LLM implementation that works with
the standard OpenAI API. It can also be used with other OpenAI-compatible
endpoints by configuring the base_url.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

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
        
        # base_url resolution: explicit param > azure > settings > default
        settings_base_url = getattr(settings.llm, 'base_url', None)
        
        if base_url:
            self.base_url = base_url
            self._use_azure_auth = False
        elif azure_endpoint:
            # Azure-compatible mode: construct deployment-based URL
            deployment = getattr(settings.llm, 'deployment_name', None) or self.model
            self.base_url = f"{azure_endpoint.rstrip('/')}/openai/deployments/{deployment}"
            self._use_azure_auth = True
            if not self.api_version:
                self.api_version = "2024-02-15-preview"
        elif settings_base_url:
            self.base_url = settings_base_url
            self._use_azure_auth = False
        else:
            self.base_url = self.DEFAULT_BASE_URL
            self._use_azure_auth = False
        
        # Store any additional kwargs for future use
        self._extra_config = kwargs
        
        # Persistent HTTP client for connection pooling
        self._http_client = httpx.Client(
            timeout=120.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    
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
                f"[LLM:{self.model}] Unexpected response format: missing key {e}"
            ) from e
        except OpenAILLMError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise OpenAILLMError(
                f"[LLM:{self.model}] Network error: {type(e).__name__}: {e}"
            ) from e
        except (ValueError, TypeError, IndexError) as e:
            raise OpenAILLMError(
                f"[LLM:{self.model}] Data error: {type(e).__name__}: {e}"
            ) from e
    
    def chat_stream(
        self,
        messages: List[Message],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ):
        """Stream a chat completion response token by token.
        
        Uses SSE (Server-Sent Events) for real-time token streaming.
        
        Args:
            messages: List of conversation messages.
            trace: Optional TraceContext for observability.
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Yields:
            Text chunks as they arrive from the API.
        """
        self.validate_messages(messages)
        
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        model = kwargs.get("model", self.model)
        
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        if self.api_version:
            url += f"?api-version={self.api_version}"
        
        if self._use_azure_auth:
            headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        
        payload = {
            "model": model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        try:
            with self._http_client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    response.read()
                    error_detail = self._parse_error_response(response)
                    raise OpenAILLMError(
                        f"[LLM:{self.model}] Stream API error (HTTP {response.status_code}): {error_detail}"
                    )
                
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]  # Remove "data: " prefix
                    if data.strip() == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
        except httpx.TimeoutException as e:
            raise OpenAILLMError(
                f"[LLM:{self.model}] Stream request timed out"
            ) from e
        except httpx.RequestError as e:
            raise OpenAILLMError(
                f"[LLM:{self.model}] Stream connection failed: {type(e).__name__}: {e}"
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
        
        # Retry logic for network issues
        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = self._http_client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_detail = self._parse_error_response(response)
                    raise OpenAILLMError(
                        f"[LLM:{self.model}] API error (HTTP {response.status_code}): {error_detail}"
                    )
                
                return response.json()
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    import time
                    time.sleep(2)  # Wait before retry
                    continue
                raise OpenAILLMError(
                    f"[LLM:{self.model}] Request timed out after 120 seconds (retried {max_retries} times)"
                ) from e
            except httpx.RequestError as e:
                last_error = e
                if attempt < max_retries:
                    import time
                    time.sleep(2)  # Wait before retry
                    continue
                raise OpenAILLMError(
                    f"[LLM:{self.model}] Connection failed: {type(e).__name__}: {e}"
                ) from e
        
        raise OpenAILLMError(f"[LLM:{self.model}] Failed after {max_retries} retries: {last_error}")
    
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
