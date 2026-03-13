"""Knowledge base ingestion API router — SSE progress."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def knowledge_health():
    return {"ok": True, "module": "knowledge"}
