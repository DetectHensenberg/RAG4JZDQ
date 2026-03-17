"""Unit tests for DocumentChunker metadata enrichment.

Tests for:
- #6: heading_path extraction
- #7: content_type, file_name, file_ext, ingested_at
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.core.types import Document
from src.ingestion.chunking.document_chunker import DocumentChunker


@pytest.fixture
def mock_settings():
    """Create mock settings for DocumentChunker."""
    settings = MagicMock()
    settings.ingestion = MagicMock()
    settings.ingestion.chunk_size = 1000
    settings.ingestion.chunk_overlap = 200
    settings.ingestion.splitter = "recursive"
    return settings


@pytest.fixture
def chunker(mock_settings):
    """Create DocumentChunker with mocked splitter."""
    with patch("src.ingestion.chunking.document_chunker.SplitterFactory") as mock_factory:
        mock_splitter = MagicMock()
        mock_factory.create.return_value = mock_splitter
        return DocumentChunker(mock_settings)


class TestHeadingPath:
    """Test heading_path extraction (#6)."""
    
    def test_single_heading(self, chunker):
        """Test single heading extraction."""
        text_fragments = ["# Introduction\n\nThis is the intro."]
        paths = chunker._build_heading_paths(text_fragments)
        
        assert len(paths) == 1
        assert paths[0] == "Introduction"
    
    def test_nested_headings(self, chunker):
        """Test nested heading hierarchy."""
        text_fragments = [
            "# Chapter 1\n\nIntro",
            "## Section 1.1\n\nContent",
            "### Subsection 1.1.1\n\nDetails",
        ]
        paths = chunker._build_heading_paths(text_fragments)
        
        assert paths[0] == "Chapter 1"
        assert paths[1] == "Chapter 1 > Section 1.1"
        assert paths[2] == "Chapter 1 > Section 1.1 > Subsection 1.1.1"
    
    def test_heading_level_reset(self, chunker):
        """Test heading level reset when same level appears."""
        text_fragments = [
            "# Chapter 1\n\nContent",
            "## Section 1.1\n\nContent",
            "## Section 1.2\n\nContent",  # Same level, should replace
        ]
        paths = chunker._build_heading_paths(text_fragments)
        
        assert paths[0] == "Chapter 1"
        assert paths[1] == "Chapter 1 > Section 1.1"
        assert paths[2] == "Chapter 1 > Section 1.2"
    
    def test_no_heading(self, chunker):
        """Test chunk without heading."""
        text_fragments = ["Just some plain text without headings."]
        paths = chunker._build_heading_paths(text_fragments)
        
        assert paths[0] == ""
    
    def test_chinese_headings(self, chunker):
        """Test Chinese heading extraction."""
        text_fragments = [
            "# 报销政策\n\n概述",
            "## 差旅报销\n\n详情",
        ]
        paths = chunker._build_heading_paths(text_fragments)
        
        assert paths[0] == "报销政策"
        assert paths[1] == "报销政策 > 差旅报销"


class TestContentType:
    """Test content_type detection (#7)."""
    
    def test_table_detection(self, chunker):
        """Test Markdown table detection."""
        text = "| Header 1 | Header 2 |\n|----------|----------|\n| Cell 1 | Cell 2 |"
        assert chunker._detect_content_type(text) == "table"
    
    def test_code_detection(self, chunker):
        """Test code block detection."""
        text = "```python\nprint('hello')\n```"
        assert chunker._detect_content_type(text) == "code"
    
    def test_numbered_list_detection(self, chunker):
        """Test numbered list detection."""
        text = "1. First item\n2. Second item\n3. Third item"
        assert chunker._detect_content_type(text) == "list"
    
    def test_bulleted_list_detection(self, chunker):
        """Test bulleted list detection."""
        text = "- Item one\n- Item two\n- Item three"
        assert chunker._detect_content_type(text) == "list"
    
    def test_plain_text(self, chunker):
        """Test plain text detection."""
        text = "This is just a paragraph of plain text without any special formatting."
        assert chunker._detect_content_type(text) == "text"


class TestFileMetadata:
    """Test file_name, file_ext, ingested_at (#7)."""
    
    def test_file_metadata_extraction(self, chunker):
        """Test file metadata extraction from source_path."""
        doc = Document(
            id="doc_123",
            text="Content",
            metadata={"source_path": "data/reports/annual_report.pdf"}
        )
        
        metadata = chunker._inherit_metadata(doc, 0, "Content", "")
        
        assert metadata["file_name"] == "annual_report"
        assert metadata["file_ext"] == "pdf"
        assert "ingested_at" in metadata
        # Verify ingested_at is valid ISO format
        datetime.fromisoformat(metadata["ingested_at"])
    
    def test_file_metadata_with_chinese_path(self, chunker):
        """Test file metadata with Chinese filename."""
        doc = Document(
            id="doc_123",
            text="Content",
            metadata={"source_path": "数据/报告/年度报告.docx"}
        )
        
        metadata = chunker._inherit_metadata(doc, 0, "Content", "")
        
        assert metadata["file_name"] == "年度报告"
        assert metadata["file_ext"] == "docx"
    
    def test_empty_source_path(self, chunker):
        """Test handling of empty source_path."""
        doc = Document(
            id="doc_123",
            text="Content",
            metadata={"source_path": ""}  # Empty but present
        )
        
        metadata = chunker._inherit_metadata(doc, 0, "Content", "")
        
        assert metadata["file_name"] == ""
        assert metadata["file_ext"] == ""


class TestInheritMetadataIntegration:
    """Test full _inherit_metadata with all new fields."""
    
    def test_all_fields_present(self, chunker):
        """Test that all new metadata fields are present."""
        doc = Document(
            id="doc_123",
            text="# Title\n\nContent",
            metadata={"source_path": "report.pdf", "doc_hash": "abc123"}
        )
        
        metadata = chunker._inherit_metadata(
            doc, 
            chunk_index=0, 
            chunk_text="# Title\n\nContent",
            heading_path="Title"
        )
        
        # Original fields
        assert metadata["source_path"] == "report.pdf"
        assert metadata["doc_hash"] == "abc123"
        
        # Existing chunk fields
        assert metadata["chunk_index"] == 0
        assert metadata["source_ref"] == "doc_123"
        
        # New fields (#6 + #7)
        assert metadata["heading_path"] == "Title"
        assert metadata["content_type"] == "text"
        assert metadata["file_name"] == "report"
        assert metadata["file_ext"] == "pdf"
        assert "ingested_at" in metadata
