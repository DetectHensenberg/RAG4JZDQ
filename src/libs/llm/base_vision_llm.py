"""Abstract base class for Vision LLM providers.

This module defines the pluggable interface for Vision Language Model providers,
enabling multimodal interactions (text + image) with seamless switching between
different backends (Azure Vision, Ollama Vision, etc.) through configuration.

Vision LLMs extend standard LLMs by accepting image inputs alongside text prompts,
enabling tasks like image captioning, visual question answering, and document
understanding with embedded images.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from src.libs.llm.base_llm import ChatResponse, Message


@dataclass
class ImageInput:
    """Represents an image input for Vision LLM.
    
    Supports multiple input formats:
    - File path: Local image file to be read and encoded
    - Bytes: Raw image bytes (already loaded)
    - Base64: Already encoded image string
    
    Attributes:
        path: Path to the image file (if loading from disk).
        data: Raw image bytes (if already loaded).
        base64: Base64-encoded image string (if already encoded).
        mime_type: MIME type of the image (e.g., 'image/png', 'image/jpeg').
    """
    path: Optional[Union[str, Path]] = None
    data: Optional[bytes] = None
    base64: Optional[str] = None
    mime_type: str = "image/png"
    
    def __post_init__(self) -> None:
        """Validate that exactly one input format is provided."""
        provided_inputs = sum([
            self.path is not None,
            self.data is not None,
            self.base64 is not None,
        ])
        if provided_inputs == 0:
            raise ValueError("Must provide one of: path, data, or base64")
        if provided_inputs > 1:
            raise ValueError("Must provide exactly one of: path, data, or base64")


class BaseVisionLLM(ABC):
    """Abstract base class for Vision LLM providers.
    
    Vision LLMs accept both text and image inputs, enabling multimodal
    understanding tasks such as image captioning, visual question answering,
    and document analysis with embedded images.
    
    All Vision LLM implementations must inherit from this class and implement
    the chat_with_image() method. This ensures consistent interface across
    different providers (Azure Vision, Ollama Vision, etc.).
    
    Design Principles Applied:
    - Pluggable: Subclasses can be swapped without changing upstream code.
    - Observable: Accepts optional TraceContext for observability integration.
    - Config-Driven: Instances are created via factory based on settings.
    - Interface Segregation: Minimal interface focused on multimodal input.
    - Extension Point: Image preprocessing (compression, format conversion) can be
      added in subclasses without changing the base interface.
    """
    
    @abstractmethod
    def chat_with_image(
        self,
        text: str,
        image: ImageInput,
        messages: Optional[list[Message]] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate a response based on text prompt and image input.
        
        This method enables multimodal interactions where the model can "see"
        the image and respond to questions or generate descriptions about it.
        
        Args:
            text: The text prompt or question about the image.
            image: The image input (path, bytes, or base64).
            messages: Optional conversation history for context. If provided,
                the text + image will be appended as the latest user message.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.).
        
        Returns:
            ChatResponse containing the generated text and metadata.
        
        Raises:
            ValueError: If text is empty or image input is invalid.
            RuntimeError: If the Vision LLM provider call fails.
        
        Example:
            >>> image = ImageInput(path="diagram.png")
            >>> response = vision_llm.chat_with_image(
            ...     text="Describe this diagram",
            ...     image=image
            ... )
            >>> print(response.content)
            "This diagram shows a system architecture with..."
        """
        pass
    
    def validate_text(self, text: str) -> None:
        """Validate text prompt.
        
        Args:
            text: Text prompt to validate.
        
        Raises:
            ValueError: If text is empty or not a string.
        """
        if not isinstance(text, str):
            raise ValueError(f"Text must be a string, got {type(text).__name__}")
        if not text or not text.strip():
            raise ValueError("Text prompt cannot be empty")
    
    def validate_image(self, image: ImageInput) -> None:
        """Validate image input.
        
        Args:
            image: Image input to validate.
        
        Raises:
            ValueError: If image is not an ImageInput instance.
        """
        if not isinstance(image, ImageInput):
            raise ValueError(
                f"Image must be an ImageInput instance, got {type(image).__name__}"
            )
    
    def preprocess_image(
        self,
        image: ImageInput,
        max_size: Optional[tuple[int, int]] = None,
    ) -> ImageInput:
        """Preprocess image before sending to Vision LLM.
        
        This method provides an extension point for image preprocessing such as:
        - Resizing to meet provider size limits
        - Format conversion (e.g., PNG to JPEG)
        - Compression to reduce payload size
        
        Default implementation returns the image unchanged. Subclasses can
        override to add provider-specific preprocessing.
        
        Args:
            image: The input image to preprocess.
            max_size: Optional maximum dimensions (width, height) in pixels.
        
        Returns:
            Preprocessed ImageInput (may be the same instance if no changes needed).
        
        Note:
            Preprocessing should be idempotent - calling it multiple times
            with the same input should produce the same output.
        """
        # Default: no preprocessing
        return image
