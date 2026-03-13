"""Data browser API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def data_health():
    return {"ok": True, "module": "data"}
