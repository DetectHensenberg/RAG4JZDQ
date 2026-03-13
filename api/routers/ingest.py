"""Ingest management API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def ingest_health():
    return {"ok": True, "module": "ingest"}
