"""Unit tests for Vision LLM factory and base interface.

This module tests the Vision LLM factory pattern, provider registration,
and the BaseVisionLLM abstract interface using a fake implementation.
"""

import pytest
from pathlib import Path
from typing import Any, Optional

from src.libs.llm.base_llm import ChatResponse, Message
from src.libs.llm.base_vision_llm import BaseVisionLLM, ImageInput
from src.libs.llm.llm_factory import LLMFactory


# ================================
# Fake Implementation for Testing
# ================================

class FakeVisionLLM(BaseVisionLLM):
    """Fake Vision LLM implementation for testing.
    
    This implementation returns deterministic responses for testing
    and tracks call counts for verification.
    """
    
    def __init__(
        self,
        settings: Any = None,
        response_template: str = "I see: {text} | Image: {image_type}",
        **kwargs: Any
    ):
        """Initialize fake Vision LLM.
        
        Args:
            settings: Optional settings object (unused in fake).
            response_template: Template for generating responses.
            **kwargs: Additional parameters (unused).
        """
        self.settings = settings
        self.response_template = response_template
        self.call_count = 0
        self.last_text = None
        self.last_image = None
        self.last_messages = None
    
    def chat_with_image(
        self,
        text: str,
        image: ImageInput,
        messages: Optional[list[Message]] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Generate fake response based on inputs."""
        # Validate inputs using base class methods
        self.validate_text(text)
        self.validate_image(image)
        
        # Track call
        self.call_count += 1
        self.last_text = text
        self.last_image = image
        self.last_messages = messages
        
        # Determine image type for response
        if image.path:
            image_type = f"path({image.path})"
        elif image.data:
            image_type = f"bytes({len(image.data)} bytes)"
        elif image.base64:
            image_type = f"base64({len(image.base64)} chars)"
        else:
            image_type = "unknown"
        
        # Generate deterministic response
        content = self.response_template.format(
            text=text,
            image_type=image_type
        )
        
        return ChatResponse(
            content=content,
            model="fake-vision-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )


# =========================
# Test BaseVisionLLM
# =========================

class TestBaseVisionLLM:
    """Test the BaseVisionLLM abstract interface."""
    
    def test_abstract_cannot_instantiate(self):
        """BaseVisionLLM cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseVisionLLM()
    
    def test_validate_text_success(self):
        """validate_text accepts valid text."""
        fake = FakeVisionLLM()
        fake.validate_text("valid text")  # Should not raise
    
    def test_validate_text_empty(self):
        """validate_text rejects empty text."""
        fake = FakeVisionLLM()
        with pytest.raises(ValueError, match="Text prompt cannot be empty"):
            fake.validate_text("")
    
    def test_validate_text_whitespace_only(self):
        """validate_text rejects whitespace-only text."""
        fake = FakeVisionLLM()
        with pytest.raises(ValueError, match="Text prompt cannot be empty"):
            fake.validate_text("   \n\t  ")
    
    def test_validate_text_non_string(self):
        """validate_text rejects non-string input."""
        fake = FakeVisionLLM()
        with pytest.raises(ValueError, match="Text must be a string"):
            fake.validate_text(123)  # type: ignore
    
    def test_validate_image_success(self):
        """validate_image accepts valid ImageInput."""
        fake = FakeVisionLLM()
        image = ImageInput(path="test.png")
        fake.validate_image(image)  # Should not raise
    
    def test_validate_image_invalid_type(self):
        """validate_image rejects non-ImageInput."""
        fake = FakeVisionLLM()
        with pytest.raises(ValueError, match="Image must be an ImageInput instance"):
            fake.validate_image("not_an_image_input")  # type: ignore
    
    def test_preprocess_image_default(self):
        """preprocess_image returns image unchanged by default."""
        fake = FakeVisionLLM()
        image = ImageInput(path="test.png")
        result = fake.preprocess_image(image)
        assert result is image  # Same instance


# =========================
# Test ImageInput
# =========================

class TestImageInput:
    """Test the ImageInput dataclass."""
    
    def test_image_input_path(self):
        """ImageInput can be created with path."""
        image = ImageInput(path="test.png")
        assert image.path == "test.png"
        assert image.data is None
        assert image.base64 is None
        assert image.mime_type == "image/png"
    
    def test_image_input_path_as_pathlib(self):
        """ImageInput accepts pathlib.Path."""
        path = Path("test.png")
        image = ImageInput(path=path)
        assert image.path == path
    
    def test_image_input_data(self):
        """ImageInput can be created with bytes data."""
        data = b"fake_image_bytes"
        image = ImageInput(data=data, mime_type="image/jpeg")
        assert image.data == data
        assert image.path is None
        assert image.base64 is None
        assert image.mime_type == "image/jpeg"
    
    def test_image_input_base64(self):
        """ImageInput can be created with base64 string."""
        base64_str = "iVBORw0KGgoAAAANSUhEUgAAAAUA"
        image = ImageInput(base64=base64_str)
        assert image.base64 == base64_str
        assert image.path is None
        assert image.data is None
    
    def test_image_input_no_input(self):
        """ImageInput raises error if no input provided."""
        with pytest.raises(ValueError, match="Must provide one of: path, data, or base64"):
            ImageInput()
    
    def test_image_input_multiple_inputs(self):
        """ImageInput raises error if multiple inputs provided."""
        with pytest.raises(ValueError, match="Must provide exactly one of"):
            ImageInput(path="test.png", data=b"bytes")


# =========================
# Test FakeVisionLLM
# =========================

class TestFakeVisionLLM:
    """Test the FakeVisionLLM implementation."""
    
    def test_chat_with_image_path(self):
        """FakeVisionLLM generates response for path-based image."""
        fake = FakeVisionLLM()
        image = ImageInput(path="diagram.png")
        
        response = fake.chat_with_image(
            text="Describe this diagram",
            image=image
        )
        
        assert response.content == "I see: Describe this diagram | Image: path(diagram.png)"
        assert response.model == "fake-vision-model"
        assert fake.call_count == 1
        assert fake.last_text == "Describe this diagram"
        assert fake.last_image == image
    
    def test_chat_with_image_bytes(self):
        """FakeVisionLLM generates response for bytes-based image."""
        fake = FakeVisionLLM()
        data = b"fake_image_data_12345"
        image = ImageInput(data=data)
        
        response = fake.chat_with_image(
            text="What is this?",
            image=image
        )
        
        assert "bytes(21 bytes)" in response.content
        assert fake.call_count == 1
    
    def test_chat_with_image_base64(self):
        """FakeVisionLLM generates response for base64-based image."""
        fake = FakeVisionLLM()
        base64_str = "iVBORw0KGgoAAAANSUhEUgAAAAUA"
        image = ImageInput(base64=base64_str)
        
        response = fake.chat_with_image(
            text="Analyze this",
            image=image
        )
        
        assert f"base64({len(base64_str)} chars)" in response.content
        assert fake.call_count == 1
    
    def test_chat_with_image_with_messages(self):
        """FakeVisionLLM accepts conversation history."""
        fake = FakeVisionLLM()
        messages = [
            Message(role="system", content="You are a helpful assistant"),
            Message(role="user", content="Previous question")
        ]
        image = ImageInput(path="test.png")
        
        response = fake.chat_with_image(
            text="New question",
            image=image,
            messages=messages
        )
        
        assert response.content is not None
        assert fake.last_messages == messages
    
    def test_chat_with_image_validates_text(self):
        """FakeVisionLLM validates text input."""
        fake = FakeVisionLLM()
        image = ImageInput(path="test.png")
        
        with pytest.raises(ValueError, match="Text prompt cannot be empty"):
            fake.chat_with_image(text="", image=image)
    
    def test_chat_with_image_validates_image(self):
        """FakeVisionLLM validates image input."""
        fake = FakeVisionLLM()
        
        with pytest.raises(ValueError, match="Image must be an ImageInput instance"):
            fake.chat_with_image(text="test", image="not_an_image")  # type: ignore
    
    def test_custom_response_template(self):
        """FakeVisionLLM accepts custom response template."""
        fake = FakeVisionLLM(response_template="Custom: {text}")
        image = ImageInput(path="test.png")
        
        response = fake.chat_with_image(text="Hello", image=image)
        
        assert response.content == "Custom: Hello"


# ================================
# Test Vision LLM Factory
# ================================

class TestVisionLLMFactory:
    """Test the Vision LLM factory pattern."""
    
    def setup_method(self):
        """Clean up registry before each test."""
        LLMFactory._VISION_PROVIDERS.clear()
    
    def test_register_vision_provider_success(self):
        """register_vision_provider registers valid provider."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        assert "fake" in LLMFactory._VISION_PROVIDERS
        assert LLMFactory._VISION_PROVIDERS["fake"] == FakeVisionLLM
    
    def test_register_vision_provider_case_insensitive(self):
        """register_vision_provider normalizes provider name to lowercase."""
        LLMFactory.register_vision_provider("FakeVision", FakeVisionLLM)
        
        assert "fakevision" in LLMFactory._VISION_PROVIDERS
        assert "FakeVision" not in LLMFactory._VISION_PROVIDERS
    
    def test_register_vision_provider_invalid_class(self):
        """register_vision_provider rejects non-BaseVisionLLM class."""
        class NotAVisionLLM:
            pass
        
        with pytest.raises(ValueError, match="must inherit from BaseVisionLLM"):
            LLMFactory.register_vision_provider("invalid", NotAVisionLLM)  # type: ignore
    
    def test_list_vision_providers_empty(self):
        """list_vision_providers returns empty list when no providers registered."""
        assert LLMFactory.list_vision_providers() == []
    
    def test_list_vision_providers_sorted(self):
        """list_vision_providers returns sorted provider names."""
        LLMFactory.register_vision_provider("zebra", FakeVisionLLM)
        LLMFactory.register_vision_provider("alpha", FakeVisionLLM)
        LLMFactory.register_vision_provider("beta", FakeVisionLLM)
        
        providers = LLMFactory.list_vision_providers()
        assert providers == ["alpha", "beta", "zebra"]
    
    def test_create_vision_llm_success(self):
        """create_vision_llm creates instance from vision_llm config."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        # Mock settings with vision_llm section
        class FakeSettings:
            class VisionLLM:
                provider = "fake"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        vision_llm = LLMFactory.create_vision_llm(settings)
        
        assert isinstance(vision_llm, FakeVisionLLM)
        assert vision_llm.settings == settings
    
    def test_create_vision_llm_fallback_to_llm_config(self):
        """create_vision_llm falls back to llm.provider if vision_llm not present."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        # Mock settings with only llm section (no vision_llm)
        class FakeSettings:
            class LLM:
                provider = "fake"
            llm = LLM()
        
        settings = FakeSettings()
        vision_llm = LLMFactory.create_vision_llm(settings)
        
        assert isinstance(vision_llm, FakeVisionLLM)
    
    def test_create_vision_llm_case_insensitive(self):
        """create_vision_llm handles case-insensitive provider names."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        class FakeSettings:
            class VisionLLM:
                provider = "FAKE"  # Uppercase
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        vision_llm = LLMFactory.create_vision_llm(settings)
        
        assert isinstance(vision_llm, FakeVisionLLM)
    
    def test_create_vision_llm_unknown_provider(self):
        """create_vision_llm raises error for unknown provider."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        class FakeSettings:
            class VisionLLM:
                provider = "unknown"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        
        with pytest.raises(ValueError, match="Unsupported Vision LLM provider: 'unknown'"):
            LLMFactory.create_vision_llm(settings)
    
    def test_create_vision_llm_missing_config(self):
        """create_vision_llm raises error if config is missing."""
        class FakeSettings:
            pass  # No vision_llm or llm section
        
        settings = FakeSettings()
        
        with pytest.raises(ValueError, match="Missing required configuration"):
            LLMFactory.create_vision_llm(settings)
    
    def test_create_vision_llm_no_providers_registered(self):
        """create_vision_llm shows available: none when registry is empty."""
        class FakeSettings:
            class VisionLLM:
                provider = "fake"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        
        with pytest.raises(ValueError, match="Available Vision LLM providers: none"):
            LLMFactory.create_vision_llm(settings)
    
    def test_create_vision_llm_with_overrides(self):
        """create_vision_llm passes override kwargs to provider."""
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
        
        class FakeSettings:
            class VisionLLM:
                provider = "fake"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        vision_llm = LLMFactory.create_vision_llm(
            settings,
            response_template="Override: {text}"
        )
        
        assert isinstance(vision_llm, FakeVisionLLM)
        assert vision_llm.response_template == "Override: {text}"
    
    def test_create_vision_llm_provider_instantiation_failure(self):
        """create_vision_llm handles provider instantiation errors."""
        class BrokenVisionLLM(BaseVisionLLM):
            def __init__(self, settings, **kwargs):
                raise RuntimeError("Intentional failure")
            
            def chat_with_image(self, text, image, messages=None, trace=None, **kwargs):
                pass
        
        LLMFactory.register_vision_provider("broken", BrokenVisionLLM)
        
        class FakeSettings:
            class VisionLLM:
                provider = "broken"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        
        with pytest.raises(RuntimeError, match="Failed to instantiate Vision LLM provider 'broken'"):
            LLMFactory.create_vision_llm(settings)


# ================================
# Integration Tests
# ================================

class TestVisionLLMIntegration:
    """Integration tests combining factory and implementation."""
    
    def setup_method(self):
        """Clean up registry and register fake provider."""
        LLMFactory._VISION_PROVIDERS.clear()
        LLMFactory.register_vision_provider("fake", FakeVisionLLM)
    
    def test_end_to_end_vision_workflow(self):
        """Full workflow: create from factory -> call vision method."""
        class FakeSettings:
            class VisionLLM:
                provider = "fake"
            vision_llm = VisionLLM()
        
        settings = FakeSettings()
        
        # Create Vision LLM from factory
        vision_llm = LLMFactory.create_vision_llm(settings)
        
        # Use it for image captioning
        image = ImageInput(path="document.pdf.page1.png")
        response = vision_llm.chat_with_image(
            text="Describe the main content of this page",
            image=image
        )
        
        assert "Describe the main content" in response.content
        assert "document.pdf.page1.png" in response.content
        assert response.model == "fake-vision-model"
