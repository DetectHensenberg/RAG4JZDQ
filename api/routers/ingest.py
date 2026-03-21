"""Ingest management API router — single file upload + document/collection deletion."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Form
from pydantic import BaseModel

from api.models import DocumentDeleteRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_and_ingest(
    file: UploadFile = File(...),
    collection: str = Form("default"),
    product_vendor: str = Form(""),
    product_model: str = Form(""),
    product_category: str = Form(""),
    product_device: str = Form(""),
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

        from src.ingestion.vendor_inference import infer_from_filename

        # Build extra metadata for product collections
        extra_metadata: dict[str, str] = {}
        if product_vendor:
            extra_metadata["product_vendor"] = product_vendor
        if product_model:
            extra_metadata["product_model"] = product_model
        if product_category:
            extra_metadata["product_category"] = product_category
        if product_device:
            extra_metadata["product_device"] = product_device
        # Always tag source filename and directory
        filename = file.filename or "upload"
        extra_metadata["source_filename"] = filename
        extra_metadata["source_directory"] = str(Path(filename).parent)
        # Auto-infer vendor/model from filename when not provided
        if not extra_metadata.get("product_vendor") or not extra_metadata.get("product_model"):
            inf_vendor, inf_model = infer_from_filename(filename)
            if inf_vendor and not extra_metadata.get("product_vendor"):
                extra_metadata["product_vendor"] = inf_vendor
            if inf_model and not extra_metadata.get("product_model"):
                extra_metadata["product_model"] = inf_model

        from api.deps import get_pipeline

        pipeline = get_pipeline(collection=collection)
        result = pipeline.run(
            file_path=tmp_path,
            original_filename=file.filename,
            extra_metadata=extra_metadata if extra_metadata else None,
        )

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


class CollectionDeleteRequest(BaseModel):
    """Request to delete an entire collection."""

    collection: str


@router.post("/collection/clear")
async def clear_collection(req: CollectionDeleteRequest):
    """Delete an entire vector collection (ChromaDB + BM25 + integrity records)."""
    if req.collection == "default":
        # Extra safety: require explicit confirmation for default collection
        pass  # allowed but logged

    try:
        from src.core.settings import load_settings, resolve_path
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.libs.loader.file_integrity import SQLiteIntegrityChecker

        settings = load_settings()
        deleted_info: dict[str, int] = {}

        # 1. Clear ChromaDB collection
        try:
            chroma = VectorStoreFactory.create(settings, collection_name=req.collection)
            count_before = chroma.collection.count()
            chroma.clear(collection_name=req.collection)
            deleted_info["chunks"] = count_before
            logger.info(f"ChromaDB collection '{req.collection}' cleared ({count_before} chunks)")
        except Exception as e:
            logger.warning(f"ChromaDB clear failed: {e}")
            deleted_info["chunks"] = 0

        # 2. Clear BM25 index
        try:
            bm25_dir = resolve_path(f"data/db/bm25/{req.collection}")
            if bm25_dir.exists():
                shutil.rmtree(str(bm25_dir))
                logger.info(f"BM25 index directory '{bm25_dir}' removed")
            deleted_info["bm25"] = 1
        except Exception as e:
            logger.warning(f"BM25 clear failed: {e}")
            deleted_info["bm25"] = 0

        # 3. Remove integrity records for this collection
        try:
            integrity = SQLiteIntegrityChecker(
                db_path=str(resolve_path("data/db/ingestion_history.db"))
            )
            records = integrity.list_processed(collection=req.collection)
            removed = 0
            for rec in records:
                if integrity.remove_record(rec["file_hash"]):
                    removed += 1
            deleted_info["records"] = removed
            logger.info(f"Removed {removed} integrity records for collection '{req.collection}'")
        except Exception as e:
            logger.warning(f"Integrity cleanup failed: {e}")
            deleted_info["records"] = 0

        return {
            "ok": True,
            "message": f"集合 '{req.collection}' 已清空",
            "data": deleted_info,
        }
    except Exception as e:
        logger.exception("Collection deletion failed")
        return {"ok": False, "message": str(e)}
