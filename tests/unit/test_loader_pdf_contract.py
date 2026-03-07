"""Unit tests for PDF Loader contract and behavior.

Tests verify:
- BaseLoader abstract interface
- PdfLoader initialization and configuration
- Helper methods (hash computation, title extraction, etc.)
- Error handling for invalid inputs
- Core PDF conversion functionality using real test files

Note: Additional integration tests are in tests/integration/test_pdf_loader_integration.py
"""

from pathlib import Path

import pytest

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader
from src.libs.loader.pdf_loader import PdfLoader


# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_documents"
SIMPLE_PDF = FIXTURES_DIR / "simple.pdf"
IMAGES_PDF = FIXTURES_DIR / "with_images.pdf"


class TestBaseLoader:
    """Tests for BaseLoader abstract interface."""
    
    def test_cannot_instantiate_abstract_class(self):
        """BaseLoader cannot be instantiated directly."""
        with pytest.raises(TypeError, match="abstract"):
            BaseLoader()
    
    def test_validate_file_existing_file(self, tmp_path):
        """_validate_file returns Path for existing files."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("dummy content")
        
        # Access static method via subclass
        validated = PdfLoader._validate_file(test_file)
        assert validated.exists()
        assert validated.is_file()
    
    def test_validate_file_nonexistent(self):
        """_validate_file raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            PdfLoader._validate_file("nonexistent_file.pdf")
    
    def test_validate_file_directory(self, tmp_path):
        """_validate_file raises ValueError for directories."""
        with pytest.raises(ValueError, match="not a file"):
            PdfLoader._validate_file(tmp_path)


class TestPdfLoaderInitialization:
    """Tests for PdfLoader initialization."""
    
    def test_default_initialization(self):
        """PdfLoader can be initialized with defaults."""
        loader = PdfLoader()
        assert loader.extract_images is True
        assert loader.image_storage_dir == Path("data/images")
    
    def test_custom_initialization(self):
        """PdfLoader respects custom configuration."""
        loader = PdfLoader(
            extract_images=False,
            image_storage_dir="custom/path"
        )
        assert loader.extract_images is False
        assert loader.image_storage_dir == Path("custom/path")
    
    def test_markitdown_available(self):
        """PdfLoader requires MarkItDown to be available."""
        loader = PdfLoader()
        assert loader._markitdown is not None


class TestPdfLoaderValidation:
    """Tests for input validation."""
    
    def test_load_requires_pdf_extension(self, tmp_path):
        """load() raises ValueError for non-PDF files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        
        loader = PdfLoader()
        with pytest.raises(ValueError, match="not a PDF"):
            loader.load(txt_file)
    
    def test_load_nonexistent_file(self):
        """load() raises FileNotFoundError for missing files."""
        loader = PdfLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.pdf")


class TestPdfLoaderHelperMethods:
    """Tests for helper methods."""
    
    def test_compute_file_hash_consistency(self, tmp_path):
        """_compute_file_hash returns consistent hash for same content."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"consistent content")
        
        loader = PdfLoader()
        hash1 = loader._compute_file_hash(test_file)
        hash2 = loader._compute_file_hash(test_file)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_compute_file_hash_differs_for_different_content(self, tmp_path):
        """_compute_file_hash returns different hashes for different content."""
        file1 = tmp_path / "file1.pdf"
        file2 = tmp_path / "file2.pdf"
        file1.write_bytes(b"content 1")
        file2.write_bytes(b"content 2")
        
        loader = PdfLoader()
        hash1 = loader._compute_file_hash(file1)
        hash2 = loader._compute_file_hash(file2)
        
        assert hash1 != hash2
    
    def test_extract_title_from_markdown_heading(self):
        """_extract_title finds first Markdown heading."""
        loader = PdfLoader()
        
        text = "# Main Title\n\nParagraph text\n\n## Subtitle"
        title = loader._extract_title(text)
        assert title == "Main Title"
    
    def test_extract_title_from_first_line(self):
        """_extract_title uses first non-empty line as fallback."""
        loader = PdfLoader()
        
        text = "First Line Title\n\nParagraph text"
        title = loader._extract_title(text)
        assert title == "First Line Title"
    
    def test_extract_title_handles_empty_text(self):
        """_extract_title returns None for empty text."""
        loader = PdfLoader()
        
        text = ""
        title = loader._extract_title(text)
        assert title is None
    
    def test_generate_image_id_format(self):
        """_generate_image_id creates consistent ID format."""
        image_id = PdfLoader._generate_image_id("abc123def456", 2, 0)
        assert image_id == "abc123de_2_0"


class TestPdfConversionCore:
    """Tests for core PDF conversion functionality using real PDF files."""
    
    def test_convert_simple_pdf_to_text(self):
        """Convert simple PDF to text - verifies core Markdown conversion."""
        if not SIMPLE_PDF.exists():
            pytest.skip(f"Test fixture not found: {SIMPLE_PDF}")
        
        loader = PdfLoader()
        doc = loader.load(SIMPLE_PDF)
        
        # Verify Document structure
        assert isinstance(doc, Document)
        assert doc.id.startswith("doc_")
        
        # Verify text content is extracted
        assert len(doc.text) > 0
        assert isinstance(doc.text, str)
        
        # Verify expected content is present (from our generated PDF)
        text_lower = doc.text.lower()
        assert "sample" in text_lower or "document" in text_lower
        assert "test" in text_lower or "pdf" in text_lower
        
        # Verify metadata
        assert doc.metadata["source_path"] == str(SIMPLE_PDF)
        assert doc.metadata["doc_type"] == "pdf"
        assert "doc_hash" in doc.metadata
    
    def test_extract_title_from_pdf(self):
        """Verify title extraction from real PDF."""
        if not SIMPLE_PDF.exists():
            pytest.skip(f"Test fixture not found: {SIMPLE_PDF}")
        
        loader = PdfLoader()
        doc = loader.load(SIMPLE_PDF)
        
        # Should extract title (either from heading or first line)
        assert "title" in doc.metadata
        assert doc.metadata["title"] is not None
        assert len(doc.metadata["title"]) > 0
        
        # Title should contain relevant keywords
        title_lower = doc.metadata["title"].lower()
        assert "sample" in title_lower or "document" in title_lower
    
    def test_pdf_with_images_structure(self):
        """Verify PDF with images is processed correctly with image extraction."""
        if not IMAGES_PDF.exists():
            pytest.skip(f"Test fixture not found: {IMAGES_PDF}")
        
        loader = PdfLoader(extract_images=True)
        doc = loader.load(IMAGES_PDF)
        
        # Verify basic structure
        assert isinstance(doc, Document)
        assert len(doc.text) > 0
        
        # Verify images were extracted
        assert "images" in doc.metadata
        assert isinstance(doc.metadata["images"], list)
        
        if len(doc.metadata["images"]) > 0:
            # Verify image metadata structure
            for img in doc.metadata["images"]:
                assert "id" in img
                assert "path" in img
                assert "page" in img
                assert "text_offset" in img
                assert "text_length" in img
                assert "position" in img
                
                # Verify image file exists
                img_path = Path(img["path"])
                assert img_path.exists(), f"Image file should exist: {img_path}"
                
                # Verify placeholder exists in text
                placeholder = f"[IMAGE: {img['id']}]"
                assert placeholder in doc.text, f"Placeholder {placeholder} should be in text"
    
    def test_image_extraction_disabled(self):
        """Verify image extraction can be disabled."""
        if not IMAGES_PDF.exists():
            pytest.skip(f"Test fixture not found: {IMAGES_PDF}")
        
        loader = PdfLoader(extract_images=False)
        doc = loader.load(IMAGES_PDF)
        
        # Should still extract text
        assert len(doc.text) > 0
        
        # Should not have images metadata
        assert "images" not in doc.metadata or doc.metadata.get("images") == []
    
    def test_document_hash_consistency(self):
        """Verify same PDF produces same document hash."""
        if not SIMPLE_PDF.exists():
            pytest.skip(f"Test fixture not found: {SIMPLE_PDF}")
        
        loader = PdfLoader()
        
        # Load same file twice
        doc1 = loader.load(SIMPLE_PDF)
        doc2 = loader.load(SIMPLE_PDF)
        
        # Should produce identical hashes (for idempotency)
        assert doc1.metadata["doc_hash"] == doc2.metadata["doc_hash"]
        assert doc1.id == doc2.id
    
    def test_document_serialization(self):
        """Verify loaded document can be serialized."""
        if not SIMPLE_PDF.exists():
            pytest.skip(f"Test fixture not found: {SIMPLE_PDF}")
        
        loader = PdfLoader()
        doc = loader.load(SIMPLE_PDF)
        
        # Serialize to dict
        doc_dict = doc.to_dict()
        assert isinstance(doc_dict, dict)
        assert "id" in doc_dict
        assert "text" in doc_dict
        assert "metadata" in doc_dict
        
        # Verify metadata is complete
        assert "source_path" in doc_dict["metadata"]
        assert "doc_type" in doc_dict["metadata"]
        assert doc_dict["metadata"]["doc_type"] == "pdf"
        
        # Verify can recreate from dict
        doc_recreated = Document.from_dict(doc_dict)
        assert doc_recreated.id == doc.id
        assert doc_recreated.text == doc.text
        assert doc_recreated.metadata == doc.metadata
