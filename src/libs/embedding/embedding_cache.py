"""Embedding cache for reducing redundant API calls.

This module provides an LRU cache for embeddings to avoid recomputing
embeddings for the same text. Useful for:
1. Query embedding caching (same queries repeated)
2. Chunk embedding caching (re-ingestion of unchanged content)

Design Principles:
- Thread-safe: Uses threading.Lock for concurrent access
- Memory-bounded: LRU eviction when cache is full
- Persistent option: Can save/load cache to disk
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


class EmbeddingCache:
    """LRU cache for text embeddings.
    
    Caches embeddings keyed by text hash to avoid redundant API calls.
    Thread-safe for concurrent access.
    
    Example:
        >>> cache = EmbeddingCache(max_size=1000)
        >>> 
        >>> # Check cache first
        >>> embedding = cache.get("Hello world")
        >>> if embedding is None:
        ...     embedding = api.embed("Hello world")
        ...     cache.put("Hello world", embedding)
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        persist_path: Optional[str] = None,
    ):
        """Initialize embedding cache.
        
        Args:
            max_size: Maximum number of embeddings to cache.
            persist_path: Optional path to persist cache to disk.
        """
        self.max_size = max_size
        self.persist_path = Path(persist_path) if persist_path else None
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        
        # Load from disk if persist_path exists
        if self.persist_path and self.persist_path.exists():
            self._load()
    
    def _hash_text(self, text: str, normalize: bool = True) -> str:
        """Generate hash key for text.
        
        Args:
            text: Text to hash.
            normalize: Whether to normalize text before hashing (for queries).
        """
        if normalize:
            text = normalize_query(text)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache.
        
        Args:
            text: Text to look up.
            
        Returns:
            Cached embedding or None if not found.
        """
        key = self._hash_text(text)
        
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            
            self._misses += 1
            return None
    
    def get_batch(self, texts: List[str]) -> Tuple[List[Optional[List[float]]], List[int]]:
        """Get embeddings for multiple texts.
        
        Args:
            texts: List of texts to look up.
            
        Returns:
            Tuple of (embeddings, miss_indices) where embeddings[i] is None
            for cache misses, and miss_indices contains indices that need
            to be computed.
        """
        results: List[Optional[List[float]]] = []
        miss_indices: List[int] = []
        
        with self._lock:
            for i, text in enumerate(texts):
                key = self._hash_text(text)
                if key in self._cache:
                    self._cache.move_to_end(key)
                    results.append(self._cache[key])
                    self._hits += 1
                else:
                    results.append(None)
                    miss_indices.append(i)
                    self._misses += 1
        
        return results, miss_indices
    
    def put(self, text: str, embedding: List[float]) -> None:
        """Store embedding in cache.
        
        Args:
            text: Original text.
            embedding: Computed embedding vector.
        """
        key = self._hash_text(text)
        
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = embedding
    
    def put_batch(self, texts: List[str], embeddings: List[List[float]]) -> None:
        """Store multiple embeddings in cache.
        
        Args:
            texts: List of original texts.
            embeddings: List of computed embeddings.
        """
        if len(texts) != len(embeddings):
            raise ValueError("texts and embeddings must have same length")
        
        with self._lock:
            for text, embedding in zip(texts, embeddings):
                key = self._hash_text(text)
                
                # Remove oldest if at capacity
                while len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                
                self._cache[key] = embedding
    
    def stats(self) -> Dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dict with hits, misses, size, and hit_rate.
        """
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
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def save(self) -> None:
        """Save cache to disk (if persist_path configured)."""
        if not self.persist_path:
            return
        
        with self._lock:
            try:
                self.persist_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.persist_path, "w", encoding="utf-8") as f:
                    json.dump(dict(self._cache), f)
                logger.info(f"Saved {len(self._cache)} embeddings to {self.persist_path}")
            except Exception as e:
                logger.warning(f"Failed to save embedding cache: {e}")
    
    def _load(self) -> None:
        """Load cache from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return
        
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._cache = OrderedDict(data)
            logger.info(f"Loaded {len(self._cache)} embeddings from {self.persist_path}")
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")


# Global cache instances
_query_cache: Optional[EmbeddingCache] = None
_chunk_cache: Optional[EmbeddingCache] = None


def get_query_cache(max_size: int = 1000) -> EmbeddingCache:
    """Get global query embedding cache."""
    global _query_cache
    if _query_cache is None:
        _query_cache = EmbeddingCache(max_size=max_size)
    return _query_cache


def get_chunk_cache(max_size: int = 50000) -> EmbeddingCache:
    """Get global chunk embedding cache."""
    global _chunk_cache
    if _chunk_cache is None:
        _chunk_cache = EmbeddingCache(max_size=max_size)
    return _chunk_cache
