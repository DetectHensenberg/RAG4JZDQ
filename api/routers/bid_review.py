"""API router for bid review (标书审查) — disqualification item checking.

Prefix: /api/bid-review
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, UploadFile
from typing import List as TypingList
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.bid.review_engine import (
    DisqualItem,
    check_bid_response_stream,
    extract_text_from_file,
    extract_text_with_pages,
    identify_items_with_llm,
    rule_based_scan,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request models ───────────────────────────────────────────────


class IdentifyItemsReq(BaseModel):
    text: str
    page_boundaries: List[List[int]] = []
    max_chars: int = 20000


class DisqualItemInput(BaseModel):
    id: str = ""
    category: str = ""
    requirement: str = ""
    source_section: str = ""
    source_page: int = 0
    original_text: str = ""


class CheckReq(BaseModel):
    items: List[DisqualItemInput]
    bid_text: str


# ── Step 1: Parse tender document ────────────────────────────────


@router.post("/parse-tender")
async def parse_tender(files: TypingList[UploadFile] = File(...)) -> Dict[str, Any]:
    """Upload and parse tender documents (PDF/DOCX), supports multiple files."""
    try:
        all_texts: list[str] = []
        all_boundaries: list[list[int]] = []
        filenames: list[str] = []
        page_offset = 0

        for file in files:
            filename = file.filename or "tender"
            suffix = Path(filename).suffix.lower()
            if suffix not in (".pdf", ".docx", ".doc"):
                return {"ok": False, "message": f"不支持的文件类型: {suffix}，仅支持 PDF/DOC/DOCX"}

            content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                text, page_boundaries = extract_text_with_pages(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if not text.strip():
                continue

            # Offset char positions for merged text
            char_offset = sum(len(t) + 2 for t in all_texts)  # +2 for \n\n separator
            for pg_num, start, end in page_boundaries:
                all_boundaries.append([pg_num + page_offset, start + char_offset, end + char_offset])

            page_offset += len(page_boundaries)
            all_texts.append(text)
            filenames.append(filename)

        if not all_texts:
            return {"ok": False, "message": "文件内容为空，无法提取文本"}

        merged_text = "\n\n".join(all_texts)
        return {
            "ok": True,
            "data": {
                "text": merged_text,
                "filenames": filenames,
                "file_count": len(filenames),
                "char_count": len(merged_text),
                "page_count": len(all_boundaries),
                "page_boundaries": all_boundaries,
            },
        }
    except Exception as e:
        logger.exception("Parse tender failed")
        return {"ok": False, "message": str(e)}


# ── Step 2: Identify disqualification items ──────────────────────


@router.post("/identify-items")
async def identify_items(req: IdentifyItemsReq) -> Dict[str, Any]:
    """Identify disqualification items from tender text using rules + LLM."""
    try:
        # Phase 1: Rule-based scan
        pb = [tuple(x) for x in req.page_boundaries] if req.page_boundaries else None
        rule_items = rule_based_scan(req.text, page_boundaries=pb)
        logger.info(f"Rule-based scan found {len(rule_items)} items")

        # Phase 2: LLM refinement
        from api.deps import get_llm
        llm = get_llm()
        refined = await identify_items_with_llm(
            req.text, rule_items, llm, max_text_chars=req.max_chars
        )
        logger.info(f"LLM refinement produced {len(refined)} items")

        return {
            "ok": True,
            "data": [item.to_dict() for item in refined],
            "rule_count": len(rule_items),
            "refined_count": len(refined),
        }
    except Exception as e:
        logger.exception("Identify items failed")
        return {"ok": False, "message": str(e)}


# ── Step 3: Parse bid document ───────────────────────────────────


@router.post("/parse-bid")
async def parse_bid(files: TypingList[UploadFile] = File(...)) -> Dict[str, Any]:
    """Upload and parse bid documents (PDF/DOCX), supports multiple files."""
    try:
        all_texts: list[str] = []
        filenames: list[str] = []

        for file in files:
            filename = file.filename or "bid"
            suffix = Path(filename).suffix.lower()
            if suffix not in (".pdf", ".docx", ".doc"):
                return {"ok": False, "message": f"不支持的文件类型: {suffix}，仅支持 PDF/DOC/DOCX"}

            content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                text = extract_text_from_file(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if text.strip():
                all_texts.append(text)
                filenames.append(filename)

        if not all_texts:
            return {"ok": False, "message": "文件内容为空，无法提取文本"}

        merged_text = "\n\n".join(all_texts)
        return {
            "ok": True,
            "data": {
                "text": merged_text,
                "filenames": filenames,
                "file_count": len(filenames),
                "char_count": len(merged_text),
            },
        }
    except Exception as e:
        logger.exception("Parse bid failed")
        return {"ok": False, "message": str(e)}


# ── Step 4: Check bid response (SSE streaming) ──────────────────


@router.post("/check")
async def check_bid(req: CheckReq):
    """Check bid document against disqualification items. Returns SSE stream."""
    items = [
        DisqualItem(
            id=i.id,
            category=i.category,
            requirement=i.requirement,
            source_section=i.source_section,
            source_page=i.source_page,
            original_text=i.original_text,
        )
        for i in req.items
    ]

    from api.deps import get_llm
    llm = get_llm()

    async def event_generator():
        try:
            async for event in check_bid_response_stream(items, req.bid_text, llm):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("Check stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
