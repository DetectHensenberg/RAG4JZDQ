"""Cache service with Redis primary and in-memory fallback.

Provides a unified async cache interface that transparently degrades
from Redis to a process-local TTLCache when Redis is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class CacheService:
    """Dual-mode cache: Redis when available, in-memory TTLCache as fallback.

    All methods are async-safe. Redis connection failures are caught
    and logged; the service never raises due to cache infrastructure issues.

    Attributes:
        _redis: Optional async Redis client.
        _memory: In-memory TTLCache fallback.
        _using_redis: Whether Redis is currently active.
    """

    # Default TTL (seconds) for cached entries when caller doesn't specify.
    # 5 minutes balances freshness with LLM call cost savings.
    DEFAULT_TTL: int = 300

    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = DEFAULT_TTL) -> None:
        """Initialize cache service.

        Args:
            redis_url: Redis connection URL. Falls back to env var REDIS_URL.
            default_ttl: Default TTL in seconds for cached entries.
        """
        self._redis = None
        self._using_redis = False
        self._default_ttl = default_ttl

        # In-memory fallback
        from cachetools import TTLCache

        self._memory: TTLCache = TTLCache(maxsize=1024, ttl=default_ttl)

        # Try Redis connection
        url = redis_url or os.environ.get("REDIS_URL", "")
        if url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
                self._using_redis = True
                logger.info(f"CacheService: Redis connected ({url[:30]}...)")
            except Exception as e:
                logger.warning(f"CacheService: Redis unavailable, using memory fallback: {e}")
        else:
            logger.info("CacheService: No REDIS_URL configured, using memory-only mode")

    @property
    def is_redis_active(self) -> bool:
        """Check if Redis backend is currently active."""
        return self._using_redis

    async def get(self, key: str) -> Optional[str]:
        """Retrieve a cached value by key.

        Args:
            key: Cache key string.

        Returns:
            The cached value string, or None if not found.
        """
        if self._using_redis:
            try:
                return await self._redis.get(key)  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"Redis GET failed, falling back to memory: {e}")
                self._using_redis = False

        return self._memory.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Store a value in cache.

        Args:
            key: Cache key string.
            value: Value to cache.
            ttl: Time-to-live in seconds. Uses default_ttl if None.
        """
        expire = ttl if ttl is not None else self._default_ttl

        if self._using_redis:
            try:
                await self._redis.setex(key, expire, value)  # type: ignore[union-attr]
                return
            except Exception as e:
                logger.debug(f"Redis SET failed, falling back to memory: {e}")
                self._using_redis = False

        self._memory[key] = value

    async def delete(self, key: str) -> None:
        """Remove a key from cache.

        Args:
            key: Cache key to delete.
        """
        if self._using_redis:
            try:
                await self._redis.delete(key)  # type: ignore[union-attr]
                return
            except Exception:
                pass
        self._memory.pop(key, None)

    async def incr(self, key: str, ttl: int = 60) -> int:
        """Atomically increment a counter (used for rate limiting).

        Args:
            key: Counter key.
            ttl: TTL in seconds for the counter window.

        Returns:
            The incremented counter value.
        """
        if self._using_redis:
            try:
                pipe = self._redis.pipeline()  # type: ignore[union-attr]
                pipe.incr(key)
                pipe.expire(key, ttl)
                results = await pipe.execute()
                return results[0]
            except Exception as e:
                logger.debug(f"Redis INCR failed, falling back to memory: {e}")
                self._using_redis = False

        # Memory fallback for rate limiting
        current = self._memory.get(key, 0)
        current += 1
        self._memory[key] = current
        return current

    async def close(self) -> None:
        """Gracefully close the Redis connection if active."""
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_cache_instance: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Return a singleton CacheService instance.

    Returns:
        The global CacheService, initialized on first call.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService()
    return _cache_instance
