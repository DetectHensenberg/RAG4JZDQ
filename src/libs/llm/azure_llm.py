"""Azure OpenAI LLM implementation.

This module provides the Azure OpenAI LLM implementation that works with
Azure's OpenAI Service API. It handles the Azure-specific authentication
and endpoint configuration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, ChatResponse, Message


class AzureLLMError(RuntimeError):
    """Raised when Azure OpenAI API call fails."""


class AzureLLM(BaseLLM):
    """Azure OpenAI LLM provider implementation.
    
    This class implements the BaseLLM interface for Azure's OpenAI Service.
    Azure uses a different authentication method (API key in header) and
    endpoint structure compared to standard OpenAI.
    
    Attributes:
        api_key: The Azure API key for authentication.
        endpoint: The Azure OpenAI endpoint URL.
        deployment_name: The deployment name for the model.
        api_version: The API version to use.
        default_temperature: Default temperature for generation.
        default_max_tokens: Default max tokens for generation.
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> llm = AzureLLM(settings, endpoint='https://my-resource.openai.azure.com')
        >>> response = llm.chat([Message(role='user', content='Hello')])
    """
    
    DEFAULT_API_VERSION = "2024-02-15-preview"
    
    def __init__(
        self,
        settings: Any,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Azure OpenAI LLM provider.
        
        Args:
            settings: Application settings containing LLM configuration.
            api_key: Optional API key override (falls back to settings.llm.api_key or env var).
            endpoint: Optional endpoint override (falls back to settings.llm.azure_endpoint or env var).
            deployment_name: Optional deployment name (defaults to settings.llm.deployment_name or model).
            api_version: Optional API version override.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If required configuration is missing.
        """
        # Deployment name: explicit > settings.deployment_name > settings.model
        self.deployment_name = (
            deployment_name 
            or getattr(settings.llm, 'deployment_name', None) 
            or settings.llm.model
        )
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        
        # API key: explicit > settings > env var
        self.api_key = (
            api_key 
            or getattr(settings.llm, 'api_key', None) 
            or os.environ.get("AZURE_OPENAI_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key not provided. Set in settings.yaml (llm.api_key), "
                "AZURE_OPENAI_API_KEY environment variable, or pass api_key parameter."
            )
        
        # Endpoint: explicit > settings > env var
        self.endpoint = (
            endpoint 
            or getattr(settings.llm, 'azure_endpoint', None) 
            or os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        if not self.endpoint:
            raise ValueError(
                "Azure OpenAI endpoint not provided. Set in settings.yaml (llm.azure_endpoint), "
                "AZURE_OPENAI_ENDPOINT environment variable, or pass endpoint parameter."
            )
        
        # API version: explicit > settings > default
        self.api_version = (
            api_version 
            or getattr(settings.llm, 'api_version', None) 
            or self.DEFAULT_API_VERSION
        )
        
        # Store any additional kwargs for future use
        self._extra_config = kwargs
    
    def chat(
        self,
        messages: List[Message],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate a chat completion using Azure OpenAI API.
        
        Args:
            messages: List of conversation messages.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse with generated content and metadata.
        
        Raises:
            ValueError: If messages are invalid.
            AzureLLMError: If API call fails.
        """
        # Validate input
        self.validate_messages(messages)
        
        # Prepare request parameters
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        deployment = kwargs.get("deployment_name", self.deployment_name)
        
        # Convert messages to API format
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        # Make API call
        try:
            response_data = self._call_api(
                messages=api_messages,
                deployment=deployment,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # Parse response
            content = response_data["choices"][0]["message"]["content"]
            usage = response_data.get("usage")
            
            return ChatResponse(
                content=content,
                model=response_data.get("model", deployment),
                usage=usage,
                raw_response=response_data,
            )
        except KeyError as e:
            raise AzureLLMError(
                f"[Azure] Unexpected response format: missing key {e}"
            ) from e
        except Exception as e:
            if isinstance(e, AzureLLMError):
                raise
            raise AzureLLMError(
                f"[Azure] API call failed: {type(e).__name__}: {e}"
            ) from e
    
    def _call_api(
        self,
        messages: List[Dict[str, str]],
        deployment: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Make the actual API call to Azure OpenAI.
        
        This method is separated to allow easy mocking in tests.
        
        Args:
            messages: Messages in API format.
            deployment: Deployment name.
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate.
        
        Returns:
            Raw API response as dictionary.
        
        Raises:
            AzureLLMError: If the API call fails.
        """
        import httpx
        
        # Azure endpoint format:
        # {endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}
        url = (
            f"{self.endpoint.rstrip('/')}/openai/deployments/{deployment}/"
            f"chat/completions?api-version={self.api_version}"
        )
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_detail = self._parse_error_response(response)
                    raise AzureLLMError(
                        f"[Azure] API error (HTTP {response.status_code}): {error_detail}"
                    )
                
                return response.json()
        except httpx.TimeoutException as e:
            raise AzureLLMError(
                f"[Azure] Request timed out after 60 seconds"
            ) from e
        except httpx.RequestError as e:
            raise AzureLLMError(
                f"[Azure] Connection failed: {type(e).__name__}: {e}"
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
