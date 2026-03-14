"""Query API router - test retrieval queries."""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import get_hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    """Request model for test query."""
    query: str
    collection: str = "default"
    top_k: int = 10


class QueryResult(BaseModel):
    """Single query result."""
    source: str
    source_path: str
    text: str
    content: str
    score: float
    page: Optional[int] = None


class QueryResponse(BaseModel):
    """Response model for test query."""
    results: list[QueryResult]
    latency_ms: float


@router.post("")
async def test_query(req: QueryRequest):
    """Execute a test retrieval query.
    
    Args:
        req: Query request with query text, collection, and top_k
        
    Returns:
        Query results with latency
    """
    try:
        start = time.time()
        
        search = get_hybrid_search(req.collection)
        results = search.search(query=req.query, top_k=req.top_k)
        
        latency_ms = (time.time() - start) * 1000
        
        query_results = [
            QueryResult(
                source=r.metadata.get("source_path", "未知"),
                source_path=r.metadata.get("source_path", "未知"),
                text=r.text[:500],
                content=r.text[:500],
                score=round(r.score, 4),
                page=r.metadata.get("page"),
            )
            for r in results
        ]
        
        return {
            "ok": True,
            "data": QueryResponse(
                results=query_results,
                latency_ms=round(latency_ms, 2),
            ).model_dump(),
        }
        
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        return {"ok": False, "message": str(e)}
