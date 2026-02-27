"""Abstract base class for Reranker providers.

This module defines the pluggable interface for reranker providers,
enabling seamless switching between reranking strategies (None, Cross-Encoder,
LLM-based) through configuration-driven instantiation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseReranker(ABC):
    """Abstract base class for reranker providers.
    
    All reranker implementations must inherit from this class and implement
    the rerank() method. This ensures a consistent interface across different
    reranking strategies.
    
    Design Principles Applied:
    - Pluggable: Subclasses can be swapped without changing upstream code.
    - Observable: Accepts optional TraceContext for observability integration.
    - Config-Driven: Instances are created via factory based on settings.
    - Fallback: Implementations should support safe degradation to original order.
    """
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Rerank candidate chunks for a given query.
        
        Args:
            query: The user query string.
            candidates: List of candidate records to rerank. Each item is a dict
                containing at least an identifier and any fields needed by the
                reranker implementation (e.g., text, score, metadata).
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Provider-specific parameters (top_k, timeout, etc.).
        
        Returns:
            A list of candidates in the reranked order. Implementations should
            preserve candidate objects and only change ordering unless explicitly
            documented.
        
        Raises:
            ValueError: If query or candidates are invalid.
            RuntimeError: If the reranker fails unexpectedly.
        """
        pass
    
    def validate_query(self, query: str) -> None:
        """Validate the query string.
        
        Args:
            query: Query string to validate.
        
        Raises:
            ValueError: If query is not a non-empty string.
        """
        if not isinstance(query, str):
            raise ValueError(f"Query must be a string, got {type(query).__name__}")
        if not query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
    
    def validate_candidates(self, candidates: List[Dict[str, Any]]) -> None:
        """Validate candidate list structure.
        
        Args:
            candidates: List of candidate records to validate.
        
        Raises:
            ValueError: If candidates list is empty or malformed.
        """
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a list of dicts")
        if not candidates:
            raise ValueError("Candidates list cannot be empty")
        for i, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ValueError(
                    f"Candidate at index {i} is not a dict (type: {type(candidate).__name__})"
                )


class NoneReranker(BaseReranker):
    """No-op reranker that preserves original order.
    
    This implementation is used when reranking is disabled or the provider is set
    to 'none'. It validates inputs and returns candidates unchanged.
    """
    
    def __init__(self, settings: Any = None, **kwargs: Any) -> None:
        self.settings = settings
        self.kwargs = kwargs
    
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Return candidates in original order.
        
        Args:
            query: Query string.
            candidates: Candidate list to return.
            trace: Optional TraceContext (unused).
            **kwargs: Ignored.
        
        Returns:
            A shallow copy of candidates preserving order.
        """
        self.validate_query(query)
        self.validate_candidates(candidates)
        return list(candidates)
