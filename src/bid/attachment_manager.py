"""Attachment manager for achievement records.

Stores uploaded files in ``data/attachments/{record_id}/`` and provides
save / list / delete / path-lookup operations.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)

_ATTACHMENTS_ROOT = resolve_path("data/attachments")


@dataclass(frozen=True)
class AttachmentInfo:
    """Metadata about a single attachment file."""

    filename: str
    size: int
    path: str


def _record_dir(record_id: int) -> Path:
    d = _ATTACHMENTS_ROOT / str(record_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_attachment(record_id: int, filename: str, content: bytes) -> AttachmentInfo:
    """Write *content* to ``data/attachments/{record_id}/{filename}``.

    Returns an :class:`AttachmentInfo` describing the saved file.
    """
    safe_name = Path(filename).name  # strip any directory components
    dest = _record_dir(record_id) / safe_name
    dest.write_bytes(content)
    logger.info(f"Saved attachment {safe_name} ({len(content)} bytes) for record {record_id}")
    return AttachmentInfo(filename=safe_name, size=len(content), path=str(dest))


def list_attachments(record_id: int) -> List[AttachmentInfo]:
    """Return all attachments for a given record."""
    d = _ATTACHMENTS_ROOT / str(record_id)
    if not d.exists():
        return []
    return [
        AttachmentInfo(filename=f.name, size=f.stat().st_size, path=str(f))
        for f in sorted(d.iterdir())
        if f.is_file()
    ]


def get_attachment_path(record_id: int, filename: str) -> Path | None:
    """Return the absolute path if the file exists, else ``None``."""
    safe_name = Path(filename).name
    p = _ATTACHMENTS_ROOT / str(record_id) / safe_name
    return p if p.is_file() else None


def delete_attachment(record_id: int, filename: str) -> bool:
    """Delete a single attachment. Returns ``True`` if removed."""
    p = get_attachment_path(record_id, filename)
    if p is None:
        return False
    p.unlink()
    logger.info(f"Deleted attachment {filename} for record {record_id}")
    return True


def delete_all_attachments(record_id: int) -> int:
    """Delete all attachments for a record. Returns count removed."""
    d = _ATTACHMENTS_ROOT / str(record_id)
    if not d.exists():
        return 0
    count = sum(1 for f in d.iterdir() if f.is_file())
    shutil.rmtree(d, ignore_errors=True)
    logger.info(f"Deleted {count} attachments for record {record_id}")
    return count
