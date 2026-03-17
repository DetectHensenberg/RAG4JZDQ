"""Retrieval result cache for skipping Embedding + Vector search.

This is the second level of the three-tier cache architecture:
1. Embedding Cache - query -> vector (saves API call)
2. Retrieval Cache - query -> chunk_ids + scores (saves embedding + search)
3. Answer Cache - query -> answer (saves entire pipeline)

When retrieval cache hits, we skip:
- Embedding API call (~300ms)
- Vector store query (~200ms)
Total savings: ~500ms per cache hit

Design Principles:
- Thread-safe: Uses threading.Lock
- Memory-bounded: LRU eviction
- TTL support: Auto-expire stale entries
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
    """Normalize query for consistent cache keys.
    
    - Lowercase
    - Strip whitespace
    - Collapse multiple spaces
    
    Args:
        query: Raw query string.
        
    Returns:
        Normalized query string.
    """
    return " ".join(query.lower().split())


@dataclass
class CachedRetrievalResult:
    """Cached retrieval result."""
    chunk_ids: List[str]
    scores: Dict[str, float]  # chunk_id -> score
    texts: Dict[str, str]     # chunk_id -> text
    metadata: Dict[str, Dict[str, Any]]  # chunk_id -> metadata
    timestamp: float          # Unix timestamp when cached


class RetrievalCache:
    """LRU cache for retrieval results with TTL support.
    
    Caches the full retrieval result (chunk_ids, scores, texts, metadata)
    so we can skip both embedding and vector search on cache hit.
    
    Example:
        >>> cache = RetrievalCache(max_size=1000, ttl_seconds=86400)
        >>> 
        >>> # Check cache
        >>> cached = cache.get("报销流程")
        >>> if cached is None:
        ...     results = hybrid_search.search("报销流程")
        ...     cache.put("报销流程", results)
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float = 86400,  # 1 day default
    ):
        """Initialize retrieval cache.
        
        Args:
            max_size: Maximum number of queries to cache.
            ttl_seconds: Time-to-live for cache entries (seconds).
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CachedRetrievalResult] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._expired = 0
    
    def _make_key(self, query: str) -> str:
        """Generate cache key from normalized query."""
        normalized = normalize_query(query)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    
    def _is_expired(self, entry: CachedRetrievalResult) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - entry.timestamp) > self.ttl_seconds
    
    def get(self, query: str) -> Optional[CachedRetrievalResult]:
        """Get cached retrieval result.
        
        Args:
            query: Search query.
            
        Returns:
            Cached result or None if not found/expired.
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
        chunk_ids: List[str],
        scores: Dict[str, float],
        texts: Dict[str, str],
        metadata: Dict[str, Dict[str, Any]],
    ) -> None:
        """Store retrieval result in cache.
        
        Args:
            query: Search query.
            chunk_ids: Ordered list of chunk IDs.
            scores: Dict of chunk_id -> score.
            texts: Dict of chunk_id -> text.
            metadata: Dict of chunk_id -> metadata.
        """
        key = self._make_key(query)
        
        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CachedRetrievalResult(
                chunk_ids=chunk_ids,
                scores=scores,
                texts=texts,
                metadata=metadata,
                timestamp=time.time(),
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
_retrieval_cache: Optional[RetrievalCache] = None


def get_retrieval_cache(
    max_size: int = 1000,
    ttl_seconds: float = 86400,
) -> RetrievalCache:
    """Get global retrieval cache."""
    global _retrieval_cache
    if _retrieval_cache is None:
        _retrieval_cache = RetrievalCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
        )
    return _retrieval_cache
