"""FastAPI application entry point for 九洲 RAG 管理平台.

Production mode: serves Vue static files from web/dist/ at root.
Development mode: Vue dev server at :5173 proxies /api to :8000.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.exceptions import register_exception_handlers
from api.routers import chat, knowledge, config, data, system, ingest, evaluation, export, plantuml, query, data_manage, file_dialog
from api.security import verify_api_key

logger = logging.getLogger(__name__)

app = FastAPI(
    title="九洲 RAG 管理平台 API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    dependencies=[Depends(verify_api_key)],
)

# Register global exception handlers
register_exception_handlers(app)

# CORS — configurable via env, defaults to Vue dev server
_cors_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# Mount API routers
app.include_router(chat.router, prefix="/api/chat", tags=["问答"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库构建"])
app.include_router(config.router, prefix="/api/config", tags=["系统配置"])
app.include_router(data.router, prefix="/api/data", tags=["数据浏览"])
app.include_router(system.router, prefix="/api/system", tags=["系统总览"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["摄取管理"])
app.include_router(evaluation.router, prefix="/api/eval", tags=["评估"])
app.include_router(export.router, prefix="/api/export", tags=["导出"])
app.include_router(plantuml.router, prefix="/api/plantuml", tags=["图表渲染"])
app.include_router(query.router, prefix="/api/query", tags=["测试查询"])
app.include_router(data_manage.router, prefix="/api/data-manage", tags=["数据管理"])
app.include_router(file_dialog.router, prefix="/api/file-dialog", tags=["文件对话框"])


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully close ChromaDB to prevent HNSW index corruption."""
    from api.deps import shutdown_stores
    shutdown_stores()
    logger.info("Application shutdown: all stores closed")


# Register allowed base paths for path traversal protection
from api.security import add_allowed_base
from src.core.settings import resolve_path

add_allowed_base(resolve_path("data"))


# Production: serve Vue static files
_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
    logger.info(f"Serving Vue static files from {_DIST_DIR}")
