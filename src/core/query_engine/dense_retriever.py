"""Dense Retriever for semantic search using vector embeddings.

This module implements the DenseRetriever component that performs semantic search
by embedding the query and retrieving similar chunks from the vector store.
It forms the Dense route in the Hybrid Search Engine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.core.types import RetrievalResult

if TYPE_CHECKING:
    from src.core.settings import Settings
    from src.libs.embedding.base_embedding import BaseEmbedding
    from src.libs.vector_store.base_vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Dense retriever using embedding-based semantic search.
    
    This class performs semantic retrieval by:
    1. Embedding the query using the configured embedding client
    2. Querying the vector store for similar vectors
    3. Returning normalized RetrievalResult objects
    
    Design Principles Applied:
    - Pluggable: Accepts embedding_client and vector_store via dependency injection.
    - Config-Driven: Default top_k read from settings.retrieval.dense_top_k.
    - Observable: Accepts optional TraceContext for observability integration.
    - Fail-Fast: Validates inputs early with clear error messages.
    - Type-Safe: Returns standardized RetrievalResult objects.
    
    Attributes:
        embedding_client: The embedding provider for query vectorization.
        vector_store: The vector store for similarity search.
        default_top_k: Default number of results to return.
    
    Example:
        >>> from src.libs.embedding.embedding_factory import EmbeddingFactory
        >>> from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        >>> 
        >>> settings = Settings.load('config/settings.yaml')
        >>> embedding_client = EmbeddingFactory.create(settings)
        >>> vector_store = VectorStoreFactory.create(settings)
        >>> 
        >>> retriever = DenseRetriever(
        ...     settings=settings,
        ...     embedding_client=embedding_client,
        ...     vector_store=vector_store
        ... )
        >>> results = retriever.retrieve("What is RAG?", top_k=5)
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedding_client: Optional[BaseEmbedding] = None,
        vector_store: Optional[BaseVectorStore] = None,
        default_top_k: int = 10,
    ) -> None:
        """Initialize DenseRetriever with dependencies.
        
        Args:
            settings: Application settings. Used to extract default_top_k if not provided.
            embedding_client: Embedding provider for query vectorization.
                              Required for actual retrieval operations.
            vector_store: Vector store for similarity search.
                          Required for actual retrieval operations.
            default_top_k: Default number of results to return (default: 10).
                           Can be overridden from settings.retrieval.dense_top_k.
        
        Raises:
            ValueError: If embedding_client or vector_store is None when required.
        
        Note:
            Dependencies can be injected for testing (with mocks) or for
            production use (with real implementations from factories).
        """
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        
        # Extract default_top_k from settings if available
        self.default_top_k = default_top_k
        if settings is not None:
            retrieval_config = getattr(settings, 'retrieval', None)
            if retrieval_config is not None:
                self.default_top_k = getattr(
                    retrieval_config, 'dense_top_k', default_top_k
                )
        
        logger.info(
            f"DenseRetriever initialized with default_top_k={self.default_top_k}"
        )
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Retrieve semantically similar chunks for a query.
        
        Args:
            query: The search query string. Must not be empty.
            top_k: Maximum number of results to return. If None, uses default_top_k.
            filters: Optional metadata filters (e.g., {"collection": "api-docs"}).
            trace: Optional TraceContext for observability (reserved for Stage F).
        
        Returns:
            List of RetrievalResult objects, sorted by similarity (descending).
            Each result contains chunk_id, score, text, and metadata.
        
        Raises:
            ValueError: If query is empty or invalid.
            RuntimeError: If embedding_client or vector_store is not configured,
                          or if the retrieval operation fails.
        
        Example:
            >>> results = retriever.retrieve("How to configure Azure OpenAI?")
            >>> for result in results:
            ...     print(f"[{result.score:.2f}] {result.chunk_id}: {result.text[:50]}...")
        """
        # Validate inputs
        self._validate_query(query)
        self._validate_dependencies()
        
        # Use default top_k if not specified
        effective_top_k = top_k if top_k is not None else self.default_top_k
        
        logger.debug(f"Retrieving for query='{query[:50]}...', top_k={effective_top_k}")
        
        # Step 1: Embed the query
        try:
            query_vectors = self.embedding_client.embed([query], trace=trace)
            query_vector = query_vectors[0]
        except Exception as e:
            raise RuntimeError(
                f"Failed to embed query: {e}. "
                "Check embedding client configuration and connectivity."
            ) from e
        
        # Step 2: Query the vector store
        try:
            raw_results = self.vector_store.query(
                vector=query_vector,
                top_k=effective_top_k,
                filters=filters,
                trace=trace,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to query vector store: {e}. "
                "Check vector store configuration and data availability."
            ) from e
        
        # Step 3: Transform to RetrievalResult objects
        results = self._transform_results(raw_results)
        
        logger.debug(f"Retrieved {len(results)} results for query")
        return results
    
    def _validate_query(self, query: str) -> None:
        """Validate the query string.
        
        Args:
            query: Query string to validate.
        
        Raises:
            ValueError: If query is empty or not a string.
        """
        if not isinstance(query, str):
            raise ValueError(
                f"Query must be a string, got {type(query).__name__}"
            )
        if not query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
    
    def _validate_dependencies(self) -> None:
        """Validate that required dependencies are configured.
        
        Raises:
            RuntimeError: If embedding_client or vector_store is None.
        """
        if self.embedding_client is None:
            raise RuntimeError(
                "DenseRetriever requires an embedding_client. "
                "Provide one during initialization or via setter."
            )
        if self.vector_store is None:
            raise RuntimeError(
                "DenseRetriever requires a vector_store. "
                "Provide one during initialization or via setter."
            )
    
    def _transform_results(
        self,
        raw_results: List[Dict[str, Any]],
    ) -> List[RetrievalResult]:
        """Transform raw vector store results to RetrievalResult objects.
        
        Args:
            raw_results: Raw results from vector store query.
                         Each result should have: id, score, text, metadata.
        
        Returns:
            List of RetrievalResult objects.
        """
        results = []
        for raw in raw_results:
            try:
                result = RetrievalResult(
                    chunk_id=str(raw.get('id', '')),
                    score=float(raw.get('score', 0.0)),
                    text=str(raw.get('text', '')),
                    metadata=raw.get('metadata', {}),
                )
                results.append(result)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to transform result {raw.get('id', 'unknown')}: {e}. "
                    "Skipping this result."
                )
                continue
        
        return results


def create_dense_retriever(
    settings: Settings,
    embedding_client: Optional[BaseEmbedding] = None,
    vector_store: Optional[BaseVectorStore] = None,
) -> DenseRetriever:
    """Factory function to create a DenseRetriever with optional dependency injection.
    
    This function simplifies DenseRetriever creation by automatically creating
    dependencies from factories if not provided.
    
    Args:
        settings: Application settings.
        embedding_client: Optional pre-configured embedding client.
                          If None, created from EmbeddingFactory.
        vector_store: Optional pre-configured vector store.
                      If None, created from VectorStoreFactory.
    
    Returns:
        Configured DenseRetriever instance.
    
    Example:
        >>> settings = Settings.load('config/settings.yaml')
        >>> retriever = create_dense_retriever(settings)
    """
    # Lazy import to avoid circular dependencies
    if embedding_client is None:
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        embedding_client = EmbeddingFactory.create(settings)
    
    if vector_store is None:
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        vector_store = VectorStoreFactory.create(settings)
    
    return DenseRetriever(
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
