"""API router for bid document (商务文件) writing assistant.

Prefix: /api/bid-document
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.bid.document_db import (
    BidMaterial,
    BidTemplate,
    CompanyDocument,
    DocumentSession,
    create_material,
    create_session,
    create_template,
    delete_company_doc,
    delete_material,
    delete_session,
    delete_template,
    get_company_doc,
    get_material,
    get_materials_dir,
    get_session,
    get_template,
    list_company_docs,
    list_materials,
    list_sessions,
    list_templates,
    search_materials,
    update_material,
    update_session,
    update_template,
    upsert_company_doc,
)
from src.bid.clause_extractor import extract_clauses, extract_clauses_stream
from src.bid.company_doc_parser import parse_and_import as parse_company_pdf
from src.bid.content_filler import fill_outline_stream
from src.bid.docx_exporter import export_to_docx
from src.bid.outline_generator import (
    enrich_outline_with_matches,
    generate_default_outline,
    generate_outline,
)
from src.bid.watermark import add_watermark, generate_watermark_text
from src.core.settings import resolve_path, load_settings
from src.libs.llm import LLMFactory

logger = logging.getLogger(__name__)

router = APIRouter()

_TENDER_DIR = resolve_path("data/tender_files")
_EXPORT_DIR = resolve_path("data/exports")


def _ensure_dirs():
    _TENDER_DIR.mkdir(parents=True, exist_ok=True)
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    get_materials_dir()


# ── Request / Response models ────────────────────────────────────


class MaterialCreateReq(BaseModel):
    name: str
    category: str = "other"
    content: str = ""
    valid_from: str = ""
    valid_to: str = ""


class MaterialUpdateReq(MaterialCreateReq):
    pass


class TemplateCreateReq(BaseModel):
    name: str
    template_type: str = "other"
    content: str


class TemplateUpdateReq(TemplateCreateReq):
    pass


class ExtractClausesReq(BaseModel):
    session_id: int


class GenerateOutlineReq(BaseModel):
    session_id: int


class UpdateOutlineReq(BaseModel):
    session_id: int
    outline: List[Dict[str, Any]]


class FillContentReq(BaseModel):
    session_id: int
    project_name: str = ""
    project_code: str = ""


class WatermarkReq(BaseModel):
    material_ids: List[int]
    project_code: str


class ExportReq(BaseModel):
    session_id: int
    format: str = "docx"


# ── Material CRUD ────────────────────────────────────────────────


@router.post("/materials/upload")
async def upload_material(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form("other"),
    valid_from: str = Form(""),
    valid_to: str = Form(""),
) -> Dict[str, Any]:
    """Upload a bid material file."""
    _ensure_dirs()
    try:
        materials_dir = get_materials_dir()
        timestamp = int(time.time())
        safe_name = f"{timestamp}_{file.filename}"
        file_path = materials_dir / safe_name

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        text_content = ""
        suffix = Path(file.filename or "").suffix.lower()
        if suffix in (".txt", ".md"):
            try:
                text_content = content.decode("utf-8")
            except Exception:
                pass

        material = BidMaterial(
            name=name,
            category=category,
            file_path=str(file_path),
            content=text_content,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        new_id = create_material(material)

        return {"ok": True, "id": new_id, "file_path": str(file_path), "message": "上传成功"}
    except Exception as e:
        logger.exception("Upload material failed")
        return {"ok": False, "message": str(e)}


@router.post("/materials")
async def create_material_text(req: MaterialCreateReq) -> Dict[str, Any]:
    """Create a text-only material (no file)."""
    try:
        material = BidMaterial(
            name=req.name,
            category=req.category,
            content=req.content,
            valid_from=req.valid_from,
            valid_to=req.valid_to,
        )
        new_id = create_material(material)
        return {"ok": True, "id": new_id, "message": "创建成功"}
    except Exception as e:
        logger.exception("Create material failed")
        return {"ok": False, "message": str(e)}


@router.get("/materials")
async def list_materials_api(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """List materials with optional filtering."""
    try:
        result = list_materials(category=category, keyword=keyword, page=page, page_size=page_size)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("List materials failed")
        return {"ok": False, "message": str(e)}


@router.get("/materials/{material_id}")
async def get_material_api(material_id: int) -> Dict[str, Any]:
    """Get a single material by ID."""
    try:
        material = get_material(material_id)
        if not material:
            return {"ok": False, "message": "材料不存在"}
        return {"ok": True, "data": material.to_dict()}
    except Exception as e:
        logger.exception("Get material failed")
        return {"ok": False, "message": str(e)}


@router.put("/materials/{material_id}")
async def update_material_api(material_id: int, req: MaterialUpdateReq) -> Dict[str, Any]:
    """Update an existing material."""
    try:
        existing = get_material(material_id)
        if not existing:
            return {"ok": False, "message": "材料不存在"}

        existing.name = req.name
        existing.category = req.category
        existing.content = req.content
        existing.valid_from = req.valid_from
        existing.valid_to = req.valid_to

        updated = update_material(existing)
        return {"ok": updated, "message": "更新成功" if updated else "更新失败"}
    except Exception as e:
        logger.exception("Update material failed")
        return {"ok": False, "message": str(e)}


@router.delete("/materials/{material_id}")
async def delete_material_api(material_id: int) -> Dict[str, Any]:
    """Delete a material."""
    try:
        material = get_material(material_id)
        if material and material.file_path:
            file_path = Path(material.file_path)
            if file_path.exists():
                file_path.unlink()

        deleted = delete_material(material_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "删除失败"}
    except Exception as e:
        logger.exception("Delete material failed")
        return {"ok": False, "message": str(e)}


@router.get("/materials/{material_id}/file")
async def download_material_file(material_id: int):
    """Download the original material file."""
    material = get_material(material_id)
    if not material or not material.file_path:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = Path(material.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.post("/materials/search")
async def search_materials_api(query: str, top_k: int = 10) -> Dict[str, Any]:
    """Semantic search for materials."""
    try:
        hits = search_materials(query, top_k=top_k)
        return {"ok": True, "data": hits}
    except Exception as e:
        logger.exception("Search materials failed")
        return {"ok": False, "message": str(e)}


# ── Template CRUD ────────────────────────────────────────────────


@router.post("/templates")
async def create_template_api(req: TemplateCreateReq) -> Dict[str, Any]:
    """Create a new template."""
    try:
        template = BidTemplate(
            name=req.name,
            template_type=req.template_type,
            content=req.content,
        )
        new_id = create_template(template)
        return {"ok": True, "id": new_id, "message": "创建成功"}
    except Exception as e:
        logger.exception("Create template failed")
        return {"ok": False, "message": str(e)}


@router.get("/templates")
async def list_templates_api(
    template_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """List templates with optional filtering."""
    try:
        result = list_templates(template_type=template_type, page=page, page_size=page_size)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("List templates failed")
        return {"ok": False, "message": str(e)}


@router.get("/templates/{template_id}")
async def get_template_api(template_id: int) -> Dict[str, Any]:
    """Get a single template by ID."""
    try:
        template = get_template(template_id)
        if not template:
            return {"ok": False, "message": "模板不存在"}
        return {"ok": True, "data": template.to_dict()}
    except Exception as e:
        logger.exception("Get template failed")
        return {"ok": False, "message": str(e)}


@router.put("/templates/{template_id}")
async def update_template_api(template_id: int, req: TemplateUpdateReq) -> Dict[str, Any]:
    """Update an existing template."""
    try:
        existing = get_template(template_id)
        if not existing:
            return {"ok": False, "message": "模板不存在"}

        existing.name = req.name
        existing.template_type = req.template_type
        existing.content = req.content

        updated = update_template(existing)
        return {"ok": updated, "message": "更新成功" if updated else "更新失败"}
    except Exception as e:
        logger.exception("Update template failed")
        return {"ok": False, "message": str(e)}


@router.delete("/templates/{template_id}")
async def delete_template_api(template_id: int) -> Dict[str, Any]:
    """Delete a template."""
    try:
        deleted = delete_template(template_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "删除失败"}
    except Exception as e:
        logger.exception("Delete template failed")
        return {"ok": False, "message": str(e)}


# ── Document Writing Flow ────────────────────────────────────────


@router.post("/upload")
async def upload_tender_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a tender file and create a new session."""
    _ensure_dirs()
    try:
        timestamp = int(time.time())
        safe_name = f"{timestamp}_{file.filename}"
        file_path = _TENDER_DIR / safe_name

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        session = DocumentSession(
            tender_file_path=str(file_path),
            status="draft",
        )
        session_id = create_session(session)

        return {
            "ok": True,
            "session_id": session_id,
            "file_path": str(file_path),
            "file_name": file.filename,
            "message": "上传成功",
        }
    except Exception as e:
        logger.exception("Upload tender file failed")
        return {"ok": False, "message": str(e)}


@router.post("/extract")
async def extract_clauses_api(req: ExtractClausesReq):
    """Extract clauses from tender file (SSE stream)."""
    session = get_session(req.session_id)
    if not session:
        return {"ok": False, "message": "会话不存在"}

    file_path = Path(session.tender_file_path)
    if not file_path.exists():
        return {"ok": False, "message": "招标文件不存在"}

    content = ""
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            try:
                import fitz
                doc = fitz.open(str(file_path))
                for page in doc:
                    content += page.get_text()
                doc.close()
            except ImportError:
                return {"ok": False, "message": "需要安装 PyMuPDF: pip install pymupdf"}
        elif suffix in (".docx", ".doc"):
            try:
                from docx import Document
                doc = Document(str(file_path))
                content = "\n".join([p.text for p in doc.paragraphs])
            except ImportError:
                return {"ok": False, "message": "需要安装 python-docx: pip install python-docx"}
        elif suffix == ".txt":
            content = file_path.read_text(encoding="utf-8")
        else:
            return {"ok": False, "message": f"不支持的文件格式: {suffix}"}
    except Exception as e:
        logger.exception("Failed to read tender file")
        return {"ok": False, "message": f"读取文件失败: {e}"}

    if not content.strip():
        return {"ok": False, "message": "文件内容为空"}

    try:
        settings = load_settings()
        llm = LLMFactory.create(settings)
        clauses = await extract_clauses(content, llm)
        session.clauses = clauses
        update_session(session)
        return {"ok": True, "clauses": clauses, "message": f"成功提取 {len(clauses)} 条条款"}
    except Exception as e:
        logger.exception("Clause extraction failed")
        return {"ok": False, "message": f"条款提取失败: {e}"}


@router.post("/outline")
async def generate_outline_api(req: GenerateOutlineReq) -> Dict[str, Any]:
    """Generate document outline from clauses."""
    try:
        session = get_session(req.session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}

        if not session.clauses:
            return {"ok": False, "message": "请先提取条款"}

        try:
            settings = load_settings()
            llm = LLMFactory.create(settings)
            outline = await generate_outline(session.clauses, llm)
        except Exception as e:
            logger.warning(f"LLM outline generation failed, using default: {e}")
            outline = generate_default_outline(session.clauses)

        outline = enrich_outline_with_matches(outline)

        session.outline = outline
        update_session(session)

        return {"ok": True, "outline": outline}
    except Exception as e:
        logger.exception("Generate outline failed")
        return {"ok": False, "message": str(e)}


@router.put("/outline")
async def update_outline_api(req: UpdateOutlineReq) -> Dict[str, Any]:
    """Update outline (user edits)."""
    try:
        session = get_session(req.session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}

        session.outline = req.outline
        updated = update_session(session)

        return {"ok": updated, "message": "更新成功" if updated else "更新失败"}
    except Exception as e:
        logger.exception("Update outline failed")
        return {"ok": False, "message": str(e)}


@router.post("/fill")
async def fill_content_api(req: FillContentReq):
    """Fill content for all sections (SSE stream)."""
    session = get_session(req.session_id)
    if not session:
        return {"ok": False, "message": "会话不存在"}

    if not session.outline:
        return {"ok": False, "message": "请先生成大纲"}

    if req.project_name:
        session.project_name = req.project_name
    if req.project_code:
        session.project_code = req.project_code
    update_session(session)

    async def generate():
        try:
            settings = load_settings()
            llm = LLMFactory.create(settings)
            content_map = {}

            async for chunk in fill_outline_stream(
                session.outline,
                session.clauses,
                llm,
                session.project_name,
                session.project_code,
            ):
                yield chunk

                try:
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if data.get("type") == "section":
                        content_map[data["section_id"]] = data["content"]
                except Exception:
                    pass

            session.content = content_map
            update_session(session)
        except Exception as e:
            logger.exception("Content fill failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/watermark")
async def add_watermark_api(req: WatermarkReq) -> Dict[str, Any]:
    """Add watermark to specified materials."""
    try:
        watermark_text = generate_watermark_text(req.project_code)
        results = []

        for material_id in req.material_ids:
            material = get_material(material_id)
            if not material or not material.file_path:
                results.append({"id": material_id, "ok": False, "message": "材料或文件不存在"})
                continue

            file_path = Path(material.file_path)
            if not file_path.exists():
                results.append({"id": material_id, "ok": False, "message": "文件不存在"})
                continue

            try:
                output_path = add_watermark(str(file_path), watermark_text)
                results.append({
                    "id": material_id,
                    "ok": True,
                    "output_path": output_path,
                    "message": "水印添加成功",
                })
            except Exception as e:
                results.append({"id": material_id, "ok": False, "message": str(e)})

        return {"ok": True, "results": results}
    except Exception as e:
        logger.exception("Add watermark failed")
        return {"ok": False, "message": str(e)}


@router.post("/export")
async def export_document_api(req: ExportReq):
    """Export document to Word format."""
    _ensure_dirs()
    try:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        if not session.outline:
            raise HTTPException(status_code=400, detail="请先生成大纲")

        timestamp = int(time.time())
        filename = f"商务文件_{session.project_name or session.id}_{timestamp}.docx"
        output_path = _EXPORT_DIR / filename

        attachments = {}
        for item in session.outline:
            section_id = item.get("id", "")
            category = item.get("material_category")
            if category:
                result = list_materials(category=category, page_size=1)
                materials = result.get("records", [])
                if materials and materials[0].get("file_path"):
                    file_path = materials[0]["file_path"]
                    suffix = Path(file_path).suffix.lower()
                    if suffix in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
                        attachments[section_id] = file_path

        export_to_docx(
            outline=session.outline,
            content=session.content,
            attachments=attachments,
            output_path=str(output_path),
            project_name=session.project_name,
            project_code=session.project_code,
        )

        session.status = "completed"
        update_session(session)

        return FileResponse(
            path=str(output_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Export document failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Session Management ───────────────────────────────────────────


@router.get("/sessions")
async def list_sessions_api(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """List document sessions."""
    try:
        result = list_sessions(status=status, page=page, page_size=page_size)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("List sessions failed")
        return {"ok": False, "message": str(e)}


@router.get("/sessions/{session_id}")
async def get_session_api(session_id: int) -> Dict[str, Any]:
    """Get a single session by ID."""
    try:
        session = get_session(session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}
        return {"ok": True, "data": session.to_dict()}
    except Exception as e:
        logger.exception("Get session failed")
        return {"ok": False, "message": str(e)}


@router.delete("/sessions/{session_id}")
async def delete_session_api(session_id: int) -> Dict[str, Any]:
    """Delete a session."""
    try:
        session = get_session(session_id)
        if session and session.tender_file_path:
            file_path = Path(session.tender_file_path)
            if file_path.exists():
                file_path.unlink()

        deleted = delete_session(session_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "删除失败"}
    except Exception as e:
        logger.exception("Delete session failed")
        return {"ok": False, "message": str(e)}


# ── Company Documents (我司资料) ─────────────────────────────────

_COMPANY_DOC_DIR = resolve_path("data/company_docs")


class CompanyDocUpdateReq(BaseModel):
    doc_name: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None


@router.get("/company-docs")
async def list_company_docs_api(category: Optional[str] = None) -> Dict[str, Any]:
    """List all company documents."""
    try:
        docs = list_company_docs(category=category)
        return {"ok": True, "docs": [d.to_dict() for d in docs]}
    except Exception as e:
        logger.exception("List company docs failed")
        return {"ok": False, "message": str(e)}


@router.get("/company-docs/{doc_id}")
async def get_company_doc_api(doc_id: int) -> Dict[str, Any]:
    """Get a single company document."""
    try:
        doc = get_company_doc(doc_id)
        if not doc:
            return {"ok": False, "message": "文档不存在"}
        return {"ok": True, "doc": doc.to_dict()}
    except Exception as e:
        logger.exception("Get company doc failed")
        return {"ok": False, "message": str(e)}


@router.put("/company-docs/{doc_id}")
async def update_company_doc_api(doc_id: int, req: CompanyDocUpdateReq) -> Dict[str, Any]:
    """Update a company document's name, category, or content."""
    try:
        doc = get_company_doc(doc_id)
        if not doc:
            return {"ok": False, "message": "文档不存在"}

        if req.doc_name is not None:
            doc.doc_name = req.doc_name
        if req.category is not None:
            doc.category = req.category
        if req.content is not None:
            doc.content = req.content

        upsert_company_doc(doc)
        return {"ok": True, "doc": doc.to_dict(), "message": "更新成功"}
    except Exception as e:
        logger.exception("Update company doc failed")
        return {"ok": False, "message": str(e)}


@router.delete("/company-docs/{doc_id}")
async def delete_company_doc_api(doc_id: int) -> Dict[str, Any]:
    """Delete a company document."""
    try:
        deleted = delete_company_doc(doc_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "删除失败"}
    except Exception as e:
        logger.exception("Delete company doc failed")
        return {"ok": False, "message": str(e)}


@router.post("/company-docs/import")
async def import_company_docs_api(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Upload a qualification response PDF and parse it into company documents."""
    _COMPANY_DOC_DIR.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "upload.pdf").suffix.lower()
    if suffix != ".pdf":
        return {"ok": False, "message": "仅支持PDF文件"}

    saved_path = _COMPANY_DOC_DIR / f"company_qualification_{int(time.time())}{suffix}"
    try:
        with open(saved_path, "wb") as f:
            content = await file.read()
            f.write(content)

        settings = load_settings()
        llm = LLMFactory.create(settings)

        docs = await parse_company_pdf(str(saved_path), llm, clear_existing=True)

        return {
            "ok": True,
            "docs": docs,
            "message": f"成功解析并导入 {len(docs)} 个文件",
            "source_file": str(saved_path),
        }
    except Exception as e:
        logger.exception("Import company docs failed")
        return {"ok": False, "message": f"导入失败: {e}"}
