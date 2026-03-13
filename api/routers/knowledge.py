"""Knowledge base ingestion API router — SSE progress streaming."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.models import IngestRequest
from src.core.settings import resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task store
_tasks: Dict[str, Dict[str, Any]] = {}


def _scan_files(folder: str, file_types: List[str]) -> List[Path]:
    """Recursively scan folder for matching files."""
    folder_path = Path(folder)
    if not folder_path.exists():
        return []
    files = []
    for ft in file_types:
        files.extend(folder_path.rglob(f"*{ft}"))
    return sorted(files)


@router.post("/scan")
async def scan_folder(body: Dict[str, Any]):
    """Scan a folder and return file list."""
    folder = body.get("folder_path", "")
    file_types = body.get("file_types", [".pdf", ".pptx", ".docx", ".md", ".txt"])
    if not folder or not Path(folder).exists():
        return {"ok": False, "message": f"文件夹不存在: {folder}"}
    files = _scan_files(folder, file_types)
    return {
        "ok": True,
        "data": {
            "files": [{"path": str(f), "name": f.name, "size": f.stat().st_size} for f in files],
            "total": len(files),
        },
    }


@router.post("/ingest")
async def start_ingest(req: IngestRequest):
    """Start ingestion and return task_id for progress tracking."""
    files = _scan_files(req.folder_path, req.file_types)
    if not files:
        return {"ok": False, "message": "未找到匹配文件"}

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "files": [str(f) for f in files],
        "collection": req.collection,
        "stop_requested": False,
        "status": "pending",
    }
    return {"ok": True, "data": {"task_id": task_id, "total_files": len(files)}}


@router.get("/progress/{task_id}")
async def ingest_progress(task_id: str):
    """SSE stream of ingestion progress."""
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "message": "任务不存在"}

    def event_stream():
        from src.core.settings import load_settings
        from src.ingestion.pipeline import IngestionPipeline

        settings = load_settings()
        pipeline = IngestionPipeline(settings, collection=task["collection"])

        files = task["files"]
        total = len(files)
        task["status"] = "running"
        results = {"success": 0, "failed": 0, "skipped": 0}

        for idx, fpath in enumerate(files):
            if task["stop_requested"]:
                yield f"data: {json.dumps({'type': 'stopped', 'completed': idx, 'total': total}, ensure_ascii=False)}\n\n"
                break

            fname = Path(fpath).name
            yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'file': fname, 'stage': '处理中'}, ensure_ascii=False)}\n\n"

            try:
                result = pipeline.run(file_path=fpath)
                if result.stages.get("integrity", {}).get("skipped"):
                    results["skipped"] += 1
                    yield f"data: {json.dumps({'type': 'file_done', 'file': fname, 'status': 'skipped'}, ensure_ascii=False)}\n\n"
                elif result.success:
                    results["success"] += 1
                    yield f"data: {json.dumps({'type': 'file_done', 'file': fname, 'status': 'success', 'chunks': result.chunk_count}, ensure_ascii=False)}\n\n"
                else:
                    results["failed"] += 1
                    yield f"data: {json.dumps({'type': 'file_done', 'file': fname, 'status': 'failed', 'error': result.error or '未知错误'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                results["failed"] += 1
                yield f"data: {json.dumps({'type': 'file_done', 'file': fname, 'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

        task["status"] = "done"
        yield f"data: {json.dumps({'type': 'done', **results}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/stop/{task_id}")
async def stop_ingest(task_id: str):
    """Request graceful stop of ingestion task."""
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "message": "任务不存在"}
    task["stop_requested"] = True
    return {"ok": True, "message": "已发送停止信号"}
