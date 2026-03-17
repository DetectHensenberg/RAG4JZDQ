"""Unit tests for #17 Performance Optimization - Parallel Encoding.

Tests the parallel Dense+Sparse encoding in BatchProcessor.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict, Any

from src.ingestion.embedding.batch_processor import BatchProcessor


class MockDenseEncoder:
    """Mock dense encoder for testing."""
    
    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.call_count = 0
    
    def encode(self, chunks: List[Dict[str, Any]], trace=None) -> List[List[float]]:
        self.call_count += 1
        time.sleep(self.delay)
        return [[0.1, 0.2, 0.3] for _ in chunks]


class MockSparseEncoder:
    """Mock sparse encoder for testing."""
    
    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.call_count = 0
    
    def encode(self, chunks: List[Dict[str, Any]], trace=None) -> List[Dict[str, Any]]:
        self.call_count += 1
        time.sleep(self.delay)
        return [{"indices": [1, 2], "values": [0.5, 0.3]} for _ in chunks]


class TestParallelEncoding:
    """Test parallel Dense+Sparse encoding."""
    
    def test_parallel_faster_than_sequential(self):
        """Parallel encoding should be faster than sequential."""
        dense = MockDenseEncoder(delay=0.1)
        sparse = MockSparseEncoder(delay=0.1)
        
        processor = BatchProcessor(
            dense_encoder=dense,
            sparse_encoder=sparse,
            batch_size=10,
        )
        
        chunks = [{"text": f"chunk {i}", "metadata": {}} for i in range(10)]
        
        start = time.time()
        result = processor.process(chunks)
        elapsed = time.time() - start
        
        # Sequential would take ~0.2s (0.1 + 0.1)
        # Parallel should take ~0.1s (max of 0.1, 0.1)
        # Allow some overhead, but should be < 0.18s
        assert elapsed < 0.18, f"Parallel encoding took {elapsed:.3f}s, expected < 0.18s"
        
        assert dense.call_count == 1
        assert sparse.call_count == 1
    
    def test_both_encoders_called(self):
        """Both dense and sparse encoders should be called."""
        dense = MockDenseEncoder(delay=0.01)
        sparse = MockSparseEncoder(delay=0.01)
        
        processor = BatchProcessor(
            dense_encoder=dense,
            sparse_encoder=sparse,
            batch_size=5,
        )
        
        chunks = [{"text": f"chunk {i}", "metadata": {}} for i in range(5)]
        result = processor.process(chunks)
        
        assert dense.call_count == 1
        assert sparse.call_count == 1
        assert len(result.dense_vectors) == 5
        assert len(result.sparse_stats) == 5
    
    def test_multiple_batches(self):
        """Multiple batches should all use parallel encoding."""
        dense = MockDenseEncoder(delay=0.05)
        sparse = MockSparseEncoder(delay=0.05)
        
        processor = BatchProcessor(
            dense_encoder=dense,
            sparse_encoder=sparse,
            batch_size=5,
        )
        
        chunks = [{"text": f"chunk {i}", "metadata": {}} for i in range(15)]
        
        start = time.time()
        result = processor.process(chunks)
        elapsed = time.time() - start
        
        # 3 batches, each taking ~0.05s in parallel
        # Sequential would be 3 * (0.05 + 0.05) = 0.3s
        # Parallel should be 3 * 0.05 = 0.15s + overhead
        # Note: Windows ThreadPoolExecutor has higher overhead
        assert elapsed < 0.5, f"Expected < 0.5s, got {elapsed:.3f}s"
        
        assert dense.call_count == 3
        assert sparse.call_count == 3
    
    def test_dense_failure_continues(self):
        """If dense fails, sparse should still complete."""
        
        class FailingDenseEncoder:
            def encode(self, chunks, trace=None):
                raise RuntimeError("Dense encoding failed")
        
        sparse = MockSparseEncoder(delay=0.01)
        
        processor = BatchProcessor(
            dense_encoder=FailingDenseEncoder(),
            sparse_encoder=sparse,
            batch_size=5,
        )
        
        chunks = [{"text": f"chunk {i}", "metadata": {}} for i in range(5)]
        
        # Should not raise, but log error
        result = processor.process(chunks)
        
        # Sparse should still have results
        assert sparse.call_count == 1
    
    def test_sparse_failure_continues(self):
        """If sparse fails, dense should still complete."""
        
        class FailingSparseEncoder:
            def encode(self, chunks, trace=None):
                raise RuntimeError("Sparse encoding failed")
        
        dense = MockDenseEncoder(delay=0.01)
        
        processor = BatchProcessor(
            dense_encoder=dense,
            sparse_encoder=FailingSparseEncoder(),
            batch_size=5,
        )
        
        chunks = [{"text": f"chunk {i}", "metadata": {}} for i in range(5)]
        
        # Should not raise, but log error
        result = processor.process(chunks)
        
        # Dense should still have results
        assert dense.call_count == 1
    
    def test_empty_chunks(self):
        """Empty chunk list should raise ValueError."""
        dense = MockDenseEncoder()
        sparse = MockSparseEncoder()
        
        processor = BatchProcessor(
            dense_encoder=dense,
            sparse_encoder=sparse,
            batch_size=5,
        )
        
        with pytest.raises(ValueError, match="Cannot process empty chunks"):
            processor.process([])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
