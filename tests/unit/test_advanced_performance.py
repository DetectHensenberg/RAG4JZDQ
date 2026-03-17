"""Unit tests for #18 Advanced Performance Optimization.

Tests:
- Async Embedding API
- Chunk deduplication
- Batch query embedding
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import List

from src.libs.embedding.base_embedding import BaseEmbedding
from src.ingestion.embedding.dense_encoder import DenseEncoder
from src.ingestion.storage.vector_upserter import VectorUpserter
from src.core.query_engine.dense_retriever import DenseRetriever
from src.core.types import Chunk


class MockEmbedding(BaseEmbedding):
    """Mock embedding for testing."""
    
    def __init__(self, dimension: int = 3, delay: float = 0.0):
        self.dimension = dimension
        self.delay = delay
        self.call_count = 0
        self.batch_sizes: List[int] = []
    
    def embed(self, texts: List[str], trace=None, **kwargs) -> List[List[float]]:
        self.call_count += 1
        self.batch_sizes.append(len(texts))
        if self.delay > 0:
            import time
            time.sleep(self.delay)
        return [[float(i) for i in range(self.dimension)] for _ in texts]
    
    def get_dimension(self) -> int:
        return self.dimension


class TestAsyncEmbedding:
    """Test async embedding methods."""
    
    @pytest.mark.asyncio
    async def test_embed_async_basic(self):
        """Test basic async embedding."""
        embedding = MockEmbedding(dimension=3)
        
        result = await embedding.embed_async(["hello", "world"])
        
        assert len(result) == 2
        assert len(result[0]) == 3
        assert embedding.call_count == 1
    
    @pytest.mark.asyncio
    async def test_embed_batches_async_concurrent(self):
        """Test concurrent batch embedding."""
        embedding = MockEmbedding(dimension=3, delay=0.05)
        
        batches = [["text1", "text2"], ["text3", "text4"], ["text5"]]
        
        import time
        start = time.time()
        result = await embedding.embed_batches_async(batches, max_concurrency=3)
        elapsed = time.time() - start
        
        # 3 batches with 0.05s each, concurrent should be ~0.05s not 0.15s
        assert elapsed < 0.12, f"Expected < 0.12s, got {elapsed:.3f}s"
        assert len(result) == 5
        assert embedding.call_count == 3
    
    @pytest.mark.asyncio
    async def test_embed_batches_async_respects_concurrency_limit(self):
        """Test that concurrency limit is respected."""
        embedding = MockEmbedding(dimension=3, delay=0.05)
        
        batches = [["t1"], ["t2"], ["t3"], ["t4"], ["t5"]]
        
        import time
        start = time.time()
        result = await embedding.embed_batches_async(batches, max_concurrency=2)
        elapsed = time.time() - start
        
        # 5 batches with max 2 concurrent = 3 rounds = ~0.15s
        assert elapsed >= 0.1, f"Expected >= 0.1s, got {elapsed:.3f}s"
        assert len(result) == 5


class TestDenseEncoderAsync:
    """Test async encoding in DenseEncoder."""
    
    @pytest.mark.asyncio
    async def test_encode_async_basic(self):
        """Test basic async encoding."""
        embedding = MockEmbedding(dimension=3)
        encoder = DenseEncoder(embedding, batch_size=2)
        
        chunks = [
            Chunk(id="1", text="Hello world", metadata={"source_path": "test.pdf", "chunk_index": 0}),
            Chunk(id="2", text="Test chunk", metadata={"source_path": "test.pdf", "chunk_index": 1}),
            Chunk(id="3", text="Another one", metadata={"source_path": "test.pdf", "chunk_index": 2}),
        ]
        
        result = await encoder.encode_async(chunks)
        
        assert len(result) == 3
        assert len(result[0]) == 3
    
    @pytest.mark.asyncio
    async def test_encode_async_faster_than_sync(self):
        """Test that async is faster for multiple batches."""
        embedding = MockEmbedding(dimension=3, delay=0.05)
        encoder = DenseEncoder(embedding, batch_size=2)
        
        chunks = [
            Chunk(id=str(i), text=f"Chunk {i}", metadata={"source_path": "test.pdf", "chunk_index": i})
            for i in range(6)
        ]
        
        import time
        
        # Async encoding
        start = time.time()
        await encoder.encode_async(chunks, max_concurrency=3)
        async_time = time.time() - start
        
        # Reset
        embedding.call_count = 0
        
        # Sync encoding
        start = time.time()
        encoder.encode(chunks)
        sync_time = time.time() - start
        
        # Async should be faster (3 batches concurrent vs sequential)
        assert async_time < sync_time, f"Async {async_time:.3f}s should be < sync {sync_time:.3f}s"


class TestChunkDeduplication:
    """Test chunk deduplication in VectorUpserter."""
    
    def test_filter_existing_chunks_all_new(self):
        """Test when all chunks are new."""
        mock_settings = Mock()
        mock_settings.vector_store = Mock()
        mock_settings.vector_store.provider = "chroma"
        
        with patch('src.ingestion.storage.vector_upserter.VectorStoreFactory') as mock_factory:
            mock_store = Mock()
            mock_collection = Mock()
            mock_collection.get.return_value = {"ids": []}
            mock_store._collection = mock_collection
            mock_factory.create.return_value = mock_store
            
            upserter = VectorUpserter(mock_settings)
            
            chunks = [
                Chunk(id="1", text="Hello", metadata={"source_path": "a.pdf", "chunk_index": 0}),
                Chunk(id="2", text="World", metadata={"source_path": "a.pdf", "chunk_index": 1}),
            ]
            
            new_chunks, indices = upserter.filter_existing_chunks(chunks)
            
            assert len(new_chunks) == 2
            assert indices == [0, 1]
    
    def test_filter_existing_chunks_some_exist(self):
        """Test when some chunks already exist."""
        mock_settings = Mock()
        mock_settings.vector_store = Mock()
        mock_settings.vector_store.provider = "chroma"
        
        with patch('src.ingestion.storage.vector_upserter.VectorStoreFactory') as mock_factory:
            mock_store = Mock()
            mock_collection = Mock()
            
            # Simulate chunk 0 already exists
            def mock_get(ids, include):
                # Return first ID as existing
                return {"ids": [ids[0]]}
            
            mock_collection.get.side_effect = mock_get
            mock_store._collection = mock_collection
            mock_factory.create.return_value = mock_store
            
            upserter = VectorUpserter(mock_settings)
            
            chunks = [
                Chunk(id="1", text="Hello", metadata={"source_path": "a.pdf", "chunk_index": 0}),
                Chunk(id="2", text="World", metadata={"source_path": "a.pdf", "chunk_index": 1}),
            ]
            
            new_chunks, indices = upserter.filter_existing_chunks(chunks)
            
            # Only second chunk should be new
            assert len(new_chunks) == 1
            assert indices == [1]
    
    def test_filter_existing_chunks_empty(self):
        """Test with empty chunk list."""
        mock_settings = Mock()
        mock_settings.vector_store = Mock()
        mock_settings.vector_store.provider = "chroma"
        
        with patch('src.ingestion.storage.vector_upserter.VectorStoreFactory') as mock_factory:
            mock_store = Mock()
            mock_factory.create.return_value = mock_store
            
            upserter = VectorUpserter(mock_settings)
            
            new_chunks, indices = upserter.filter_existing_chunks([])
            
            assert new_chunks == []
            assert indices == []


class TestBatchQueryEmbedding:
    """Test batch query embedding in DenseRetriever."""
    
    def test_embed_queries_batch_single_api_call(self):
        """Test that batch embedding uses single API call."""
        mock_embedding = MockEmbedding(dimension=3)
        mock_store = Mock()
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        with patch('src.core.query_engine.dense_retriever.get_query_cache') as mock_cache_fn:
            mock_cache = Mock()
            mock_cache.get.return_value = None  # All cache misses
            mock_cache_fn.return_value = mock_cache
            
            queries = ["query1", "query2", "query3"]
            vectors = retriever.embed_queries_batch(queries)
            
            assert len(vectors) == 3
            # Should be single API call for all 3 queries
            assert mock_embedding.call_count == 1
            assert mock_embedding.batch_sizes == [3]
    
    def test_embed_queries_batch_with_cache_hits(self):
        """Test batch embedding with partial cache hits."""
        mock_embedding = MockEmbedding(dimension=3)
        mock_store = Mock()
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        with patch('src.core.query_engine.dense_retriever.get_query_cache') as mock_cache_fn:
            mock_cache = Mock()
            # query2 is cached
            def mock_get(query):
                if query == "query2":
                    return [0.5, 0.5, 0.5]
                return None
            mock_cache.get.side_effect = mock_get
            mock_cache_fn.return_value = mock_cache
            
            queries = ["query1", "query2", "query3"]
            vectors = retriever.embed_queries_batch(queries)
            
            assert len(vectors) == 3
            # Only 2 queries should be embedded (query1, query3)
            assert mock_embedding.call_count == 1
            assert mock_embedding.batch_sizes == [2]
    
    def test_embed_queries_batch_all_cached(self):
        """Test batch embedding when all queries are cached."""
        mock_embedding = MockEmbedding(dimension=3)
        mock_store = Mock()
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        with patch('src.core.query_engine.dense_retriever.get_query_cache') as mock_cache_fn:
            mock_cache = Mock()
            mock_cache.get.return_value = [1.0, 2.0, 3.0]  # All cached
            mock_cache_fn.return_value = mock_cache
            
            queries = ["query1", "query2", "query3"]
            vectors = retriever.embed_queries_batch(queries)
            
            assert len(vectors) == 3
            # No API calls needed
            assert mock_embedding.call_count == 0
    
    def test_embed_queries_batch_empty(self):
        """Test batch embedding with empty list."""
        mock_embedding = MockEmbedding(dimension=3)
        mock_store = Mock()
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        vectors = retriever.embed_queries_batch([])
        
        assert vectors == []
        assert mock_embedding.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
