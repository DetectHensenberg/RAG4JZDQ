"""Document export API router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def export_health():
    return {"ok": True, "module": "export"}
