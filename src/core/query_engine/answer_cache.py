"""Answer cache for FAQ-type queries (Level 3 cache).

This is the third level of the three-tier cache architecture:
1. Embedding Cache - query -> vector (saves API call)
2. Retrieval Cache - query -> chunk_ids + scores (saves embedding + search)
3. Answer Cache - query -> answer (saves entire pipeline including LLM)

When answer cache hits, we skip the ENTIRE pipeline and return immediately.
This is ideal for FAQ-type questions where the answer is stable.

Design Principles:
- Thread-safe: Uses threading.Lock
- Memory-bounded: LRU eviction
- TTL support: Auto-expire stale entries (shorter TTL for dynamic content)
- Query normalization: Consistent cache keys
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_query(query: str) -> str:
    """Normalize query for consistent cache keys."""
    return " ".join(query.lower().split())


@dataclass
class CachedAnswer:
    """Cached answer result."""
    answer: str
    sources: List[Dict[str, Any]]  # chunk_id, score, source_path
    timestamp: float
    metadata: Dict[str, Any]  # model, tokens, etc.


class AnswerCache:
    """LRU cache for complete answers with TTL support.
    
    Caches the final answer text so we can skip the entire RAG pipeline
    on cache hit. Best for FAQ-type questions with stable answers.
    
    Example:
        >>> cache = AnswerCache(max_size=500, ttl_seconds=604800)  # 7 days
        >>> 
        >>> # Check cache
        >>> cached = cache.get("报销流程是什么")
        >>> if cached is None:
        ...     answer = rag_pipeline.generate("报销流程是什么")
        ...     cache.put("报销流程是什么", answer, sources)
    """
    
    def __init__(
        self,
        max_size: int = 500,
        ttl_seconds: float = 604800,  # 7 days default for FAQ
    ):
        """Initialize answer cache.
        
        Args:
            max_size: Maximum number of answers to cache.
            ttl_seconds: Time-to-live for cache entries (seconds).
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CachedAnswer] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._expired = 0
    
    def _make_key(self, query: str) -> str:
        """Generate cache key from normalized query."""
        normalized = normalize_query(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    
    def _is_expired(self, entry: CachedAnswer) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - entry.timestamp) > self.ttl_seconds
    
    def get(self, query: str) -> Optional[CachedAnswer]:
        """Get cached answer.
        
        Args:
            query: Search query.
            
        Returns:
            Cached answer or None if not found/expired.
        """
        key = self._make_key(query)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if self._is_expired(entry):
                del self._cache[key]
                self._expired += 1
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry
    
    def put(
        self,
        query: str,
        answer: str,
        sources: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store answer in cache.
        
        Args:
            query: Search query.
            answer: Generated answer text.
            sources: List of source chunks used.
            metadata: Optional metadata (model, tokens, etc.).
        """
        key = self._make_key(query)
        
        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CachedAnswer(
                answer=answer,
                sources=sources,
                timestamp=time.time(),
                metadata=metadata or {},
            )
    
    def invalidate(self, query: Optional[str] = None) -> int:
        """Invalidate cache entries.
        
        Args:
            query: Specific query to invalidate. If None, clears all.
            
        Returns:
            Number of entries invalidated.
        """
        with self._lock:
            if query is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            
            key = self._make_key(query)
            if key in self._cache:
                del self._cache[key]
                return 1
            return 0
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "expired": self._expired,
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hit_rate": round(hit_rate, 4),
            }
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._expired = 0


# Global cache instance
_answer_cache: Optional[AnswerCache] = None


def get_answer_cache(
    max_size: int = 500,
    ttl_seconds: float = 604800,
) -> AnswerCache:
    """Get global answer cache."""
    global _answer_cache
    if _answer_cache is None:
        _answer_cache = AnswerCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
        )
    return _answer_cache
