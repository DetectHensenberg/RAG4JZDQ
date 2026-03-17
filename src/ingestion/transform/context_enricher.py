"""Context Enricher transform for Contextual Retrieval.

Injects document-level context (filename) into chunk embedding text
to improve retrieval quality without LLM costs.
"""

import logging
from pathlib import Path
from typing import List, Optional

from src.core.settings import Settings
from src.core.types import Chunk
from src.ingestion.transform.base_transform import BaseTransform

logger = logging.getLogger(__name__)


class ContextEnricher(BaseTransform):
    """Enriches chunks with document context for better embedding.
    
    Implements rule-based Contextual Retrieval by prepending document
    filename to chunk text, stored in metadata["embedding_text"].
    This allows the embedding model to capture document-level context
    without modifying the original chunk text.
    
    Key Features:
    - Zero-cost: No LLM calls required
    - Non-destructive: Original chunk.text preserved
    - Configurable: Can be disabled via settings
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize ContextEnricher.
        
        Args:
            settings: Application settings containing context_enricher config.
        """
        self.settings = settings
        self.enabled = True
        
        if settings.ingestion and settings.ingestion.context_enricher:
            self.enabled = settings.ingestion.context_enricher.enabled
        
        logger.info(f"ContextEnricher initialized (enabled={self.enabled})")

    def transform(
        self,
        chunks: List[Chunk],
        trace: Optional[object] = None,
    ) -> List[Chunk]:
        """Transform chunks by adding document context to embedding text.
        
        Args:
            chunks: List of chunks to enrich.
            trace: Optional trace context for observability.
            
        Returns:
            List of chunks with embedding_text in metadata.
        """
        if not self.enabled:
            logger.debug("ContextEnricher disabled, skipping")
            return chunks
        
        if not chunks:
            return chunks
        
        enriched_count = 0
        for chunk in chunks:
            embedding_text = self._create_embedding_text(chunk)
            if embedding_text:
                chunk.metadata["embedding_text"] = embedding_text
                enriched_count += 1
        
        logger.info(f"ContextEnricher: enriched {enriched_count}/{len(chunks)} chunks")
        return chunks

    def _create_embedding_text(self, chunk: Chunk) -> Optional[str]:
        """Create embedding text with document context prefix.
        
        Format: [文档: {filename}] {chunk_text}
        
        Args:
            chunk: The chunk to create embedding text for.
            
        Returns:
            Embedding text with context prefix, or None if no source_path.
        """
        source_path = chunk.metadata.get("source_path")
        if not source_path:
            return None
        
        filename = Path(source_path).stem
        if not filename:
            return None
        
        return f"[文档: {filename}] {chunk.text}"
