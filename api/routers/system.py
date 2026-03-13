"""System overview API router — stats and metrics."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()


def _dir_size(path: Path) -> int:
    total = 0
    if path.exists():
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024*1024):.1f} MB"
    return f"{size_bytes / (1024*1024*1024):.2f} GB"


@router.get("/stats")
async def get_stats():
    """Return system-wide statistics."""
    stats: dict[str, Any] = {
        "collections": [],
        "total_documents": 0,
        "total_chunks": 0,
        "total_images": 0,
        "chroma_size": "0 B",
        "bm25_size": "0 B",
        "image_size": "0 B",
    }

    # ChromaDB stats
    chroma_dir = resolve_path("data/db/chroma")
    stats["chroma_size"] = _format_size(_dir_size(chroma_dir))

    try:
        import sqlite3
        db_path = chroma_dir / "chroma.sqlite3"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            stats["total_chunks"] = count
            conn.close()
    except Exception:
        pass

    # BM25 stats
    bm25_dir = resolve_path("data/db/bm25")
    stats["bm25_size"] = _format_size(_dir_size(bm25_dir))

    # Image stats
    images_dir = resolve_path("data/images")
    stats["image_size"] = _format_size(_dir_size(images_dir))
    if images_dir.exists():
        stats["total_images"] = sum(1 for _ in images_dir.rglob("*.png"))

    # Document count from ingestion history
    try:
        import sqlite3
        hist_path = resolve_path("data/db/ingestion_history.db")
        if hist_path.exists():
            conn = sqlite3.connect(str(hist_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM ingestion_history WHERE status='success'").fetchone()[0]
                stats["total_documents"] = count
            except Exception:
                pass
            conn.close()
    except Exception:
        pass

    # Collections from BM25 directories
    if bm25_dir.exists():
        for d in bm25_dir.iterdir():
            if d.is_dir():
                stats["collections"].append(d.name)
    if not stats["collections"]:
        stats["collections"] = ["default"]

    return {"ok": True, "data": stats}
