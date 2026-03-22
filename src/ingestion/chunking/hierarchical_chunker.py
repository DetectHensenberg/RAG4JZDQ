"""Hierarchical Chunker - Splits documents into Parent and Child chunks.

This module implements the 'Parent Document Retrieval' splitting strategy:
1. Document is first split into large 'Parent' chunks.
2. Each Parent chunk is further split into small 'Child' chunks.
3. Children maintain a 'parent_id' reference for retrieval-time expansion.
"""

from __future__ import annotations
from typing import List, Tuple, TYPE_CHECKING
from src.core.types import Chunk, Document
from src.ingestion.chunking.document_chunker import DocumentChunker
from src.libs.splitter.recursive_splitter import RecursiveSplitter
from src.observability.logger import get_logger

if TYPE_CHECKING:
    from src.core.settings import Settings

logger = get_logger(__name__)

class HierarchicalChunker(DocumentChunker):
    """Chunker that produces a hierarchy of chunks (Parent -> Children).
    
    Inherits from DocumentChunker to reuse ID generation and metadata enrichment logic.
    """
    
    def __init__(self, settings: Settings):
        """Initialize with two splitters based on hierarchical config."""
        super().__init__(settings)
        
        # Determine parent/child sizes from settings
        # Default to 2000/400 if not specified
        parent_config = settings.ingestion.parent_retrieval if settings.ingestion else None
        
        self.parent_size = getattr(parent_config, "parent_chunk_size", 2000) if parent_config else 2000
        self.child_size = getattr(parent_config, "child_chunk_size", 400) if parent_config else 400
        self.child_overlap = getattr(parent_config, "child_chunk_overlap", 50) if parent_config else 50
        
        # Override self._splitter (which is the child splitter in this context)
        # to ensure it uses the child_size
        self._child_splitter = RecursiveSplitter(
            settings, 
            chunk_size=self.child_size, 
            chunk_overlap=self.child_overlap
        )
        
        # Create parent splitter
        self._parent_splitter = RecursiveSplitter(
            settings,
            chunk_size=self.parent_size,
            chunk_overlap=0 # Parents usually don't need overlap for context retrieval
        )
        
        logger.info(f"HierarchicalChunker initialized: Parent={self.parent_size}, Child={self.child_size}")

    def split_hierarchical(self, document: Document) -> Tuple[List[Chunk], List[Chunk]]:
        """Split document into hierarchical parent and child chunks.
        
        Returns:
            Tuple of (child_chunks, parent_chunks)
        """
        if not document.text or not document.text.strip():
            raise ValueError(f"Document {document.id} has no text content")

        # 1. Generate Parent Chunks
        parent_texts = self._parent_splitter.split_text(document.text)
        parent_chunks: List[Chunk] = []
        
        # Build heading paths for parents for better context
        parent_heading_paths = self._build_heading_paths(parent_texts)
        
        for i, p_text in enumerate(parent_texts):
            p_id = f"{document.id}_p_{i:03d}"
            p_metadata = self._inherit_metadata(
                document, i, p_text, 
                parent_heading_paths[i] if i < len(parent_heading_paths) else ""
            )
            p_metadata["is_parent"] = True
            
            parent_chunks.append(Chunk(
                id=p_id,
                text=p_text,
                metadata=p_metadata
            ))

        # 2. Generate Child Chunks for each Parent
        all_child_chunks: List[Chunk] = []
        child_global_index = 0
        
        for parent in parent_chunks:
            child_texts = self._child_splitter.split_text(parent.text)
            child_heading_paths = self._build_heading_paths(child_texts)
            
            for j, c_text in enumerate(child_texts):
                # Generate unique child ID that includes parent info for traceability
                c_id = self._generate_chunk_id(parent.id, j, c_text)
                c_metadata = self._inherit_metadata(
                    document, child_global_index, c_text,
                    child_heading_paths[j] if j < len(child_heading_paths) else ""
                )
                c_metadata["parent_id"] = parent.id
                c_metadata["is_child"] = True
                
                all_child_chunks.append(Chunk(
                    id=c_id,
                    text=c_text,
                    metadata=c_metadata
                ))
                child_global_index += 1
                
        logger.info(f"Hierarchical split: {len(parent_chunks)} parents -> {len(all_child_chunks)} children")
        return all_child_chunks, parent_chunks
