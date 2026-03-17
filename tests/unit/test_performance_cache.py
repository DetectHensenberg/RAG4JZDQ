"""Unit tests for #17 Performance Optimization - Cache modules.

Tests:
- L1: EmbeddingCache (query -> vector)
- L2: RetrievalCache (query -> chunks)
- L3: AnswerCache (query -> answer)
- RerankCache (query + candidates -> reranked order)
- Query normalization
"""

import pytest
import time
import threading
from typing import List

from src.libs.embedding.embedding_cache import (
    EmbeddingCache,
    normalize_query as emb_normalize,
    get_query_cache,
)
from src.core.query_engine.retrieval_cache import (
    RetrievalCache,
    normalize_query as ret_normalize,
    get_retrieval_cache,
)
from src.core.query_engine.answer_cache import (
    AnswerCache,
    normalize_query as ans_normalize,
    get_answer_cache,
)
from src.core.query_engine.rerank_cache import (
    RerankCache,
    get_rerank_cache,
)


class TestQueryNormalization:
    """Test query normalization for consistent cache keys."""
    
    def test_lowercase(self):
        assert emb_normalize("Hello World") == "hello world"
        assert ret_normalize("UPPERCASE") == "uppercase"
        assert ans_normalize("MiXeD CaSe") == "mixed case"
    
    def test_whitespace_collapse(self):
        assert emb_normalize("hello   world") == "hello world"
        assert emb_normalize("  leading") == "leading"
        assert emb_normalize("trailing  ") == "trailing"
        assert emb_normalize("  multiple   spaces  ") == "multiple spaces"
    
    def test_chinese_preserved(self):
        assert emb_normalize("报销流程") == "报销流程"
        assert emb_normalize("  报销  流程  ") == "报销 流程"
    
    def test_mixed_content(self):
        assert emb_normalize("What is 报销流程?") == "what is 报销流程?"


class TestEmbeddingCache:
    """Test L1: Embedding cache."""
    
    def test_put_and_get(self):
        cache = EmbeddingCache(max_size=100)
        vector = [0.1, 0.2, 0.3]
        
        cache.put("test query", vector)
        result = cache.get("test query")
        
        assert result == vector
    
    def test_cache_miss(self):
        cache = EmbeddingCache(max_size=100)
        result = cache.get("nonexistent")
        assert result is None
    
    def test_normalized_key(self):
        """Same query with different formatting should hit cache."""
        cache = EmbeddingCache(max_size=100)
        vector = [1.0, 2.0, 3.0]
        
        cache.put("Hello World", vector)
        
        # These should all hit the same cache entry
        assert cache.get("hello world") == vector
        assert cache.get("HELLO WORLD") == vector
        assert cache.get("  hello   world  ") == vector
    
    def test_lru_eviction(self):
        cache = EmbeddingCache(max_size=3)
        
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        cache.put("d", [4.0])  # Should evict "a"
        
        assert cache.get("a") is None
        assert cache.get("b") == [2.0]
        assert cache.get("c") == [3.0]
        assert cache.get("d") == [4.0]
    
    def test_lru_access_order(self):
        cache = EmbeddingCache(max_size=3)
        
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        
        # Access "a" to make it recently used
        cache.get("a")
        
        cache.put("d", [4.0])  # Should evict "b" (least recently used)
        
        assert cache.get("a") == [1.0]
        assert cache.get("b") is None
    
    def test_stats(self):
        cache = EmbeddingCache(max_size=100)
        
        cache.put("test", [1.0])
        cache.get("test")  # hit
        cache.get("test")  # hit
        cache.get("miss")  # miss
        
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == pytest.approx(0.6667, rel=0.01)
    
    def test_batch_operations(self):
        cache = EmbeddingCache(max_size=100)
        
        texts = ["a", "b", "c"]
        vectors = [[1.0], [2.0], [3.0]]
        
        cache.put_batch(texts, vectors)
        
        results, misses = cache.get_batch(["a", "b", "c", "d"])
        
        assert results[0] == [1.0]
        assert results[1] == [2.0]
        assert results[2] == [3.0]
        assert results[3] is None
        assert misses == [3]
    
    def test_thread_safety(self):
        cache = EmbeddingCache(max_size=1000)
        errors = []
        
        def writer(thread_id: int):
            try:
                for i in range(100):
                    cache.put(f"key_{thread_id}_{i}", [float(i)])
            except Exception as e:
                errors.append(e)
        
        def reader(thread_id: int):
            try:
                for i in range(100):
                    cache.get(f"key_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestRetrievalCache:
    """Test L2: Retrieval result cache."""
    
    def test_put_and_get(self):
        cache = RetrievalCache(max_size=100, ttl_seconds=3600)
        
        cache.put(
            query="test query",
            chunk_ids=["c1", "c2"],
            scores={"c1": 0.9, "c2": 0.8},
            texts={"c1": "text1", "c2": "text2"},
            metadata={"c1": {"source": "a.pdf"}, "c2": {"source": "b.pdf"}},
        )
        
        result = cache.get("test query")
        
        assert result is not None
        assert result.chunk_ids == ["c1", "c2"]
        assert result.scores["c1"] == 0.9
        assert result.texts["c1"] == "text1"
    
    def test_ttl_expiration(self):
        cache = RetrievalCache(max_size=100, ttl_seconds=0.1)
        
        cache.put("test", ["c1"], {"c1": 0.9}, {"c1": "text"}, {"c1": {}})
        
        assert cache.get("test") is not None
        
        time.sleep(0.15)
        
        assert cache.get("test") is None
        
        stats = cache.stats()
        assert stats["expired"] == 1
    
    def test_normalized_key(self):
        cache = RetrievalCache(max_size=100, ttl_seconds=3600)
        
        cache.put("Hello World", ["c1"], {"c1": 0.9}, {"c1": "text"}, {"c1": {}})
        
        assert cache.get("hello world") is not None
        assert cache.get("HELLO WORLD") is not None
    
    def test_invalidate_single(self):
        cache = RetrievalCache(max_size=100, ttl_seconds=3600)
        
        cache.put("a", ["c1"], {"c1": 0.9}, {"c1": "text"}, {"c1": {}})
        cache.put("b", ["c2"], {"c2": 0.8}, {"c2": "text"}, {"c2": {}})
        
        count = cache.invalidate("a")
        
        assert count == 1
        assert cache.get("a") is None
        assert cache.get("b") is not None
    
    def test_invalidate_all(self):
        cache = RetrievalCache(max_size=100, ttl_seconds=3600)
        
        cache.put("a", ["c1"], {"c1": 0.9}, {"c1": "text"}, {"c1": {}})
        cache.put("b", ["c2"], {"c2": 0.8}, {"c2": "text"}, {"c2": {}})
        
        count = cache.invalidate()
        
        assert count == 2
        assert cache.get("a") is None
        assert cache.get("b") is None


class TestAnswerCache:
    """Test L3: Answer cache."""
    
    def test_put_and_get(self):
        cache = AnswerCache(max_size=100, ttl_seconds=3600)
        
        cache.put(
            query="报销流程",
            answer="报销流程如下：1. 提交申请...",
            sources=[{"source": "制度.pdf", "score": 0.9}],
            metadata={"model": "gpt-4"},
        )
        
        result = cache.get("报销流程")
        
        assert result is not None
        assert "报销流程如下" in result.answer
        assert len(result.sources) == 1
        assert result.metadata["model"] == "gpt-4"
    
    def test_ttl_expiration(self):
        cache = AnswerCache(max_size=100, ttl_seconds=0.1)
        
        cache.put("test", "answer", [], {})
        
        assert cache.get("test") is not None
        
        time.sleep(0.15)
        
        assert cache.get("test") is None
    
    def test_faq_scenario(self):
        """Simulate FAQ-type repeated queries."""
        cache = AnswerCache(max_size=100, ttl_seconds=604800)  # 7 days
        
        # First query - cache miss
        result = cache.get("什么是报销流程")
        assert result is None
        
        # Store answer
        cache.put(
            "什么是报销流程",
            "报销流程包括...",
            [{"source": "制度.pdf"}],
        )
        
        # Repeated queries - cache hit
        for _ in range(10):
            result = cache.get("什么是报销流程")
            assert result is not None
        
        stats = cache.stats()
        assert stats["hits"] == 10
        assert stats["misses"] == 1


class TestRerankCache:
    """Test Reranker result cache."""
    
    def test_put_and_get(self):
        cache = RerankCache(max_size=100)
        
        cache.put(
            query="test",
            candidate_ids=["a", "b", "c"],
            reranked_ids=["b", "a", "c"],
            scores={"a": 0.8, "b": 0.9, "c": 0.7},
        )
        
        result = cache.get("test", ["a", "b", "c"])
        
        assert result is not None
        assert result.reranked_ids == ["b", "a", "c"]
        assert result.scores["b"] == 0.9
    
    def test_candidate_order_independent(self):
        """Cache should hit regardless of candidate order."""
        cache = RerankCache(max_size=100)
        
        cache.put("test", ["a", "b", "c"], ["b", "a", "c"], {"a": 0.8, "b": 0.9, "c": 0.7})
        
        # Different order of candidates should still hit
        result = cache.get("test", ["c", "a", "b"])
        assert result is not None
    
    def test_different_candidates_miss(self):
        """Different candidate set should miss."""
        cache = RerankCache(max_size=100)
        
        cache.put("test", ["a", "b"], ["b", "a"], {"a": 0.8, "b": 0.9})
        
        # Different candidates should miss
        result = cache.get("test", ["a", "b", "c"])
        assert result is None


class TestGlobalCacheInstances:
    """Test global cache singleton instances."""
    
    def test_query_cache_singleton(self):
        cache1 = get_query_cache()
        cache2 = get_query_cache()
        assert cache1 is cache2
    
    def test_retrieval_cache_singleton(self):
        cache1 = get_retrieval_cache()
        cache2 = get_retrieval_cache()
        assert cache1 is cache2
    
    def test_answer_cache_singleton(self):
        cache1 = get_answer_cache()
        cache2 = get_answer_cache()
        assert cache1 is cache2
    
    def test_rerank_cache_singleton(self):
        cache1 = get_rerank_cache()
        cache2 = get_rerank_cache()
        assert cache1 is cache2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
