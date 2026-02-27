"""Ollama LLM implementation for local model inference.

This module provides the Ollama LLM implementation that works with
locally running Ollama instances. Ollama enables running LLMs like
Llama, Mistral, CodeLlama, etc. on local hardware.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, ChatResponse, Message


class OllamaLLMError(RuntimeError):
    """Raised when Ollama API call fails.
    
    This exception provides clear error messages without exposing
    sensitive configuration details like internal URLs or credentials.
    """


class OllamaLLM(BaseLLM):
    """Ollama LLM provider implementation for local inference.
    
    This class implements the BaseLLM interface for Ollama's chat API,
    enabling local LLM inference without cloud dependencies.
    
    Attributes:
        base_url: The base URL for the Ollama server (default: http://localhost:11434).
        model: The model identifier to use (e.g., 'llama3', 'mistral').
        default_temperature: Default temperature for generation.
        default_max_tokens: Default max tokens for generation (num_predict in Ollama).
        timeout: Request timeout in seconds.
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> llm = OllamaLLM(settings)
        >>> response = llm.chat([Message(role='user', content='Hello')])
    """
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_TIMEOUT = 120.0  # Longer timeout for local inference
    
    def __init__(
        self,
        settings: Any,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Ollama LLM provider.
        
        Args:
            settings: Application settings containing LLM configuration.
            base_url: Optional base URL override (falls back to env var OLLAMA_BASE_URL).
            timeout: Optional timeout override for requests.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If required configuration is missing.
        """
        self.model = settings.llm.model
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        
        # Base URL: explicit > env var > default
        self.base_url = (
            base_url 
            or os.environ.get("OLLAMA_BASE_URL") 
            or self.DEFAULT_BASE_URL
        )
        
        # Timeout: explicit > default
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        
        # Store any additional kwargs for future use
        self._extra_config = kwargs
    
    def chat(
        self,
        messages: List[Message],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate a chat completion using Ollama API.
        
        Args:
            messages: List of conversation messages.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse with generated content and metadata.
        
        Raises:
            ValueError: If messages are invalid.
            OllamaLLMError: If API call fails.
        """
        # Validate input
        self.validate_messages(messages)
        
        # Prepare request parameters
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        model = kwargs.get("model", self.model)
        
        # Convert messages to Ollama API format
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        # Make API call
        try:
            response_data = self._call_api(
                messages=api_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # Parse response - Ollama returns different format than OpenAI
            # Handle both /api/chat (streaming disabled) response format
            if "message" in response_data:
                # Standard chat response
                content = response_data["message"]["content"]
            elif "response" in response_data:
                # Legacy generate endpoint response (fallback)
                content = response_data["response"]
            else:
                raise OllamaLLMError(
                    "[Ollama] Unexpected response format: missing 'message' or 'response' key"
                )
            
            # Build usage stats if available
            usage = None
            if "eval_count" in response_data or "prompt_eval_count" in response_data:
                usage = {
                    "prompt_tokens": response_data.get("prompt_eval_count", 0),
                    "completion_tokens": response_data.get("eval_count", 0),
                    "total_tokens": (
                        response_data.get("prompt_eval_count", 0) +
                        response_data.get("eval_count", 0)
                    ),
                }
            
            return ChatResponse(
                content=content,
                model=response_data.get("model", model),
                usage=usage,
                raw_response=response_data,
            )
        except KeyError as e:
            raise OllamaLLMError(
                f"[Ollama] Unexpected response format: missing key {e}"
            ) from e
        except Exception as e:
            if isinstance(e, OllamaLLMError):
                raise
            raise OllamaLLMError(
                f"[Ollama] API call failed: {type(e).__name__}: {e}"
            ) from e
    
    def _call_api(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Make the actual API call to Ollama.
        
        This method is separated to allow easy mocking in tests.
        
        Args:
            messages: Messages in API format.
            model: Model identifier.
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate (num_predict in Ollama).
        
        Returns:
            Raw API response as dictionary.
        
        Raises:
            OllamaLLMError: If the API call fails.
        """
        import httpx
        
        url = f"{self.base_url.rstrip('/')}/api/chat"
        headers = {
            "Content-Type": "application/json",
        }
        
        # Ollama uses 'num_predict' instead of 'max_tokens'
        # and 'options' object for model parameters
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,  # Disable streaming for synchronous response
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_detail = self._parse_error_response(response)
                    raise OllamaLLMError(
                        f"[Ollama] API error (HTTP {response.status_code}): {error_detail}"
                    )
                
                return response.json()
        except httpx.TimeoutException as e:
            raise OllamaLLMError(
                f"[Ollama] Request timed out after {self.timeout} seconds. "
                "Consider increasing timeout for larger models or longer responses."
            ) from e
        except httpx.ConnectError as e:
            raise OllamaLLMError(
                "[Ollama] Connection failed. Ensure Ollama is running locally. "
                "Start it with 'ollama serve' command."
            ) from e
        except httpx.RequestError as e:
            raise OllamaLLMError(
                f"[Ollama] Request failed: {type(e).__name__}"
            ) from e
    
    def _parse_error_response(self, response: Any) -> str:
        """Parse error details from API response.
        
        Args:
            response: The HTTP response object.
        
        Returns:
            Human-readable error message without exposing sensitive details.
        """
        try:
            error_data = response.json()
            if "error" in error_data:
                return str(error_data["error"])
            return response.text[:200] if response.text else "Unknown error"
        except Exception:
            return response.text[:200] if response.text else "Unknown error"
