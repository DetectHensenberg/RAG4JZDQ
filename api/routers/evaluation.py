"""Evaluation API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def eval_health():
    return {"ok": True, "module": "evaluation"}
