"""Data management API router - clear data, reset collections."""

from __future__ import annotations

import logging
import shutil
from typing import List

from fastapi import APIRouter

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()


@router.delete("/clear-all")
async def clear_all_data():
    """Clear all data from all stores (ChromaDB, BM25, images, history).
    
    WARNING: This is a destructive operation!
    
    Returns:
        Summary of what was cleared
    """
    summary = {
        "chroma_cleared": False,
        "bm25_cleared": False,
        "images_cleared": False,
        "history_cleared": False,
        "traces_cleared": False,
        "errors": [],
    }
    
    # 1. Clear ChromaDB
    try:
        chroma_dir = resolve_path("data/db/chroma")
        if chroma_dir.exists():
            shutil.rmtree(chroma_dir)
            chroma_dir.mkdir(parents=True, exist_ok=True)
        summary["chroma_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"ChromaDB: {e}")
        logger.exception(f"Failed to clear ChromaDB: {e}")
    
    # 2. Clear BM25 indexes
    try:
        bm25_dir = resolve_path("data/db/bm25")
        if bm25_dir.exists():
            shutil.rmtree(bm25_dir)
            bm25_dir.mkdir(parents=True, exist_ok=True)
        summary["bm25_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"BM25: {e}")
        logger.exception(f"Failed to clear BM25: {e}")
    
    # 3. Clear image storage
    try:
        img_db = resolve_path("data/db/image_index.db")
        if img_db.exists():
            img_db.unlink()
        img_dir = resolve_path("data/images")
        if img_dir.exists():
            shutil.rmtree(img_dir)
            img_dir.mkdir(parents=True, exist_ok=True)
        summary["images_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"Images: {e}")
        logger.exception(f"Failed to clear images: {e}")
    
    # 4. Clear ingestion history
    try:
        hist_db = resolve_path("data/db/ingestion_history.db")
        if hist_db.exists():
            hist_db.unlink()
        summary["history_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"History: {e}")
        logger.exception(f"Failed to clear history: {e}")
    
    # 5. Clear trace logs
    try:
        traces_file = resolve_path("logs/traces.jsonl")
        if traces_file.exists():
            traces_file.unlink()
        summary["traces_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"Traces: {e}")
        logger.exception(f"Failed to clear traces: {e}")
    
    # Reset cached instances
    try:
        from api.deps import reset_all
        reset_all()
    except Exception as e:
        summary["errors"].append(f"Reset: {e}")
    
    logger.info(f"Clear all data completed: {summary}")
    return {"ok": True, "data": summary}


@router.delete("/collection/{collection_name}")
async def clear_collection(collection_name: str):
    """Clear data for a specific collection.
    
    Args:
        collection_name: Name of the collection to clear
        
    Returns:
        Summary of what was cleared
    """
    summary = {
        "collection": collection_name,
        "chroma_cleared": False,
        "bm25_cleared": False,
        "errors": [],
    }
    
    # 1. Clear collection from ChromaDB
    try:
        import chromadb
        chroma_dir = resolve_path("data/db/chroma")
        client = chromadb.PersistentClient(path=str(chroma_dir))
        try:
            client.delete_collection(collection_name)
            summary["chroma_cleared"] = True
        except Exception:
            # Collection might not exist
            summary["chroma_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"ChromaDB: {e}")
        logger.exception(f"Failed to clear ChromaDB collection: {e}")
    
    # 2. Clear BM25 index for collection
    try:
        bm25_dir = resolve_path(f"data/db/bm25/{collection_name}")
        if bm25_dir.exists():
            shutil.rmtree(bm25_dir)
        summary["bm25_cleared"] = True
    except Exception as e:
        summary["errors"].append(f"BM25: {e}")
        logger.exception(f"Failed to clear BM25 index: {e}")
    
    # Reset cached instances
    try:
        from api.deps import reset_all
        reset_all()
    except Exception as e:
        summary["errors"].append(f"Reset: {e}")
    
    logger.info(f"Clear collection '{collection_name}' completed: {summary}")
    return {"ok": True, "data": summary}
