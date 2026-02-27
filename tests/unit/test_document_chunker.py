"""Unit tests for DocumentChunker - Document to Chunk adapter.

This test suite validates the DocumentChunker's five core value-add features:
1. Unique and deterministic chunk ID generation
2. Complete metadata inheritance from Document to Chunk
3. chunk_index tracking for sequential position
4. source_ref establishing parent-child traceability
5. Type contract compliance (core.types.Chunk)

All tests use FakeSplitter to isolate DocumentChunker's business logic from
the underlying text splitting implementation, ensuring no external dependencies.
"""

import pytest
from unittest.mock import Mock

from src.core.types import Document, Chunk
from src.core.settings import Settings
from src.ingestion.chunking import DocumentChunker
from src.libs.splitter.base_splitter import BaseSplitter


class FakeSplitter(BaseSplitter):
    """Fake splitter for testing - returns predictable chunks.
    
    This fake implementation allows us to test DocumentChunker's business logic
    without depending on real text splitting algorithms or external libraries.
    """
    
    def __init__(self, chunk_size: int = 100, overlap: int = 0, **kwargs):
        """Initialize with ignored parameters for compatibility."""
        pass
    
    def split_text(self, text: str) -> list[str]:
        """Split text by double newlines (paragraph-based splitting)."""
        # Simple splitting for testing: split on double newlines
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]


@pytest.fixture
def fake_settings():
    """Fixture providing minimal settings for testing."""
    settings = Mock(spec=Settings)
    settings.splitter = Mock()
    settings.splitter.provider = "fake"
    settings.splitter.chunk_size = 100
    settings.splitter.overlap = 0
    return settings


@pytest.fixture
def chunker(fake_settings, monkeypatch):
    """Fixture providing DocumentChunker with FakeSplitter injected."""
    # Monkey-patch SplitterFactory to return our FakeSplitter
    from src.libs.splitter import splitter_factory
    
    original_create = splitter_factory.SplitterFactory.create
    
    def mock_create(settings):
        return FakeSplitter()
    
    monkeypatch.setattr(splitter_factory.SplitterFactory, "create", mock_create)
    
    return DocumentChunker(fake_settings)


@pytest.fixture
def sample_document():
    """Fixture providing a sample document for testing."""
    return Document(
        id="doc_sample_001",
        text="First paragraph content.\n\nSecond paragraph content.\n\nThird paragraph content.",
        metadata={
            "source_path": "data/documents/sample.pdf",
            "doc_type": "pdf",
            "title": "Sample Document",
            "page_count": 3
        }
    )


# =============================================================================
# Test 1: Chunk ID Generation - Uniqueness and Determinism
# =============================================================================

def test_chunk_ids_are_unique(chunker, sample_document):
    """Test that each chunk gets a unique ID."""
    chunks = chunker.split_document(sample_document)
    
    # Extract all chunk IDs
    chunk_ids = [chunk.id for chunk in chunks]
    
    # Verify uniqueness: no duplicates
    assert len(chunk_ids) == len(set(chunk_ids)), "Chunk IDs must be unique"


def test_chunk_ids_are_deterministic(chunker, sample_document):
    """Test that splitting the same document twice produces identical IDs."""
    # Split twice
    chunks_first = chunker.split_document(sample_document)
    chunks_second = chunker.split_document(sample_document)
    
    # Extract IDs
    ids_first = [c.id for c in chunks_first]
    ids_second = [c.id for c in chunks_second]
    
    # Verify determinism: IDs match across runs
    assert ids_first == ids_second, "Chunk IDs must be deterministic"


def test_chunk_id_format(chunker, sample_document):
    """Test that chunk IDs follow expected format: {doc_id}_{index:04d}_{hash}."""
    chunks = chunker.split_document(sample_document)
    
    for i, chunk in enumerate(chunks):
        # Expected format: doc_sample_001_0000_{hash}, doc_sample_001_0001_{hash}, etc.
        assert chunk.id.startswith(f"doc_sample_001_{i:04d}_"), \
            f"Chunk ID should start with 'doc_sample_001_{i:04d}_', got: {chunk.id}"
        
        # Hash portion should be 8 characters
        hash_part = chunk.id.split("_")[-1]
        assert len(hash_part) == 8, f"Hash should be 8 chars, got: {hash_part}"


def test_chunk_id_changes_with_content(chunker):
    """Test that chunk ID changes when content changes."""
    doc1 = Document(
        id="doc_001",
        text="Content A",
        metadata={"source_path": "file.pdf"}
    )
    doc2 = Document(
        id="doc_001",  # Same doc_id
        text="Content B",  # Different content
        metadata={"source_path": "file.pdf"}
    )
    
    chunks1 = chunker.split_document(doc1)
    chunks2 = chunker.split_document(doc2)
    
    # IDs should differ due to content hash
    assert chunks1[0].id != chunks2[0].id, \
        "Chunk ID should change when content changes"


# =============================================================================
# Test 2: Metadata Inheritance - Complete Propagation
# =============================================================================

def test_metadata_inheritance(chunker, sample_document):
    """Test that all document metadata is inherited by chunks."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        # All document metadata should be present
        assert chunk.metadata["source_path"] == "data/documents/sample.pdf"
        assert chunk.metadata["doc_type"] == "pdf"
        assert chunk.metadata["title"] == "Sample Document"
        assert chunk.metadata["page_count"] == 3


def test_metadata_independence(chunker, sample_document):
    """Test that each chunk gets its own metadata dict (not shared reference)."""
    chunks = chunker.split_document(sample_document)
    
    # Modify first chunk's metadata
    chunks[0].metadata["custom_field"] = "test_value"
    
    # Other chunks should not be affected
    assert "custom_field" not in chunks[1].metadata, \
        "Chunks should have independent metadata dicts"


def test_metadata_with_empty_document_metadata(chunker):
    """Test chunking when document has minimal metadata."""
    doc = Document(
        id="doc_minimal",
        text="Paragraph 1.\n\nParagraph 2.",
        metadata={"source_path": "minimal.txt"}  # Only required field
    )
    
    chunks = chunker.split_document(doc)
    
    # Should still work with minimal metadata
    assert len(chunks) == 2
    assert chunks[0].metadata["source_path"] == "minimal.txt"


# =============================================================================
# Test 3: chunk_index - Sequential Position Tracking
# =============================================================================

def test_chunk_index_sequential(chunker, sample_document):
    """Test that chunk_index starts at 0 and increments sequentially."""
    chunks = chunker.split_document(sample_document)
    
    # Verify sequential indices: 0, 1, 2, ...
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["chunk_index"] == i, \
            f"Chunk at position {i} should have chunk_index={i}"


def test_chunk_index_added_to_all_chunks(chunker, sample_document):
    """Test that every chunk has chunk_index field."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        assert "chunk_index" in chunk.metadata, \
            "All chunks must have chunk_index field"
        assert isinstance(chunk.metadata["chunk_index"], int), \
            "chunk_index must be an integer"


# =============================================================================
# Test 4: source_ref - Parent-Child Traceability
# =============================================================================

def test_source_ref_points_to_document(chunker, sample_document):
    """Test that source_ref correctly references parent document ID."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        assert chunk.metadata["source_ref"] == sample_document.id, \
            f"source_ref should point to document ID '{sample_document.id}'"


def test_source_ref_added_to_all_chunks(chunker, sample_document):
    """Test that every chunk has source_ref field."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        assert "source_ref" in chunk.metadata, \
            "All chunks must have source_ref field"


# =============================================================================
# Test 5: Type Contract - core.types.Chunk Compliance
# =============================================================================

def test_chunks_are_chunk_type(chunker, sample_document):
    """Test that output items are Chunk objects."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        assert isinstance(chunk, Chunk), \
            f"Output should be Chunk objects, got: {type(chunk)}"


def test_chunk_serialization(chunker, sample_document):
    """Test that chunks can be serialized to dict."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        chunk_dict = chunk.to_dict()
        
        # Verify dict structure
        assert "id" in chunk_dict
        assert "text" in chunk_dict
        assert "metadata" in chunk_dict
        assert isinstance(chunk_dict["metadata"], dict)


def test_chunk_fields_complete(chunker, sample_document):
    """Test that chunks have all required Chunk fields."""
    chunks = chunker.split_document(sample_document)
    
    for chunk in chunks:
        # Required Chunk fields
        assert hasattr(chunk, "id") and chunk.id
        assert hasattr(chunk, "text") and chunk.text
        assert hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict)


# =============================================================================
# Test 6: Configuration-Driven Behavior
# =============================================================================

def test_different_splitter_config_produces_different_chunks(fake_settings, monkeypatch):
    """Test that changing splitter config affects chunk output."""
    # This test verifies that DocumentChunker respects splitter configuration
    
    from src.libs.splitter import splitter_factory
    
    # Create two different fake splitters with different behaviors
    class SmallChunkSplitter(BaseSplitter):
        def split_text(self, text: str) -> list[str]:
            # Split by sentence (period)
            return [s.strip() + "." for s in text.split(".") if s.strip()]
    
    class LargeChunkSplitter(BaseSplitter):
        def split_text(self, text: str) -> list[str]:
            # Return entire text as one chunk
            return [text]
    
    document = Document(
        id="doc_test",
        text="First sentence. Second sentence. Third sentence.",
        metadata={"source_path": "test.txt"}
    )
    
    # Test with small chunks
    def mock_create_small(settings):
        return SmallChunkSplitter()
    
    monkeypatch.setattr(splitter_factory.SplitterFactory, "create", mock_create_small)
    chunker_small = DocumentChunker(fake_settings)
    chunks_small = chunker_small.split_document(document)
    
    # Test with large chunks
    def mock_create_large(settings):
        return LargeChunkSplitter()
    
    monkeypatch.setattr(splitter_factory.SplitterFactory, "create", mock_create_large)
    chunker_large = DocumentChunker(fake_settings)
    chunks_large = chunker_large.split_document(document)
    
    # Different configs should produce different number of chunks
    assert len(chunks_small) != len(chunks_large), \
        "Different splitter configs should produce different chunk counts"


# =============================================================================
# Test 7: Edge Cases and Error Handling
# =============================================================================

def test_empty_document_raises_error(chunker):
    """Test that empty document raises clear error."""
    doc = Document(
        id="doc_empty",
        text="",
        metadata={"source_path": "empty.txt"}
    )
    
    with pytest.raises(ValueError, match="has no text content"):
        chunker.split_document(doc)


def test_whitespace_only_document_raises_error(chunker):
    """Test that whitespace-only document raises error."""
    doc = Document(
        id="doc_whitespace",
        text="   \n\n   \t  ",
        metadata={"source_path": "whitespace.txt"}
    )
    
    with pytest.raises(ValueError, match="has no text content"):
        chunker.split_document(doc)


def test_splitter_returns_empty_list_raises_error(chunker, monkeypatch):
    """Test that if splitter returns no chunks, a clear error is raised."""
    from src.libs.splitter import splitter_factory
    
    class EmptySplitter(BaseSplitter):
        def split_text(self, text: str) -> list[str]:
            return []  # Return no chunks
    
    def mock_create(settings):
        return EmptySplitter()
    
    monkeypatch.setattr(splitter_factory.SplitterFactory, "create", mock_create)
    
    doc = Document(
        id="doc_test",
        text="Some content",
        metadata={"source_path": "test.txt"}
    )
    
    chunker_empty = DocumentChunker(chunker._settings)
    
    with pytest.raises(ValueError, match="Splitter returned no chunks"):
        chunker_empty.split_document(doc)


# =============================================================================
# Test 8: Integration Smoke Test
# =============================================================================

def test_end_to_end_smoke(chunker, sample_document):
    """Smoke test verifying complete end-to-end chunking flow."""
    # Execute full split
    chunks = chunker.split_document(sample_document)
    
    # Basic sanity checks
    assert len(chunks) > 0, "Should produce at least one chunk"
    
    # Verify each chunk passes all requirements
    for i, chunk in enumerate(chunks):
        # ID requirements
        assert chunk.id
        assert chunk.id.startswith(sample_document.id)
        
        # Text requirements
        assert chunk.text
        assert chunk.text.strip()
        
        # Metadata requirements
        assert chunk.metadata["source_path"] == sample_document.metadata["source_path"]
        assert chunk.metadata["chunk_index"] == i
        assert chunk.metadata["source_ref"] == sample_document.id
        
        # Type requirements
        assert isinstance(chunk, Chunk)
