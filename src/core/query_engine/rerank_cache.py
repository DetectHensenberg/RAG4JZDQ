"""Reranker result cache for reducing redundant cross-encoder calls.

Cross-encoder reranking is CPU-intensive (~3.5s per query). This cache
stores reranked results keyed by (query, candidate_ids) to avoid
recomputing for repeated queries with same candidates.

Design Principles:
- Thread-safe: Uses threading.Lock for concurrent access
- Memory-bounded: LRU eviction when cache is full
- Fast lookup: Hash-based key generation
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CachedRerankResult:
    """Cached rerank result."""
    reranked_ids: List[str]  # Ordered list of chunk IDs after reranking
    scores: Dict[str, float]  # chunk_id -> rerank_score


class RerankCache:
    """LRU cache for reranker results.
    
    Caches reranked results keyed by (query_hash, candidate_ids_hash) to
    avoid redundant cross-encoder computations.
    
    Example:
        >>> cache = RerankCache(max_size=500)
        >>> 
        >>> # Check cache
        >>> cached = cache.get(query, candidate_ids)
        >>> if cached is None:
        ...     result = reranker.rerank(query, candidates)
        ...     cache.put(query, candidate_ids, result)
    """
    
    def __init__(self, max_size: int = 500):
        """Initialize rerank cache.
        
        Args:
            max_size: Maximum number of rerank results to cache.
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, CachedRerankResult] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, query: str, candidate_ids: List[str]) -> str:
        """Generate cache key from query and candidate IDs."""
        # Sort candidate IDs for consistent hashing
        sorted_ids = sorted(candidate_ids)
        key_str = f"{query}|{'|'.join(sorted_ids)}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:24]
    
    def get(
        self, 
        query: str, 
        candidate_ids: List[str]
    ) -> Optional[CachedRerankResult]:
        """Get cached rerank result.
        
        Args:
            query: The search query.
            candidate_ids: List of candidate chunk IDs.
            
        Returns:
            Cached result or None if not found.
        """
        key = self._make_key(query, candidate_ids)
        
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            
            self._misses += 1
            return None
    
    def put(
        self,
        query: str,
        candidate_ids: List[str],
        reranked_ids: List[str],
        scores: Dict[str, float],
    ) -> None:
        """Store rerank result in cache.
        
        Args:
            query: The search query.
            candidate_ids: Original candidate chunk IDs.
            reranked_ids: Reranked chunk IDs (in order).
            scores: Dict of chunk_id -> rerank_score.
        """
        key = self._make_key(query, candidate_ids)
        
        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CachedRerankResult(
                reranked_ids=reranked_ids,
                scores=scores,
            )
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": round(hit_rate, 4),
            }
    
    def clear(self) -> None:
        """Clear cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global cache instance
_rerank_cache: Optional[RerankCache] = None


def get_rerank_cache(max_size: int = 500) -> RerankCache:
    """Get global rerank cache."""
    global _rerank_cache
    if _rerank_cache is None:
        _rerank_cache = RerankCache(max_size=max_size)
    return _rerank_cache
