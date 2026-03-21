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
from src.ingestion.vendor_inference import infer_from_filename

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
    """Search products collection for matching products (deduplicated by source)."""
    try:
        search = get_hybrid_search(req.collection)
        # Retrieve more chunks to ensure coverage, then deduplicate by source
        results = search.search(query=req.query, top_k=50)

        # Group by source_path, keep highest score chunk per source
        source_best: Dict[str, Any] = {}
        for r in results:
            meta = r.metadata or {}
            source = meta.get("source_path", "")
            if not source:
                continue
            if source not in source_best or r.score > source_best[source]["score"]:
                source_best[source] = {"result": r, "score": r.score}

        # Build product list from unique sources
        products = []
        for source, item in source_best.items():
            r = item["result"]
            meta = r.metadata or {}
            vendor = meta.get("product_vendor", "")
            model = meta.get("product_model", "")
            # Fallback: infer from filename when metadata is missing
            if not vendor or not model:
                inf_vendor, inf_model = infer_from_filename(source)
                if not vendor:
                    vendor = inf_vendor
                if not model:
                    model = inf_model
            products.append({
                "source": source,
                "score": round(item["score"], 4),
                "text": r.text[:500] if r.text else "",
                "vendor": vendor,
                "model": model,
                "category": meta.get("product_category", ""),
            })

        # Sort by score descending
        products.sort(key=lambda x: x["score"], reverse=True)

        return {"ok": True, "data": products[:req.top_k]}
    except Exception as e:
        logger.exception("Product search failed")
        return {"ok": False, "message": f"产品检索失败: {e}"}


# ── Step 2: Upload + Extract ─────────────────────────────────────


def _sse(data: Dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/upload")
async def bid_upload(
    file: UploadFile = File(...),
    doc_type: str = Form("vendor"),
    collection: str = Form("products"),
    official_id: Optional[int] = Form(None),
    product_vendor: str = Form(""),
    product_model: str = Form(""),
    product_category: str = Form(""),
    product_device: str = Form(""),
):
    """Upload a vendor file, parse it, and extract params via SSE progress stream.

    The file is parsed and chunked locally (NOT ingested into the vector store).
    Parameters are extracted from chunks via LLM and saved to the product DB.

    SSE events:
    - {type:'progress', stage, message, percent} — progress updates
    - {type:'done', ok, data, vendor_param_ids, message} — final result
    - {type:'error', message} — on failure
    """
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc"):
        return StreamingResponse(
            iter([_sse({"type": "error", "message": f"不支持的文件类型: {suffix}，仅支持 PDF/DOCX"})]),
            media_type="text/event-stream",
        )

    # Read file content while still async
    content = await file.read()

    def event_stream():
        from src.bid.param_extractor import (
            ChunkMeta, _batch_chunks, extract_params_from_text,
        )
        from src.bid.product_db import ProductParamRecord, save_params
        from src.libs.loader.loader_factory import LoaderFactory
        from src.ingestion.chunking.document_chunker import DocumentChunker

        # ── Stage 1: Parse file (no ingestion) ───────────────────
        yield _sse({"type": "progress", "stage": "parsing", "message": f"正在解析文件 \"{filename}\"...", "percent": 5})

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            loader = LoaderFactory.create(tmp_path)
            document = loader.load(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)

            if not document or not document.text or not document.text.strip():
                yield _sse({"type": "error", "message": "文件解析失败：未提取到文本内容"})
                return
        except Exception as e:
            yield _sse({"type": "error", "message": f"文件解析失败: {e}"})
            return

        yield _sse({"type": "progress", "stage": "chunking", "message": "正在分块...", "percent": 15})

        # ── Stage 2: Chunk document ──────────────────────────────
        try:
            settings = get_settings()
            chunker = DocumentChunker(settings)
            chunks = chunker.split_document(document)
        except Exception as e:
            yield _sse({"type": "error", "message": f"文件分块失败: {e}"})
            return

        chunk_metas: List[ChunkMeta] = []
        for c in chunks:
            meta = c.metadata or {}
            chunk_metas.append(ChunkMeta(
                text=c.text,
                page=int(meta.get("page_number", 0) or 0),
                section=meta.get("heading_path", "") or meta.get("section", ""),
                source=filename,
            ))
        chunk_metas.sort(key=lambda c: c.page)

        if not chunk_metas:
            yield _sse({"type": "done", "ok": True, "data": [], "vendor_param_ids": [],
                         "message": "文件已解析，但未生成有效分块"})
            return

        yield _sse({"type": "progress", "stage": "parsed", "message": f"解析完成，共 {len(chunk_metas)} 个分块", "percent": 20})

        # ── Stage 3: Extract params batch by batch with progress ─
        yield _sse({"type": "progress", "stage": "extracting", "message": f"正在提取参数（{len(chunk_metas)} 个分块）...", "percent": 25})

        batches = _batch_chunks(chunk_metas)
        total_batches = len(batches)
        logger.info(f"Batched {len(chunk_metas)} chunks → {total_batches} LLM calls")

        llm = get_llm()
        all_extractions: List[Dict[str, Any]] = []

        for i, (text, page, section) in enumerate(batches):
            batch_pct = 25 + int(65 * (i / total_batches))
            yield _sse({
                "type": "progress", "stage": "extracting",
                "message": f"正在提取参数（{i + 1}/{total_batches} 批）...",
                "percent": batch_pct, "batch": i + 1, "total": total_batches,
            })

            try:
                products = extract_params_from_text(llm, text, page=page, section=section)
                if products:
                    all_extractions.append({"products": products})
            except Exception as e:
                logger.warning(f"Batch {i + 1} extraction failed: {e}")

        if not all_extractions:
            yield _sse({"type": "done", "ok": True, "data": [], "vendor_param_ids": [],
                         "message": f"文件已解析（{len(chunk_metas)} 个分块），参数提取未返回结果"})
            return

        # ── Stage 4: Merge and save ──────────────────────────────
        yield _sse({"type": "progress", "stage": "saving", "message": "正在合并和保存参数...", "percent": 92})

        import sys
        from src.core.settings import REPO_ROOT
        scripts_dir = str(REPO_ROOT / ".github" / "skills" / "bid-param-extractor" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from merge_params import merge_product_params

        merged = merge_product_params(all_extractions)

        saved_ids: List[int] = []
        for p in merged:
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

        total_params = sum(len(p.get("params", [])) for p in merged)
        yield _sse({
            "type": "done", "ok": True, "data": merged,
            "vendor_param_ids": saved_ids,
            "message": f"成功提取 {len(merged)} 个产品的参数（共 {total_params} 项）",
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Auto-extract official params from KB ──────────────────────────


class ExtractOfficialRequest(BaseModel):
    """Request to extract official params from knowledge base."""

    query: str
    vendor: str = ""
    model: str = ""
    category: str = ""
    collection: str = "products"


@router.post("/extract-official")
async def extract_official_params(req: ExtractOfficialRequest):
    """Extract official product params from existing KB chunks.

    Called automatically before comparison when no official record exists.
    Searches the knowledge base, groups chunks by source document,
    extracts structured params from each source via LLM, and saves them
    as doc_type='official'.
    """
    try:
        from src.bid.param_extractor import ChunkMeta, extract_params_from_chunks
        from src.bid.product_db import ProductParamRecord, save_params

        search = get_hybrid_search(req.collection)
        # Retrieve more chunks to ensure coverage across multiple sources
        results = search.search(query=req.query, top_k=50)

        # Group chunks by source_path and sort by page for complete coverage
        source_chunks: Dict[str, List[ChunkMeta]] = {}
        for r in results:
            if not r.text:
                continue
            meta = r.metadata or {}
            source = meta.get("source_path", "")
            if not source:
                continue
            if source not in source_chunks:
                source_chunks[source] = []
            source_chunks[source].append(ChunkMeta(
                text=r.text,
                page=int(meta.get("page_number", 0) or 0),
                section=meta.get("section", "") or meta.get("heading", ""),
                source=source,
            ))

        # Sort each source's chunks by page number for sequential processing
        for source in source_chunks:
            source_chunks[source].sort(key=lambda c: c.page)

        if not source_chunks:
            return {"ok": False, "message": "知识库中未找到该产品的文档内容"}

        logger.info(f"Found {len(source_chunks)} source documents for extraction")

        # Extract params from each source document separately
        llm = get_llm()
        all_products: List[Dict[str, Any]] = []

        for source, chunks in source_chunks.items():
            logger.info(f"Extracting from {source}: {len(chunks)} chunks")
            try:
                # No chunk limit for official extraction - process all chunks
                products = extract_params_from_chunks(llm, chunks, max_chunks=len(chunks))
                if products:
                    # Add source info to each product
                    for p in products:
                        p["_source"] = source
                    all_products.extend(products)
                    logger.info(f"Extracted {len(products)} products from {source}")
            except Exception as e:
                logger.warning(f"Extraction failed for {source}: {e}")
                continue

        if not all_products:
            return {"ok": False, "message": "无法从知识库内容中提取结构化参数"}

        # Merge products with same vendor+model from different sources
        merged_products: Dict[str, Dict[str, Any]] = {}
        for p in all_products:
            key = f"{p.get('vendor', '')}|{p.get('model', '')}"
            if key not in merged_products:
                merged_products[key] = p
            else:
                # Merge params from same product across sources
                existing = merged_products[key]
                existing_params = {param.get("name"): param for param in existing.get("params", [])}
                for param in p.get("params", []):
                    name = param.get("name")
                    if name and name not in existing_params:
                        existing.get("params", []).append(param)
                logger.info(f"Merged params from {p.get('_source')} into {key}")

        final_products = list(merged_products.values())

        # Save as official
        saved_ids: List[int] = []
        for p in final_products:
            record = ProductParamRecord(
                vendor=p.get("vendor", "") or req.vendor,
                model=p.get("model", "") or req.model,
                product_name=p.get("product_name", ""),
                category=p.get("category", "") or req.category,
                doc_type="official",
                doc_source=f"KB:{req.collection}",
                params=p.get("params", []),
            )
            rid = save_params(record)
            saved_ids.append(rid)

        return {
            "ok": True,
            "data": final_products,
            "official_param_ids": saved_ids,
            "message": f"从知识库提取 {len(final_products)} 个产品的官方参数（来自 {len(source_chunks)} 个文档）",
        }
    except Exception as e:
        logger.exception("Official param extraction failed")
        return {"ok": False, "message": f"官方参数提取失败: {e}"}

# ... (rest of the code remains the same)
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
