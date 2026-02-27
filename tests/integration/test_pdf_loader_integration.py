"""Integration tests for PDF Loader using real PDF files.

These tests use actual PDF files from fixtures/sample_documents to verify
end-to-end functionality of the PDF loader.
"""

from pathlib import Path

import pytest

from src.core.types import Document
from src.libs.loader.pdf_loader import PdfLoader


# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_documents"
SIMPLE_PDF = FIXTURES_DIR / "simple.pdf"
IMAGES_PDF = FIXTURES_DIR / "with_images.pdf"


class TestPdfLoaderWithRealFiles:
    """Integration tests using real PDF files."""
    
    def test_simple_pdf_exists(self):
        """Verify test fixture exists."""
        assert SIMPLE_PDF.exists(), f"Test fixture not found: {SIMPLE_PDF}"
    
    def test_images_pdf_exists(self):
        """Verify test fixture with images exists."""
        assert IMAGES_PDF.exists(), f"Test fixture not found: {IMAGES_PDF}"
    
    def test_load_simple_pdf(self):
        """Load a simple text-only PDF and verify Document structure."""
        loader = PdfLoader()
        doc = loader.load(SIMPLE_PDF)
        
        # Verify Document structure
        assert isinstance(doc, Document)
        assert doc.id.startswith("doc_")
        assert len(doc.text) > 0
        
        # Verify required metadata
        assert doc.metadata["source_path"] == str(SIMPLE_PDF)
        assert doc.metadata["doc_type"] == "pdf"
        assert "doc_hash" in doc.metadata
        
        # Verify title extraction (the PDF has "Sample Document" as title)
        assert "title" in doc.metadata
        assert len(doc.metadata["title"]) > 0
        assert "sample" in doc.metadata["title"].lower() or "document" in doc.metadata["title"].lower()
        
        # Verify text content contains expected keywords
        assert "sample" in doc.text.lower() or "test" in doc.text.lower()
    
    def test_load_pdf_with_images(self):
        """Load a PDF with images and verify Document structure."""
        loader = PdfLoader(extract_images=True)
        doc = loader.load(IMAGES_PDF)
        
        # Verify Document structure
        assert isinstance(doc, Document)
        assert doc.id.startswith("doc_")
        assert len(doc.text) > 0
        
        # Verify required metadata
        assert doc.metadata["source_path"] == str(IMAGES_PDF)
        assert doc.metadata["doc_type"] == "pdf"
        assert "doc_hash" in doc.metadata
        
        # Note: Current implementation returns empty images list (stub)
        # Full image extraction will be implemented later
        if "images" in doc.metadata:
            assert isinstance(doc.metadata["images"], list)
    
    def test_load_simple_pdf_without_image_extraction(self):
        """Load PDF with image extraction disabled."""
        loader = PdfLoader(extract_images=False)
        doc = loader.load(SIMPLE_PDF)
        
        assert isinstance(doc, Document)
        assert doc.metadata["doc_type"] == "pdf"
        # Should not have images metadata when extraction is disabled
        assert "images" not in doc.metadata or doc.metadata.get("images") == []
    
    def test_document_is_serializable(self):
        """Verify loaded Document can be serialized to dict/JSON."""
        loader = PdfLoader()
        doc = loader.load(SIMPLE_PDF)
        
        doc_dict = doc.to_dict()
        assert isinstance(doc_dict, dict)
        assert "id" in doc_dict
        assert "text" in doc_dict
        assert "metadata" in doc_dict
        
        # Verify can recreate from dict
        doc_recreated = Document.from_dict(doc_dict)
        assert doc_recreated.id == doc.id
        assert doc_recreated.text == doc.text
    
    def test_file_hash_consistency(self):
        """Verify same file produces same hash."""
        loader = PdfLoader()
        
        doc1 = loader.load(SIMPLE_PDF)
        doc2 = loader.load(SIMPLE_PDF)
        
        # Same file should produce same doc_hash
        assert doc1.metadata["doc_hash"] == doc2.metadata["doc_hash"]
    
    def test_different_files_different_hash(self):
        """Verify different files produce different hashes."""
        loader = PdfLoader()
        
        doc1 = loader.load(SIMPLE_PDF)
        doc2 = loader.load(IMAGES_PDF)
        
        # Different files should produce different hashes
        assert doc1.metadata["doc_hash"] != doc2.metadata["doc_hash"]
    
    def test_custom_image_storage_dir(self):
        """Verify custom image storage directory is respected."""
        custom_dir = "custom/images"
        loader = PdfLoader(extract_images=True, image_storage_dir=custom_dir)
        
        assert loader.image_storage_dir == Path(custom_dir)
