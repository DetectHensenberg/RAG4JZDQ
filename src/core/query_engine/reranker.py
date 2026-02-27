"""Core layer Reranker orchestrating libs.reranker backends with fallback support.

This module implements the CoreReranker class that:
1. Integrates with libs.reranker (LLM, CrossEncoder, None) via RerankerFactory
2. Provides graceful fallback when backend fails or times out
3. Converts RetrievalResult to/from reranker input/output format
4. Supports TraceContext for observability

Design Principles:
- Pluggable: Uses RerankerFactory to instantiate configured backend
- Config-Driven: Reads rerank settings from settings.yaml
- Graceful Fallback: Returns original order on backend failure
- Observable: TraceContext integration for debugging
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.core.types import RetrievalResult
from src.libs.reranker.base_reranker import BaseReranker, NoneReranker
from src.libs.reranker.reranker_factory import RerankerFactory

if TYPE_CHECKING:
    from src.core.settings import Settings

logger = logging.getLogger(__name__)


class RerankError(RuntimeError):
    """Raised when reranking fails."""


@dataclass
class RerankConfig:
    """Configuration for CoreReranker.
    
    Attributes:
        enabled: Whether reranking is enabled
        top_k: Number of results to return after reranking
        timeout: Timeout for reranker backend (seconds)
        fallback_on_error: Whether to return original order on error
    """
    enabled: bool = True
    top_k: int = 5
    timeout: float = 30.0
    fallback_on_error: bool = True


@dataclass
class RerankResult:
    """Result of a rerank operation.
    
    Attributes:
        results: Reranked list of RetrievalResults
        used_fallback: Whether fallback was used due to backend failure
        fallback_reason: Reason for fallback (if applicable)
        reranker_type: Type of reranker used ('llm', 'cross_encoder', 'none')
        original_order: Original results before reranking (for debugging)
    """
    results: List[RetrievalResult] = field(default_factory=list)
    used_fallback: bool = False
    fallback_reason: Optional[str] = None
    reranker_type: str = "none"
    original_order: Optional[List[RetrievalResult]] = None


class CoreReranker:
    """Core layer Reranker with fallback support.
    
    This class wraps libs.reranker implementations and provides:
    1. Type conversion between RetrievalResult and reranker dict format
    2. Graceful fallback when backend fails
    3. Configuration-driven backend selection
    4. TraceContext integration
    
    Design Principles Applied:
    - Pluggable: Backend via RerankerFactory
    - Config-Driven: All parameters from settings
    - Fallback: Returns original order on failure
    - Observable: TraceContext support
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings("config/settings.yaml")
        >>> reranker = CoreReranker(settings)
        >>> results = [RetrievalResult(chunk_id="1", score=0.8, text="...", metadata={})]
        >>> reranked = reranker.rerank("query", results)
        >>> print(reranked.results)
    """
    
    def __init__(
        self,
        settings: Settings,
        reranker: Optional[BaseReranker] = None,
        config: Optional[RerankConfig] = None,
    ) -> None:
        """Initialize CoreReranker.
        
        Args:
            settings: Application settings containing rerank configuration.
            reranker: Optional reranker backend. If None, creates via RerankerFactory.
            config: Optional RerankConfig. If None, extracts from settings.
        """
        self.settings = settings
        
        # Extract config from settings or use provided
        if config is not None:
            self.config = config
        else:
            self.config = self._extract_config(settings)
        
        # Initialize reranker backend
        if reranker is not None:
            self._reranker = reranker
        elif not self.config.enabled:
            self._reranker = NoneReranker(settings=settings)
        else:
            try:
                self._reranker = RerankerFactory.create(settings)
            except Exception as e:
                logger.warning(f"Failed to create reranker, using NoneReranker: {e}")
                self._reranker = NoneReranker(settings=settings)
        
        # Determine reranker type for result reporting
        self._reranker_type = self._get_reranker_type()
    
    def _extract_config(self, settings: Settings) -> RerankConfig:
        """Extract RerankConfig from settings.
        
        Args:
            settings: Application settings.
            
        Returns:
            RerankConfig with values from settings.
        """
        try:
            rerank_settings = settings.rerank
            return RerankConfig(
                enabled=bool(rerank_settings.enabled) if rerank_settings else False,
                top_k=int(rerank_settings.top_k) if rerank_settings and hasattr(rerank_settings, 'top_k') else 5,
                timeout=float(getattr(rerank_settings, 'timeout', 30.0)) if rerank_settings else 30.0,
                fallback_on_error=True,
            )
        except AttributeError:
            logger.warning("Missing rerank configuration, using defaults (disabled)")
            return RerankConfig(enabled=False)
    
    def _get_reranker_type(self) -> str:
        """Get the type name of the current reranker backend.
        
        Returns:
            String identifier for the reranker type.
        """
        class_name = self._reranker.__class__.__name__
        if "LLM" in class_name:
            return "llm"
        elif "CrossEncoder" in class_name:
            return "cross_encoder"
        elif "None" in class_name:
            return "none"
        else:
            return class_name.lower()
    
    def _results_to_candidates(self, results: List[RetrievalResult]) -> List[Dict[str, Any]]:
        """Convert RetrievalResults to reranker candidate format.
        
        Args:
            results: List of RetrievalResult objects.
            
        Returns:
            List of dicts suitable for reranker input.
        """
        candidates = []
        for result in results:
            candidates.append({
                "id": result.chunk_id,
                "text": result.text,
                "score": result.score,
                "metadata": result.metadata.copy(),
            })
        return candidates
    
    def _candidates_to_results(
        self,
        candidates: List[Dict[str, Any]],
        original_results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """Convert reranked candidates back to RetrievalResults.
        
        Args:
            candidates: Reranked candidates from reranker.
            original_results: Original results for reference.
            
        Returns:
            List of RetrievalResult in reranked order.
        """
        # Build lookup from original results
        id_to_original = {r.chunk_id: r for r in original_results}
        
        results = []
        for candidate in candidates:
            chunk_id = candidate["id"]
            
            # Get original result or build new one
            if chunk_id in id_to_original:
                original = id_to_original[chunk_id]
                # Create new result with updated score
                rerank_score = candidate.get("rerank_score", candidate.get("score", 0.0))
                results.append(RetrievalResult(
                    chunk_id=original.chunk_id,
                    score=rerank_score,
                    text=original.text,
                    metadata={
                        **original.metadata,
                        "original_score": original.score,
                        "rerank_score": rerank_score,
                        "reranked": True,
                    },
                ))
            else:
                # Candidate not in original - build from candidate data
                results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    score=candidate.get("rerank_score", candidate.get("score", 0.0)),
                    text=candidate.get("text", ""),
                    metadata=candidate.get("metadata", {}),
                ))
        
        return results
    
    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> RerankResult:
        """Rerank retrieval results using configured backend.
        
        Args:
            query: The user query string.
            results: List of RetrievalResult objects to rerank.
            top_k: Number of results to return. If None, uses config.top_k.
            trace: Optional TraceContext for observability.
            **kwargs: Additional parameters passed to reranker backend.
            
        Returns:
            RerankResult containing reranked results and metadata.
        """
        effective_top_k = top_k if top_k is not None else self.config.top_k
        
        # Early return for empty or single results
        if not results:
            return RerankResult(
                results=[],
                used_fallback=False,
                reranker_type=self._reranker_type,
            )
        
        if len(results) == 1:
            return RerankResult(
                results=results[:],
                used_fallback=False,
                reranker_type=self._reranker_type,
            )
        
        # If reranking disabled, return top_k results in original order
        if not self.config.enabled or isinstance(self._reranker, NoneReranker):
            return RerankResult(
                results=results[:effective_top_k],
                used_fallback=False,
                reranker_type="none",
                original_order=results[:],
            )
        
        # Convert to reranker input format
        candidates = self._results_to_candidates(results)
        
        # Attempt reranking
        try:
            logger.debug(f"Reranking {len(candidates)} candidates with {self._reranker_type}")
            _t0 = time.monotonic()
            reranked_candidates = self._reranker.rerank(
                query=query,
                candidates=candidates,
                trace=trace,
                **kwargs,
            )
            _elapsed = (time.monotonic() - _t0) * 1000.0
            
            # Convert back to RetrievalResult
            reranked_results = self._candidates_to_results(reranked_candidates, results)
            
            # Apply top_k limit
            final_results = reranked_results[:effective_top_k]
            
            logger.info(f"Reranking complete: {len(final_results)} results returned")
            
            if trace is not None:
                trace.record_stage("rerank", {
                    "method": self._reranker_type,
                    "provider": self._reranker_type,
                    "input_count": len(candidates),
                    "output_count": len(final_results),
                    "chunks": [
                        {
                            "chunk_id": r.chunk_id,
                            "score": round(r.score, 4),
                            "text": r.text or "",
                            "source": r.metadata.get("source_path", r.metadata.get("source", "")),
                        }
                        for r in final_results
                    ],
                }, elapsed_ms=_elapsed)
            
            return RerankResult(
                results=final_results,
                used_fallback=False,
                reranker_type=self._reranker_type,
                original_order=results[:],
            )
            
        except Exception as e:
            logger.warning(f"Reranking failed, using fallback: {e}")
            
            if self.config.fallback_on_error:
                # Return original order as fallback
                fallback_results = []
                for result in results[:effective_top_k]:
                    fallback_results.append(RetrievalResult(
                        chunk_id=result.chunk_id,
                        score=result.score,
                        text=result.text,
                        metadata={
                            **result.metadata,
                            "reranked": False,
                            "rerank_fallback": True,
                        },
                    ))
                
                return RerankResult(
                    results=fallback_results,
                    used_fallback=True,
                    fallback_reason=str(e),
                    reranker_type=self._reranker_type,
                    original_order=results[:],
                )
            else:
                raise RerankError(f"Reranking failed and fallback disabled: {e}") from e
    
    @property
    def reranker_type(self) -> str:
        """Get the type of the current reranker backend."""
        return self._reranker_type
    
    @property
    def is_enabled(self) -> bool:
        """Check if reranking is enabled."""
        return self.config.enabled and not isinstance(self._reranker, NoneReranker)


def create_core_reranker(
    settings: Settings,
    reranker: Optional[BaseReranker] = None,
) -> CoreReranker:
    """Factory function to create a CoreReranker instance.
    
    Args:
        settings: Application settings.
        reranker: Optional reranker backend override.
        
    Returns:
        Configured CoreReranker instance.
    """
    return CoreReranker(settings=settings, reranker=reranker)
