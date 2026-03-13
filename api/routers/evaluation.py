"""Evaluation API router — run retrieval quality evaluations."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from api.models import EvalRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run")
async def run_evaluation(req: EvalRequest):
    """Run evaluation on a set of queries."""
    try:
        from src.core.settings import load_settings
        from api.deps import get_hybrid_search

        settings = load_settings()
        search = get_hybrid_search(req.collection)

        results = []
        for query in req.queries:
            hits = search.search(query=query, top_k=10)
            results.append({
                "query": query,
                "hits": len(hits),
                "top_sources": [h.metadata.get("source_path", "?") for h in hits[:3]],
                "top_scores": [round(h.score, 4) for h in hits[:3]],
            })

        return {"ok": True, "data": {"results": results, "total_queries": len(req.queries)}}
    except Exception as e:
        logger.exception("Evaluation failed")
        return {"ok": False, "message": str(e)}
