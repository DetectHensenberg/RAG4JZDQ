"""Chunking module - document splitting adapter layer.

This module provides the business adapter for text splitting, transforming
Document objects into Chunk objects with proper metadata and traceability.
"""

from src.ingestion.chunking.document_chunker import DocumentChunker

__all__ = ["DocumentChunker"]
