"""FastAPI application entry point for 九洲 RAG 管理平台.

Production mode: serves Vue static files from web/dist/ at root.
Development mode: Vue dev server at :5173 proxies /api to :8000.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import chat, knowledge, config, data, system, ingest, evaluation, export

logger = logging.getLogger(__name__)

app = FastAPI(
    title="九洲 RAG 管理平台 API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# CORS — allow Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/api/health")
async def health():
    return {"ok": True}


# Production: serve Vue static files
_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
    logger.info(f"Serving Vue static files from {_DIST_DIR}")
