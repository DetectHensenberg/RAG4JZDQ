import pytest
from pathlib import Path
from src.core.settings import load_settings
from src.core.types import Chunk
from src.ingestion.transform.image_captioner import ImageCaptioner

@pytest.mark.integration
def test_image_captioner_azure_integration():
    """Integration test for ImageCaptioner using real Azure OpenAI Vision LLM.
    
    Requires valid credentials in config/settings.yaml (configured by user).
    """
    # 1. Load Settings
    settings = load_settings("config/settings.yaml")
    
    # Skip if vision not enabled or provider not configured
    if not settings.vision_llm or not settings.vision_llm.enabled:
        pytest.skip("Vision LLM not enabled in settings")
        
    if settings.vision_llm.provider != "azure":
        pytest.skip("Test specific for Azure provider (as requested)")

    # 2. Check Test Image
    image_path = Path("tests/fixtures/sample_documents/test_vision_llm.jpg")
    if not image_path.exists():
        pytest.fail(f"Test image not found at {image_path}")
        
    # 3. Create Sample Chunk
    # Emulate a chunk that came from a loader
    chunk = Chunk(
        id="chunk_test_001",
        text="Here is an image: [IMAGE: img_001]",
        metadata={
            "source_path": str(image_path),
            "images": [
                {
                    "id": "img_001",
                    "path": str(image_path),
                    "page": 1
                }
            ]
        }
    )
    
    # 4. Initialize ImageCaptioner
    captioner = ImageCaptioner(settings=settings)
    
    # 5. Run Transform
    # This calls the real API
    processed_chunks = captioner.transform([chunk])
    
    # 6. Verify Results
    assert len(processed_chunks) == 1
    processed_chunk = processed_chunks[0]
    
    # Check text modification
    print(f"\nOriginal Text: 'Here is an image: [IMAGE: img_001]'")
    print(f"New Text: '{processed_chunk.text}'")
    
    assert "[IMAGE: img_001]" in processed_chunk.text
    assert "(Description:" in processed_chunk.text
    assert "image_captions" in processed_chunk.metadata
    assert len(processed_chunk.metadata["image_captions"]) == 1
    
    caption = processed_chunk.metadata["image_captions"][0]["caption"]
    print(f"Generated Caption: {caption}")
    assert len(caption) > 10
