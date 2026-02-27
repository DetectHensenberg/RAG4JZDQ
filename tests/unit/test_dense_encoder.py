"""Unit tests for DenseEncoder.

Tests the DenseEncoder class in isolation using mocked BaseEmbedding providers.
Validates batch processing, error handling, and output correctness.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import List

from src.ingestion.embedding.dense_encoder import DenseEncoder
from src.core.types import Chunk
from src.libs.embedding.base_embedding import BaseEmbedding


class FakeEmbedding(BaseEmbedding):
    """Fake embedding provider for testing.
    
    Returns deterministic vectors based on text length.
    """
    
    def __init__(self, dimension: int = 1536, fail_on_call: bool = False):
        self.dimension = dimension
        self.fail_on_call = fail_on_call
        self.call_count = 0
        self.call_history: List[List[str]] = []
    
    def embed(self, texts: List[str], trace=None, **kwargs) -> List[List[float]]:
        """Generate fake embeddings."""
        self.call_count += 1
        self.call_history.append(texts)
        
        if self.fail_on_call:
            raise RuntimeError("Simulated embedding failure")
        
        # Validate inputs (like real provider would)
        self.validate_texts(texts)
        
        # Generate deterministic vectors based on text length
        vectors = []
        for text in texts:
            # Use text length to create deterministic but varying vectors
            base_value = len(text) / 1000.0
            vector = [base_value + (i * 0.001) for i in range(self.dimension)]
            vectors.append(vector)
        
        return vectors


# ============================================================================
# Constructor Tests
# ============================================================================

def test_constructor_valid():
    """Test DenseEncoder initialization with valid parameters."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding, batch_size=32)
    
    assert encoder.embedding is embedding
    assert encoder.batch_size == 32


def test_constructor_default_batch_size():
    """Test DenseEncoder uses default batch_size when not specified."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding)
    
    assert encoder.batch_size == 100


def test_constructor_rejects_zero_batch_size():
    """Test that batch_size=0 is rejected."""
    embedding = FakeEmbedding()
    
    with pytest.raises(ValueError, match="batch_size must be positive"):
        DenseEncoder(embedding, batch_size=0)


def test_constructor_rejects_negative_batch_size():
    """Test that negative batch_size is rejected."""
    embedding = FakeEmbedding()
    
    with pytest.raises(ValueError, match="batch_size must be positive"):
        DenseEncoder(embedding, batch_size=-1)


# ============================================================================
# Basic Encoding Tests
# ============================================================================

def test_encode_single_chunk():
    """Test encoding a single chunk."""
    embedding = FakeEmbedding(dimension=4)
    encoder = DenseEncoder(embedding, batch_size=10)
    
    chunks = [Chunk(id="1", text="Hello world", metadata={"source_path": "test.pdf"})]
    vectors = encoder.encode(chunks)
    
    assert len(vectors) == 1
    assert len(vectors[0]) == 4
    assert embedding.call_count == 1
    assert embedding.call_history[0] == ["Hello world"]


def test_encode_multiple_chunks():
    """Test encoding multiple chunks in single batch."""
    embedding = FakeEmbedding(dimension=8)
    encoder = DenseEncoder(embedding, batch_size=10)
    
    chunks = [
        Chunk(id="1", text="First chunk", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="Second chunk", metadata={"source_path": "test.pdf"}),
        Chunk(id="3", text="Third chunk", metadata={"source_path": "test.pdf"}),
    ]
    vectors = encoder.encode(chunks)
    
    assert len(vectors) == 3
    assert all(len(v) == 8 for v in vectors)
    assert embedding.call_count == 1  # All in one batch


def test_encode_preserves_chunk_order():
    """Test that output vectors maintain input chunk order."""
    embedding = FakeEmbedding(dimension=4)
    encoder = DenseEncoder(embedding, batch_size=10)
    
    chunks = [
        Chunk(id="1", text="A" * 10, metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="B" * 20, metadata={"source_path": "test.pdf"}),
        Chunk(id="3", text="C" * 30, metadata={"source_path": "test.pdf"}),
    ]
    vectors = encoder.encode(chunks)
    
    # Vectors should be ordered by text length (since FakeEmbedding uses length)
    assert vectors[0][0] < vectors[1][0] < vectors[2][0]


# ============================================================================
# Batch Processing Tests
# ============================================================================

def test_encode_respects_batch_size():
    """Test that encoding respects configured batch_size."""
    embedding = FakeEmbedding(dimension=4)
    encoder = DenseEncoder(embedding, batch_size=2)
    
    chunks = [
        Chunk(id="1", text="Chunk 1", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="Chunk 2", metadata={"source_path": "test.pdf"}),
        Chunk(id="3", text="Chunk 3", metadata={"source_path": "test.pdf"}),
        Chunk(id="4", text="Chunk 4", metadata={"source_path": "test.pdf"}),
        Chunk(id="5", text="Chunk 5", metadata={"source_path": "test.pdf"}),
    ]
    vectors = encoder.encode(chunks)
    
    # Should make 3 calls: [0:2], [2:4], [4:5]
    assert embedding.call_count == 3
    assert len(embedding.call_history[0]) == 2  # First batch
    assert len(embedding.call_history[1]) == 2  # Second batch
    assert len(embedding.call_history[2]) == 1  # Last batch
    
    # All vectors returned
    assert len(vectors) == 5


def test_encode_exact_batch_boundary():
    """Test encoding when chunk count is exact multiple of batch_size."""
    embedding = FakeEmbedding(dimension=4)
    encoder = DenseEncoder(embedding, batch_size=3)
    
    chunks = [Chunk(id=str(i), text=f"Chunk {i}", metadata={"source_path": "test.pdf"}) for i in range(6)]
    vectors = encoder.encode(chunks)
    
    assert embedding.call_count == 2  # Exactly 2 batches
    assert len(vectors) == 6


def test_encode_large_batch():
    """Test encoding with batch size larger than chunk count."""
    embedding = FakeEmbedding(dimension=4)
    encoder = DenseEncoder(embedding, batch_size=100)
    
    chunks = [Chunk(id=str(i), text=f"Chunk {i}", metadata={"source_path": "test.pdf"}) for i in range(10)]
    vectors = encoder.encode(chunks)
    
    assert embedding.call_count == 1  # Single batch
    assert len(vectors) == 10


# ============================================================================
# Input Validation Tests
# ============================================================================

def test_encode_rejects_empty_chunks_list():
    """Test that encode() rejects empty chunks list."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding)
    
    with pytest.raises(ValueError, match="Cannot encode empty chunks list"):
        encoder.encode([])


def test_encode_rejects_chunk_with_empty_text():
    """Test that chunks with empty text are rejected."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding)
    
    chunks = [
        Chunk(id="1", text="Valid text", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="", metadata={"source_path": "test.pdf"}),  # Empty
    ]
    
    with pytest.raises(ValueError, match="Chunk at index 1.*has empty"):
        encoder.encode(chunks)


def test_encode_rejects_chunk_with_whitespace_only_text():
    """Test that chunks with whitespace-only text are rejected."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding)
    
    chunks = [
        Chunk(id="1", text="   \n\t  ", metadata={"source_path": "test.pdf"}),  # Whitespace only
    ]
    
    with pytest.raises(ValueError, match="has empty or whitespace-only text"):
        encoder.encode(chunks)


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_encode_handles_embedding_provider_failure():
    """Test that embedding provider failures are properly surfaced."""
    embedding = FakeEmbedding(fail_on_call=True)
    encoder = DenseEncoder(embedding, batch_size=10)
    
    chunks = [Chunk(id="1", text="Test", metadata={"source_path": "test.pdf"})]
    
    with pytest.raises(RuntimeError, match="Failed to encode batch.*Simulated embedding failure"):
        encoder.encode(chunks)


def test_encode_failure_includes_batch_range():
    """Test that error messages include batch range for debugging."""
    embedding = FakeEmbedding(fail_on_call=True)
    encoder = DenseEncoder(embedding, batch_size=2)
    
    chunks = [
        Chunk(id="1", text="Chunk 1", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="Chunk 2", metadata={"source_path": "test.pdf"}),
        Chunk(id="3", text="Chunk 3", metadata={"source_path": "test.pdf"}),
    ]
    
    with pytest.raises(RuntimeError, match=r"Failed to encode batch 0-2"):
        encoder.encode(chunks)


def test_encode_validates_vector_count():
    """Test that mismatched vector count is detected."""
    embedding = Mock(spec=BaseEmbedding)
    # Return wrong number of vectors
    embedding.embed.return_value = [[0.1, 0.2]]  # Only 1 vector
    
    encoder = DenseEncoder(embedding, batch_size=10)
    chunks = [
        Chunk(id="1", text="Chunk 1", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="Chunk 2", metadata={"source_path": "test.pdf"}),
    ]
    
    with pytest.raises(RuntimeError, match="returned 1 vectors for 2 texts"):
        encoder.encode(chunks)


def test_encode_validates_vector_dimensions():
    """Test that inconsistent vector dimensions are detected."""
    embedding = Mock(spec=BaseEmbedding)
    # Return vectors with inconsistent dimensions
    embedding.embed.return_value = [
        [0.1, 0.2, 0.3],  # 3 dims
        [0.4, 0.5],       # 2 dims (inconsistent!)
    ]
    
    encoder = DenseEncoder(embedding, batch_size=10)
    chunks = [
        Chunk(id="1", text="Chunk 1", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="Chunk 2", metadata={"source_path": "test.pdf"}),
    ]
    
    with pytest.raises(RuntimeError, match="Inconsistent vector dimensions"):
        encoder.encode(chunks)


# ============================================================================
# Utility Method Tests
# ============================================================================

def test_get_batch_count_single_batch():
    """Test batch count calculation for single batch."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding, batch_size=10)
    
    assert encoder.get_batch_count(5) == 1
    assert encoder.get_batch_count(10) == 1


def test_get_batch_count_multiple_batches():
    """Test batch count calculation for multiple batches."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding, batch_size=10)
    
    assert encoder.get_batch_count(11) == 2
    assert encoder.get_batch_count(20) == 2
    assert encoder.get_batch_count(21) == 3


def test_get_batch_count_zero_chunks():
    """Test batch count for zero chunks."""
    embedding = FakeEmbedding()
    encoder = DenseEncoder(embedding, batch_size=10)
    
    assert encoder.get_batch_count(0) == 0


def test_get_batch_count_with_different_batch_sizes():
    """Test batch count varies with batch_size."""
    embedding = FakeEmbedding()
    
    encoder_small = DenseEncoder(embedding, batch_size=2)
    encoder_large = DenseEncoder(embedding, batch_size=100)
    
    assert encoder_small.get_batch_count(10) == 5
    assert encoder_large.get_batch_count(10) == 1


# ============================================================================
# Integration-Like Tests (Still Mocked)
# ============================================================================

def test_encode_realistic_scenario():
    """Test realistic encoding scenario with multiple batches."""
    embedding = FakeEmbedding(dimension=1536)
    encoder = DenseEncoder(embedding, batch_size=32)
    
    # Create 100 chunks
    chunks = [
        Chunk(
            id=f"chunk_{i}",
            text=f"This is chunk number {i} with some content",
            metadata={"source_path": "test.pdf", "page": i // 10}
        )
        for i in range(100)
    ]
    
    vectors = encoder.encode(chunks)
    
    # Verify output
    assert len(vectors) == 100
    assert all(len(v) == 1536 for v in vectors)
    
    # Verify batching (100 / 32 = 4 batches)
    assert embedding.call_count == 4
    
    # Verify all chunks were processed
    total_processed = sum(len(batch) for batch in embedding.call_history)
    assert total_processed == 100


def test_encode_with_trace_context():
    """Test that trace context is passed through to embedding provider."""
    embedding = Mock(spec=BaseEmbedding)
    embedding.embed.return_value = [[0.1, 0.2, 0.3]]
    
    encoder = DenseEncoder(embedding, batch_size=10)
    chunks = [Chunk(id="1", text="Test", metadata={"source_path": "test.pdf"})]
    
    mock_trace = {"trace_id": "test_trace"}
    encoder.encode(chunks, trace=mock_trace)
    
    # Verify trace was passed to embedding provider
    embedding.embed.assert_called_once()
    call_kwargs = embedding.embed.call_args.kwargs
    assert call_kwargs["trace"] == mock_trace
