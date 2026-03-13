"""System overview API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def system_health():
    return {"ok": True, "module": "system"}
