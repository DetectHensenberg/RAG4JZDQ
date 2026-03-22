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
    from src.core.query_engine.strategy_router import StrategyRouter
    from src.core.query_engine.reranker import CoreReranker

    embedding = EmbeddingFactory.create(settings)
    vector_store = VectorStoreFactory.create(settings, collection_name=collection)

    bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
    bm25.load(collection)

    dense_retriever = DenseRetriever(settings=settings, embedding_client=embedding, vector_store=vector_store)
    sparse_retriever = SparseRetriever(settings=settings, bm25_indexer=bm25, vector_store=vector_store)
    query_processor = QueryProcessor()
    fusion = RRFFusion()

    # Create reranker (gracefully falls back to NoneReranker if disabled/failed)
    reranker: CoreReranker | None = None
    try:
        reranker = CoreReranker(settings)
        if not reranker.is_enabled:
            reranker = None
    except Exception as e:
        logger.warning(f"Reranker init failed, proceeding without: {e}")

    _hybrid_search = HybridSearch(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion=fusion,
        reranker=reranker,
    )

    parent_mode = getattr(settings.retrieval, "parent_retrieval_mode", "never")
    graph_mode = getattr(settings.retrieval, "graph_rag_mode", "never")

    if parent_mode != "never":
        try:
            from src.ingestion.storage.parent_store import ParentStore

            _hybrid_search.parent_store = ParentStore(
                db_path=str(resolve_path(f"data/db/parent_store/{collection}.db"))
            )
        except Exception as e:
            logger.warning(f"ParentStore init failed: {e}")

    if graph_mode != "never":
        try:
            from src.ingestion.storage.graph_store import GraphStore

            _hybrid_search.graph_store = GraphStore(
                db_path=str(resolve_path(f"data/db/graph_store/{collection}.db"))
            )
        except Exception as e:
            logger.warning(f"GraphStore init failed: {e}")

    router_llm = None
    if parent_mode == "auto" or graph_mode == "auto":
        try:
            router_llm = get_llm()
        except Exception as e:
            logger.warning(f"StrategyRouter LLM init failed, using fallback routing: {e}")

    _hybrid_search.strategy_router = StrategyRouter(settings=settings, llm=router_llm)
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
# IngestionPipeline (cached per collection + skip_llm key)
# ---------------------------------------------------------------------------

_pipelines: dict[tuple[str, bool], Any] = {}


def get_pipeline(collection: str = "default", skip_llm_transform: bool = False) -> Any:
    """Return a cached IngestionPipeline, creating one if needed."""
    key = (collection, skip_llm_transform)
    if key in _pipelines:
        return _pipelines[key]

    from src.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        get_settings(),
        collection=collection,
        skip_llm_transform=skip_llm_transform,
    )
    _pipelines[key] = pipeline
    logger.info(f"Pipeline cached: collection={collection}, skip_llm={skip_llm_transform}")
    return pipeline


# ---------------------------------------------------------------------------
# Reset (called after config changes)
# ---------------------------------------------------------------------------

def reset_all() -> None:
    """Clear all cached instances — called after config update."""
    global _hybrid_search, _hybrid_collection, _llm, _pipelines
    _hybrid_search = None
    _hybrid_collection = ""
    _llm = None
    # Close pipeline resources before clearing
    for p in _pipelines.values():
        try:
            p.close()
        except Exception:
            pass
    _pipelines = {}
    get_settings.cache_clear()
    logger.info("All cached instances cleared")


def shutdown_stores() -> None:
    """Gracefully close all vector stores to prevent HNSW index corruption.
    
    Called on FastAPI shutdown event. Ensures ChromaDB WAL is checkpointed
    and HNSW index is flushed before process exits.
    """
    global _hybrid_search
    if _hybrid_search is not None:
        try:
            dense = getattr(_hybrid_search, "dense_retriever", None)
            if dense:
                vs = getattr(dense, "vector_store", None)
                if vs and hasattr(vs, "close"):
                    vs.close()
                    logger.info("Vector store closed gracefully")
        except Exception as e:
            logger.warning(f"Error closing vector store: {e}")
    reset_all()
