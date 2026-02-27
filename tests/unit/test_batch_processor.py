"""Unit tests for BatchProcessor.

Tests batch processing orchestration, timing metrics, and error handling.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import List, Dict, Any

from src.core.types import Chunk
from src.ingestion.embedding.batch_processor import BatchProcessor, BatchResult
from src.ingestion.embedding.dense_encoder import DenseEncoder
from src.ingestion.embedding.sparse_encoder import SparseEncoder
from src.core.trace.trace_context import TraceContext


class FakeDenseEncoder:
    """Fake DenseEncoder for testing without real embedding calls."""
    
    def __init__(self, vector_dim: int = 3, should_fail: bool = False):
        self.vector_dim = vector_dim
        self.should_fail = should_fail
        self.encode_call_count = 0
    
    def encode(self, chunks: List[Chunk], trace=None) -> List[List[float]]:
        """Return deterministic fake vectors."""
        self.encode_call_count += 1
        
        if self.should_fail:
            raise RuntimeError("Dense encoder failed")
        
        # Generate deterministic vectors based on chunk ID
        vectors = []
        for chunk in chunks:
            # Simple deterministic vector with configured dimension
            chunk_id_hash = float(hash(chunk.id) % 100) / 100.0
            # First element is based on hash, rest are 0.5
            vec = [chunk_id_hash] + [0.5] * (self.vector_dim - 1)
            vectors.append(vec)
        return vectors


class FakeSparseEncoder:
    """Fake SparseEncoder for testing without real tokenization."""
    
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.encode_call_count = 0
    
    def encode(self, chunks: List[Chunk], trace=None) -> List[Dict[str, Any]]:
        """Return deterministic fake statistics."""
        self.encode_call_count += 1
        
        if self.should_fail:
            raise RuntimeError("Sparse encoder failed")
        
        stats = []
        for chunk in chunks:
            stats.append({
                "chunk_id": chunk.id,
                "term_frequencies": {"fake": 1, "terms": 1},
                "doc_length": 2,
                "unique_terms": 2
            })
        return stats


# ============================================================================
# Test BatchProcessor Initialization
# ============================================================================

def test_batch_processor_initialization():
    """Test BatchProcessor can be initialized with required components."""
    dense = FakeDenseEncoder()
    sparse = FakeSparseEncoder()
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=10
    )
    
    assert processor.dense_encoder is dense
    assert processor.sparse_encoder is sparse
    assert processor.batch_size == 10


def test_batch_processor_initialization_with_default_batch_size():
    """Test default batch size is 100."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder()
    )
    assert processor.batch_size == 100


def test_batch_processor_rejects_invalid_batch_size():
    """Test initialization fails with invalid batch_size."""
    with pytest.raises(ValueError, match="batch_size must be positive"):
        BatchProcessor(
            dense_encoder=FakeDenseEncoder(),
            sparse_encoder=FakeSparseEncoder(),
            batch_size=0
        )
    
    with pytest.raises(ValueError, match="batch_size must be positive"):
        BatchProcessor(
            dense_encoder=FakeDenseEncoder(),
            sparse_encoder=FakeSparseEncoder(),
            batch_size=-5
        )


# ============================================================================
# Test Batch Creation
# ============================================================================

def test_create_batches_divides_evenly():
    """Test chunks are divided into even batches."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [
        Chunk(id="1", text="a", metadata={"source_path": "test.pdf"}),
        Chunk(id="2", text="b", metadata={"source_path": "test.pdf"}),
        Chunk(id="3", text="c", metadata={"source_path": "test.pdf"}),
        Chunk(id="4", text="d", metadata={"source_path": "test.pdf"})
    ]
    
    batches = processor._create_batches(chunks)
    
    assert len(batches) == 2
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert batches[0][0].id == "1"
    assert batches[1][1].id == "4"


def test_create_batches_handles_remainder():
    """Test batching with remainder chunks (5 chunks, batch_size=2 -> 3 batches)."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text=f"text{i}", metadata={"source_path": "doc.pdf"}) for i in range(5)]
    batches = processor._create_batches(chunks)
    
    assert len(batches) == 3, "5 chunks with batch_size=2 should create 3 batches"
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1, "Last batch should have 1 chunk"


def test_create_batches_preserves_order():
    """Test batch creation maintains chunk order."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [Chunk(id=f"chunk_{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(5)]
    batches = processor._create_batches(chunks)
    
    # Flatten batches and verify order
    flattened = [chunk for batch in batches for chunk in batch]
    assert [c.id for c in flattened] == [f"chunk_{i}" for i in range(5)]


def test_create_batches_single_chunk():
    """Test batching with single chunk."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=10
    )
    
    chunks = [Chunk(id="1", text="single", metadata={"source_path": "test.pdf"})]
    batches = processor._create_batches(chunks)
    
    assert len(batches) == 1
    assert len(batches[0]) == 1
    assert batches[0][0].id == "1"


def test_get_batch_count():
    """Test batch count calculation utility."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    assert processor.get_batch_count(0) == 0
    assert processor.get_batch_count(1) == 1
    assert processor.get_batch_count(2) == 1
    assert processor.get_batch_count(3) == 2
    assert processor.get_batch_count(4) == 2
    assert processor.get_batch_count(5) == 3


# ============================================================================
# Test Process Method - Happy Path
# ============================================================================

def test_process_encodes_all_chunks():
    """Test process() encodes all chunks through both encoders."""
    dense = FakeDenseEncoder(vector_dim=3)
    sparse = FakeSparseEncoder()
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text=f"text {i}", metadata={"source_path": "test.pdf"}) for i in range(5)]
    result = processor.process(chunks)
    
    # Verify results
    assert len(result.dense_vectors) == 5
    assert len(result.sparse_stats) == 5
    assert result.successful_chunks == 5
    assert result.failed_chunks == 0
    assert result.batch_count == 3  # 5 chunks / batch_size=2 -> 3 batches


def test_process_maintains_chunk_order():
    """Test output order matches input chunk order."""
    dense = FakeDenseEncoder()
    sparse = FakeSparseEncoder()
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=2
    )
    
    chunks = [Chunk(id=f"chunk_{i}", text=f"text {i}", metadata={"source_path": "test.pdf"}) for i in range(5)]
    result = processor.process(chunks)
    
    # Verify sparse stats maintain order
    assert [stat["chunk_id"] for stat in result.sparse_stats] == [f"chunk_{i}" for i in range(5)]


def test_process_returns_correct_batch_count():
    """Test BatchResult contains correct batch count."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=3
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(10)]
    result = processor.process(chunks)
    
    assert result.batch_count == 4  # 10 / 3 = 4 batches


def test_process_records_timing():
    """Test process() records total processing time."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(3)]
    result = processor.process(chunks)
    
    assert result.total_time > 0.0
    assert isinstance(result.total_time, float)


# ============================================================================
# Test Process with TraceContext
# ============================================================================

def test_process_with_trace_records_batch_info():
    """Test process() records batch information to TraceContext."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(5)]
    trace = TraceContext()
    result = processor.process(chunks, trace=trace)
    
    # Verify batch_processing stage was recorded
    batch_data = trace.get_stage_data("batch_processing")
    assert batch_data is not None
    assert batch_data["total_chunks"] == 5
    assert batch_data["batch_count"] == 3
    assert batch_data["batch_size"] == 2
    assert batch_data["successful_chunks"] == 5
    assert batch_data["failed_chunks"] == 0


def test_process_with_trace_records_individual_batches():
    """Test individual batch timings are recorded."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(5)]
    trace = TraceContext()
    processor.process(chunks, trace=trace)
    
    # Verify individual batch stages
    for batch_idx in range(3):
        batch_data = trace.get_stage_data(f"batch_{batch_idx}")
        assert batch_data is not None
        assert "duration_seconds" in batch_data
        assert "chunks_processed" in batch_data


# ============================================================================
# Test Error Handling
# ============================================================================

def test_process_rejects_empty_chunks():
    """Test process() raises ValueError for empty chunks list."""
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        batch_size=2
    )
    
    with pytest.raises(ValueError, match="Cannot process empty chunks list"):
        processor.process([])


def test_process_continues_on_batch_failure():
    """Test process() continues processing after a batch fails."""
    # Create encoder that fails on second call
    dense = FakeDenseEncoder()
    sparse = FakeSparseEncoder()
    
    # Make dense encoder fail on second batch
    original_encode = dense.encode
    call_count = [0]
    
    def failing_encode(chunks, trace=None):
        call_count[0] += 1
        if call_count[0] == 2:  # Fail on second batch
            raise RuntimeError("Simulated batch failure")
        return original_encode(chunks, trace)
    
    dense.encode = failing_encode
    
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(6)]
    result = processor.process(chunks)
    
    # Should process batches 1 and 3 successfully, batch 2 fails
    assert result.successful_chunks == 4  # 2 from batch 1, 2 from batch 3
    assert result.failed_chunks == 2  # batch 2


def test_process_records_batch_errors_to_trace():
    """Test batch errors are recorded to TraceContext."""
    dense = FakeDenseEncoder(should_fail=True)
    sparse = FakeSparseEncoder()
    
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=2
    )
    
    chunks = [Chunk(id=f"{i}", text="", metadata={"source_path": "test.pdf"}) for i in range(3)]
    trace = TraceContext()
    result = processor.process(chunks, trace=trace)
    
    # Verify errors were recorded
    assert result.failed_chunks == 3
    batch_0_error = trace.get_stage_data("batch_0_error")
    assert batch_0_error is not None
    assert "Dense encoder failed" in batch_0_error["error"]


# ============================================================================
# Test BatchResult Dataclass
# ============================================================================

def test_batch_result_structure():
    """Test BatchResult contains all required fields."""
    result = BatchResult(
        dense_vectors=[[0.1, 0.2]],
        sparse_stats=[{"chunk_id": "1", "term_frequencies": {}}],
        batch_count=1,
        total_time=0.5,
        successful_chunks=1,
        failed_chunks=0
    )
    
    assert len(result.dense_vectors) == 1
    assert len(result.sparse_stats) == 1
    assert result.batch_count == 1
    assert result.total_time == 0.5
    assert result.successful_chunks == 1
    assert result.failed_chunks == 0


# ============================================================================
# Test Integration with Real Encoders (using Fakes)
# ============================================================================

def test_process_integration_with_encoders():
    """Test BatchProcessor integrates correctly with encoder interfaces."""
    dense = FakeDenseEncoder(vector_dim=4)
    sparse = FakeSparseEncoder()
    
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=10
    )
    
    chunks = [
        Chunk(id="doc1_chunk0", text="machine learning systems", metadata={"source_path": "doc1.pdf", "source": "doc1"}),
        Chunk(id="doc1_chunk1", text="natural language processing", metadata={"source_path": "doc1.pdf", "source": "doc1"}),
        Chunk(id="doc2_chunk0", text="computer vision models", metadata={"source_path": "doc2.pdf", "source": "doc2"})
    ]
    
    result = processor.process(chunks)
    
    # Verify dense vectors
    assert len(result.dense_vectors) == 3
    assert all(len(vec) == 4 for vec in result.dense_vectors)
    
    # Verify sparse stats
    assert len(result.sparse_stats) == 3
    assert all("chunk_id" in stat for stat in result.sparse_stats)
    assert result.sparse_stats[0]["chunk_id"] == "doc1_chunk0"
    
    # Verify metrics
    assert result.batch_count == 1  # All fit in one batch
    assert result.successful_chunks == 3
    assert result.failed_chunks == 0
    assert result.total_time > 0


def test_process_deterministic_output():
    """Test same chunks produce same output."""
    dense = FakeDenseEncoder()
    sparse = FakeSparseEncoder()
    processor = BatchProcessor(
        dense_encoder=dense,
        sparse_encoder=sparse,
        batch_size=2
    )
    
    chunks = [Chunk(id=f"chunk_{i}", text=f"text {i}", metadata={"source_path": "test.pdf"}) for i in range(3)]
    
    result1 = processor.process(chunks)
    result2 = processor.process(chunks)
    
    # Dense vectors should be identical (deterministic based on chunk ID)
    assert result1.dense_vectors == result2.dense_vectors
    
    # Sparse stats should be identical
    assert result1.sparse_stats == result2.sparse_stats

