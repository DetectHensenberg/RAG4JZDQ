"""Data browser API router — browse collections, documents, chunks."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/collections")
async def list_collections():
    """List all collections with chunk counts."""
    bm25_dir = resolve_path("data/db/bm25")
    collections = []
    if bm25_dir.exists():
        for d in bm25_dir.iterdir():
            if d.is_dir():
                collections.append(d.name)
    if not collections:
        collections = ["default"]

    # Get chunk count from ChromaDB
    result = []
    try:
        db_path = resolve_path("data/db/chroma/chroma.sqlite3")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            conn.close()
            result = [{"name": c, "count": count if c == "default" else 0} for c in collections]
        else:
            result = [{"name": c, "count": 0} for c in collections]
    except Exception:
        result = [{"name": c, "count": 0} for c in collections]

    return {"ok": True, "data": result}


@router.get("/documents")
async def list_documents(collection: str = "default", page: int = 1, size: int = 20):
    """List documents in a collection with pagination."""
    try:
        hist_path = resolve_path("data/db/ingestion_history.db")
        if not hist_path.exists():
            return {"ok": True, "data": {"items": [], "total": 0}}

        conn = sqlite3.connect(str(hist_path))
        total = conn.execute(
            "SELECT COUNT(*) FROM ingestion_history WHERE status='success' AND collection=?",
            (collection,),
        ).fetchone()[0]

        offset = (page - 1) * size
        rows = conn.execute(
            "SELECT file_hash, source_path, collection, status, created_at FROM ingestion_history "
            "WHERE status='success' AND collection=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (collection, size, offset),
        ).fetchall()
        conn.close()

        items = [
            {"file_hash": r[0], "source_path": r[1], "collection": r[2], "status": r[3], "created_at": r[4]}
            for r in rows
        ]
        return {"ok": True, "data": {"items": items, "total": total}}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.get("/chunks/{file_hash}")
async def get_chunks(file_hash: str):
    """Get chunks for a specific document by file hash."""
    try:
        db_path = resolve_path("data/db/chroma/chroma.sqlite3")
        if not db_path.exists():
            return {"ok": True, "data": []}

        conn = sqlite3.connect(str(db_path))
        # Find embedding IDs matching the file hash prefix
        rows = conn.execute(
            "SELECT e.embedding_id, em.string_value "
            "FROM embeddings e JOIN embedding_metadata em ON e.id = em.id "
            "WHERE em.key = 'text' AND e.embedding_id LIKE ?",
            (f"{file_hash[:8]}%",),
        ).fetchall()
        conn.close()

        chunks = [{"id": r[0], "text": r[1][:500] if r[1] else ""} for r in rows]
        return {"ok": True, "data": chunks}
    except Exception as e:
        return {"ok": False, "message": str(e)}
