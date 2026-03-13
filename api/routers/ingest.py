"""Ingest management API router — single file upload + document deletion."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, Form

from api.models import DocumentDeleteRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_and_ingest(
    file: UploadFile = File(...),
    collection: str = Form("default"),
):
    """Upload a single file and run ingestion pipeline."""
    try:
        from src.core.settings import load_settings
        from src.ingestion.pipeline import IngestionPipeline

        # Save uploaded file to temp
        suffix = Path(file.filename or "upload").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        settings = load_settings()
        pipeline = IngestionPipeline(settings, collection=collection)
        result = pipeline.run(file_path=tmp_path)

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if result.success:
            return {
                "ok": True,
                "data": {
                    "chunks": result.chunk_count,
                    "images": result.image_count,
                    "skipped": result.stages.get("integrity", {}).get("skipped", False),
                },
            }
        else:
            return {"ok": False, "message": result.error or "摄取失败"}
    except Exception as e:
        logger.exception("Upload ingestion failed")
        return {"ok": False, "message": str(e)}


@router.delete("/document")
async def delete_document(req: DocumentDeleteRequest):
    """Delete a document and its chunks from all stores."""
    try:
        from src.core.settings import load_settings
        from src.ingestion.document_manager import DocumentManager
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.ingestion.storage.image_storage import ImageStorage
        from src.core.settings import resolve_path

        settings = load_settings()
        chroma = VectorStoreFactory.create(settings, collection_name=req.collection)
        bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{req.collection}")))
        images = ImageStorage(
            db_path=str(resolve_path("data/db/image_index.db")),
            images_root=str(resolve_path("data/images")),
        )

        manager = DocumentManager(
            chroma_store=chroma,
            bm25_indexer=bm25,
            image_storage=images,
        )

        result = manager.delete_document(
            source_path=req.source_path,
            collection=req.collection,
            source_hash=req.source_hash,
        )

        return {"ok": result.success, "message": "已删除" if result.success else (result.error or "删除失败")}
    except Exception as e:
        logger.exception("Document deletion failed")
        return {"ok": False, "message": str(e)}
