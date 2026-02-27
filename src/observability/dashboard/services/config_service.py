"""Dashboard configuration reading service.

Wraps :class:`Settings` to provide formatted component information
for the Overview page.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.settings import Settings, load_settings


@dataclass
class ComponentInfo:
    """Summary of a single configured component."""

    name: str
    provider: str
    model: str
    extra: Dict[str, Any]


class ConfigService:
    """Read-only service that exposes application configuration.

    Args:
        settings_path: Path to ``settings.yaml``.
    """

    def __init__(self, settings_path: Optional[str] = None) -> None:
        self._settings_path = settings_path
        self._settings: Optional[Settings] = None

    # ── lazy load ────────────────────────────────────────────────────

    def _load(self) -> Settings:
        if self._settings is None:
            self._settings = load_settings(self._settings_path)
        return self._settings

    def reload(self) -> None:
        """Force reload of settings from disk."""
        self._settings = None

    @property
    def settings(self) -> Settings:
        return self._load()

    # ── component cards ──────────────────────────────────────────────

    def get_component_cards(self) -> List[ComponentInfo]:
        """Return a list of component summaries for the Overview page."""
        s = self._load()
        cards: List[ComponentInfo] = []

        # LLM
        cards.append(ComponentInfo(
            name="LLM",
            provider=s.llm.provider,
            model=s.llm.model,
            extra={"temperature": s.llm.temperature, "max_tokens": s.llm.max_tokens},
        ))

        # Embedding
        cards.append(ComponentInfo(
            name="Embedding",
            provider=s.embedding.provider,
            model=s.embedding.model,
            extra={"dimensions": s.embedding.dimensions},
        ))

        # VectorStore
        cards.append(ComponentInfo(
            name="Vector Store",
            provider=s.vector_store.provider,
            model=s.vector_store.collection_name,
            extra={"persist_directory": s.vector_store.persist_directory},
        ))

        # Retrieval
        cards.append(ComponentInfo(
            name="Retrieval",
            provider="hybrid",
            model="dense + sparse + RRF",
            extra={
                "dense_top_k": s.retrieval.dense_top_k,
                "sparse_top_k": s.retrieval.sparse_top_k,
                "fusion_top_k": s.retrieval.fusion_top_k,
            },
        ))

        # Rerank
        cards.append(ComponentInfo(
            name="Reranker",
            provider=s.rerank.provider if s.rerank.enabled else "disabled",
            model=s.rerank.model if s.rerank.enabled else "-",
            extra={"enabled": s.rerank.enabled, "top_k": s.rerank.top_k},
        ))

        # Vision LLM
        if s.vision_llm and s.vision_llm.enabled:
            cards.append(ComponentInfo(
                name="Vision LLM",
                provider=s.vision_llm.provider,
                model=s.vision_llm.model,
                extra={"max_image_size": s.vision_llm.max_image_size},
            ))

        # Ingestion
        if s.ingestion:
            cards.append(ComponentInfo(
                name="Ingestion",
                provider=s.ingestion.splitter,
                model="-",
                extra={
                    "chunk_size": s.ingestion.chunk_size,
                    "chunk_overlap": s.ingestion.chunk_overlap,
                    "batch_size": s.ingestion.batch_size,
                },
            ))

        return cards
