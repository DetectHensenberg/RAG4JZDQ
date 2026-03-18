"""PlantUML rendering API router - render diagrams from PlantUML text."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import zlib
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Kroki rendering server (local Docker preferred, fallback to public)
# Local: docker run -d --name kroki -p 8200:8000 --restart unless-stopped yuzutech/kroki
KROKI_BASE = "http://localhost:8200"

# In-memory SVG cache (md5 -> bytes), avoids duplicate Kroki calls
_svg_cache: dict[str, bytes] = {}
_CACHE_MAX = 200


class PlantUMLRequest(BaseModel):
    """Request model for PlantUML rendering."""
    code: str
    format: str = "svg"


_ACTIVITY_KEYWORDS = re.compile(r"(?:^|\n)\s*(?:start|stop|:.*?;)", re.DOTALL)


def _sanitize_plantuml(code: str) -> str:
    """Fix common LLM mistakes in PlantUML syntax."""
    # Chinese em-dash arrow -> PlantUML arrow
    code = code.replace("\u2014>", "-->")    # —>
    code = code.replace("\u2014\u2014>", "-->")  # ——>
    code = code.replace("\u2192", "-->")     # →
    code = code.replace("\u2190", "<--")     # ←
    code = code.replace("\u21d2", "==>")     # ⇒
    # Full-width punctuation -> ASCII
    code = code.replace("\uff08", "(")       # （
    code = code.replace("\uff09", ")")       # ）
    code = code.replace("\uff1a", ":")       # ：
    code = code.replace("\uff1b", ";")       # ；
    code = code.replace("\u3001", ",")       # 、
    code = code.replace("\u201c", '"')       # \u201c
    code = code.replace("\u201d", '"')       # \u201d
    # Fix broken arrows with extra spaces
    code = re.sub(r"-\s+->", "-->", code)
    code = re.sub(r"<-\s+-", "<--", code)
    # Remove 'left to right direction' from activity diagrams (incompatible
    # with Kroki's PlantUML engine — causes "Assumed diagram type: class")
    if _ACTIVITY_KEYWORDS.search(code):
        code = re.sub(r"(?m)^\s*left to right direction\s*\n?", "", code)
    return code


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
    code = _sanitize_plantuml(req.code)

    # Auto-wrap with @startuml/@enduml if missing (LLMs often omit them)
    stripped = code.strip()
    if not stripped.lower().startswith("@start"):
        code = f"@startuml\n{stripped}\n@enduml"

    # Check cache
    cache_key = hashlib.md5(code.encode()).hexdigest()
    if cache_key in _svg_cache:
        content_type = "image/svg+xml" if req.format == "svg" else "image/png"
        return Response(content=_svg_cache[cache_key], media_type=content_type)

    try:
        # Use Kroki POST API (more reliable than GET with encoded URL)
        # Must specify charset=utf-8 for Chinese characters
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KROKI_BASE}/plantuml/{req.format}",
                content=code.encode('utf-8'),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            
            if resp.status_code != 200:
                logger.warning(f"Kroki returned {resp.status_code}: {resp.text[:200]}")
                return Response(
                    content=f"PlantUML render failed: {resp.status_code} - {resp.text[:200]}",
                    status_code=400,
                )
            
            # Cache result
            if len(_svg_cache) >= _CACHE_MAX:
                _svg_cache.pop(next(iter(_svg_cache)))
            _svg_cache[cache_key] = resp.content

            content_type = "image/svg+xml" if req.format == "svg" else "image/png"
            return Response(content=resp.content, media_type=content_type)
            
    except httpx.TimeoutException:
        logger.debug("PlantUML render timeout")
        return Response(content="PlantUML render timeout", status_code=504)
    except httpx.ConnectError:
        # 网络不通时静默处理，不刷屏
        logger.debug("PlantUML service unreachable (network issue)")
        return Response(content="PlantUML service unreachable", status_code=503)
    except Exception as e:
        logger.warning(f"PlantUML render error: {e}")
        return Response(content=str(e), status_code=500)


@router.post("/render-base64")
async def render_plantuml_base64(req: PlantUMLRequest):
    """Render PlantUML and return as base64 data URI.
    
    Returns JSON with base64 data suitable for <img src="data:...">
    """
    try:
        encoded = _encode_plantuml(req.code)
        url = f"{KROKI_BASE}/plantuml/{req.format}/{encoded}"
        
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
