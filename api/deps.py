"""Dependency injection for FastAPI — singleton instances of heavy objects."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> Any:
    """Return cached Settings instance."""
    from src.core.settings import load_settings
    return load_settings()


# ---------------------------------------------------------------------------
# HybridSearch (lazy singleton)
# ---------------------------------------------------------------------------

_hybrid_search: Optional[Any] = None
_hybrid_collection: str = ""


def get_hybrid_search(collection: str = "default") -> Any:
    """Return a cached HybridSearch instance, rebuilding if collection changes."""
    global _hybrid_search, _hybrid_collection

    if _hybrid_search is not None and _hybrid_collection == collection:
        return _hybrid_search

    settings = get_settings()

    from src.core.settings import resolve_path
    from src.libs.embedding.embedding_factory import EmbeddingFactory
    from src.libs.vector_store.vector_store_factory import VectorStoreFactory
    from src.ingestion.storage.bm25_indexer import BM25Indexer
    from src.core.query_engine.dense_retriever import DenseRetriever
    from src.core.query_engine.sparse_retriever import SparseRetriever
    from src.core.query_engine.query_processor import QueryProcessor
    from src.core.query_engine.fusion import RRFFusion
    from src.core.query_engine.hybrid_search import HybridSearch

    embedding = EmbeddingFactory.create(settings)
    vector_store = VectorStoreFactory.create(settings, collection_name=collection)

    bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
    bm25.load(collection)

    dense_retriever = DenseRetriever(settings=settings, embedding=embedding, vector_store=vector_store)
    sparse_retriever = SparseRetriever(settings=settings, bm25_indexer=bm25, vector_store=vector_store)
    query_processor = QueryProcessor(settings=settings)
    fusion = RRFFusion(settings=settings)

    _hybrid_search = HybridSearch(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion=fusion,
    )
    _hybrid_collection = collection
    logger.info(f"HybridSearch initialized for collection '{collection}'")
    return _hybrid_search


# ---------------------------------------------------------------------------
# LLM (lazy singleton)
# ---------------------------------------------------------------------------

_llm: Optional[Any] = None


def get_llm() -> Any:
    """Return a cached LLM instance."""
    global _llm
    if _llm is not None:
        return _llm

    from src.libs.llm.llm_factory import LLMFactory
    _llm = LLMFactory.create(get_settings())
    return _llm


# ---------------------------------------------------------------------------
# Reset (called after config changes)
# ---------------------------------------------------------------------------

def reset_all() -> None:
    """Clear all cached instances — called after config update."""
    global _hybrid_search, _hybrid_collection, _llm
    _hybrid_search = None
    _hybrid_collection = ""
    _llm = None
    get_settings.cache_clear()
    logger.info("All cached instances cleared")
