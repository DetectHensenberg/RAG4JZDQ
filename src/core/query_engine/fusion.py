"""Reciprocal Rank Fusion (RRF) for combining multiple retrieval results.

This module implements the RRF fusion algorithm that combines ranking lists from
Dense and Sparse retrievers into a unified ranking. RRF is a simple yet effective
rank aggregation method that doesn't require score normalization.

Reference:
    Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009).
    "Reciprocal rank fusion outperforms condorcet and individual rank learning methods."
    SIGIR '09.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.types import RetrievalResult

logger = logging.getLogger(__name__)


class RRFFusion:
    """Reciprocal Rank Fusion (RRF) for combining multiple ranking lists.
    
    RRF combines rankings from multiple sources using the formula:
        RRF_score(d) = Σ 1 / (k + rank(d))
    
    where:
        - d is a document (chunk)
        - k is a smoothing constant (typically 60)
        - rank(d) is the 1-based rank of document d in a ranking list
    
    Key Properties:
    - Deterministic: Same inputs always produce same output ordering
    - Score-agnostic: Uses only rank positions, not raw scores
    - No normalization needed: Works with heterogeneous score scales
    - Handles missing documents: Documents in only one list still contribute
    
    Design Principles Applied:
    - Config-Driven: k parameter configurable (default: 60)
    - Type-Safe: Returns standardized RetrievalResult objects
    - Deterministic: Stable sorting with tie-breaking on chunk_id
    - Observable: Logging for debugging fusion process
    
    Attributes:
        k: Smoothing constant for RRF formula (default: 60).
           Higher k gives more weight to lower-ranked documents.
    
    Example:
        >>> fusion = RRFFusion(k=60)
        >>> dense_results = [
        ...     RetrievalResult(chunk_id="a", score=0.9, text="...", metadata={}),
        ...     RetrievalResult(chunk_id="b", score=0.8, text="...", metadata={}),
        ... ]
        >>> sparse_results = [
        ...     RetrievalResult(chunk_id="b", score=5.2, text="...", metadata={}),
        ...     RetrievalResult(chunk_id="c", score=4.1, text="...", metadata={}),
        ... ]
        >>> fused = fusion.fuse([dense_results, sparse_results], top_k=5)
    """
    
    # Default smoothing constant as recommended in the original RRF paper
    DEFAULT_K = 60
    
    def __init__(self, k: int = DEFAULT_K) -> None:
        """Initialize RRF fusion with configurable smoothing constant.
        
        Args:
            k: Smoothing constant for RRF formula (default: 60).
               - Must be a positive integer
               - Higher values reduce the importance of rank differences
               - Common values: 60 (original paper), 20, 100
        
        Raises:
            ValueError: If k is not a positive integer.
        """
        if not isinstance(k, int) or k <= 0:
            raise ValueError(f"k must be a positive integer, got {k}")
        
        self.k = k
        logger.info(f"RRFFusion initialized with k={k}")
    
    def fuse(
        self,
        ranking_lists: List[List[RetrievalResult]],
        top_k: Optional[int] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Fuse multiple ranking lists using Reciprocal Rank Fusion.
        
        Args:
            ranking_lists: List of ranking lists, each containing RetrievalResult
                           objects sorted by relevance (descending).
                           Typically [dense_results, sparse_results].
            top_k: Maximum number of results to return. If None, returns all.
            trace: Optional TraceContext for observability (reserved for Stage F).
        
        Returns:
            List of RetrievalResult objects, sorted by fused RRF score (descending).
            The score field contains the RRF score, not the original retrieval score.
            Text and metadata are preserved from the first occurrence of each chunk.
        
        Raises:
            ValueError: If ranking_lists is empty.
        
        Note:
            - Documents appearing in multiple lists get contributions from all
            - Documents appearing in only one list still receive RRF score
            - Tie-breaking: When RRF scores are equal, sort by chunk_id for stability
        
        Example:
            >>> fusion = RRFFusion(k=60)
            >>> fused = fusion.fuse([dense_results, sparse_results], top_k=10)
            >>> for r in fused:
            ...     print(f"[RRF={r.score:.4f}] {r.chunk_id}")
        """
        if not ranking_lists:
            raise ValueError("ranking_lists cannot be empty")
        
        # Filter out empty lists
        non_empty_lists = [lst for lst in ranking_lists if lst]
        
        if not non_empty_lists:
            logger.debug("All ranking lists are empty, returning empty result")
            return []
        
        logger.debug(
            f"Fusing {len(non_empty_lists)} ranking lists with "
            f"sizes {[len(lst) for lst in non_empty_lists]}"
        )
        
        # Step 1: Calculate RRF scores for each unique chunk
        rrf_scores: Dict[str, float] = {}
        chunk_data: Dict[str, RetrievalResult] = {}  # Preserve text/metadata
        
        for list_idx, ranking_list in enumerate(non_empty_lists):
            for rank, result in enumerate(ranking_list, start=1):
                chunk_id = result.chunk_id
                
                # Calculate RRF contribution: 1 / (k + rank)
                rrf_contribution = 1.0 / (self.k + rank)
                
                # Accumulate scores
                if chunk_id not in rrf_scores:
                    rrf_scores[chunk_id] = 0.0
                    # Store first occurrence's data (text, metadata)
                    chunk_data[chunk_id] = result
                
                rrf_scores[chunk_id] += rrf_contribution
        
        logger.debug(f"Computed RRF scores for {len(rrf_scores)} unique chunks")
        
        # Step 2: Create fused results with RRF scores
        fused_results = []
        for chunk_id, rrf_score in rrf_scores.items():
            original = chunk_data[chunk_id]
            fused_results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=rrf_score,
                    text=original.text,
                    metadata=original.metadata.copy(),
                )
            )
        
        # Step 3: Sort by RRF score (descending), then by chunk_id for stability
        fused_results.sort(key=lambda r: (-r.score, r.chunk_id))
        
        # Step 4: Apply top_k limit if specified
        if top_k is not None and top_k > 0:
            fused_results = fused_results[:top_k]
        
        logger.debug(
            f"Fusion complete: {len(fused_results)} results "
            f"(top_k={top_k if top_k else 'all'})"
        )
        
        return fused_results
    
    def fuse_with_weights(
        self,
        ranking_lists: List[List[RetrievalResult]],
        weights: Optional[List[float]] = None,
        top_k: Optional[int] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Fuse multiple ranking lists with optional per-list weights.
        
        This is an extended version of fuse() that allows weighting different
        ranking sources. For example, giving more weight to dense retrieval
        for semantic queries, or more weight to sparse retrieval for keyword queries.
        
        Args:
            ranking_lists: List of ranking lists, each containing RetrievalResult objects.
            weights: Optional list of weights for each ranking list (default: uniform).
                     Must have same length as ranking_lists if provided.
                     Weights are multiplied with RRF contributions.
            top_k: Maximum number of results to return. If None, returns all.
            trace: Optional TraceContext for observability (reserved for Stage F).
        
        Returns:
            List of RetrievalResult objects, sorted by weighted RRF score (descending).
        
        Raises:
            ValueError: If ranking_lists is empty or weights length doesn't match.
        
        Example:
            >>> fusion = RRFFusion(k=60)
            >>> # Give 1.5x weight to dense results
            >>> fused = fusion.fuse_with_weights(
            ...     [dense_results, sparse_results],
            ...     weights=[1.5, 1.0],
            ...     top_k=10
            ... )
        """
        if not ranking_lists:
            raise ValueError("ranking_lists cannot be empty")
        
        # Default to uniform weights
        if weights is None:
            weights = [1.0] * len(ranking_lists)
        
        if len(weights) != len(ranking_lists):
            raise ValueError(
                f"weights length ({len(weights)}) must match "
                f"ranking_lists length ({len(ranking_lists)})"
            )
        
        # Validate weights
        for i, w in enumerate(weights):
            if not isinstance(w, (int, float)) or w < 0:
                raise ValueError(f"Weight at index {i} must be non-negative, got {w}")
        
        # Filter out empty lists (keep their weights aligned)
        filtered = [
            (lst, w) for lst, w in zip(ranking_lists, weights) if lst
        ]
        
        if not filtered:
            logger.debug("All ranking lists are empty, returning empty result")
            return []
        
        non_empty_lists, filtered_weights = zip(*filtered)
        
        logger.debug(
            f"Fusing {len(non_empty_lists)} ranking lists with "
            f"weights={list(filtered_weights)}"
        )
        
        # Calculate weighted RRF scores
        rrf_scores: Dict[str, float] = {}
        chunk_data: Dict[str, RetrievalResult] = {}
        
        for list_idx, (ranking_list, weight) in enumerate(zip(non_empty_lists, filtered_weights)):
            for rank, result in enumerate(ranking_list, start=1):
                chunk_id = result.chunk_id
                
                # Weighted RRF contribution
                rrf_contribution = weight * (1.0 / (self.k + rank))
                
                if chunk_id not in rrf_scores:
                    rrf_scores[chunk_id] = 0.0
                    chunk_data[chunk_id] = result
                
                rrf_scores[chunk_id] += rrf_contribution
        
        # Create and sort results
        fused_results = [
            RetrievalResult(
                chunk_id=chunk_id,
                score=rrf_score,
                text=chunk_data[chunk_id].text,
                metadata=chunk_data[chunk_id].metadata.copy(),
            )
            for chunk_id, rrf_score in rrf_scores.items()
        ]
        
        fused_results.sort(key=lambda r: (-r.score, r.chunk_id))
        
        if top_k is not None and top_k > 0:
            fused_results = fused_results[:top_k]
        
        return fused_results


def rrf_score(rank: int, k: int = RRFFusion.DEFAULT_K) -> float:
    """Calculate RRF score contribution for a single rank position.
    
    This is a utility function for calculating individual RRF contributions.
    
    Args:
        rank: 1-based rank position (1 = highest rank)
        k: Smoothing constant (default: 60)
    
    Returns:
        RRF score contribution: 1 / (k + rank)
    
    Raises:
        ValueError: If rank is not a positive integer or k is not positive.
    
    Example:
        >>> rrf_score(1, k=60)  # Top-ranked document
        0.01639344262295082
        >>> rrf_score(10, k=60)  # 10th-ranked document
        0.014285714285714285
    """
    if not isinstance(rank, int) or rank <= 0:
        raise ValueError(f"rank must be a positive integer, got {rank}")
    if not isinstance(k, int) or k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}")
    
    return 1.0 / (k + rank)
