"""Unit tests for PptxLoader, focusing on text extraction and image extraction."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.libs.loader.pptx_loader import PptxLoader

# Test fixture paths
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sample_documents"
SIMPLE_PPTX = FIXTURES_DIR / "simple.pptx"
IMAGES_PPTX = FIXTURES_DIR / "with_images.pptx"


class TestPptxLoaderInitialization:
    """Tests for PptxLoader initialization."""

    def test_default_initialization(self):
        loader = PptxLoader()
        assert loader.extract_images is True
        assert loader.vision_llm is None

    def test_custom_initialization(self, tmp_path):
        loader = PptxLoader(
            extract_images=False,
            image_storage_dir=tmp_path / "imgs",
            vision_llm=None,
        )
        assert loader.extract_images is False
        assert loader.image_storage_dir == tmp_path / "imgs"


class TestPptxLoaderValidation:
    """Tests for input validation."""

    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("hello")
        loader = PptxLoader()
        with pytest.raises(ValueError, match="Unsupported file type"):
            loader.load(f)

    def test_nonexistent_file(self):
        loader = PptxLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.pptx")


class TestPptxLoaderTextOnly:
    """Tests for text-only extraction (no Vision LLM)."""

    @pytest.fixture(autouse=True)
    def _check_fixtures(self):
        if not SIMPLE_PPTX.exists():
            pytest.skip("Test fixture simple.pptx not found. Run generate_test_pptx.py first.")

    def test_load_simple_pptx(self):
        loader = PptxLoader(extract_images=False)
        doc = loader.load(SIMPLE_PPTX)

        assert doc.id.startswith("doc_")
        assert doc.text  # non-empty
        assert doc.metadata["doc_type"] == "pptx"
        assert doc.metadata["doc_hash"]
        assert "Simple Test Slide" in doc.text
        assert "Second Slide" in doc.text

    def test_slide_count_in_metadata(self):
        loader = PptxLoader(extract_images=False)
        doc = loader.load(SIMPLE_PPTX)
        assert doc.metadata.get("slide_count") == 2

    def test_title_extraction(self):
        loader = PptxLoader(extract_images=False)
        doc = loader.load(SIMPLE_PPTX)
        assert doc.metadata.get("title") == "Simple Test Slide"

    def test_document_hash_consistency(self):
        loader = PptxLoader(extract_images=False)
        doc1 = loader.load(SIMPLE_PPTX)
        doc2 = loader.load(SIMPLE_PPTX)
        assert doc1.metadata["doc_hash"] == doc2.metadata["doc_hash"]
        assert doc1.id == doc2.id


class TestPptxLoaderImageExtraction:
    """Tests for embedded image extraction from PPTX."""

    @pytest.fixture(autouse=True)
    def _check_fixtures(self):
        if not IMAGES_PPTX.exists():
            pytest.skip("Test fixture with_images.pptx not found. Run generate_test_pptx.py first.")

    def test_images_extracted_to_disk(self, tmp_path):
        loader = PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        images = doc.metadata.get("images", [])
        assert len(images) == 3, f"Expected 3 images, got {len(images)}: {images}"

        # All image files should exist on disk
        for img_meta in images:
            p = Path(img_meta["path"])
            assert p.exists(), f"Image file not found: {p}"
            assert p.stat().st_size > 0, f"Image file is empty: {p}"

    def test_image_placeholders_in_text(self, tmp_path):
        loader = PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        images = doc.metadata.get("images", [])
        for img_meta in images:
            placeholder = f"[IMAGE: {img_meta['id']}]"
            assert placeholder in doc.text, (
                f"Placeholder '{placeholder}' not found in document text"
            )

    def test_image_metadata_structure(self, tmp_path):
        loader = PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        images = doc.metadata.get("images", [])
        for img_meta in images:
            assert "id" in img_meta
            assert "path" in img_meta
            assert "page" in img_meta
            assert "position" in img_meta
            assert "width" in img_meta["position"]
            assert "height" in img_meta["position"]
            # Dimensions should be > 0 (we created real images)
            assert img_meta["position"]["width"] > 0
            assert img_meta["position"]["height"] > 0

    def test_images_per_slide(self, tmp_path):
        """Slide 1 has 1 image, slide 2 has 2 images, slide 3 has 0 images."""
        loader = PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        images = doc.metadata.get("images", [])
        slide1_imgs = [m for m in images if m["page"] == 1]
        slide2_imgs = [m for m in images if m["page"] == 2]
        slide3_imgs = [m for m in images if m["page"] == 3]

        assert len(slide1_imgs) == 1, f"Slide 1: expected 1 image, got {len(slide1_imgs)}"
        assert len(slide2_imgs) == 2, f"Slide 2: expected 2 images, got {len(slide2_imgs)}"
        assert len(slide3_imgs) == 0, f"Slide 3: expected 0 images, got {len(slide3_imgs)}"

    def test_no_images_when_disabled(self, tmp_path):
        loader = PptxLoader(
            extract_images=False,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        assert "images" not in doc.metadata or doc.metadata.get("images") is None

    def test_text_still_extracted_with_images(self, tmp_path):
        """Even with image extraction, text content should be present."""
        loader = PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_path / "imgs",
        )
        doc = loader.load(IMAGES_PPTX)

        assert "Slide With Images" in doc.text
        assert "Two Images Here" in doc.text
        assert "Text Only Slide" in doc.text


class TestLoaderFactory:
    """Test that LoaderFactory creates the right loader for PPTX files."""

    def test_factory_creates_pptx_loader(self, tmp_path):
        from src.libs.loader.loader_factory import LoaderFactory
        f = tmp_path / "test.pptx"
        f.write_bytes(b"")
        loader = LoaderFactory.create(str(f))
        assert isinstance(loader, PptxLoader)

    def test_factory_creates_pptx_loader_for_ppt(self, tmp_path):
        from src.libs.loader.loader_factory import LoaderFactory
        f = tmp_path / "test.ppt"
        f.write_bytes(b"")
        loader = LoaderFactory.create(str(f))
        assert isinstance(loader, PptxLoader)

    def test_factory_creates_pdf_loader_for_pdf(self, tmp_path):
        from src.libs.loader.loader_factory import LoaderFactory
        from src.libs.loader.pdf_loader import PdfLoader
        f = tmp_path / "test.pdf"
        f.write_bytes(b"")
        loader = LoaderFactory.create(str(f))
        assert isinstance(loader, PdfLoader)
