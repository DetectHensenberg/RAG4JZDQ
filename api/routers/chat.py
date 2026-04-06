"""Chat/QA API router — SSE streaming for knowledge-based Q&A.

This module is a thin HTTP adapter. All business logic resides in
:class:`src.services.chat_service.ChatService`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.deps import get_hybrid_search, get_llm
from api.models import ChatRequest
from src.repositories.history_repo import HistoryRepository
from src.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()

# Singleton repo (lightweight, stateless)
_history_repo = HistoryRepository()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint for knowledge-based Q&A.

    Delegates entirely to ChatService for retrieval, LLM streaming,
    image processing, and history persistence.
    """
    service = ChatService(
        llm=get_llm(),
        hybrid_search=get_hybrid_search(req.collection),
        history_repo=_history_repo,
    )
    return StreamingResponse(
        service.stream_answer(
            question=req.question,
            collection=req.collection,
            top_k=req.top_k,
            max_tokens=req.max_tokens,
            uploaded_text=req.uploaded_text,
        ),
        media_type="text/event-stream",
    )


@router.get("/history")
async def get_history(limit: int = 50):
    """Return recent QA history.

    Args:
        limit: Maximum number of records to return.
    """
    try:
        data = await _history_repo.list_recent(limit=limit)
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.delete("/history")
async def clear_history():
    """Clear all QA history."""
    try:
        await _history_repo.clear_all()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}
