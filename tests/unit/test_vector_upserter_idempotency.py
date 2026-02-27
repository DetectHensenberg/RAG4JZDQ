"""Unit tests for VectorUpserter idempotency and correctness.

Test Coverage:
1. Idempotency: Same chunk produces same ID on repeated upserts
2. Determinism: Chunk ID generation is stable and reproducible
3. Content sensitivity: Different content produces different IDs
4. Batch operations: Ordering and correctness with multiple chunks
5. Error handling: Validation and failure scenarios
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.ingestion.storage.vector_upserter import VectorUpserter
from src.core.types import Chunk
from src.core.settings import Settings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_settings():
    """Create mock Settings object with vector_store configuration."""
    settings = Mock(spec=Settings)
    settings.vector_store = Mock()
    settings.vector_store.backend = "chroma"
    settings.vector_store.persist_path = "data/db/chroma"
    return settings


@pytest.fixture
def mock_vector_store():
    """Create mock VectorStore that captures upsert calls."""
    mock_store = Mock()
    mock_store.upsert = Mock()
    return mock_store


@pytest.fixture
def upserter_with_mock_store(mock_settings, mock_vector_store):
    """Create VectorUpserter with mocked vector store."""
    with patch("src.ingestion.storage.vector_upserter.VectorStoreFactory") as mock_factory:
        mock_factory.create.return_value = mock_vector_store
        upserter = VectorUpserter(mock_settings)
        return upserter, mock_vector_store


@pytest.fixture
def sample_chunk():
    """Create a sample Chunk for testing."""
    return Chunk(
        id="temp_id",  # Will be replaced by generated ID
        text="This is a test chunk for vector storage.",
        metadata={
            "source_path": "data/documents/test.pdf",
            "chunk_index": 0,
            "source_ref": "doc_abc123",
        },
    )


@pytest.fixture
def sample_vector():
    """Create a sample embedding vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


# ============================================================================
# Chunk ID Generation Tests
# ============================================================================

def test_chunk_id_deterministic(upserter_with_mock_store, sample_chunk):
    """Test that same chunk produces same ID every time."""
    upserter, _ = upserter_with_mock_store
    
    # Generate ID multiple times
    id1 = upserter._generate_chunk_id(sample_chunk)
    id2 = upserter._generate_chunk_id(sample_chunk)
    id3 = upserter._generate_chunk_id(sample_chunk)
    
    assert id1 == id2 == id3, "Chunk ID must be deterministic"


def test_chunk_id_format(upserter_with_mock_store, sample_chunk):
    """Test that chunk ID follows expected format."""
    upserter, _ = upserter_with_mock_store
    
    chunk_id = upserter._generate_chunk_id(sample_chunk)
    
    # Format: {source_hash}_{index:04d}_{content_hash}
    parts = chunk_id.split("_")
    
    assert len(parts) == 3, "Chunk ID must have 3 parts"
    assert len(parts[0]) == 8, "Source hash must be 8 characters"
    assert parts[1] == "0000", "Index must be zero-padded to 4 digits"
    assert len(parts[2]) == 8, "Content hash must be 8 characters"


def test_chunk_id_changes_with_content(upserter_with_mock_store, sample_chunk):
    """Test that different content produces different IDs."""
    upserter, _ = upserter_with_mock_store
    
    id1 = upserter._generate_chunk_id(sample_chunk)
    
    # Modify content
    sample_chunk.text = "Different content"
    id2 = upserter._generate_chunk_id(sample_chunk)
    
    assert id1 != id2, "Different content must produce different IDs"
    
    # But source hash and index should remain same
    assert id1.split("_")[0] == id2.split("_")[0], "Source hash should be same"
    assert id1.split("_")[1] == id2.split("_")[1], "Index should be same"


def test_chunk_id_changes_with_index(upserter_with_mock_store, sample_chunk):
    """Test that different index produces different IDs."""
    upserter, _ = upserter_with_mock_store
    
    id1 = upserter._generate_chunk_id(sample_chunk)
    
    # Modify index
    sample_chunk.metadata["chunk_index"] = 5
    id2 = upserter._generate_chunk_id(sample_chunk)
    
    assert id1 != id2, "Different index must produce different IDs"
    assert id1.split("_")[1] == "0000", "First ID should have index 0000"
    assert id2.split("_")[1] == "0005", "Second ID should have index 0005"


def test_chunk_id_changes_with_source_path(upserter_with_mock_store, sample_chunk):
    """Test that different source path produces different IDs."""
    upserter, _ = upserter_with_mock_store
    
    id1 = upserter._generate_chunk_id(sample_chunk)
    
    # Modify source path
    sample_chunk.metadata["source_path"] = "data/documents/other.pdf"
    id2 = upserter._generate_chunk_id(sample_chunk)
    
    assert id1 != id2, "Different source path must produce different IDs"
    assert id1.split("_")[0] != id2.split("_")[0], "Source hash should be different"


def test_chunk_id_generation_missing_source_path(upserter_with_mock_store):
    """Test that missing source_path raises ValueError during Chunk creation."""
    upserter, _ = upserter_with_mock_store
    
    # Chunk validation will catch this during initialization
    with pytest.raises(ValueError, match="source_path"):
        chunk = Chunk(
            id="temp",
            text="Test",
            metadata={"chunk_index": 0},  # Missing source_path
        )


def test_chunk_id_generation_missing_chunk_index(upserter_with_mock_store):
    """Test that missing chunk_index raises ValueError."""
    upserter, _ = upserter_with_mock_store
    
    chunk = Chunk(
        id="temp",
        text="Test",
        metadata={"source_path": "test.pdf"},  # Missing chunk_index
    )
    
    with pytest.raises(ValueError, match="chunk_index"):
        upserter._generate_chunk_id(chunk)


# ============================================================================
# Upsert Tests
# ============================================================================

def test_upsert_single_chunk(upserter_with_mock_store, sample_chunk, sample_vector):
    """Test upserting a single chunk with vector."""
    upserter, mock_store = upserter_with_mock_store
    
    chunk_ids = upserter.upsert([sample_chunk], [sample_vector])
    
    # Verify ID returned
    assert len(chunk_ids) == 1
    assert isinstance(chunk_ids[0], str)
    
    # Verify vector store was called
    assert mock_store.upsert.called
    call_args = mock_store.upsert.call_args
    records = call_args[0][0]
    
    assert len(records) == 1
    assert records[0]["id"] == chunk_ids[0]
    assert records[0]["vector"] == sample_vector
    assert records[0]["metadata"]["text"] == sample_chunk.text


def test_upsert_multiple_chunks(upserter_with_mock_store):
    """Test upserting multiple chunks maintains order."""
    upserter, mock_store = upserter_with_mock_store
    
    chunks = [
        Chunk(
            id=f"temp{i}",
            text=f"Chunk {i}",
            metadata={"source_path": "test.pdf", "chunk_index": i},
        )
        for i in range(5)
    ]
    vectors = [[float(i)] * 5 for i in range(5)]
    
    chunk_ids = upserter.upsert(chunks, vectors)
    
    # Verify count and order
    assert len(chunk_ids) == 5
    
    # Verify vector store received correct records
    records = mock_store.upsert.call_args[0][0]
    assert len(records) == 5
    
    for i, record in enumerate(records):
        assert record["id"] == chunk_ids[i]
        assert record["vector"] == vectors[i]
        assert record["metadata"]["text"] == f"Chunk {i}"


def test_upsert_idempotency(upserter_with_mock_store, sample_chunk, sample_vector):
    """Test that repeated upserts produce same IDs."""
    upserter, mock_store = upserter_with_mock_store
    
    # First upsert
    ids1 = upserter.upsert([sample_chunk], [sample_vector])
    
    # Second upsert (same chunk)
    ids2 = upserter.upsert([sample_chunk], [sample_vector])
    
    # IDs should be identical
    assert ids1 == ids2, "Idempotent upsert must produce same IDs"


def test_upsert_preserves_metadata(upserter_with_mock_store, sample_chunk, sample_vector):
    """Test that all metadata is preserved in storage."""
    upserter, mock_store = upserter_with_mock_store
    
    # Add extra metadata
    sample_chunk.metadata["custom_field"] = "custom_value"
    sample_chunk.metadata["tags"] = ["tag1", "tag2"]
    
    upserter.upsert([sample_chunk], [sample_vector])
    
    records = mock_store.upsert.call_args[0][0]
    metadata = records[0]["metadata"]
    
    # Verify all original metadata preserved
    assert metadata["source_path"] == "data/documents/test.pdf"
    assert metadata["chunk_index"] == 0
    assert metadata["source_ref"] == "doc_abc123"
    assert metadata["custom_field"] == "custom_value"
    assert metadata["tags"] == ["tag1", "tag2"]
    
    # Verify text stored
    assert metadata["text"] == sample_chunk.text


def test_upsert_empty_chunks_raises_error(upserter_with_mock_store):
    """Test that empty chunks list raises ValueError."""
    upserter, _ = upserter_with_mock_store
    
    with pytest.raises(ValueError, match="empty chunks"):
        upserter.upsert([], [])


def test_upsert_mismatched_lengths_raises_error(upserter_with_mock_store, sample_chunk):
    """Test that mismatched chunks and vectors lengths raises error."""
    upserter, _ = upserter_with_mock_store
    
    chunks = [sample_chunk, sample_chunk]
    vectors = [[0.1, 0.2]]  # Only 1 vector for 2 chunks
    
    with pytest.raises(ValueError, match="must match"):
        upserter.upsert(chunks, vectors)


def test_upsert_vector_store_failure(upserter_with_mock_store, sample_chunk, sample_vector):
    """Test that vector store failures are properly wrapped."""
    upserter, mock_store = upserter_with_mock_store
    
    # Simulate vector store failure
    mock_store.upsert.side_effect = Exception("Connection failed")
    
    with pytest.raises(RuntimeError, match="Vector store upsert failed"):
        upserter.upsert([sample_chunk], [sample_vector])


def test_upsert_with_trace_context(upserter_with_mock_store, sample_chunk, sample_vector):
    """Test that trace context is passed to vector store."""
    upserter, mock_store = upserter_with_mock_store
    
    mock_trace = Mock()
    upserter.upsert([sample_chunk], [sample_vector], trace=mock_trace)
    
    # Verify trace was passed to vector store
    call_kwargs = mock_store.upsert.call_args[1]
    assert call_kwargs["trace"] == mock_trace


# ============================================================================
# Batch Upsert Tests
# ============================================================================

def test_upsert_batch_single_batch(upserter_with_mock_store):
    """Test upserting a single batch."""
    upserter, mock_store = upserter_with_mock_store
    
    chunks = [
        Chunk(id="t1", text="C1", metadata={"source_path": "test.pdf", "chunk_index": 0}),
        Chunk(id="t2", text="C2", metadata={"source_path": "test.pdf", "chunk_index": 1}),
    ]
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    
    batches = [(chunks, vectors)]
    chunk_ids = upserter.upsert_batch(batches)
    
    assert len(chunk_ids) == 2
    assert mock_store.upsert.call_count == 1


def test_upsert_batch_multiple_batches(upserter_with_mock_store):
    """Test upserting multiple batches preserves order."""
    upserter, mock_store = upserter_with_mock_store
    
    batch1 = (
        [
            Chunk(id="t1", text="C1", metadata={"source_path": "test.pdf", "chunk_index": 0}),
            Chunk(id="t2", text="C2", metadata={"source_path": "test.pdf", "chunk_index": 1}),
        ],
        [[0.1, 0.2], [0.3, 0.4]],
    )
    
    batch2 = (
        [
            Chunk(id="t3", text="C3", metadata={"source_path": "test.pdf", "chunk_index": 2}),
        ],
        [[0.5, 0.6]],
    )
    
    chunk_ids = upserter.upsert_batch([batch1, batch2])
    
    # Should have 3 total chunks
    assert len(chunk_ids) == 3
    
    # Should be single upsert call with flattened data
    assert mock_store.upsert.call_count == 1
    records = mock_store.upsert.call_args[0][0]
    assert len(records) == 3


def test_upsert_batch_empty_batches(upserter_with_mock_store):
    """Test that empty batches list raises error."""
    upserter, _ = upserter_with_mock_store
    
    with pytest.raises(ValueError, match="empty"):
        upserter.upsert_batch([])


# ============================================================================
# Edge Cases
# ============================================================================

def test_chunk_with_unicode_text(upserter_with_mock_store):
    """Test handling of unicode characters in chunk text."""
    upserter, mock_store = upserter_with_mock_store
    
    chunk = Chunk(
        id="temp",
        text="测试中文 🚀 émojis αβγ",
        metadata={"source_path": "test.pdf", "chunk_index": 0},
    )
    
    chunk_id = upserter._generate_chunk_id(chunk)
    
    # Should not raise, ID should be valid ASCII
    assert isinstance(chunk_id, str)
    assert chunk_id.isascii()


def test_chunk_with_long_source_path(upserter_with_mock_store):
    """Test handling of very long source paths."""
    upserter, _ = upserter_with_mock_store
    
    long_path = "a" * 500 + ".pdf"
    chunk = Chunk(
        id="temp",
        text="Test",
        metadata={"source_path": long_path, "chunk_index": 0},
    )
    
    chunk_id = upserter._generate_chunk_id(chunk)
    
    # ID should still be reasonable length (hash keeps it short)
    assert len(chunk_id) < 50


def test_chunk_with_large_index(upserter_with_mock_store):
    """Test handling of large chunk indices."""
    upserter, _ = upserter_with_mock_store
    
    chunk = Chunk(
        id="temp",
        text="Test",
        metadata={"source_path": "test.pdf", "chunk_index": 9999},
    )
    
    chunk_id = upserter._generate_chunk_id(chunk)
    
    # Index should be zero-padded to 4 digits
    assert "_9999_" in chunk_id
