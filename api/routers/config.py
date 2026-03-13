"""System config API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def config_health():
    return {"ok": True, "module": "config"}
