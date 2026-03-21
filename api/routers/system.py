"""System overview API router — stats and metrics."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from src.core.settings import resolve_path
from src.ingestion.stats import get_stats_tracker

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
        import aiosqlite
        db_path = chroma_dir / "chroma.sqlite3"
        if db_path.exists():
            async with aiosqlite.connect(str(db_path)) as conn:
                async with conn.execute("SELECT COUNT(*) FROM embeddings") as cursor:
                    row = await cursor.fetchone()
                    stats["total_chunks"] = row[0] if row else 0
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
        import aiosqlite
        hist_path = resolve_path("data/db/ingestion_history.db")
        if hist_path.exists():
            async with aiosqlite.connect(str(hist_path)) as conn:
                try:
                    async with conn.execute("SELECT COUNT(*) FROM ingestion_history WHERE status='success'") as cursor:
                        row = await cursor.fetchone()
                        stats["total_documents"] = row[0] if row else 0
                except Exception:
                    pass
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


@router.get("/ingestion-stats")
async def get_ingestion_stats(days: int = 30):
    """Return ingestion pipeline statistics.
    
    Args:
        days: Number of days to aggregate (default 30)
        
    Returns:
        Aggregated ingestion statistics
    """
    try:
        tracker = get_stats_tracker()
        stats = tracker.to_dict(days=days)
        return {"ok": True, "data": stats}
    except Exception as e:
        logger.exception(f"Failed to get ingestion stats: {e}")
        return {"ok": False, "message": str(e)}


@router.get("/cache-stats")
async def get_cache_stats():
    """Return cache statistics for performance monitoring.
    
    Returns:
        Statistics for all cache layers (L1: Embedding, L2: Retrieval, L3: Answer, Rerank).
    """
    try:
        from src.libs.embedding.embedding_cache import get_query_cache
        from src.core.query_engine.retrieval_cache import get_retrieval_cache
        from src.core.query_engine.answer_cache import get_answer_cache
        from src.core.query_engine.rerank_cache import get_rerank_cache
        
        query_cache = get_query_cache()
        retrieval_cache = get_retrieval_cache()
        answer_cache = get_answer_cache()
        rerank_cache = get_rerank_cache()
        
        return {
            "ok": True,
            "data": {
                "L1_embedding_cache": query_cache.stats(),
                "L2_retrieval_cache": retrieval_cache.stats(),
                "L3_answer_cache": answer_cache.stats(),
                "rerank_cache": rerank_cache.stats(),
            }
        }
    except Exception as e:
        logger.exception(f"Failed to get cache stats: {e}")
        return {"ok": False, "message": str(e)}
