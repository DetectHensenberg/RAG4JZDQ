"""Rate limiting middleware using Redis (or in-memory fallback).

Implements a sliding-window counter per client IP. When Redis is
unavailable, degrades to process-local cachetools.TTLCache counting.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-route rate limit configuration
# ---------------------------------------------------------------------------
# Format: route_prefix -> (max_requests, window_seconds)
# LLM-heavy endpoints have tighter limits to prevent token abuse.
# Adjust values based on deployment scale and cost tolerance.
DEFAULT_RATE_LIMITS: Dict[str, tuple[int, int]] = {
    "/api/chat/stream": (20, 60),    # 20 req/min — LLM streaming, high cost
    "/api/ingest": (5, 60),          # 5 req/min  — file ingestion, I/O heavy
    "/api/bid": (15, 60),            # 15 req/min — bid assistant
    "/api/solution": (15, 60),       # 15 req/min — solution assistant
}

# Default limit for routes without specific config
GLOBAL_RATE_LIMIT: tuple[int, int] = (60, 60)  # 60 req/min


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces per-IP rate limiting.

    Uses Redis INCR for distributed counting, with automatic
    degradation to in-memory counting when Redis is offline.

    Attributes:
        rate_limits: Route-specific rate limit configuration.
        global_limit: Default rate limit for unspecified routes.
    """

    def __init__(
        self,
        app: Callable,
        rate_limits: Optional[Dict[str, tuple[int, int]]] = None,
        global_limit: Optional[tuple[int, int]] = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            app: The ASGI application to wrap.
            rate_limits: Route-specific limits as dict of prefix -> (max, window_sec).
            global_limit: Default limit for routes without specific config.
        """
        super().__init__(app)
        self.rate_limits = rate_limits or DEFAULT_RATE_LIMITS
        self.global_limit = global_limit or GLOBAL_RATE_LIMIT

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through rate limiter.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware/handler in the chain.

        Returns:
            The response, or 429 if rate limit exceeded.
        """
        path = request.url.path

        # Skip non-API and health endpoints
        if not path.startswith("/api/") or path in ("/api/health", "/api/docs", "/api/openapi.json"):
            return await call_next(request)

        # Determine rate limit for this route
        max_requests, window = self.global_limit
        for prefix, (limit, win) in self.rate_limits.items():
            if path.startswith(prefix):
                max_requests, window = limit, win
                break

        # Build rate limit key from client IP
        client_ip = request.client.host if request.client else "unknown"
        rate_key = f"rl:{client_ip}:{path.split('/')[2] if len(path.split('/')) > 2 else 'default'}"

        # Check counter
        cache = get_cache_service()
        current_count = await cache.incr(rate_key, ttl=window)

        if current_count > max_requests:
            logger.warning(
                f"Rate limit exceeded: {client_ip} on {path} ({current_count}/{max_requests})"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "message": f"请求过于频繁，请在 {window} 秒后重试",
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Proceed and attach rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, max_requests - current_count))
        return response
