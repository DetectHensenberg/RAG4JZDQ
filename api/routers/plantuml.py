"""PlantUML rendering API router - render diagrams from PlantUML text."""

from __future__ import annotations

import base64
import hashlib
import logging
import zlib
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Kroki.io public API (free, no auth required)
# Can be self-hosted for production
KROKI_URL = "https://kroki.io/plantuml/svg"


class PlantUMLRequest(BaseModel):
    """Request model for PlantUML rendering."""
    code: str
    format: str = "svg"


def _encode_plantuml(text: str) -> str:
    """Encode PlantUML text for Kroki URL format.
    
    Uses deflate compression + base64 encoding (URL-safe).
    """
    # Compress with deflate
    compressed = zlib.compress(text.encode('utf-8'), level=9)[2:-4]  # Strip zlib header/trailer
    # Base64 encode (URL-safe)
    return base64.urlsafe_b64encode(compressed).decode('ascii')


@router.post("/render")
async def render_plantuml(req: PlantUMLRequest):
    """Render PlantUML code to image.
    
    Args:
        req: PlantUML request with code and format
        
    Returns:
        SVG or PNG image data
    """
    try:
        # Use Kroki POST API (more reliable than GET with encoded URL)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://kroki.io/plantuml/{req.format}",
                content=req.code.encode('utf-8'),
                headers={"Content-Type": "text/plain"},
            )
            
            if resp.status_code != 200:
                logger.warning(f"Kroki returned {resp.status_code}: {resp.text[:200]}")
                return Response(
                    content=f"PlantUML render failed: {resp.status_code} - {resp.text[:200]}",
                    status_code=400,
                )
            
            content_type = "image/svg+xml" if req.format == "svg" else "image/png"
            return Response(content=resp.content, media_type=content_type)
            
    except httpx.TimeoutException:
        return Response(content="PlantUML render timeout", status_code=504)
    except Exception as e:
        logger.exception(f"PlantUML render error: {e}")
        return Response(content=str(e), status_code=500)


@router.post("/render-base64")
async def render_plantuml_base64(req: PlantUMLRequest):
    """Render PlantUML and return as base64 data URI.
    
    Returns JSON with base64 data suitable for <img src="data:...">
    """
    try:
        encoded = _encode_plantuml(req.code)
        url = f"https://kroki.io/plantuml/{req.format}/{encoded}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            
            if resp.status_code != 200:
                return {"ok": False, "message": f"Render failed: {resp.status_code}"}
            
            b64_data = base64.b64encode(resp.content).decode('utf-8')
            mime_type = "image/svg+xml" if req.format == "svg" else "image/png"
            data_uri = f"data:{mime_type};base64,{b64_data}"
            
            return {
                "ok": True,
                "data": {
                    "data_uri": data_uri,
                    "mime_type": mime_type,
                }
            }
            
    except Exception as e:
        logger.exception(f"PlantUML render error: {e}")
        return {"ok": False, "message": str(e)}
