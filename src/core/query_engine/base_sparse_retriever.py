"""Base class and protocol for Sparse Retrieval components."""

from __future__ import annotations
from typing import Protocol, List, Dict, Any, Optional
from src.core.types import RetrievalResult

class BaseSparseRetriever(Protocol):
    """Protocol defining the interface for all sparse retrievers (BM25, Tantivy, etc.)."""
    
    def retrieve(
        self,
        keywords: List[str],
        top_k: Optional[int] = None,
        collection: Optional[str] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Retrieve chunks matching the given keywords.
        
        Args:
            keywords: List of search terms.
            top_k: Number of results to return.
            collection: Target collection name.
            trace: Trace context for observability.
            
        Returns:
            List of RetrievalResult objects.
        """
        ...
