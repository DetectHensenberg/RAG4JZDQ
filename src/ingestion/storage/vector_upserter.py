"""Vector Upserter for writing chunks to vector database.

This module implements the VectorUpserter component, responsible for:
- Generating deterministic chunk IDs from content
- Transforming chunks and vectors into storage records
- Calling VectorStore for idempotent writes
- Supporting batch operations with consistent ordering

Design Principles:
- Idempotent: Same content produces same ID, repeated writes safe
- Observable: Accepts TraceContext for future integration
- Config-Driven: Uses VectorStoreFactory from settings
- Deterministic: Stable hash-based ID generation
- Type-Safe: Full type hints and validation
"""

import hashlib
from typing import List, Dict, Any, Optional

from src.core.types import Chunk
from src.core.settings import Settings
from src.libs.vector_store.vector_store_factory import VectorStoreFactory


class VectorUpserter:
    """Write chunks and vectors to vector database with idempotent guarantees.
    
    This upserter receives chunks and their dense vectors from DenseEncoder,
    generates stable chunk IDs, and writes them to the configured vector store.
    
    Chunk ID Format:
        {source_path_hash}_{chunk_index:04d}_{content_hash}
        
        Where:
        - source_path_hash = first 8 chars of SHA256(source_path)
        - chunk_index = zero-padded 4-digit index
        - content_hash = first 8 chars of SHA256(chunk.text)
        
    This ensures:
        - Same content → same ID (idempotent)
        - Content change → different ID (versioning)
        - Human-readable with source traceability
    
    Example:
        >>> upserter = VectorUpserter(settings)
        >>> 
        >>> chunks = [
        ...     Chunk(id="temp1", text="Hello world", metadata={"source_path": "doc.pdf", "chunk_index": 0}),
        ...     Chunk(id="temp2", text="Python rocks", metadata={"source_path": "doc.pdf", "chunk_index": 1})
        ... ]
        >>> vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        >>> 
        >>> upserter.upsert(chunks, vectors)
        >>> # Chunks written with stable IDs like: "a1b2c3d4_0000_e5f6g7h8"
    """
    
    def __init__(self, settings: Settings, collection_name: Optional[str] = None):
        """Initialize VectorUpserter with configured vector store.
        
        Args:
            settings: Application settings containing vector_store configuration.
            collection_name: Optional collection name to override settings default.
        
        Raises:
            ValueError: If settings are invalid or vector store cannot be created.
        """
        self.settings = settings
        kwargs = {}
        if collection_name:
            kwargs['collection_name'] = collection_name
        self.vector_store = VectorStoreFactory.create(settings, **kwargs)
    
    def upsert(
        self,
        chunks: List[Chunk],
        vectors: List[List[float]],
        trace: Optional[Any] = None,
    ) -> List[str]:
        """Upsert chunks with their vectors to vector store.
        
        Args:
            chunks: List of Chunk objects to store.
            vectors: List of embedding vectors (same order and length as chunks).
            trace: Optional TraceContext for observability (reserved for Stage F).
        
        Returns:
            List of generated chunk IDs (same order as input chunks).
        
        Raises:
            ValueError: If chunks and vectors lengths don't match, or if required
                       metadata fields are missing.
            RuntimeError: If vector store upsert operation fails.
        
        Example:
            >>> chunks = [Chunk(...), Chunk(...)]
            >>> vectors = [[0.1, 0.2], [0.3, 0.4]]
            >>> chunk_ids = upserter.upsert(chunks, vectors)
            >>> len(chunk_ids) == len(chunks)  # True
        """
        # Validate input lengths match
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunk count ({len(chunks)}) must match vector count ({len(vectors)})"
            )
        
        if not chunks:
            raise ValueError("Cannot upsert empty chunks list")
        
        # Generate stable chunk IDs and build records
        records = []
        chunk_ids = []
        
        for chunk, vector in zip(chunks, vectors):
            # Generate deterministic chunk ID
            chunk_id = self._generate_chunk_id(chunk)
            chunk_ids.append(chunk_id)
            
            # Build storage record
            record = {
                "id": chunk_id,
                "vector": vector,
                "metadata": {
                    **chunk.metadata,  # Preserve all original metadata
                    "text": chunk.text,  # Store text for retrieval
                    "chunk_id": chunk_id,  # Redundant but useful for queries
                },
            }
            records.append(record)
        
        # Perform idempotent upsert
        try:
            self.vector_store.upsert(records, trace=trace)
        except Exception as e:
            raise RuntimeError(
                f"Vector store upsert failed: {str(e)}"
            ) from e
        
        return chunk_ids
    
    def _generate_chunk_id(self, chunk: Chunk) -> str:
        """Generate deterministic chunk ID from content.
        
        Args:
            chunk: Chunk object to generate ID for.
        
        Returns:
            Stable chunk ID string.
        
        Raises:
            ValueError: If required metadata fields are missing.
        """
        # Validate required metadata
        if "source_path" not in chunk.metadata:
            raise ValueError("Chunk metadata must contain 'source_path'")
        if "chunk_index" not in chunk.metadata:
            raise ValueError("Chunk metadata must contain 'chunk_index'")
        
        source_path = chunk.metadata["source_path"]
        chunk_index = chunk.metadata["chunk_index"]
        
        # Compute stable hashes
        source_hash = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:8]
        content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()[:8]
        
        # Format: {source_hash}_{index:04d}_{content_hash}
        chunk_id = f"{source_hash}_{chunk_index:04d}_{content_hash}"
        
        return chunk_id
    
    def upsert_batch(
        self,
        batches: List[tuple[List[Chunk], List[List[float]]]],
        trace: Optional[Any] = None,
    ) -> List[str]:
        """Upsert multiple batches of chunks and vectors.
        
        This is a convenience method for processing outputs from BatchProcessor.
        All batches are flattened and processed in a single upsert operation
        to maintain ordering and reduce vector store round trips.
        
        Args:
            batches: List of (chunks, vectors) tuples from batch processing.
            trace: Optional TraceContext for observability.
        
        Returns:
            List of all generated chunk IDs in order.
        
        Example:
            >>> batch1 = ([chunk1, chunk2], [[0.1, 0.2], [0.3, 0.4]])
            >>> batch2 = ([chunk3], [[0.5, 0.6]])
            >>> chunk_ids = upserter.upsert_batch([batch1, batch2])
            >>> len(chunk_ids)  # 3
        """
        # Flatten all batches
        all_chunks = []
        all_vectors = []
        
        for chunks, vectors in batches:
            all_chunks.extend(chunks)
            all_vectors.extend(vectors)
        
        # Single upsert operation
        return self.upsert(all_chunks, all_vectors, trace=trace)
