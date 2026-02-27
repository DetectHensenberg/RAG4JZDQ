"""OpenAI-compatible Vision LLM implementation.

This module provides an OpenAI-compatible Vision LLM implementation for multimodal
interactions (text + image). Supports GPT-4o and similar vision-capable models.

When azure_endpoint is present in settings, the provider automatically constructs
the Azure-compatible URL and uses api-key auth header, allowing the same OpenAI
standard protocol to work against Azure OpenAI endpoints.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Optional

from src.libs.llm.base_llm import ChatResponse, Message
from src.libs.llm.base_vision_llm import BaseVisionLLM, ImageInput


class OpenAIVisionLLMError(RuntimeError):
    """Raised when OpenAI Vision API call fails."""


class OpenAIVisionLLM(BaseVisionLLM):
    """OpenAI-compatible Vision LLM provider implementation.
    
    This class implements the BaseVisionLLM interface using the OpenAI standard
    protocol. It supports both standard OpenAI endpoints and Azure OpenAI
    endpoints in compatibility mode.
    
    When azure_endpoint is detected in settings.vision_llm, it automatically:
    - Constructs the deployment-based URL
    - Uses api-key header for authentication
    - Appends api-version query parameter
    
    Attributes:
        api_key: The API key for authentication.
        base_url: The base URL for the API.
        model: The model identifier / deployment name.
        api_version: Optional API version (for Azure compat).
        max_image_size: Maximum image dimension in pixels (default 2048).
        default_temperature: Default temperature for generation.
        default_max_tokens: Default max tokens for generation.
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> vision_llm = OpenAIVisionLLM(settings)
        >>> image = ImageInput(path="diagram.png")
        >>> response = vision_llm.chat_with_image("Describe this", image)
    """
    
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MAX_IMAGE_SIZE = 2048  # pixels
    
    def __init__(
        self,
        settings: Any,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_image_size: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the OpenAI Vision LLM provider.
        
        Args:
            settings: Application settings containing vision_llm configuration.
            api_key: Optional API key override.
            base_url: Optional base URL override.
            max_image_size: Maximum image dimension in pixels for auto-compression.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If required configuration is missing.
        """
        # Get vision settings section
        vision_settings = getattr(settings, "vision_llm", None)
        
        # Temperature / max_tokens: vision_llm section > llm section defaults
        self.default_temperature = getattr(settings.llm, 'temperature', 0.0)
        self.default_max_tokens = getattr(settings.llm, 'max_tokens', 4096)
        
        # Model / deployment name
        vision_model = getattr(vision_settings, 'model', None) if vision_settings else None
        vision_dep = getattr(vision_settings, 'deployment_name', None) if vision_settings else None
        self.model = vision_dep or vision_model or settings.llm.model
        
        # Max image size
        vision_max_size = getattr(vision_settings, 'max_image_size', None) if vision_settings else None
        self.max_image_size = max_image_size or vision_max_size or self.DEFAULT_MAX_IMAGE_SIZE
        
        # API key: explicit > vision_settings > llm settings > env var
        self.api_key = api_key
        if not self.api_key and vision_settings:
            self.api_key = getattr(vision_settings, 'api_key', None)
        if not self.api_key:
            self.api_key = getattr(settings.llm, 'api_key', None)
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set in settings.yaml (vision_llm.api_key), "
                "OPENAI_API_KEY environment variable, or pass api_key parameter."
            )
        
        # Azure-compatible mode detection
        azure_endpoint = None
        if vision_settings:
            azure_endpoint = getattr(vision_settings, 'azure_endpoint', None)
        if not azure_endpoint:
            azure_endpoint = getattr(settings.llm, 'azure_endpoint', None)
        
        self.api_version = None
        if vision_settings:
            self.api_version = getattr(vision_settings, 'api_version', None)
        if not self.api_version:
            self.api_version = getattr(settings.llm, 'api_version', None)
        
        self._use_azure_auth = False
        
        if base_url:
            self.base_url = base_url
        elif azure_endpoint:
            # Azure-compatible mode
            self.base_url = (
                f"{azure_endpoint.rstrip('/')}/openai/deployments/{self.model}"
            )
            self._use_azure_auth = True
            if not self.api_version:
                self.api_version = "2024-02-15-preview"
        else:
            self.base_url = self.DEFAULT_BASE_URL
        
        self._extra_config = kwargs
    
    def chat_with_image(
        self,
        text: str,
        image: ImageInput,
        messages: Optional[list[Message]] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate a response based on text prompt and image input.
        
        Args:
            text: The text prompt or question about the image.
            image: The image input (path, bytes, or base64).
            messages: Optional conversation history for context.
            trace: Optional TraceContext for observability.
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse containing the generated text and metadata.
        
        Raises:
            ValueError: If text or image input is invalid.
            OpenAIVisionLLMError: If API call fails.
        """
        # Validate inputs
        self.validate_text(text)
        self.validate_image(image)
        
        # Preprocess image (compress if needed)
        processed_image = self.preprocess_image(
            image,
            max_size=(self.max_image_size, self.max_image_size)
        )
        
        # Convert image to base64
        image_base64 = self._get_image_base64(processed_image)
        
        # Prepare request parameters
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        
        # Build message list
        api_messages = []
        if messages:
            api_messages.extend([{"role": m.role, "content": m.content} for m in messages])
        
        # Add current text + image message
        current_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": text
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{processed_image.mime_type};base64,{image_base64}"
                    }
                }
            ]
        }
        api_messages.append(current_message)
        
        # Make API call
        try:
            response_data = self._call_api(
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            content = response_data["choices"][0]["message"]["content"]
            usage = response_data.get("usage")
            
            return ChatResponse(
                content=content,
                model=response_data.get("model", self.model),
                usage=usage,
                raw_response=response_data,
            )
        except KeyError as e:
            raise OpenAIVisionLLMError(
                f"[OpenAI Vision] Unexpected response format: missing key {e}"
            ) from e
        except Exception as e:
            if isinstance(e, OpenAIVisionLLMError):
                raise
            raise OpenAIVisionLLMError(
                f"[OpenAI Vision] API call failed: {type(e).__name__}: {e}"
            ) from e
    
    def preprocess_image(
        self,
        image: ImageInput,
        max_size: Optional[tuple[int, int]] = None,
    ) -> ImageInput:
        """Preprocess image before sending to Vision API.
        
        Compresses image if it exceeds max_size to reduce payload size.
        
        Args:
            image: The input image to preprocess.
            max_size: Maximum dimensions (width, height) in pixels.
        
        Returns:
            Preprocessed ImageInput with compressed data if needed.
        """
        if not max_size:
            return image
        
        try:
            from PIL import Image
        except ImportError:
            return image
        
        # Get image bytes
        if image.data:
            image_bytes = image.data
        elif image.path:
            image_bytes = Path(image.path).read_bytes()
        elif image.base64:
            return image
        else:
            return image
        
        # Load image and check size
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        max_width, max_height = max_size
        if width <= max_width and height <= max_height:
            return image
        
        # Calculate new size maintaining aspect ratio
        ratio = min(max_width / width, max_height / height)
        new_size = (int(width * ratio), int(height * ratio))
        
        # Resize image
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to bytes
        buffer = io.BytesIO()
        img_format = img.format or "PNG"
        img_resized.save(buffer, format=img_format)
        compressed_bytes = buffer.getvalue()
        
        return ImageInput(
            data=compressed_bytes,
            mime_type=image.mime_type
        )
    
    def _get_image_base64(self, image: ImageInput) -> str:
        """Convert ImageInput to base64 string."""
        try:
            if image.base64:
                return image.base64
            elif image.data:
                return base64.b64encode(image.data).decode("utf-8")
            elif image.path:
                image_bytes = Path(image.path).read_bytes()
                return base64.b64encode(image_bytes).decode("utf-8")
            else:
                raise ValueError("ImageInput has no valid data source")
        except Exception as e:
            raise OpenAIVisionLLMError(
                f"[OpenAI Vision] Failed to encode image: {e}"
            ) from e
    
    def _call_api(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Make HTTP request to the Vision API.
        
        Args:
            messages: List of API-formatted messages.
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate.
        
        Returns:
            API response as dictionary.
        
        Raises:
            OpenAIVisionLLMError: If API call fails.
        """
        import httpx
        
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
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_detail = self._parse_error_response(response)
                    raise OpenAIVisionLLMError(
                        f"[OpenAI Vision] API error (HTTP {response.status_code}): {error_detail}"
                    )
                
                return response.json()
        except httpx.TimeoutException as e:
            raise OpenAIVisionLLMError(
                "[OpenAI Vision] Request timed out after 60 seconds"
            ) from e
        except httpx.RequestError as e:
            raise OpenAIVisionLLMError(
                f"[OpenAI Vision] Connection failed: {type(e).__name__}: {e}"
            ) from e
    
    def _parse_error_response(self, response: Any) -> str:
        """Parse error details from API response."""
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
