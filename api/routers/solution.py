"""API router for Solution Assistant (方案助手).

Prefix: /api/solution

Endpoints:
- POST /parse            — 上传需求文件或提交文本，解析为结构化需求
- POST /upload-template  — 上传方案模板 Word，提取大纲结构
- POST /outline          — 基于需求(+模板)生成方案大纲
- PUT  /outline          — 用户手动编辑大纲
- POST /generate         — 逐章节生成内容（SSE 流）
- POST /export           — 导出 Word 文档
- GET/DELETE /sessions   — 会话管理
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from api.deps import get_hybrid_search, get_llm
from src.core.settings import resolve_path
from src.solution.solution_db import (
    SolutionSession,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_UPLOAD_DIR = resolve_path("data/solution_files")
_EXPORT_DIR = resolve_path("data/exports")


def _ensure_dirs() -> None:
    """确保上传和导出目录存在."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# ── Request models ───────────────────────────────────────────────


class ParseTextReq(BaseModel):
    """纯文本需求解析请求."""

    text: str
    project_name: str = ""
    project_type: str = ""
    collection: str = "default"


class GenerateOutlineReq(BaseModel):
    """大纲生成请求."""

    session_id: int


class UpdateOutlineReq(BaseModel):
    """大纲更新请求."""

    session_id: int
    outline: List[Dict[str, Any]]


class GenerateContentReq(BaseModel):
    """内容生成请求."""

    session_id: int


class ExportReq(BaseModel):
    """导出请求."""

    session_id: int


# ── Step 1a: Parse requirements from file ────────────────────────


@router.post("/parse")
async def parse_requirements_api(
    file: Optional[UploadFile] = File(None),
    text: str = Form(""),
    project_name: str = Form(""),
    project_type: str = Form(""),
    collection: str = Form("default"),
) -> Dict[str, Any]:
    """上传需求文件或提交文本，解析为结构化需求.

    支持 PDF/DOCX 文件上传和纯文本两种方式。
    """
    _ensure_dirs()

    try:
        from src.solution.requirement_parser import parse_requirements

        file_path: str | None = None
        source_text = text

        if file and file.filename:
            # 文件上传模式
            suffix = Path(file.filename).suffix.lower()
            if suffix not in (".pdf", ".docx", ".doc", ".txt", ".md"):
                return {"ok": False, "message": f"不支持的文件类型: {suffix}"}

            timestamp = int(time.time())
            safe_name = f"{timestamp}_{file.filename}"
            saved_path = _UPLOAD_DIR / safe_name

            content = await file.read()
            with open(saved_path, "wb") as f:
                f.write(content)

            file_path = str(saved_path)
        elif not text.strip():
            return {"ok": False, "message": "请上传文件或输入需求文本"}

        llm = get_llm()
        requirements = await parse_requirements(
            llm=llm, file_path=file_path, text=source_text or None
        )

        # 创建会话
        session = SolutionSession(
            project_name=project_name,
            project_type=project_type,
            source_file_path=file_path or "",
            source_text=source_text,
            requirements=requirements,
            collection=collection,
            status="draft",
        )
        session_id = create_session(session)

        return {
            "ok": True,
            "session_id": session_id,
            "requirements": requirements,
            "message": f"成功解析 {len(requirements)} 条需求",
        }
    except Exception as e:
        logger.exception("Parse requirements failed")
        return {"ok": False, "message": str(e)}


# ── Step 1b: Upload template ─────────────────────────────────────


@router.post("/upload-template")
async def upload_template_api(
    file: UploadFile = File(...),
    session_id: int = Form(...),
) -> Dict[str, Any]:
    """上传方案模板 Word 文件，提取大纲结构.

    将模板大纲保存到会话中，后续大纲生成时以此为骨架。
    """
    _ensure_dirs()

    try:
        session = get_session(session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".docx", ".doc"):
            return {"ok": False, "message": "模板仅支持 Word 格式 (.docx)"}

        timestamp = int(time.time())
        safe_name = f"template_{timestamp}_{file.filename}"
        saved_path = _UPLOAD_DIR / safe_name

        content = await file.read()
        with open(saved_path, "wb") as f:
            f.write(content)

        from src.solution.template_parser import parse_template

        template_outline = parse_template(str(saved_path))

        session.template_file_path = str(saved_path)
        session.template_outline = template_outline
        update_session(session)

        return {
            "ok": True,
            "template_outline": template_outline,
            "message": f"成功从模板提取 {len(template_outline)} 个章节",
        }
    except Exception as e:
        logger.exception("Upload template failed")
        return {"ok": False, "message": str(e)}


# ── Step 2: Generate outline ─────────────────────────────────────


@router.post("/outline")
async def generate_outline_api(req: GenerateOutlineReq) -> Dict[str, Any]:
    """基于需求(+模板)生成方案大纲."""
    try:
        session = get_session(req.session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}

        if not session.requirements:
            return {"ok": False, "message": "请先解析需求"}

        from src.solution.outline_generator import (
            generate_default_outline,
            generate_outline,
        )

        llm = get_llm()
        hybrid_search = None
        try:
            hybrid_search = get_hybrid_search(session.collection)
        except Exception as e:
            logger.warning(f"知识库检索初始化失败: {e}")

        try:
            outline = await generate_outline(
                requirements=session.requirements,
                llm=llm,
                template_outline=session.template_outline or None,
                hybrid_search=hybrid_search,
            )
        except Exception as e:
            logger.warning(f"LLM 大纲生成失败，使用默认大纲: {e}")
            outline = generate_default_outline(session.requirements)

        session.outline = outline
        session.status = "outlining"
        update_session(session)

        return {"ok": True, "outline": outline}
    except Exception as e:
        logger.exception("Generate outline failed")
        return {"ok": False, "message": str(e)}


# ── Step 2b: Update outline (user edit) ──────────────────────────


@router.put("/outline")
async def update_outline_api(req: UpdateOutlineReq) -> Dict[str, Any]:
    """用户手动编辑大纲后更新."""
    try:
        session = get_session(req.session_id)
        if not session:
            return {"ok": False, "message": "会话不存在"}

        session.outline = req.outline
        updated = update_session(session)
        return {"ok": updated, "message": "大纲更新成功" if updated else "更新失败"}
    except Exception as e:
        logger.exception("Update outline failed")
        return {"ok": False, "message": str(e)}


# ── Step 3: Generate content (SSE) ───────────────────────────────


@router.post("/generate")
async def generate_content_api(req: GenerateContentReq):
    """逐章节生成方案内容，SSE 流式输出."""
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if not session.outline:
        raise HTTPException(status_code=400, detail="请先生成大纲")

    from src.solution.content_generator import generate_content_stream

    llm = get_llm()
    hybrid_search = None
    try:
        hybrid_search = get_hybrid_search(session.collection)
    except Exception as e:
        logger.warning(f"知识库检索初始化失败: {e}")

    session.status = "generating"
    update_session(session)

    async def event_stream():
        """SSE 事件流生成器."""
        content_map: Dict[str, str] = {}
        try:
            async for chunk in generate_content_stream(
                session=session,
                llm=llm,
                hybrid_search=hybrid_search,
            ):
                yield chunk

                # 解析 done 事件，持久化内容
                try:
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if data.get("type") == "section":
                        content_map[data["section_id"]] = data.get("content", "")
                    elif data.get("type") == "done":
                        content_map = data.get("content", content_map)
                except Exception:
                    pass

            # 持久化所有内容
            session.content = content_map
            session.status = "completed"
            update_session(session)
        except Exception as e:
            logger.exception("Content generation stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Step 4: Export ───────────────────────────────────────────────


@router.post("/export")
async def export_document_api(req: ExportReq):
    """导出方案为 Word 文档."""
    _ensure_dirs()
    try:
        session = get_session(req.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        if not session.outline:
            raise HTTPException(status_code=400, detail="请先生成大纲")

        from src.solution.solution_exporter import export_to_docx

        timestamp = int(time.time())
        name = session.project_name or f"方案_{session.id}"
        filename = f"{name}_{timestamp}.docx"
        output_path = _EXPORT_DIR / filename

        export_to_docx(
            outline=session.outline,
            content=session.content,
            output_path=str(output_path),
            project_name=session.project_name,
            project_type=session.project_type,
        )

        return FileResponse(
            path=str(output_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document",
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
    """列出方案会话."""
    try:
        result = list_sessions(status=status, page=page, page_size=page_size)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("List sessions failed")
        return {"ok": False, "message": str(e)}


@router.get("/sessions/{session_id}")
async def get_session_api(session_id: int) -> Dict[str, Any]:
    """获取单个会话详情."""
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
    """删除会话."""
    try:
        session = get_session(session_id)
        if session:
            # 清理关联文件
            for path_str in [session.source_file_path, session.template_file_path]:
                if path_str:
                    p = Path(path_str)
                    if p.exists():
                        p.unlink(missing_ok=True)

        deleted = delete_session(session_id)
        return {"ok": deleted, "message": "删除成功" if deleted else "删除失败"}
    except Exception as e:
        logger.exception("Delete session failed")
        return {"ok": False, "message": str(e)}
