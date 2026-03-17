"""Integration tests for #17 Performance Optimization - Cache Integration.

Tests cache integration with actual components:
- DenseRetriever with Embedding cache
- HybridSearch with Retrieval cache
- CoreReranker with Rerank cache
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict, Any

from src.core.types import RetrievalResult


class TestDenseRetrieverCacheIntegration:
    """Test DenseRetriever integration with Embedding cache."""
    
    def test_cache_hit_skips_embedding_call(self):
        """When cache hits, embedding API should not be called."""
        from src.core.query_engine.dense_retriever import DenseRetriever
        from src.libs.embedding.embedding_cache import EmbeddingCache
        
        # Create mock embedding client
        mock_embedding = Mock()
        mock_embedding.embed = Mock(return_value=[[0.1, 0.2, 0.3]])
        
        # Create mock vector store
        mock_store = Mock()
        mock_store.query = Mock(return_value=[
            {"id": "c1", "score": 0.9, "text": "test", "metadata": {}}
        ])
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        # First call - cache miss
        with patch('src.core.query_engine.dense_retriever.get_query_cache') as mock_cache_fn:
            cache = EmbeddingCache(max_size=100)
            mock_cache_fn.return_value = cache
            
            results1 = retriever.retrieve("test query")
            assert mock_embedding.embed.call_count == 1
            
            # Second call - cache hit
            results2 = retriever.retrieve("test query")
            # Embedding should not be called again
            assert mock_embedding.embed.call_count == 1
    
    def test_normalized_query_cache_hit(self):
        """Normalized queries should hit the same cache entry."""
        from src.core.query_engine.dense_retriever import DenseRetriever
        from src.libs.embedding.embedding_cache import EmbeddingCache
        
        mock_embedding = Mock()
        mock_embedding.embed = Mock(return_value=[[0.1, 0.2, 0.3]])
        
        mock_store = Mock()
        mock_store.query = Mock(return_value=[
            {"id": "c1", "score": 0.9, "text": "test", "metadata": {}}
        ])
        
        retriever = DenseRetriever(
            embedding_client=mock_embedding,
            vector_store=mock_store,
        )
        
        with patch('src.core.query_engine.dense_retriever.get_query_cache') as mock_cache_fn:
            cache = EmbeddingCache(max_size=100)
            mock_cache_fn.return_value = cache
            
            retriever.retrieve("Hello World")
            retriever.retrieve("hello world")  # Should hit cache
            retriever.retrieve("HELLO WORLD")  # Should hit cache
            
            # Only one embedding call
            assert mock_embedding.embed.call_count == 1


class TestCoreRerankerCacheIntegration:
    """Test CoreReranker integration with Rerank cache."""
    
    def test_cache_hit_skips_reranking(self):
        """When cache hits, reranker should not be called."""
        from src.core.query_engine.reranker import CoreReranker, RerankConfig
        from src.core.query_engine.rerank_cache import RerankCache
        from src.libs.reranker.base_reranker import NoneReranker
        
        # Create mock settings
        mock_settings = Mock()
        mock_settings.rerank = Mock()
        mock_settings.rerank.enabled = True
        mock_settings.rerank.top_k = 5
        
        # Create mock reranker backend
        mock_backend = Mock()
        mock_backend.rerank = Mock(return_value=[
            {"id": "c2", "rerank_score": 0.95},
            {"id": "c1", "rerank_score": 0.85},
        ])
        
        reranker = CoreReranker(
            settings=mock_settings,
            reranker=mock_backend,
            config=RerankConfig(enabled=True, top_k=5),
        )
        
        results = [
            RetrievalResult(chunk_id="c1", score=0.9, text="text1", metadata={}),
            RetrievalResult(chunk_id="c2", score=0.8, text="text2", metadata={}),
        ]
        
        with patch('src.core.query_engine.reranker.get_rerank_cache') as mock_cache_fn:
            cache = RerankCache(max_size=100)
            mock_cache_fn.return_value = cache
            
            # First call - cache miss
            result1 = reranker.rerank("test query", results)
            assert mock_backend.rerank.call_count == 1
            
            # Second call - cache hit
            result2 = reranker.rerank("test query", results)
            # Reranker should not be called again
            assert mock_backend.rerank.call_count == 1


class TestCacheStatsAPI:
    """Test cache statistics API endpoint."""
    
    def test_cache_stats_endpoint(self):
        """Test /api/system/cache-stats returns all cache stats."""
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        response = client.get("/api/system/cache-stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        
        stats = data["data"]
        assert "L1_embedding_cache" in stats
        assert "L2_retrieval_cache" in stats
        assert "L3_answer_cache" in stats
        assert "rerank_cache" in stats
        
        # Check stats structure
        for cache_name in ["L1_embedding_cache", "L2_retrieval_cache", "L3_answer_cache", "rerank_cache"]:
            cache_stats = stats[cache_name]
            assert "hits" in cache_stats
            assert "misses" in cache_stats
            assert "size" in cache_stats
            assert "hit_rate" in cache_stats


class TestAnswerCacheIntegration:
    """Test Answer cache integration with chat API."""
    
    def test_answer_cache_structure(self):
        """Test answer cache stores correct structure."""
        from src.core.query_engine.answer_cache import AnswerCache
        
        cache = AnswerCache(max_size=100, ttl_seconds=3600)
        
        cache.put(
            query="报销流程是什么",
            answer="报销流程如下：\n1. 提交申请\n2. 审批\n3. 打款",
            sources=[
                {"source": "制度.pdf", "score": 0.95, "text": "报销需要..."},
                {"source": "流程.docx", "score": 0.88, "text": "申请步骤..."},
            ],
            metadata={"model": "gpt-4", "tokens": 150},
        )
        
        result = cache.get("报销流程是什么")
        
        assert result is not None
        assert "报销流程如下" in result.answer
        assert len(result.sources) == 2
        assert result.sources[0]["source"] == "制度.pdf"
        assert result.metadata["model"] == "gpt-4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
