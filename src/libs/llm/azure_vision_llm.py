"""Azure OpenAI Vision LLM implementation.

This module provides Azure OpenAI Vision LLM implementation for multimodal
interactions (text + image). Supports GPT-4o and GPT-4-Vision-Preview models
for image understanding tasks like image captioning, visual question answering,
and document analysis.
"""

from __future__ import annotations

import base64
import io
import os
import requests
from pathlib import Path
from typing import Any, Optional

from src.libs.llm.base_llm import ChatResponse, Message
from src.libs.llm.base_vision_llm import BaseVisionLLM, ImageInput


class AzureVisionLLMError(RuntimeError):
    """Raised when Azure Vision API call fails."""


class AzureVisionLLM(BaseVisionLLM):
    """Azure OpenAI Vision LLM provider implementation.
    
    This class implements the BaseVisionLLM interface for Azure's OpenAI Vision
    Service, supporting GPT-4o and GPT-4-Vision-Preview models. It handles
    Azure-specific authentication, endpoint configuration, and image preprocessing.
    
    Design Principles Applied:
    - Pluggable: Implements BaseVisionLLM for seamless provider switching
    - Config-Driven: Uses settings.yaml for all configuration
    - Observable: Accepts TraceContext parameter (reserved for Stage F)
    - Graceful Errors: Provides clear, actionable error messages
    - Image Preprocessing: Auto-compresses images exceeding max_image_size
    
    Attributes:
        api_key: The Azure API key for authentication.
        endpoint: The Azure OpenAI endpoint URL.
        deployment_name: The deployment name for the Vision model.
        api_version: The API version to use.
        max_image_size: Maximum image dimension in pixels (default 2048).
        default_temperature: Default temperature for generation.
        default_max_tokens: Default max tokens for generation.
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> vision_llm = AzureVisionLLM(
        ...     settings,
        ...     endpoint='https://my-resource.openai.azure.com',
        ...     deployment_name='gpt-4o'
        ... )
        >>> image = ImageInput(path="diagram.png")
        >>> response = vision_llm.chat_with_image(
        ...     text="Describe this diagram",
        ...     image=image
        ... )
    """
    
    DEFAULT_API_VERSION = "2024-02-15-preview"
    DEFAULT_MAX_IMAGE_SIZE = 2048  # pixels
    
    def __init__(
        self,
        settings: Any,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: Optional[str] = None,
        max_image_size: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Azure OpenAI Vision LLM provider.
        
        Args:
            settings: Application settings containing LLM configuration.
            api_key: Optional API key override (falls back to env var).
            endpoint: Optional endpoint override (falls back to env var).
            deployment_name: Optional deployment name (defaults to settings.llm.model).
            api_version: Optional API version override.
            max_image_size: Maximum image dimension in pixels for auto-compression.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If required configuration is missing.
        """
        self.deployment_name = deployment_name or settings.llm.model
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        
        # Check source of vision settings
        vision_settings = getattr(settings, "vision_llm", None)
        
        # Resolve Deployment Name
        # Priority: arg > vision_settings.deployment > vision_settings.model > settings.llm.model
        vision_dep = getattr(vision_settings, "deployment_name", None)
        vision_model = getattr(vision_settings, "model", None)
        self.deployment_name = deployment_name or vision_dep or vision_model or settings.llm.model
        
        # Resolve Max Image Size
        # Priority: arg > vision_settings.max_image_size > DEFAULT
        vision_max_size = getattr(vision_settings, "max_image_size", None)
        self.max_image_size = max_image_size or vision_max_size or self.DEFAULT_MAX_IMAGE_SIZE

            
        # API Key Resolution Order:
        # 1. Constructor arg
        # 2. Vision settings (settings.vision_llm.api_key)
        # 3. Env var (AZURE_OPENAI_API_KEY)
        # 4. LLM settings fallback? (Usually not for API keys in settings object, but let's check)
        
        self.api_key = api_key 
        if not self.api_key and vision_settings and vision_settings.api_key:
             self.api_key = vision_settings.api_key
        if not self.api_key:
             self.api_key = os.environ.get("AZURE_OPENAI_API_KEY")
             
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key not provided. Set AZURE_OPENAI_API_KEY "
                "environment variable or pass api_key parameter."
            )
            
        # Endpoint Resolution Order
        self.endpoint = endpoint
        if not self.endpoint and vision_settings and vision_settings.azure_endpoint:
             self.endpoint = vision_settings.azure_endpoint
        if not self.endpoint:
             self.endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or getattr(settings.llm, "azure_endpoint", None)
             
        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint not provided.")
            
        # API Version Resolution Order
        self.api_version = api_version
        if not self.api_version and vision_settings and vision_settings.api_version:
             self.api_version = vision_settings.api_version
        if not self.api_version:
             self.api_version = getattr(settings.llm, "api_version", None) or self.DEFAULT_API_VERSION
        
        # Validate initialized client
        # We don't initialize a client object here because we use request/httpx per call or custom logic
        # But we ensures keys are present.

        
        # Store any additional kwargs for future use
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
        
        This method sends the text and image to Azure OpenAI Vision API
        (GPT-4o or GPT-4-Vision-Preview) and returns the generated response.
        
        Args:
            text: The text prompt or question about the image.
            image: The image input (path, bytes, or base64).
            messages: Optional conversation history for context.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Override parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse containing the generated text and metadata.
        
        Raises:
            ValueError: If text or image input is invalid.
            AzureVisionLLMError: If API call fails.
        
        Example:
            >>> image = ImageInput(path="chart.png")
            >>> response = vision_llm.chat_with_image(
            ...     text="What does this chart show?",
            ...     image=image
            ... )
        """
        # Validate inputs
        self.validate_text(text)
        self.validate_image(image)
        
        # Preprocess image (compress if needed)
        processed_image = self.preprocess_image(
            image,
            max_size=(self.max_image_size, self.max_image_size)
        )
        
        # Convert image to base64 if needed
        image_base64 = self._get_image_base64(processed_image)
        
        # Prepare request parameters
        temperature = kwargs.get("temperature", self.default_temperature)
        max_tokens = kwargs.get("max_tokens", self.default_max_tokens)
        deployment = kwargs.get("deployment_name", self.deployment_name)
        
        # Build message list
        api_messages = []
        if messages:
            # Add conversation history
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
            raise AzureVisionLLMError(
                f"[Azure Vision] Unexpected response format: missing key {e}"
            ) from e
        except Exception as e:
            if isinstance(e, AzureVisionLLMError):
                raise
            raise AzureVisionLLMError(
                f"[Azure Vision] API call failed: {type(e).__name__}: {e}"
            ) from e
    
    def preprocess_image(
        self,
        image: ImageInput,
        max_size: Optional[tuple[int, int]] = None,
    ) -> ImageInput:
        """Preprocess image before sending to Azure Vision API.
        
        Compresses image if it exceeds max_size to reduce API payload size
        and meet Azure's size limits. Uses PIL for image manipulation.
        
        This operation is idempotent - calling it multiple times with the
        same input produces the same output.
        
        Args:
            image: The input image to preprocess.
            max_size: Maximum dimensions (width, height) in pixels.
        
        Returns:
            Preprocessed ImageInput with compressed data if needed.
        
        Note:
            If the image is already within size limits, returns it unchanged.
        """
        if not max_size:
            return image
        
        try:
            from PIL import Image
        except ImportError:
            # If PIL not available, skip preprocessing
            return image
        
        # Get image bytes
        if image.data:
            image_bytes = image.data
        elif image.path:
            image_bytes = Path(image.path).read_bytes()
        elif image.base64:
            # Already encoded, skip preprocessing
            return image
        else:
            return image
        
        # Load image and check size
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # Check if compression needed
        max_width, max_height = max_size
        if width <= max_width and height <= max_height:
            # No compression needed
            return image
        
        # Calculate new size maintaining aspect ratio
        ratio = min(max_width / width, max_height / height)
        new_size = (int(width * ratio), int(height * ratio))
        
        # Resize image
        img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to bytes
        buffer = io.BytesIO()
        # Preserve original format if possible
        img_format = img.format or "PNG"
        img_resized.save(buffer, format=img_format)
        compressed_bytes = buffer.getvalue()
        
        # Return new ImageInput with compressed data
        return ImageInput(
            data=compressed_bytes,
            mime_type=image.mime_type
        )
    
    def _get_image_base64(self, image: ImageInput) -> str:
        """Convert ImageInput to base64 string.
        
        Args:
            image: The image to convert.
        
        Returns:
            Base64-encoded image string.
        
        Raises:
            AzureVisionLLMError: If image cannot be encoded.
        """
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
            raise AzureVisionLLMError(
                f"[Azure Vision] Failed to encode image: {e}"
            ) from e
    
    def _call_api(
        self,
        messages: list[dict],
        deployment: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Make HTTP request to Azure OpenAI Vision API.
        
        Args:
            messages: List of API-formatted messages.
            deployment: Deployment name to use.
            temperature: Generation temperature.
            max_tokens: Maximum tokens to generate.
        
        Returns:
            API response as dictionary.
        
        Raises:
            AzureVisionLLMError: If API call fails.
        """
        # Clean endpoint trail slash
        endpoint = self.endpoint.rstrip("/")
        
        # Build API URL
        url = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={self.api_version}"
        )
        
        # Prepare request payload
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
             error_details = e.response.text if e.response else str(e)
             raise AzureVisionLLMError(
                 f"[Azure Vision] HTTP Error: {e} - Response: {error_details}"
             ) from e
        except requests.exceptions.RequestException as e:
             raise AzureVisionLLMError(
                 f"[Azure Vision] Request failed: {e}"
             ) from e
