"""Knowledge base ingestion API router — SSE progress streaming.

Architecture:
- Ingestion runs in background thread, decoupled from SSE connection
- Task state stored in _tasks dict with event queue for progress updates
- SSE endpoint polls event queue, allowing reconnection without losing progress
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.models import IngestRequest
from api.security import validate_path
from src.core.settings import resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task store with event queues
_tasks: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()


# Allowed file extensions for ingestion (whitelist)
_ALLOWED_EXTENSIONS = frozenset({".pdf", ".pptx", ".docx", ".md", ".txt", ".csv", ".xlsx"})


def _scan_files(folder: str, file_types: List[str]) -> List[Path]:
    """Recursively scan folder for matching files."""
    folder_path = Path(folder)
    if not folder_path.exists():
        return []
    # Only allow whitelisted extensions
    safe_types = [ft for ft in file_types if ft.lower() in _ALLOWED_EXTENSIONS]
    files = []
    for ft in safe_types:
        files.extend(folder_path.rglob(f"*{ft}"))
    return sorted(files)


@router.post("/scan")
async def scan_folder(body: Dict[str, Any]):
    """Scan a folder and return file list."""
    folder = body.get("folder_path", "")
    file_types = body.get("file_types", [".pdf", ".pptx", ".docx", ".md", ".txt"])
    
    # Basic validation — block traversal patterns but allow user folders
    from api.security import _DANGEROUS_PATTERNS
    if not folder or not folder.strip():
        return {"ok": False, "message": "路径不能为空"}
    if _DANGEROUS_PATTERNS.search(folder):
        return {"ok": False, "message": "路径包含非法字符"}
    
    folder_path = Path(folder).resolve()
    if not folder_path.exists():
        return {"ok": False, "message": f"路径不存在: {folder}"}
    if not folder_path.is_dir():
        return {"ok": False, "message": "路径不是文件夹"}
    
    files = _scan_files(str(folder_path), file_types)
    return {
        "ok": True,
        "data": {
            "files": [{"path": str(f), "name": f.name, "size": f.stat().st_size} for f in files],
            "total": len(files),
        },
    }


def _run_ingestion_worker(task_id: str, task: Dict[str, Any]) -> None:
    """Background worker that runs ingestion and pushes events to queue.
    
    This runs in a separate thread, decoupled from SSE connection.
    """
    from src.core.settings import load_settings
    from src.ingestion.pipeline import IngestionPipeline

    event_queue: queue.Queue = task["event_queue"]
    
    try:
        settings = load_settings()
        pipeline = IngestionPipeline(
            settings,
            collection=task["collection"],
            force=task.get("force", False),
            skip_llm_transform=task.get("skip_llm_transform", False),
        )

        files = task["files"]
        total = len(files)
        
        with _task_lock:
            task["status"] = "running"
            task["current"] = 0
            task["total"] = total
        
        results = {"success": 0, "failed": 0, "skipped": 0}

        for idx, fpath in enumerate(files):
            if task["stop_requested"]:
                event_queue.put({"type": "stopped", "completed": idx, "total": total})
                break

            fname = Path(fpath).name
            
            with _task_lock:
                task["current"] = idx + 1
                task["current_file"] = fname
            
            event_queue.put({
                "type": "progress", 
                "current": idx + 1, 
                "total": total, 
                "file": fname, 
                "stage": "处理中"
            })

            try:
                from src.ingestion.vendor_inference import infer_from_filename

                extra_meta = task.get("extra_metadata")
                file_meta = dict(extra_meta) if extra_meta else {}
                file_meta["source_filename"] = fname
                file_meta["source_directory"] = str(Path(fpath).parent.name)
                # Auto-infer vendor/model from filename when not provided
                if not file_meta.get("product_vendor") or not file_meta.get("product_model"):
                    inf_vendor, inf_model = infer_from_filename(fname)
                    if inf_vendor and not file_meta.get("product_vendor"):
                        file_meta["product_vendor"] = inf_vendor
                    if inf_model and not file_meta.get("product_model"):
                        file_meta["product_model"] = inf_model
                result = pipeline.run(
                    file_path=fpath,
                    original_filename=fname,
                    extra_metadata=file_meta if file_meta else None,
                )
                if result.stages.get("integrity", {}).get("skipped"):
                    results["skipped"] += 1
                    event_queue.put({"type": "file_done", "file": fname, "status": "skipped"})
                elif result.success:
                    results["success"] += 1
                    event_queue.put({"type": "file_done", "file": fname, "status": "success", "chunks": result.chunk_count})
                else:
                    results["failed"] += 1
                    event_queue.put({"type": "file_done", "file": fname, "status": "failed", "error": result.error or "未知错误"})
            except Exception as e:
                results["failed"] += 1
                event_queue.put({"type": "file_done", "file": fname, "status": "failed", "error": str(e)})
                logger.exception(f"Ingestion failed for {fname}")

        with _task_lock:
            task["status"] = "done"
            task["results"] = results
        
        event_queue.put({"type": "done", **results})
        
    except Exception as e:
        logger.exception("Ingestion worker crashed")
        with _task_lock:
            task["status"] = "error"
            task["error"] = str(e)
        event_queue.put({"type": "error", "message": str(e)})


@router.post("/ingest")
async def start_ingest(req: IngestRequest):
    """Start ingestion in background thread and return task_id for progress tracking."""
    from api.security import _DANGEROUS_PATTERNS
    if not req.folder_path or not req.folder_path.strip():
        return {"ok": False, "message": "路径不能为空"}
    if _DANGEROUS_PATTERNS.search(req.folder_path):
        return {"ok": False, "message": "路径包含非法字符"}
    
    folder_path = Path(req.folder_path).resolve()
    if not folder_path.exists():
        return {"ok": False, "message": f"路径不存在: {req.folder_path}"}
    if not folder_path.is_dir():
        return {"ok": False, "message": "路径不是文件夹"}
    
    files = _scan_files(str(folder_path), req.file_types)
    if not files:
        return {"ok": False, "message": "未找到匹配文件"}

    task_id = str(uuid.uuid4())[:8]
    # Build extra metadata for product collections
    extra_metadata: Dict[str, str] = {}
    if req.product_vendor:
        extra_metadata["product_vendor"] = req.product_vendor
    if req.product_model:
        extra_metadata["product_model"] = req.product_model
    if req.product_category:
        extra_metadata["product_category"] = req.product_category
    if req.product_device:
        extra_metadata["product_device"] = req.product_device

    task = {
        "files": [str(f) for f in files],
        "collection": req.collection,
        "force": req.force,
        "skip_llm_transform": req.skip_llm_transform,
        "extra_metadata": extra_metadata if extra_metadata else None,
        "stop_requested": False,
        "status": "pending",
        "event_queue": queue.Queue(),
        "current": 0,
        "total": len(files),
        "current_file": "",
        "events_sent": 0,  # Track how many events SSE has consumed
    }
    
    with _task_lock:
        _tasks[task_id] = task
    
    # Start background worker thread
    worker = threading.Thread(
        target=_run_ingestion_worker,
        args=(task_id, task),
        daemon=True,
        name=f"ingest-{task_id}",
    )
    worker.start()
    
    return {"ok": True, "data": {"task_id": task_id, "total_files": len(files)}}


@router.get("/progress/{task_id}")
async def ingest_progress(task_id: str):
    """SSE stream of ingestion progress.
    
    This endpoint can be reconnected without losing progress.
    Events are consumed from the task's event queue.
    """
    with _task_lock:
        task = _tasks.get(task_id)
    
    if not task:
        return {"ok": False, "message": "任务不存在"}

    def event_stream():
        event_queue: queue.Queue = task["event_queue"]
        
        # Send current state for reconnection
        with _task_lock:
            if task["current"] > 0:
                yield f"data: {json.dumps({'type': 'reconnect', 'current': task['current'], 'total': task['total'], 'file': task.get('current_file', '')}, ensure_ascii=False)}\n\n"
        
        while True:
            try:
                # Poll with timeout to allow checking task status
                event = event_queue.get(timeout=1.0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                
                # Terminal events
                if event.get("type") in ("done", "stopped", "error"):
                    break
                    
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                
                # Check if task is done (in case we missed the event)
                with _task_lock:
                    if task["status"] in ("done", "error"):
                        results = task.get("results", {})
                        yield f"data: {json.dumps({'type': 'done', **results}, ensure_ascii=False)}\n\n"
                        break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/stop/{task_id}")
async def stop_ingest(task_id: str):
    """Request graceful stop of ingestion task."""
    with _task_lock:
        task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "message": "任务不存在"}
    task["stop_requested"] = True
    return {"ok": True, "message": "已发送停止信号"}
