"""Data browser API router — browse collections, documents, chunks, images."""

from __future__ import annotations

import base64
import logging
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from api.db import get_connection
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
            with get_connection(db_path, wal=False) as conn:
                count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
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

        with get_connection(hist_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM ingestion_history WHERE status='success' AND collection=?",
                (collection,),
            ).fetchone()[0]

            offset = (page - 1) * size
            rows = conn.execute(
                "SELECT file_hash, file_path, collection, status, processed_at FROM ingestion_history "
                "WHERE status='success' AND collection=? ORDER BY processed_at DESC LIMIT ? OFFSET ?",
                (collection, size, offset),
            ).fetchall()

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

        with get_connection(db_path, wal=False) as conn:
            # Find embedding IDs matching the file hash prefix
            rows = conn.execute(
                "SELECT e.embedding_id, em.string_value "
                "FROM embeddings e JOIN embedding_metadata em ON e.id = em.id "
                "WHERE em.key = 'text' AND e.embedding_id LIKE ?",
                (f"{file_hash[:8]}%",),
            ).fetchall()

        chunks = [{"id": r[0], "text": r[1][:500] if r[1] else ""} for r in rows]
        return {"ok": True, "data": chunks}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.get("/images/{image_id}")
async def get_image(image_id: str, collection: str = "default"):
    """Get image by ID, returns base64 encoded image data."""
    try:
        from src.ingestion.storage.image_storage import ImageStorage
        
        images_root = resolve_path("data/images")
        db_path = resolve_path("data/db/image_index.db")
        
        storage = ImageStorage(str(db_path), str(images_root))
        img_path = storage.get_image_path(image_id)
        
        if not img_path:
            return {"ok": False, "message": f"Image not found: {image_id}"}
        
        path = Path(img_path)
        if not path.exists():
            return {"ok": False, "message": f"Image file not found: {img_path}"}
        
        # Read and encode image
        data = path.read_bytes()
        b64_data = base64.b64encode(data).decode("utf-8")
        
        # Detect MIME type
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/png")
        
        return {
            "ok": True,
            "data": {
                "image_id": image_id,
                "base64": b64_data,
                "mime_type": mime_type,
            }
        }
    except Exception as e:
        logger.exception(f"Failed to get image {image_id}")
        return {"ok": False, "message": str(e)}


@router.get("/images/{image_id}/raw")
async def get_image_raw(image_id: str, collection: str = "default"):
    """Get raw image file by ID."""
    try:
        from src.ingestion.storage.image_storage import ImageStorage
        
        images_root = resolve_path("data/images")
        db_path = resolve_path("data/db/image_index.db")
        
        storage = ImageStorage(str(db_path), str(images_root))
        img_path = storage.get_image_path(image_id)
        
        if not img_path:
            return Response(content=b"Image not found", status_code=404)
        
        path = Path(img_path)
        if not path.exists():
            return Response(content=b"Image file not found", status_code=404)
        
        # Detect MIME type
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/png")
        
        return Response(content=path.read_bytes(), media_type=mime_type)
    except Exception as e:
        logger.exception(f"Failed to get raw image {image_id}")
        return Response(content=str(e), status_code=500)
