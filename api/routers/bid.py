"""Bid Assistant API router — chat-driven sequential workflow.

Endpoints:
- POST /api/bid/search       — Step1: search products collection
- POST /api/bid/upload       — Step2: upload vendor file + extract params
- POST /api/bid/compare      — Step3: SSE stream comparison report (done has table_data)
- GET  /api/bid/params       — list extracted param records
- GET  /api/bid/params/{id}  — get single param record
- DELETE /api/bid/params/{id} — delete param record
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import get_hybrid_search, get_llm, get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Request models ───────────────────────────────────────────────


class BidSearchRequest(BaseModel):
    """Product search request."""

    query: str
    top_k: int = 10
    collection: str = "products"


class BidCompareRequest(BaseModel):
    """Parameter comparison request."""

    official_id: int
    vendor_id: int


# ── Step 1: Product Search ───────────────────────────────────────


@router.post("/search")
async def bid_search(req: BidSearchRequest):
    """Search products collection for matching products."""
    try:
        search = get_hybrid_search(req.collection)
        results = search.search(query=req.query, top_k=req.top_k)

        products = []
        for r in results:
            meta = r.metadata or {}
            products.append({
                "source": meta.get("source_path", ""),
                "score": round(r.score, 4),
                "text": r.text[:500] if r.text else "",
                "vendor": meta.get("product_vendor", ""),
                "model": meta.get("product_model", ""),
                "category": meta.get("product_category", ""),
            })

        return {"ok": True, "data": products}
    except Exception as e:
        logger.exception("Product search failed")
        return {"ok": False, "message": f"产品检索失败: {e}"}


# ── Step 2: Upload + Extract ─────────────────────────────────────


@router.post("/upload")
async def bid_upload(
    file: UploadFile = File(...),
    doc_type: str = Form("vendor"),
    collection: str = Form("products"),
    official_id: Optional[int] = Form(None),
):
    """Upload a vendor file (PDF/DOCX), ingest it, and extract params.

    This combines file upload → ingestion → parameter extraction into
    one step for the chat workflow.

    Args:
        file: The uploaded file.
        doc_type: 'vendor' (default) or 'official'.
        official_id: If provided, the ID of the official param record to
                     compare against (used for automatic comparison).
    """
    try:
        from src.bid.param_extractor import ChunkMeta, extract_params_from_chunks
        from src.bid.product_db import ProductParamRecord, save_params
        from src.core.settings import load_settings
        from src.ingestion.pipeline import IngestionPipeline

        filename = file.filename or "upload"
        suffix = Path(filename).suffix.lower()
        if suffix not in (".pdf", ".docx", ".doc"):
            return {"ok": False, "message": f"不支持的文件类型: {suffix}，仅支持 PDF/DOCX"}

        # Save to temp and ingest
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        settings = load_settings()
        pipeline = IngestionPipeline(settings, collection=collection)
        result = pipeline.run(file_path=tmp_path, original_filename=filename)
        Path(tmp_path).unlink(missing_ok=True)

        if not result.success:
            return {"ok": False, "message": result.error or "文件摄取失败"}

        # Retrieve the chunks we just ingested
        search = get_hybrid_search(collection)
        results = search.search(query=filename, top_k=50)

        # Filter to chunks from this specific document
        chunk_metas: List[ChunkMeta] = []
        for r in results:
            meta = r.metadata or {}
            source = meta.get("source_path", "")
            if r.text and (filename in source or Path(filename).stem in source):
                chunk_metas.append(ChunkMeta(
                    text=r.text,
                    page=int(meta.get("page_number", 0) or 0),
                    section=meta.get("section", "") or meta.get("heading", ""),
                    source=source,
                ))

        if not chunk_metas:
            return {
                "ok": True,
                "message": f"文件已摄取 ({result.chunk_count} 个块)，但未找到可提取参数的内容",
                "data": [],
                "vendor_param_ids": [],
            }

        # Extract params via LLM
        llm = get_llm()
        products = extract_params_from_chunks(llm, chunk_metas)

        if not products:
            return {
                "ok": True,
                "message": "文件已摄取，但未检测到结构化技术参数",
                "data": [],
                "vendor_param_ids": [],
            }

        # Save each extracted product
        saved_ids: List[int] = []
        for p in products:
            record = ProductParamRecord(
                vendor=p.get("vendor", ""),
                model=p.get("model", ""),
                product_name=p.get("product_name", ""),
                category=p.get("category", ""),
                doc_type=doc_type,
                doc_source=filename,
                params=p.get("params", []),
            )
            rid = save_params(record)
            saved_ids.append(rid)

        return {
            "ok": True,
            "data": products,
            "vendor_param_ids": saved_ids,
            "message": f"成功提取 {len(products)} 个产品的参数（共 {sum(len(p.get('params', [])) for p in products)} 项）",
        }
    except Exception as e:
        logger.exception("Upload and extraction failed")
        return {"ok": False, "message": f"上传处理失败: {e}"}


# ── Step 3: Compare (SSE) ────────────────────────────────────────


@router.post("/compare")
async def bid_compare(req: BidCompareRequest):
    """Stream parameter comparison report via SSE.

    The final 'done' event includes both the full markdown answer and
    a structured `table_data` array for frontend table rendering.
    """
    from src.bid.param_comparator import compare_params_stream, parse_table_data
    from src.bid.product_db import get_params

    official = get_params(req.official_id)
    vendor = get_params(req.vendor_id)

    if not official:
        raise HTTPException(404, f"官方参数记录 {req.official_id} 不存在")
    if not vendor:
        raise HTTPException(404, f"送审参数记录 {req.vendor_id} 不存在")

    def event_stream():
        llm = get_llm()
        full_answer = ""

        try:
            for chunk in compare_params_stream(
                llm,
                official_params=official.params,
                vendor_params=vendor.params,
                official_info={
                    "vendor": official.vendor,
                    "model": official.model,
                    "product_name": official.product_name,
                },
                vendor_info={
                    "vendor": vendor.vendor,
                    "model": vendor.model,
                    "product_name": vendor.product_name,
                },
            ):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("Comparison stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # Parse the completed markdown into structured table data
        table_data = parse_table_data(full_answer)

        yield f"data: {json.dumps({'type': 'done', 'answer': full_answer, 'table_data': table_data}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Param Records CRUD ───────────────────────────────────────────


@router.get("/params")
async def bid_list_params(
    doc_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
):
    """List extracted product parameter records."""
    from src.bid.product_db import list_params

    try:
        records = list_params(doc_type=doc_type, category=category, limit=limit)
        return {
            "ok": True,
            "data": [
                {
                    "id": r.id,
                    "vendor": r.vendor,
                    "model": r.model,
                    "product_name": r.product_name,
                    "category": r.category,
                    "doc_type": r.doc_type,
                    "doc_source": r.doc_source,
                    "param_count": len(r.params),
                    "params": r.params,
                    "created_at": r.created_at,
                }
                for r in records
            ],
        }
    except Exception as e:
        logger.exception("Failed to list params")
        return {"ok": False, "message": str(e)}


@router.get("/params/{record_id}")
async def bid_get_params(record_id: int):
    """Get a single product parameter record."""
    from src.bid.product_db import get_params

    record = get_params(record_id)
    if not record:
        raise HTTPException(404, "参数记录不存在")
    return {
        "ok": True,
        "data": {
            "id": record.id,
            "vendor": record.vendor,
            "model": record.model,
            "product_name": record.product_name,
            "category": record.category,
            "doc_type": record.doc_type,
            "doc_source": record.doc_source,
            "params": record.params,
            "created_at": record.created_at,
        },
    }


@router.delete("/params/{record_id}")
async def bid_delete_params(record_id: int):
    """Delete a product parameter record."""
    from src.bid.product_db import delete_params

    ok = delete_params(record_id)
    if not ok:
        raise HTTPException(404, "参数记录不存在")
    return {"ok": True, "message": "已删除"}
