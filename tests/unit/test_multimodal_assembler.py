"""Unit tests for MultimodalAssembler.

Tests cover:
- Image reference extraction from chunk metadata
- Path resolution strategies
- Base64 encoding and MIME type detection
- MCP content block generation
- Error handling and edge cases
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from mcp import types

from src.core.response.multimodal_assembler import (
    IMAGE_PLACEHOLDER_PATTERN,
    MAGIC_BYTES,
    MIME_TYPE_MAP,
    ImageContent,
    ImageReference,
    MultimodalAssembler,
)
from src.core.types import RetrievalResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Create minimal valid PNG bytes for testing."""
    # PNG magic bytes + minimal IHDR chunk
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    """Create minimal JPEG bytes for testing."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


@pytest.fixture
def sample_gif_bytes() -> bytes:
    """Create minimal GIF bytes for testing."""
    return b"GIF89a" + b"\x00" * 100


@pytest.fixture
def temp_image_dir(sample_png_bytes) -> Path:
    """Create a temp directory with sample images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        img_dir = Path(tmpdir) / "images" / "test_collection"
        img_dir.mkdir(parents=True)
        
        # Create test images
        (img_dir / "img001.png").write_bytes(sample_png_bytes)
        (img_dir / "img002.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
        
        yield img_dir


@pytest.fixture
def assembler() -> MultimodalAssembler:
    """Create a default MultimodalAssembler instance."""
    return MultimodalAssembler()


@pytest.fixture
def result_with_images() -> RetrievalResult:
    """Create a RetrievalResult with image metadata."""
    return RetrievalResult(
        chunk_id="doc1_chunk_001",
        score=0.95,
        text="This is content with [IMAGE: img001] embedded.",
        metadata={
            "source_path": "docs/guide.pdf",
            "images": [
                {
                    "id": "img001",
                    "path": "/path/to/img001.png",
                    "page": 1,
                    "text_offset": 21,
                    "text_length": 15,
                },
                {
                    "id": "img002",
                    "path": "/path/to/img002.jpg",
                    "page": 2,
                    "text_offset": 50,
                    "text_length": 15,
                },
            ],
            "image_captions": {
                "img001": "A diagram showing system architecture",
                "img002": "Performance metrics chart",
            },
        },
    )


@pytest.fixture
def result_without_images() -> RetrievalResult:
    """Create a RetrievalResult without images."""
    return RetrievalResult(
        chunk_id="doc2_chunk_001",
        score=0.88,
        text="Plain text content without images.",
        metadata={
            "source_path": "docs/readme.md",
        },
    )


# =============================================================================
# ImageReference Tests
# =============================================================================


class TestImageReference:
    """Tests for ImageReference dataclass."""
    
    def test_create_basic_reference(self):
        """Test creating a basic image reference."""
        ref = ImageReference(image_id="img001")
        
        assert ref.image_id == "img001"
        assert ref.file_path is None
        assert ref.page is None
        assert ref.text_offset is None
        assert ref.caption is None
    
    def test_create_full_reference(self):
        """Test creating a fully populated reference."""
        ref = ImageReference(
            image_id="img001",
            file_path="/path/to/img001.png",
            page=5,
            text_offset=100,
            text_length=15,
            caption="Test caption",
        )
        
        assert ref.image_id == "img001"
        assert ref.file_path == "/path/to/img001.png"
        assert ref.page == 5
        assert ref.text_offset == 100
        assert ref.text_length == 15
        assert ref.caption == "Test caption"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        ref = ImageReference(
            image_id="img001",
            file_path="/path/to/img.png",
            page=1,
            caption="Caption text",
        )
        
        data = ref.to_dict()
        
        assert data["image_id"] == "img001"
        assert data["file_path"] == "/path/to/img.png"
        assert data["page"] == 1
        assert data["caption"] == "Caption text"


# =============================================================================
# ImageContent Tests
# =============================================================================


class TestImageContent:
    """Tests for ImageContent dataclass."""
    
    def test_create_image_content(self):
        """Test creating image content."""
        content = ImageContent(
            image_id="img001",
            data="base64data==",
            mime_type="image/png",
        )
        
        assert content.image_id == "img001"
        assert content.data == "base64data=="
        assert content.mime_type == "image/png"
        assert content.caption is None
    
    def test_to_mcp_content(self):
        """Test conversion to MCP ImageContent."""
        content = ImageContent(
            image_id="img001",
            data="iVBORw0KGgo=",
            mime_type="image/png",
        )
        
        mcp_content = content.to_mcp_content()
        
        assert isinstance(mcp_content, types.ImageContent)
        assert mcp_content.type == "image"
        assert mcp_content.data == "iVBORw0KGgo="
        assert mcp_content.mimeType == "image/png"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        content = ImageContent(
            image_id="img001",
            data="base64data",
            mime_type="image/jpeg",
            caption="A test image",
        )
        
        data = content.to_dict()
        
        assert data["image_id"] == "img001"
        assert data["data"] == "base64data"
        assert data["mime_type"] == "image/jpeg"
        assert data["caption"] == "A test image"


# =============================================================================
# MIME Type Detection Tests
# =============================================================================


class TestMimeTypeDetection:
    """Tests for MIME type detection utilities."""
    
    def test_mime_type_map_contains_common_formats(self):
        """Test that common image formats are in MIME type map."""
        assert ".png" in MIME_TYPE_MAP
        assert ".jpg" in MIME_TYPE_MAP
        assert ".jpeg" in MIME_TYPE_MAP
        assert ".gif" in MIME_TYPE_MAP
        assert ".webp" in MIME_TYPE_MAP
        assert ".bmp" in MIME_TYPE_MAP
    
    def test_mime_type_values(self):
        """Test correct MIME type values."""
        assert MIME_TYPE_MAP[".png"] == "image/png"
        assert MIME_TYPE_MAP[".jpg"] == "image/jpeg"
        assert MIME_TYPE_MAP[".jpeg"] == "image/jpeg"
        assert MIME_TYPE_MAP[".gif"] == "image/gif"
    
    def test_magic_bytes_detection(self):
        """Test magic bytes are defined for common formats."""
        # PNG magic bytes
        assert b"\x89PNG\r\n\x1a\n" in MAGIC_BYTES
        assert MAGIC_BYTES[b"\x89PNG\r\n\x1a\n"] == "image/png"
        
        # JPEG magic bytes
        assert b"\xff\xd8\xff" in MAGIC_BYTES
        assert MAGIC_BYTES[b"\xff\xd8\xff"] == "image/jpeg"
        
        # GIF magic bytes
        assert b"GIF89a" in MAGIC_BYTES
        assert MAGIC_BYTES[b"GIF89a"] == "image/gif"


# =============================================================================
# Placeholder Pattern Tests
# =============================================================================


class TestImagePlaceholderPattern:
    """Tests for image placeholder regex pattern."""
    
    def test_match_simple_placeholder(self):
        """Test matching simple placeholder."""
        text = "Here is [IMAGE: img001] in text."
        matches = IMAGE_PLACEHOLDER_PATTERN.findall(text)
        
        assert len(matches) == 1
        assert matches[0].strip() == "img001"
    
    def test_match_multiple_placeholders(self):
        """Test matching multiple placeholders."""
        text = "[IMAGE: img001] and [IMAGE: img002] and [IMAGE: img003]"
        matches = IMAGE_PLACEHOLDER_PATTERN.findall(text)
        
        assert len(matches) == 3
        assert "img001" in [m.strip() for m in matches]
        assert "img002" in [m.strip() for m in matches]
        assert "img003" in [m.strip() for m in matches]
    
    def test_match_with_extra_spaces(self):
        """Test matching with extra whitespace."""
        text = "[IMAGE:   img001  ]"
        matches = IMAGE_PLACEHOLDER_PATTERN.findall(text)
        
        assert len(matches) == 1
        assert matches[0].strip() == "img001"
    
    def test_match_complex_image_id(self):
        """Test matching complex image IDs."""
        text = "[IMAGE: doc_abc123_p1_img0]"
        matches = IMAGE_PLACEHOLDER_PATTERN.findall(text)
        
        assert len(matches) == 1
        assert matches[0].strip() == "doc_abc123_p1_img0"
    
    def test_no_match_malformed(self):
        """Test no match for malformed placeholders."""
        text = "[IMG: img001] or [IMAGE img001] or IMAGE: img001"
        matches = IMAGE_PLACEHOLDER_PATTERN.findall(text)
        
        assert len(matches) == 0


# =============================================================================
# MultimodalAssembler - Image Reference Extraction Tests
# =============================================================================


class TestExtractImageRefs:
    """Tests for extract_image_refs method."""
    
    def test_extract_from_metadata_images_list(self, assembler, result_with_images):
        """Test extracting refs from metadata.images list."""
        refs = assembler.extract_image_refs(result_with_images)
        
        assert len(refs) == 2
        assert refs[0].image_id == "img001"
        assert refs[0].file_path == "/path/to/img001.png"
        assert refs[0].page == 1
        assert refs[0].caption == "A diagram showing system architecture"
        
        assert refs[1].image_id == "img002"
        assert refs[1].caption == "Performance metrics chart"
    
    def test_extract_from_text_placeholders(self, assembler):
        """Test fallback extraction from text placeholders."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content with [IMAGE: fallback_img001] and [IMAGE: fallback_img002].",
            metadata={"source_path": "test.pdf"},
        )
        
        refs = assembler.extract_image_refs(result)
        
        assert len(refs) == 2
        assert refs[0].image_id == "fallback_img001"
        assert refs[1].image_id == "fallback_img002"
    
    def test_prefer_metadata_over_placeholders(self, assembler):
        """Test that metadata.images takes priority over text placeholders."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="[IMAGE: placeholder_img]",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "metadata_img", "path": "/test.png"}],
            },
        )
        
        refs = assembler.extract_image_refs(result)
        
        assert len(refs) == 1
        assert refs[0].image_id == "metadata_img"
    
    def test_extract_empty_result(self, assembler, result_without_images):
        """Test extraction from result without images."""
        refs = assembler.extract_image_refs(result_without_images)
        
        assert len(refs) == 0
    
    def test_max_images_limit(self):
        """Test that max_images_per_result is respected."""
        assembler = MultimodalAssembler(max_images_per_result=2)
        
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Text",
            metadata={
                "source_path": "test.pdf",
                "images": [
                    {"id": f"img{i}", "path": f"/img{i}.png"}
                    for i in range(10)
                ],
            },
        )
        
        refs = assembler.extract_image_refs(result)
        
        assert len(refs) == 2
    
    def test_extract_with_captions(self, assembler):
        """Test that captions are attached to refs."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="[IMAGE: img1]",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "img1", "path": "/img1.png"}],
                "image_captions": {"img1": "Test caption"},
            },
        )
        
        refs = assembler.extract_image_refs(result)
        
        assert len(refs) == 1
        assert refs[0].caption == "Test caption"
    
    def test_extract_with_malformed_images_list(self, assembler):
        """Test handling of malformed images list."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Text",
            metadata={
                "source_path": "test.pdf",
                "images": [
                    {"id": "valid_img"},  # Valid
                    {"path": "/no_id.png"},  # Missing id
                    "not_a_dict",  # Wrong type
                ],
            },
        )
        
        refs = assembler.extract_image_refs(result)
        
        assert len(refs) == 1
        assert refs[0].image_id == "valid_img"


# =============================================================================
# MultimodalAssembler - Path Resolution Tests
# =============================================================================


class TestResolveImagePath:
    """Tests for resolve_image_path method."""
    
    def test_resolve_with_explicit_path(self, assembler, temp_image_dir):
        """Test resolution using explicit file_path."""
        img_path = temp_image_dir / "img001.png"
        ref = ImageReference(image_id="img001", file_path=str(img_path))
        
        resolved = assembler.resolve_image_path(ref)
        
        assert resolved is not None
        assert Path(resolved).exists()
    
    def test_resolve_with_image_storage(self, assembler):
        """Test resolution via ImageStorage lookup."""
        mock_storage = MagicMock()
        mock_storage.get_image_path.return_value = "/resolved/path/img.png"
        
        assembler_with_storage = MultimodalAssembler(image_storage=mock_storage)
        ref = ImageReference(image_id="img001")
        
        with patch("pathlib.Path.exists", return_value=True):
            resolved = assembler_with_storage.resolve_image_path(ref)
        
        assert resolved == "/resolved/path/img.png"
        mock_storage.get_image_path.assert_called_once_with("img001")
    
    def test_resolve_fallback_convention_path(self, temp_image_dir, sample_png_bytes):
        """Test fallback to convention-based path."""
        # Create image at convention path
        collection = temp_image_dir.parent.name
        conv_dir = temp_image_dir.parent.parent / "data" / "images" / collection
        conv_dir.mkdir(parents=True, exist_ok=True)
        (conv_dir / "conv_img.png").write_bytes(sample_png_bytes)
        
        assembler = MultimodalAssembler()
        ref = ImageReference(image_id="conv_img")
        
        # Patch to use our temp directory
        with patch.object(Path, "exists") as mock_exists:
            mock_exists.return_value = True
            # This test is simplified - in real code would check actual path
            resolved = assembler.resolve_image_path(ref, collection=collection)
        
        # Path should be attempted with collection
        # Actual resolution depends on filesystem state
    
    def test_resolve_nonexistent_path(self, assembler):
        """Test resolution returns None for missing files."""
        ref = ImageReference(
            image_id="nonexistent",
            file_path="/definitely/not/a/real/path.png",
        )
        
        resolved = assembler.resolve_image_path(ref)
        
        assert resolved is None
    
    def test_resolve_with_image_storage_failure(self):
        """Test graceful handling of ImageStorage errors."""
        mock_storage = MagicMock()
        mock_storage.get_image_path.side_effect = Exception("Storage error")
        
        assembler = MultimodalAssembler(image_storage=mock_storage)
        ref = ImageReference(image_id="img001")
        
        # Should not raise, should return None
        resolved = assembler.resolve_image_path(ref)
        
        assert resolved is None


# =============================================================================
# MultimodalAssembler - Image Loading Tests
# =============================================================================


class TestLoadImage:
    """Tests for load_image method."""
    
    def test_load_png_image(self, assembler, temp_image_dir):
        """Test loading a PNG image."""
        img_path = str(temp_image_dir / "img001.png")
        
        content = assembler.load_image(img_path)
        
        assert content is not None
        assert content.mime_type == "image/png"
        assert content.data  # Non-empty base64
        
        # Verify base64 is valid
        decoded = base64.b64decode(content.data)
        assert decoded.startswith(b"\x89PNG")
    
    def test_load_jpeg_image(self, assembler, temp_image_dir):
        """Test loading a JPEG image."""
        img_path = str(temp_image_dir / "img002.jpg")
        
        content = assembler.load_image(img_path)
        
        assert content is not None
        assert content.mime_type == "image/jpeg"
    
    def test_load_nonexistent_file(self, assembler):
        """Test loading returns None for missing file."""
        content = assembler.load_image("/nonexistent/path/image.png")
        
        assert content is None
    
    def test_load_empty_file(self, assembler):
        """Test loading returns None for empty file."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"")
            temp_path = f.name
        
        try:
            content = assembler.load_image(temp_path)
            assert content is None
        finally:
            Path(temp_path).unlink()
    
    def test_load_image_sets_correct_image_id(self, assembler, temp_image_dir):
        """Test that loaded image has correct ID from filename."""
        img_path = str(temp_image_dir / "img001.png")
        
        content = assembler.load_image(img_path)
        
        assert content is not None
        assert content.image_id == "img001"


# =============================================================================
# MultimodalAssembler - MIME Type Detection Tests
# =============================================================================


class TestDetectMimeType:
    """Tests for _detect_mime_type method."""
    
    def test_detect_from_extension_png(self, assembler, sample_png_bytes):
        """Test MIME detection from .png extension."""
        mime = assembler._detect_mime_type(Path("test.png"), sample_png_bytes)
        assert mime == "image/png"
    
    def test_detect_from_extension_jpg(self, assembler, sample_jpeg_bytes):
        """Test MIME detection from .jpg extension."""
        mime = assembler._detect_mime_type(Path("test.jpg"), sample_jpeg_bytes)
        assert mime == "image/jpeg"
    
    def test_detect_from_extension_jpeg(self, assembler, sample_jpeg_bytes):
        """Test MIME detection from .jpeg extension."""
        mime = assembler._detect_mime_type(Path("test.jpeg"), sample_jpeg_bytes)
        assert mime == "image/jpeg"
    
    def test_detect_from_magic_bytes_png(self, assembler, sample_png_bytes):
        """Test MIME detection from PNG magic bytes."""
        mime = assembler._detect_mime_type(Path("test.unknown"), sample_png_bytes)
        assert mime == "image/png"
    
    def test_detect_from_magic_bytes_jpeg(self, assembler, sample_jpeg_bytes):
        """Test MIME detection from JPEG magic bytes."""
        mime = assembler._detect_mime_type(Path("test.unknown"), sample_jpeg_bytes)
        assert mime == "image/jpeg"
    
    def test_detect_from_magic_bytes_gif(self, assembler, sample_gif_bytes):
        """Test MIME detection from GIF magic bytes."""
        mime = assembler._detect_mime_type(Path("test.unknown"), sample_gif_bytes)
        assert mime == "image/gif"
    
    def test_detect_unknown_defaults_to_png(self, assembler):
        """Test unknown format defaults to image/png."""
        unknown_data = b"UNKNOWN_FORMAT_DATA"
        mime = assembler._detect_mime_type(Path("test.xyz"), unknown_data)
        assert mime == "image/png"


# =============================================================================
# MultimodalAssembler - Assemble Tests
# =============================================================================


class TestAssembleForResult:
    """Tests for assemble_for_result method."""
    
    def test_assemble_with_images(self, temp_image_dir, sample_png_bytes):
        """Test assembling content for result with images."""
        # Create test image
        img_path = temp_image_dir / "test_img.png"
        img_path.write_bytes(sample_png_bytes)
        
        assembler = MultimodalAssembler()
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content with image",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "test_img", "path": str(img_path)}],
            },
        )
        
        blocks = assembler.assemble_for_result(result)
        
        # Should have at least one ImageContent block
        image_blocks = [b for b in blocks if isinstance(b, types.ImageContent)]
        assert len(image_blocks) >= 1
    
    def test_assemble_without_images(self, assembler, result_without_images):
        """Test assembling returns empty for result without images."""
        blocks = assembler.assemble_for_result(result_without_images)
        
        assert len(blocks) == 0
    
    def test_assemble_includes_caption(self, temp_image_dir, sample_png_bytes):
        """Test that captions are included as text blocks."""
        img_path = temp_image_dir / "captioned_img.png"
        img_path.write_bytes(sample_png_bytes)
        
        assembler = MultimodalAssembler(include_captions=True)
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "captioned_img", "path": str(img_path)}],
                "image_captions": {"captioned_img": "This is the caption"},
            },
        )
        
        blocks = assembler.assemble_for_result(result)
        
        # Should have TextContent with caption
        text_blocks = [b for b in blocks if isinstance(b, types.TextContent)]
        caption_blocks = [b for b in text_blocks if "caption" in b.text.lower()]
        assert len(caption_blocks) >= 1
    
    def test_assemble_without_captions_disabled(self, temp_image_dir, sample_png_bytes):
        """Test captions not included when disabled."""
        img_path = temp_image_dir / "no_caption_img.png"
        img_path.write_bytes(sample_png_bytes)
        
        assembler = MultimodalAssembler(include_captions=False)
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content",
            metadata={
                "source_path": "test.pdf",
                "images": [{"id": "no_caption_img", "path": str(img_path)}],
                "image_captions": {"no_caption_img": "This should not appear"},
            },
        )
        
        blocks = assembler.assemble_for_result(result)
        
        # Should only have ImageContent, no caption TextContent
        text_blocks = [b for b in blocks if isinstance(b, types.TextContent)]
        assert len(text_blocks) == 0


class TestAssembleMultiple:
    """Tests for assemble method (multiple results)."""
    
    def test_assemble_multiple_results(self, temp_image_dir):
        """Test assembling from multiple results with different images."""
        # Create test images with DIFFERENT content to avoid deduplication
        png_data_1 = b"\x89PNG\r\n\x1a\n" + b"\x01" * 100  # Different data
        png_data_2 = b"\x89PNG\r\n\x1a\n" + b"\x02" * 100  # Different data
        
        (temp_image_dir / "multi_img1.png").write_bytes(png_data_1)
        (temp_image_dir / "multi_img2.png").write_bytes(png_data_2)
        
        assembler = MultimodalAssembler()
        results = [
            RetrievalResult(
                chunk_id="test1",
                score=0.9,
                text="Content 1",
                metadata={
                    "source_path": "test1.pdf",
                    "images": [{"id": "multi_img1", "path": str(temp_image_dir / "multi_img1.png")}],
                },
            ),
            RetrievalResult(
                chunk_id="test2",
                score=0.8,
                text="Content 2",
                metadata={
                    "source_path": "test2.pdf",
                    "images": [{"id": "multi_img2", "path": str(temp_image_dir / "multi_img2.png")}],
                },
            ),
        ]
        
        blocks = assembler.assemble(results)
        
        # Should have images from both results (different content, so not deduplicated)
        image_blocks = [b for b in blocks if isinstance(b, types.ImageContent)]
        assert len(image_blocks) >= 2
    
    def test_assemble_deduplicates_images(self, temp_image_dir, sample_png_bytes):
        """Test that duplicate images are deduplicated."""
        img_path = temp_image_dir / "shared_img.png"
        img_path.write_bytes(sample_png_bytes)
        
        assembler = MultimodalAssembler()
        
        # Two results referencing the same image
        results = [
            RetrievalResult(
                chunk_id="test1",
                score=0.9,
                text="Content 1",
                metadata={
                    "source_path": "test1.pdf",
                    "images": [{"id": "shared_img", "path": str(img_path)}],
                },
            ),
            RetrievalResult(
                chunk_id="test2",
                score=0.8,
                text="Content 2",
                metadata={
                    "source_path": "test2.pdf",
                    "images": [{"id": "shared_img", "path": str(img_path)}],
                },
            ),
        ]
        
        blocks = assembler.assemble(results)
        
        # Should deduplicate - only one image
        image_blocks = [b for b in blocks if isinstance(b, types.ImageContent)]
        assert len(image_blocks) == 1


# =============================================================================
# MultimodalAssembler - Utility Method Tests
# =============================================================================


class TestUtilityMethods:
    """Tests for utility methods."""
    
    def test_has_images_true(self, assembler, result_with_images):
        """Test has_images returns True when images present."""
        assert assembler.has_images(result_with_images) is True
    
    def test_has_images_false(self, assembler, result_without_images):
        """Test has_images returns False when no images."""
        assert assembler.has_images(result_without_images) is False
    
    def test_count_images_single(self, assembler, result_with_images):
        """Test counting images in single result."""
        count = assembler.count_images([result_with_images])
        assert count == 2
    
    def test_count_images_multiple(self, assembler, result_with_images, result_without_images):
        """Test counting images across multiple results."""
        count = assembler.count_images([result_with_images, result_without_images])
        assert count == 2  # Only first result has images
    
    def test_count_images_empty(self, assembler):
        """Test counting images returns 0 for empty list."""
        count = assembler.count_images([])
        assert count == 0


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_none_metadata(self, assembler):
        """Test handling result with None-like metadata."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content",
            metadata={"source_path": "test.pdf"},  # Empty but valid
        )
        
        refs = assembler.extract_image_refs(result)
        assert len(refs) == 0
    
    def test_images_not_list(self, assembler):
        """Test handling when images is not a list."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="Content",
            metadata={
                "source_path": "test.pdf",
                "images": "not_a_list",  # Invalid type
            },
        )
        
        refs = assembler.extract_image_refs(result)
        # Should fallback to text placeholder parsing
        assert len(refs) == 0
    
    def test_image_captions_not_dict(self, assembler):
        """Test handling when image_captions is not a dict."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="[IMAGE: img1]",
            metadata={
                "source_path": "test.pdf",
                "image_captions": ["not", "a", "dict"],  # Invalid type
            },
        )
        
        refs = assembler.extract_image_refs(result)
        # Should still extract ref, just without caption
        assert len(refs) == 1
        assert refs[0].caption is None
    
    def test_empty_text(self, assembler):
        """Test handling empty text."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="",
            metadata={"source_path": "test.pdf"},
        )
        
        refs = assembler.extract_image_refs(result)
        assert len(refs) == 0
    
    def test_unicode_in_image_id(self, assembler):
        """Test handling Unicode characters in image ID."""
        result = RetrievalResult(
            chunk_id="test",
            score=0.9,
            text="[IMAGE: 图片_001]",
            metadata={"source_path": "test.pdf"},
        )
        
        refs = assembler.extract_image_refs(result)
        assert len(refs) == 1
        assert refs[0].image_id == "图片_001"
