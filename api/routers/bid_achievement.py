"""API router for achievement (业绩) management and intelligent search.

Prefix: /api/bid-achievement
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.bid.achievement_db import (
    AchievementRecord,
    ListFilter,
    create_achievement,
    delete_achievement,
    get_achievement,
    list_achievements,
    semantic_search,
    update_achievement,
)
from src.bid.attachment_manager import (
    delete_all_attachments,
    delete_attachment,
    get_attachment_path,
    list_attachments,
    save_attachment,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ────────────────────────────────────


class AchievementCreateReq(BaseModel):
    project_name: str
    project_content: str = ""
    amount: Optional[float] = None
    sign_date: str = ""
    acceptance_date: str = ""
    client_contact: str = ""
    client_phone: str = ""
    tags: List[str] = []


class AchievementUpdateReq(AchievementCreateReq):
    pass


class AchievementListReq(BaseModel):
    keyword: str = ""
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: str = ""
    end_date: str = ""
    tags: List[str] = []
    page: int = 1
    page_size: int = 20
    sort_by: str = "updated_at"
    sort_order: str = "desc"


class SemanticSearchReq(BaseModel):
    query: str
    top_k: int = 10


# ── CRUD endpoints ───────────────────────────────────────────────


@router.post("/list")
async def achievement_list(req: AchievementListReq) -> Dict[str, Any]:
    """List achievements with filtering and pagination."""
    try:
        f = ListFilter(
            keyword=req.keyword,
            min_amount=req.min_amount,
            max_amount=req.max_amount,
            start_date=req.start_date,
            end_date=req.end_date,
            tags=req.tags,
            page=req.page,
            page_size=req.page_size,
            sort_by=req.sort_by,
            sort_order=req.sort_order,
        )
        result = list_achievements(f)
        return {
            "ok": True,
            "data": [r.to_dict() for r in result.records],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }
    except Exception as e:
        logger.exception("List achievements failed")
        return {"ok": False, "message": str(e)}


@router.post("/create")
async def achievement_create(req: AchievementCreateReq) -> Dict[str, Any]:
    """Create a new achievement record."""
    try:
        record = AchievementRecord(
            project_name=req.project_name,
            project_content=req.project_content,
            amount=req.amount,
            sign_date=req.sign_date,
            acceptance_date=req.acceptance_date,
            client_contact=req.client_contact,
            client_phone=req.client_phone,
            tags=req.tags,
        )
        new_id = create_achievement(record)
        return {"ok": True, "id": new_id, "message": "创建成功"}
    except Exception as e:
        logger.exception("Create achievement failed")
        return {"ok": False, "message": str(e)}


@router.put("/{record_id}")
async def achievement_update(record_id: int, req: AchievementUpdateReq) -> Dict[str, Any]:
    """Update an existing achievement record."""
    try:
        existing = get_achievement(record_id)
        if not existing:
            return {"ok": False, "message": "记录不存在"}

        existing.project_name = req.project_name
        existing.project_content = req.project_content
        existing.amount = req.amount
        existing.sign_date = req.sign_date
        existing.acceptance_date = req.acceptance_date
        existing.client_contact = req.client_contact
        existing.client_phone = req.client_phone
        existing.tags = req.tags

        updated = update_achievement(existing)
        return {"ok": updated, "message": "更新成功" if updated else "更新失败"}
    except Exception as e:
        logger.exception("Update achievement failed")
        return {"ok": False, "message": str(e)}


@router.delete("/{record_id}")
async def achievement_delete(record_id: int) -> Dict[str, Any]:
    """Delete an achievement record and its attachments."""
    try:
        deleted = delete_achievement(record_id)
        if deleted:
            delete_all_attachments(record_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "记录不存在"}
    except Exception as e:
        logger.exception("Delete achievement failed")
        return {"ok": False, "message": str(e)}


@router.get("/{record_id}")
async def achievement_get(record_id: int) -> Dict[str, Any]:
    """Get a single achievement record by ID."""
    try:
        record = get_achievement(record_id)
        if not record:
            return {"ok": False, "message": "记录不存在"}
        return {"ok": True, "data": record.to_dict()}
    except Exception as e:
        logger.exception("Get achievement failed")
        return {"ok": False, "message": str(e)}


# ── Semantic search ──────────────────────────────────────────────


@router.post("/search")
async def achievement_search(req: SemanticSearchReq) -> Dict[str, Any]:
    """Semantic search across achievements via ChromaDB."""
    try:
        hits = semantic_search(req.query, top_k=req.top_k)

        # Enrich with full records
        enriched = []
        for hit in hits:
            rid = hit.get("record_id")
            if rid:
                record = get_achievement(int(rid))
                if record:
                    item = record.to_dict()
                    item["score"] = hit.get("score", 0)
                    enriched.append(item)

        return {"ok": True, "data": enriched}
    except Exception as e:
        logger.exception("Semantic search failed")
        return {"ok": False, "message": str(e)}


# ── Attachment endpoints ─────────────────────────────────────────


@router.post("/{record_id}/attachments")
async def upload_attachment(
    record_id: int,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload an attachment for an achievement record."""
    try:
        record = get_achievement(record_id)
        if not record:
            return {"ok": False, "message": "记录不存在"}

        content = await file.read()
        filename = file.filename or "upload"
        info = save_attachment(record_id, filename, content)

        # Update attachments list in record
        att_entry = {"filename": info.filename, "size": info.size}
        if att_entry not in record.attachments:
            record.attachments.append(att_entry)
            update_achievement(record)

        return {"ok": True, "data": {"filename": info.filename, "size": info.size}}
    except Exception as e:
        logger.exception("Upload attachment failed")
        return {"ok": False, "message": str(e)}


@router.get("/{record_id}/attachments")
async def get_attachments(record_id: int) -> Dict[str, Any]:
    """List all attachments for an achievement record."""
    try:
        items = list_attachments(record_id)
        return {
            "ok": True,
            "data": [{"filename": a.filename, "size": a.size} for a in items],
        }
    except Exception as e:
        logger.exception("List attachments failed")
        return {"ok": False, "message": str(e)}


@router.get("/{record_id}/attachments/{filename}")
async def download_attachment(record_id: int, filename: str):
    """Download an attachment file."""
    path = get_attachment_path(record_id, filename)
    if path is None:
        return {"ok": False, "message": "附件不存在"}
    return FileResponse(path, filename=filename)


@router.delete("/{record_id}/attachments/{filename}")
async def remove_attachment(record_id: int, filename: str) -> Dict[str, Any]:
    """Delete an attachment file."""
    try:
        deleted = delete_attachment(record_id, filename)
        if deleted:
            # Remove from record's attachments list
            record = get_achievement(record_id)
            if record:
                record.attachments = [
                    a for a in record.attachments if a.get("filename") != filename
                ]
                update_achievement(record)
        return {"ok": deleted, "message": "删除成功" if deleted else "附件不存在"}
    except Exception as e:
        logger.exception("Delete attachment failed")
        return {"ok": False, "message": str(e)}


# ── Import endpoints ─────────────────────────────────────────────


@router.post("/import-excel")
async def import_excel_endpoint(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Batch import achievements from Excel/CSV file."""
    try:
        from src.bid.achievement_import import import_file

        content = await file.read()
        filename = file.filename or "import.csv"
        result = import_file(filename, content)
        return {
            "ok": result.success_count > 0 or result.error_count == 0,
            "message": f"导入完成：成功 {result.success_count} 条，失败 {result.error_count} 条",
            "success_count": result.success_count,
            "error_count": result.error_count,
            "errors": result.errors[:20],
        }
    except Exception as e:
        logger.exception("Excel import failed")
        return {"ok": False, "message": str(e)}


@router.post("/import-pdf")
async def import_pdf_endpoint(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Extract achievements from contract PDF via LLM."""
    try:
        from api.deps import get_llm
        from src.bid.achievement_pdf_extractor import extract_achievements_from_pdf

        content = await file.read()
        filename = file.filename or "contract.pdf"
        suffix = Path(filename).suffix.lower()
        if suffix != ".pdf":
            return {"ok": False, "message": f"仅支持 PDF 格式，收到: {suffix}"}

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            llm = get_llm()
            extracted = extract_achievements_from_pdf(tmp_path, llm)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not extracted:
            return {"ok": False, "message": "未能从 PDF 中提取到业绩信息"}

        # Save extracted records
        created_ids = []
        for item in extracted:
            record = AchievementRecord(
                project_name=item.get("project_name", ""),
                project_content=item.get("project_content", ""),
                amount=item.get("amount"),
                sign_date=item.get("sign_date", ""),
                acceptance_date=item.get("acceptance_date", ""),
                client_contact=item.get("client_contact", ""),
                client_phone=item.get("client_phone", ""),
                tags=item.get("tags", []),
            )
            new_id = create_achievement(record)
            created_ids.append(new_id)

        return {
            "ok": True,
            "message": f"从 PDF 中提取并保存了 {len(created_ids)} 条业绩记录",
            "data": extracted,
            "ids": created_ids,
        }
    except Exception as e:
        logger.exception("PDF import failed")
        return {"ok": False, "message": str(e)}
