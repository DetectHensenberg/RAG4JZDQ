"""Security utilities — API Key authentication and path validation.

When the environment variable APP_API_KEY is set, all /api/* endpoints
(except /api/health and /api/docs) require the header ``X-API-Key``.
If the variable is empty or unset, authentication is **disabled** so
that local development stays frictionless.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Paths that never require authentication
_PUBLIC_PATHS = frozenset({"/api/health", "/api/docs", "/api/openapi.json"})


def _get_app_api_key() -> Optional[str]:
    """Return configured API key, or None if auth is disabled."""
    key = os.environ.get("APP_API_KEY", "").strip()
    return key if key else None


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> Optional[str]:
    """FastAPI dependency that enforces API-key auth when configured.

    Returns the validated key, or None when auth is disabled.
    Raises 401 if key is missing/wrong and auth is enabled.
    """
    expected = _get_app_api_key()

    # Auth disabled — pass through
    if expected is None:
        return None

    # Public endpoints — pass through
    if request.url.path in _PUBLIC_PATHS:
        return None

    if not api_key or api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )

    return api_key


# ---------------------------------------------------------------------------
# Path Traversal Protection
# ---------------------------------------------------------------------------

# Allowed base directories for file operations (normalised at startup)
_ALLOWED_BASES: list[Path] = []

# Dangerous patterns in path components
_DANGEROUS_PATTERNS = re.compile(r"\.\.|~|%2e%2e|%252e", re.IGNORECASE)


def add_allowed_base(path: str | Path) -> None:
    """Register an allowed base directory for path validation."""
    resolved = Path(path).resolve()
    if resolved not in _ALLOWED_BASES:
        _ALLOWED_BASES.append(resolved)
        logger.debug("Allowed base directory registered: %s", resolved)


def validate_path(user_path: str, must_exist: bool = False) -> Path:
    """Validate a user-supplied path against traversal attacks.

    Args:
        user_path: The raw path string from the request.
        must_exist: If True, also verify the path exists on disk.

    Returns:
        Resolved, validated Path object.

    Raises:
        HTTPException 400: If the path contains traversal patterns or
            falls outside all allowed base directories.
        HTTPException 404: If *must_exist* is True and path is missing.
    """
    if not user_path or not user_path.strip():
        raise HTTPException(status_code=400, detail="路径不能为空")

    # Block obvious traversal patterns before resolution
    if _DANGEROUS_PATTERNS.search(user_path):
        logger.warning("Path traversal attempt blocked: %s", user_path[:200])
        raise HTTPException(status_code=400, detail="路径包含非法字符")

    resolved = Path(user_path).resolve()

    # If allowed bases are configured, enforce them
    if _ALLOWED_BASES:
        if not any(
            resolved == base or _is_subpath(resolved, base)
            for base in _ALLOWED_BASES
        ):
            logger.warning(
                "Path outside allowed bases: %s (allowed: %s)",
                resolved,
                [str(b) for b in _ALLOWED_BASES],
            )
            raise HTTPException(status_code=400, detail="路径不在允许的范围内")

    if must_exist and not resolved.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {user_path}")

    return resolved


def _is_subpath(child: Path, parent: Path) -> bool:
    """Check if *child* is a sub-path of *parent* (platform-safe)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
