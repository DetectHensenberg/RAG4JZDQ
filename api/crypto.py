"""Symmetric encryption utilities for secrets at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` package.
A machine-local key is derived from ``APP_ENCRYPT_KEY`` env var.  If the
var is unset, a random key is generated and persisted to ``.encrypt_key``
beside the project root (gitignored).

Fallback: if the ``cryptography`` package is not installed, functions
degrade to base64-only encoding with a logged warning.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KEY: Optional[bytes] = None
_HAS_FERNET = False

try:
    from cryptography.fernet import Fernet

    _HAS_FERNET = True
except ImportError:
    logger.warning(
        "cryptography package not installed — secrets will use base64 only. "
        "Install with: pip install cryptography"
    )


def _get_or_create_key() -> bytes:
    """Return a 32-byte Fernet key, creating one if needed."""
    global _KEY
    if _KEY is not None:
        return _KEY

    # Priority 1: env var
    env_key = os.environ.get("APP_ENCRYPT_KEY", "").strip()
    if env_key:
        # Derive a proper Fernet key from arbitrary string
        derived = hashlib.sha256(env_key.encode()).digest()
        _KEY = base64.urlsafe_b64encode(derived)
        return _KEY

    # Priority 2: key file
    key_file = Path(__file__).resolve().parent.parent / ".encrypt_key"
    if key_file.exists():
        _KEY = key_file.read_bytes().strip()
        return _KEY

    # Priority 3: generate and persist
    if _HAS_FERNET:
        _KEY = Fernet.generate_key()
    else:
        _KEY = base64.urlsafe_b64encode(os.urandom(32))
    key_file.write_bytes(_KEY)
    logger.info("Generated new encryption key at %s", key_file)
    return _KEY


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a URL-safe base64 token.

    Args:
        plaintext: The secret to encrypt.

    Returns:
        Encrypted token string.
    """
    if not plaintext:
        return ""

    key = _get_or_create_key()

    if _HAS_FERNET:
        f = Fernet(key)
        return f.encrypt(plaintext.encode("utf-8")).decode("ascii")

    # Fallback: base64 only (not secure, just obfuscation)
    return base64.urlsafe_b64encode(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token back to plaintext.

    Args:
        token: The encrypted token from :func:`encrypt`.

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If decryption fails (wrong key or corrupted token).
    """
    if not token:
        return ""

    key = _get_or_create_key()

    if _HAS_FERNET:
        try:
            f = Fernet(key)
            return f.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise ValueError(f"Decryption failed: {exc}") from exc

    # Fallback: base64
    try:
        return base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Base64 decode failed: {exc}") from exc
