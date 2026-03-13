"""Chat/QA API router — SSE streaming."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def chat_health():
    return {"ok": True, "module": "chat"}
