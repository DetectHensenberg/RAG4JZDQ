"""Hybrid Search Engine orchestrating Dense + Sparse retrieval with RRF Fusion.

This module implements the HybridSearch class that combines:
1. QueryProcessor: Preprocess queries and extract keywords/filters
2. DenseRetriever: Semantic search using embeddings
3. SparseRetriever: Keyword search using BM25
4. RRFFusion: Combine results using Reciprocal Rank Fusion

Design Principles:
- Graceful Degradation: If one retrieval path fails, fall back to the other
- Pluggable: All components injected via constructor for testability
- Observable: TraceContext integration for debugging and monitoring
- Config-Driven: Top-k and other parameters read from settings
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from src.core.types import ProcessedQuery, RetrievalResult
from src.core.query_engine.retrieval_cache import get_retrieval_cache, normalize_query

if TYPE_CHECKING:
    from src.core.query_engine.dense_retriever import DenseRetriever
    from src.core.query_engine.fusion import RRFFusion
    from src.core.query_engine.query_processor import QueryProcessor
    from src.core.query_engine.strategy_router import StrategyRouter
    from src.core.query_engine.sparse_retriever import SparseRetriever
    from src.core.settings import Settings
    from src.ingestion.storage.parent_store import ParentStore
    from src.ingestion.storage.graph_store import GraphStore

logger = logging.getLogger(__name__)


def _snapshot_results(
    results: Optional[List[RetrievalResult]],
) -> List[Dict[str, Any]]:
    """Create a serialisable snapshot of retrieval results for trace storage.

    Args:
        results: List of RetrievalResult objects.

    Returns:
        List of dicts with chunk_id, score, full text, source.
    """
    if not results:
        return []
    return [
        {
            "chunk_id": r.chunk_id,
            "score": round(r.score, 4),
            "text": r.text or "",
            "source": r.metadata.get("source_path", r.metadata.get("source", "")),
        }
        for r in results
    ]


@dataclass
class HybridSearchConfig:
    """Configuration for HybridSearch.
    
    Attributes:
        dense_top_k: Number of results from dense retrieval
        sparse_top_k: Number of results from sparse retrieval
        fusion_top_k: Final number of results after fusion
        enable_dense: Whether to use dense retrieval
        enable_sparse: Whether to use sparse retrieval
        parallel_retrieval: Whether to run retrievals in parallel
        metadata_filter_post: Apply metadata filters after fusion (fallback)
    """
    dense_top_k: int = 20
    sparse_top_k: int = 20
    fusion_top_k: int = 10
    enable_dense: bool = True
    enable_sparse: bool = True
    parallel_retrieval: bool = True
    metadata_filter_post: bool = True


@dataclass
class HybridSearchResult:
    """Result of a hybrid search operation.
    
    Attributes:
        results: Final ranked list of RetrievalResults
        dense_results: Results from dense retrieval (for debugging)
        sparse_results: Results from sparse retrieval (for debugging)
        dense_error: Error message if dense retrieval failed
        sparse_error: Error message if sparse retrieval failed
        used_fallback: Whether fallback mode was used
        processed_query: The processed query (for debugging)
    """
    results: List[RetrievalResult] = field(default_factory=list)
    dense_results: Optional[List[RetrievalResult]] = None
    sparse_results: Optional[List[RetrievalResult]] = None
    dense_error: Optional[str] = None
    sparse_error: Optional[str] = None
    used_fallback: bool = False
    processed_query: Optional[ProcessedQuery] = None


class HybridSearch:
    """Hybrid Search Engine combining Dense and Sparse retrieval.
    
    This class orchestrates the complete hybrid search flow:
    1. Query Processing: Extract keywords and filters from raw query
    2. Parallel Retrieval: Run Dense and Sparse retrievers concurrently
    3. Fusion: Combine results using RRF algorithm
    4. Post-Filtering: Apply metadata filters if specified
    
    Design Principles Applied:
    - Graceful Degradation: If one path fails, use results from the other
    - Pluggable: All components via dependency injection
    - Observable: TraceContext support for debugging
    - Config-Driven: All parameters from settings
    
    Example:
        >>> # Initialize components
        >>> query_processor = QueryProcessor()
        >>> dense_retriever = DenseRetriever(settings, embedding_client, vector_store)
        >>> sparse_retriever = SparseRetriever(settings, bm25_indexer, vector_store)
        >>> fusion = RRFFusion(k=60)
        >>> 
        >>> # Create HybridSearch
        >>> hybrid = HybridSearch(
        ...     settings=settings,
        ...     query_processor=query_processor,
        ...     dense_retriever=dense_retriever,
        ...     sparse_retriever=sparse_retriever,
        ...     fusion=fusion
        ... )
        >>> 
        >>> # Search
        >>> results = hybrid.search("如何配置 Azure OpenAI？", top_k=10)
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        query_processor: Optional[QueryProcessor] = None,
        dense_retriever: Optional[DenseRetriever] = None,
        sparse_retriever: Optional[SparseRetriever] = None,
        fusion: Optional[RRFFusion] = None,
        config: Optional[HybridSearchConfig] = None,
        reranker: Optional[Any] = None,
    ) -> None:
        """Initialize HybridSearch with components.
        
        Args:
            settings: Application settings for extracting configuration.
            query_processor: QueryProcessor for preprocessing queries.
            dense_retriever: DenseRetriever for semantic search.
            sparse_retriever: SparseRetriever for keyword search.
            fusion: RRFFusion for combining results.
            config: Optional HybridSearchConfig. If not provided, extracted from settings.
            reranker: Optional cross-encoder reranker with .rerank(query, results) method.
        
        Note:
            At least one of dense_retriever or sparse_retriever must be provided
            for search to function. The search will gracefully degrade if one
            is unavailable or fails.
        """
        self.query_processor = query_processor
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.fusion = fusion
        self.reranker = reranker
        self.parent_store: Optional[Any] = None  # ParentStore, set externally for Parent Retrieval
        self.graph_store: Optional[Any] = None   # GraphStore, set externally for GraphRAG
        self.strategy_router: Optional[Any] = None  # StrategyRouter, set externally
        
        # Extract config from settings or use provided/default
        self.config = config or self._extract_config(settings)
        
        logger.info(
            f"HybridSearch initialized: dense={self.dense_retriever is not None}, "
            f"sparse={self.sparse_retriever is not None}, "
            f"reranker={self.reranker is not None}, "
            f"config={self.config}"
        )
    
    def _extract_config(self, settings: Optional[Settings]) -> HybridSearchConfig:
        """Extract HybridSearchConfig from Settings.
        
        Args:
            settings: Application settings object.
            
        Returns:
            HybridSearchConfig with values from settings or defaults.
        """
        if settings is None:
            return HybridSearchConfig()
        
        retrieval_config = getattr(settings, 'retrieval', None)
        if retrieval_config is None:
            return HybridSearchConfig()
        
        return HybridSearchConfig(
            dense_top_k=getattr(retrieval_config, 'dense_top_k', 20),
            sparse_top_k=getattr(retrieval_config, 'sparse_top_k', 20),
            fusion_top_k=getattr(retrieval_config, 'fusion_top_k', 10),
            enable_dense=True,
            enable_sparse=True,
            parallel_retrieval=True,
            metadata_filter_post=True,
        )
    
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
        return_details: bool = False,
    ) -> List[RetrievalResult] | HybridSearchResult:
        """Perform hybrid search combining Dense and Sparse retrieval.
        
        Args:
            query: The search query string.
            top_k: Maximum number of results to return. If None, uses config.fusion_top_k.
            filters: Optional metadata filters (e.g., {"collection": "docs"}).
            trace: Optional TraceContext for observability.
            return_details: If True, return HybridSearchResult with debug info.
        
        Returns:
            If return_details=False: List of RetrievalResult sorted by relevance.
            If return_details=True: HybridSearchResult with full details.
        
        Raises:
            ValueError: If query is empty or invalid.
            RuntimeError: If both retrievers fail or are unavailable.
        
        Example:
            >>> results = hybrid.search("Azure configuration", top_k=5)
            >>> for r in results:
            ...     print(f"[{r.score:.4f}] {r.chunk_id}: {r.text[:50]}...")
        """
        # Validate query
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or whitespace-only")
        
        effective_top_k = top_k if top_k is not None else self.config.fusion_top_k
        # When reranker is available, retrieve more candidates for it to rerank
        fusion_top_k = effective_top_k * 3 if self.reranker is not None else effective_top_k
        
        logger.debug(f"HybridSearch: query='{query[:50]}...', top_k={effective_top_k}, fusion_k={fusion_top_k}")
        
        # Step 0: Check retrieval cache (Level 2 cache - skips embedding + search)
        retrieval_cache = get_retrieval_cache()
        cached = retrieval_cache.get(query)
        
        if cached is not None and not filters:  # Don't use cache if filters specified
            logger.debug("Retrieval cache hit - skipping embedding and search")
            # Reconstruct RetrievalResult from cache
            cached_results = [
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=cached.scores.get(chunk_id, 0.0),
                    text=cached.texts.get(chunk_id, ""),
                    metadata={**cached.metadata.get(chunk_id, {}), "cache_hit": True},
                )
                for chunk_id in cached.chunk_ids
            ]
            
            # Still apply reranking if available (reranker has its own cache)
            if self.reranker is not None and cached_results:
                rerank_result = self.reranker.rerank(query, cached_results, top_k=effective_top_k * 2)
                cached_results = rerank_result.results
            
            # Apply source diversification and limits
            cached_results = self._diversify_by_source(cached_results, max_per_source=2)
            final_results = cached_results[:effective_top_k]
            
            if return_details:
                return HybridSearchResult(
                    results=final_results,
                    dense_results=None,
                    sparse_results=None,
                    used_fallback=False,
                    processed_query=None,
                )
            return final_results
        
        # Step 1: Process query
        _t0 = time.monotonic()
        processed_query = self._process_query(query)
        _elapsed = (time.monotonic() - _t0) * 1000.0
        if trace is not None:
            trace.record_stage("query_processing", {
                "method": "query_processor",
                "original_query": query,
                "keywords": processed_query.keywords,
            }, elapsed_ms=_elapsed)
        
        # Merge explicit filters with query-extracted filters
        merged_filters = self._merge_filters(processed_query.filters, filters)
        
        # Step 2: Run retrievals
        dense_results, sparse_results, dense_error, sparse_error = self._run_retrievals(
            processed_query=processed_query,
            filters=merged_filters,
            trace=trace,
        )
        
        # Step 3: Handle fallback scenarios
        used_fallback = False
        if dense_error and sparse_error:
            # Both failed - raise error
            raise RuntimeError(
                f"Both retrieval paths failed. "
                f"Dense error: {dense_error}. Sparse error: {sparse_error}"
            )
        elif dense_error:
            # Dense failed, use sparse only
            logger.warning(f"Dense retrieval failed, using sparse only: {dense_error}")
            used_fallback = True
            fused_results = sparse_results or []
        elif sparse_error:
            # Sparse failed, use dense only
            logger.warning(f"Sparse retrieval failed, using dense only: {sparse_error}")
            used_fallback = True
            fused_results = dense_results or []
        elif not dense_results and not sparse_results:
            # Both succeeded but returned empty
            fused_results = []
        else:
            # Step 4: Fuse results
            fused_results = self._fuse_results(
                dense_results=dense_results or [],
                sparse_results=sparse_results or [],
                weights=processed_query.intent_weights,
                top_k=fusion_top_k,
                trace=trace,
            )
        
        # Step 5: Apply post-fusion metadata filters (if any)
        if merged_filters and self.config.metadata_filter_post:
            fused_results = self._apply_metadata_filters(fused_results, merged_filters)
        
        # Step 5.3: Filename boost — nudge chunks whose source filename
        #           contains query keywords so they enter the reranker pool.
        fused_results = self._apply_filename_boost(fused_results, query)
        
        # Snapshot all candidates before reranking trims the list
        all_candidates = list(fused_results)
        
        # Step 5.5: Rerank with cross-encoder if available
        if self.reranker is not None and fused_results:
            # Request 2x top_k so source diversification has enough candidates
            rerank_top_k = effective_top_k * 2
            rerank_result = self.reranker.rerank(query, fused_results, top_k=rerank_top_k)
            fused_results = rerank_result.results
            logger.info(
                f"Reranked {len(fused_results)} results "
                f"(fallback={rerank_result.used_fallback}, type={rerank_result.reranker_type})"
            )
        
        # Step 5.7: Source diversification — limit chunks per source document
        #           so results cover different files, not just one big doc.
        fused_results = self._diversify_by_source(
            fused_results, max_per_source=2,
        )
        
        # Step 5.9: Title match guarantee — if a document whose filename
        #           matches the query isn't in results yet, inject its best chunk.
        fused_results = self._inject_title_matches(
            fused_results, all_candidates, query,
        )
        
        # Step 6: Limit to top_k
        final_results = fused_results[:effective_top_k]
        
        # Step 7: Store in retrieval cache (L2) if no filters were applied
        if not filters and final_results:
            try:
                chunk_ids = [r.chunk_id for r in final_results]
                scores = {r.chunk_id: r.score for r in final_results}
                texts = {r.chunk_id: r.text for r in final_results}
                metadata = {r.chunk_id: r.metadata for r in final_results}
                retrieval_cache.put(query, chunk_ids, scores, texts, metadata)
                logger.debug(f"Stored {len(final_results)} results in retrieval cache")
            except Exception as e:
                logger.warning(f"Failed to store in retrieval cache: {e}")
        
        logger.debug(f"HybridSearch: returning {len(final_results)} results")

        if self.strategy_router is not None:
            routing = self.strategy_router.route(query, trace=trace)
            if routing.use_parent_retrieval and self.parent_store is not None:
                final_results = self._expand_with_parents(final_results)
            if routing.use_graph_rag and self.graph_store is not None:
                final_results = self._expand_with_graph(final_results, query)

        if return_details:
            return HybridSearchResult(
                results=final_results,
                dense_results=dense_results,
                sparse_results=sparse_results,
                dense_error=dense_error,
                sparse_error=sparse_error,
                used_fallback=used_fallback,
                processed_query=processed_query,
            )
        
        return final_results
    
    def _process_query(self, query: str) -> ProcessedQuery:
        """Process raw query using QueryProcessor.
        
        Args:
            query: Raw query string.
            
        Returns:
            ProcessedQuery with keywords and filters.
        """
        if self.query_processor is None:
            # Fallback: create basic ProcessedQuery
            logger.warning("No QueryProcessor configured, using basic tokenization")
            keywords = query.split()
            return ProcessedQuery(
                original_query=query,
                keywords=keywords,
                filters={},
            )
        
        return self.query_processor.process(query)
    
    def _merge_filters(
        self,
        query_filters: Dict[str, Any],
        explicit_filters: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge query-extracted filters with explicit filters.
        
        Explicit filters take precedence over query-extracted filters.
        
        Args:
            query_filters: Filters extracted from query by QueryProcessor.
            explicit_filters: Filters passed explicitly to search().
            
        Returns:
            Merged filter dictionary.
        """
        merged = query_filters.copy() if query_filters else {}
        if explicit_filters:
            merged.update(explicit_filters)
        return merged
    
    def _run_retrievals(
        self,
        processed_query: ProcessedQuery,
        filters: Optional[Dict[str, Any]],
        trace: Optional[Any],
    ) -> Tuple[
        Optional[List[RetrievalResult]],
        Optional[List[RetrievalResult]],
        Optional[str],
        Optional[str],
    ]:
        """Run Dense and Sparse retrievals.
        
        Runs in parallel if configured, otherwise sequentially.
        
        Args:
            processed_query: The processed query with keywords.
            filters: Merged filters to apply.
            trace: Optional TraceContext.
            
        Returns:
            Tuple of (dense_results, sparse_results, dense_error, sparse_error).
        """
        dense_results: Optional[List[RetrievalResult]] = None
        sparse_results: Optional[List[RetrievalResult]] = None
        dense_error: Optional[str] = None
        sparse_error: Optional[str] = None
        
        # Determine what to run
        run_dense = (
            self.config.enable_dense 
            and self.dense_retriever is not None
        )
        run_sparse = (
            self.config.enable_sparse 
            and self.sparse_retriever is not None
            and processed_query.keywords  # Need keywords for sparse
        )
        
        if not run_dense and not run_sparse:
            # Nothing to run
            if self.dense_retriever is None and self.sparse_retriever is None:
                dense_error = "No retriever configured"
                sparse_error = "No retriever configured"
            return dense_results, sparse_results, dense_error, sparse_error
        
        if self.config.parallel_retrieval and run_dense and run_sparse:
            # Run in parallel
            dense_results, sparse_results, dense_error, sparse_error = (
                self._run_parallel_retrievals(processed_query, filters, trace)
            )
        else:
            # Run sequentially
            if run_dense:
                dense_results, dense_error = self._run_dense_retrieval(
                    processed_query.original_query, filters, trace
                )
            
            if run_sparse:
                sparse_results, sparse_error = self._run_sparse_retrieval(
                    processed_query.keywords, filters, trace
                )
        
        return dense_results, sparse_results, dense_error, sparse_error
    
    def _run_parallel_retrievals(
        self,
        processed_query: ProcessedQuery,
        filters: Optional[Dict[str, Any]],
        trace: Optional[Any],
    ) -> Tuple[
        Optional[List[RetrievalResult]],
        Optional[List[RetrievalResult]],
        Optional[str],
        Optional[str],
    ]:
        """Run Dense and Sparse retrievals in parallel using ThreadPoolExecutor.
        
        Args:
            processed_query: The processed query.
            filters: Filters to apply.
            trace: Optional TraceContext.
            
        Returns:
            Tuple of (dense_results, sparse_results, dense_error, sparse_error).
        """
        dense_results: Optional[List[RetrievalResult]] = None
        sparse_results: Optional[List[RetrievalResult]] = None
        dense_error: Optional[str] = None
        sparse_error: Optional[str] = None
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            # Submit dense retrieval
            futures['dense'] = executor.submit(
                self._run_dense_retrieval,
                processed_query.original_query,
                filters,
                trace,
            )
            
            # Submit sparse retrieval
            futures['sparse'] = executor.submit(
                self._run_sparse_retrieval,
                processed_query.keywords,
                filters,
                trace,
            )
            
            # Collect results
            for name, future in futures.items():
                try:
                    results, error = future.result(timeout=30)
                    if name == 'dense':
                        dense_results = results
                        dense_error = error
                    else:
                        sparse_results = results
                        sparse_error = error
                except Exception as e:
                    error_msg = f"{name} retrieval failed with exception: {e}"
                    logger.error(error_msg)
                    if name == 'dense':
                        dense_error = error_msg
                    else:
                        sparse_error = error_msg
        
        return dense_results, sparse_results, dense_error, sparse_error
    
    def _run_dense_retrieval(
        self,
        query: str,
        filters: Optional[Dict[str, Any]],
        trace: Optional[Any],
    ) -> Tuple[Optional[List[RetrievalResult]], Optional[str]]:
        """Run dense retrieval with error handling.
        
        Args:
            query: Original query string.
            filters: Filters to apply.
            trace: Optional TraceContext.
            
        Returns:
            Tuple of (results, error). If successful, error is None.
        """
        if self.dense_retriever is None:
            return None, "Dense retriever not configured"
        
        try:
            _t0 = time.monotonic()
            results = self.dense_retriever.retrieve(
                query=query,
                top_k=self.config.dense_top_k,
                filters=filters,
                trace=trace,
            )
            _elapsed = (time.monotonic() - _t0) * 1000.0
            if trace is not None:
                trace.record_stage("dense_retrieval", {
                    "method": "dense",
                    "provider": getattr(self.dense_retriever, 'provider_name', 'unknown'),
                    "top_k": self.config.dense_top_k,
                    "result_count": len(results) if results else 0,
                    "chunks": _snapshot_results(results),
                }, elapsed_ms=_elapsed)
            return results, None
        except Exception as e:
            error_msg = f"Dense retrieval error: {e}"
            logger.error(error_msg)
            if trace is not None:
                trace.record_stage("dense_retrieval", {
                    "method": "dense",
                    "error": error_msg,
                    "result_count": 0,
                })
            return None, error_msg
    
    def _run_sparse_retrieval(
        self,
        keywords: List[str],
        filters: Optional[Dict[str, Any]],
        trace: Optional[Any],
    ) -> Tuple[Optional[List[RetrievalResult]], Optional[str]]:
        """Run sparse retrieval with error handling.
        
        Args:
            keywords: List of keywords from QueryProcessor.
            filters: Filters to apply.
            trace: Optional TraceContext.
            
        Returns:
            Tuple of (results, error). If successful, error is None.
        """
        if self.sparse_retriever is None:
            return None, "Sparse retriever not configured"
        
        if not keywords:
            return [], None  # No keywords, return empty (not an error)
        
        try:
            # Extract collection from filters if present
            collection = filters.get('collection') if filters else None
            
            _t0 = time.monotonic()
            results = self.sparse_retriever.retrieve(
                keywords=keywords,
                top_k=self.config.sparse_top_k,
                collection=collection,
                trace=trace,
            )
            _elapsed = (time.monotonic() - _t0) * 1000.0
            if trace is not None:
                trace.record_stage("sparse_retrieval", {
                    "method": "bm25",
                    "keyword_count": len(keywords),
                    "top_k": self.config.sparse_top_k,
                    "result_count": len(results) if results else 0,
                    "chunks": _snapshot_results(results),
                }, elapsed_ms=_elapsed)
            return results, None
        except Exception as e:
            error_msg = f"Sparse retrieval error: {e}"
            logger.error(error_msg)
            return None, error_msg
    
    def _fuse_results(
        self,
        dense_results: List[RetrievalResult],
        sparse_results: List[RetrievalResult],
        top_k: int,
        weights: Optional[List[float]] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Fuse Dense and Sparse results using RRF.
        
        Args:
            dense_results: Results from dense retrieval.
            sparse_results: Results from sparse retrieval.
            top_k: Number of results to return after fusion.
            weights: Optional weights for [dense, sparse].
            trace: Optional TraceContext.
            
        Returns:
            Fused and ranked list of RetrievalResults.
        """
        if self.fusion is None:
            # Fallback: interleave results (simple round-robin)
            logger.warning("No fusion configured, using simple interleave")
            return self._interleave_results(dense_results, sparse_results, top_k)
        
        # Build ranking lists for RRF
        ranking_lists = []
        if dense_results:
            ranking_lists.append(dense_results)
        if sparse_results:
            ranking_lists.append(sparse_results)
        
        if not ranking_lists:
            return []
        
        if len(ranking_lists) == 1:
            # Only one source, no fusion needed
            return ranking_lists[0][:top_k]
        
        _t0 = time.monotonic()
        fused = self.fusion.fuse_with_weights(
            ranking_lists=ranking_lists,
            weights=weights,
            top_k=top_k,
            trace=trace,
        )
        _elapsed = (time.monotonic() - _t0) * 1000.0
        if trace is not None:
            trace.record_stage("fusion", {
                "method": "rrf",
                "input_lists": len(ranking_lists),
                "top_k": top_k,
                "result_count": len(fused),
                "chunks": _snapshot_results(fused),
            }, elapsed_ms=_elapsed)
        return fused
    
    def _interleave_results(
        self,
        dense_results: List[RetrievalResult],
        sparse_results: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        """Simple interleave fallback when no fusion is configured.
        
        Args:
            dense_results: Results from dense retrieval.
            sparse_results: Results from sparse retrieval.
            top_k: Maximum results to return.
            
        Returns:
            Interleaved results, deduped by chunk_id.
        """
        seen_ids = set()
        interleaved = []
        
        d_idx, s_idx = 0, 0
        while len(interleaved) < top_k and (d_idx < len(dense_results) or s_idx < len(sparse_results)):
            # Alternate between dense and sparse
            if d_idx < len(dense_results):
                r = dense_results[d_idx]
                d_idx += 1
                if r.chunk_id not in seen_ids:
                    seen_ids.add(r.chunk_id)
                    interleaved.append(r)
            
            if len(interleaved) >= top_k:
                break
            
            if s_idx < len(sparse_results):
                r = sparse_results[s_idx]
                s_idx += 1
                if r.chunk_id not in seen_ids:
                    seen_ids.add(r.chunk_id)
                    interleaved.append(r)
        
        return interleaved
    
    def _inject_title_matches(
        self,
        results: List[RetrievalResult],
        all_candidates: List[RetrievalResult],
        query: str,
    ) -> List[RetrievalResult]:
        """Guarantee that documents whose filename matches the query appear.

        If a candidate's source filename contains query keywords but no chunk
        from that source is already in ``results``, inject the highest-scored
        chunk from ``all_candidates``.

        Args:
            results: Current result list (post-diversification).
            all_candidates: Full candidate pool (pre-rerank).
            query: Original user query.

        Returns:
            Results with title-matching chunks injected (appended at end).
        """
        if not all_candidates or not query:
            return results

        keywords = [w for w in query.strip().split() if len(w) >= 2]
        if not keywords:
            keywords = [query.strip()]

        # Sources already in results
        existing_sources = {r.metadata.get("source_path", "") for r in results}

        # Find title-matching candidates NOT in results
        injected = []
        seen_sources: set[str] = set()
        for r in all_candidates:
            source = r.metadata.get("source_path", "")
            if source in existing_sources or source in seen_sources:
                continue
            fname = source.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if source else ""
            stem = fname.rsplit(".", 1)[0] if "." in fname else fname
            if any(kw in stem for kw in keywords):
                injected.append(r)
                seen_sources.add(source)

        if injected:
            sources = [r.metadata.get("source_path", "").rsplit("\\", 1)[-1] for r in injected]
            logger.info(f"Title match guarantee: injected {len(injected)} chunk(s) from {sources}")

        return list(results) + injected

    def _diversify_by_source(
        self,
        results: List[RetrievalResult],
        max_per_source: int = 3,
    ) -> List[RetrievalResult]:
        """Limit chunks per source document to ensure result diversity.

        Iterates through results in score order, keeping at most
        ``max_per_source`` chunks from each source file.

        Args:
            results: Scored results (descending by score).
            max_per_source: Maximum chunks to keep per source document.

        Returns:
            Diversified results preserving original score order.
        """
        if not results or max_per_source <= 0:
            return results

        source_counts: Dict[str, int] = {}
        diversified: List[RetrievalResult] = []

        for r in results:
            source = r.metadata.get("source_path", "")
            count = source_counts.get(source, 0)
            if count < max_per_source:
                diversified.append(r)
                source_counts[source] = count + 1

        if len(diversified) < len(results):
            logger.debug(
                f"Source diversification: {len(results)} -> {len(diversified)} "
                f"(max {max_per_source}/source)"
            )

        return diversified

    def _apply_filename_boost(
        self,
        results: List[RetrievalResult],
        query: str,
        boost_factor: float = 1.5,
    ) -> List[RetrievalResult]:
        """Boost scores for chunks whose source filename contains query keywords.

        Ensures documents whose title directly matches the query topic rank
        higher and enter the reranker candidate pool.

        Args:
            results: Fused results to boost.
            query: Original user query string.
            boost_factor: Score multiplier for matching chunks (default: 1.5).

        Returns:
            Re-sorted results with filename-matching chunks boosted.
        """
        if not results or not query:
            return results

        # Build keyword set: split query into 2+ char segments
        keywords = [w for w in query.strip().split() if len(w) >= 2]
        if not keywords:
            keywords = [query.strip()]

        boosted = []
        boosted_count = 0
        for r in results:
            source = r.metadata.get("source_path", "")
            filename = source.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if source else ""
            # Strip extension for matching
            fname_stem = filename.rsplit(".", 1)[0] if "." in filename else filename

            matched = any(kw in fname_stem for kw in keywords)
            if matched:
                boosted.append(RetrievalResult(
                    chunk_id=r.chunk_id,
                    score=r.score * boost_factor,
                    text=r.text,
                    metadata={**r.metadata, "filename_boosted": True},
                ))
                boosted_count += 1
            else:
                boosted.append(r)

        if boosted_count > 0:
            boosted.sort(key=lambda x: (-x.score, x.chunk_id))
            logger.info(f"Filename boost: {boosted_count} chunks boosted for query '{query[:30]}'")

        return boosted

    def _apply_metadata_filters(
        self,
        results: List[RetrievalResult],
        filters: Dict[str, Any],
    ) -> List[RetrievalResult]:
        """Apply metadata filters to results (post-fusion fallback).
        
        This is a backup filter mechanism for cases where the underlying
        storage doesn't fully support the filter syntax.
        
        Args:
            results: Results to filter.
            filters: Filter conditions to apply.
            
        Returns:
            Filtered results.
        """
        if not filters:
            return results
        
        filtered = []
        for result in results:
            if self._matches_filters(result.metadata, filters):
                filtered.append(result)
        
        return filtered
    
    def _matches_filters(
        self,
        metadata: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> bool:
        """Check if metadata matches all filter conditions.
        
        Args:
            metadata: Result metadata.
            filters: Filter conditions.
            
        Returns:
            True if all filters match, False otherwise.
        """
        for key, value in filters.items():
            if key == "collection":
                # Collection might be in different metadata keys
                meta_collection = (
                    metadata.get("collection") 
                    or metadata.get("source_collection")
                )
                if meta_collection != value:
                    return False
            elif key == "doc_type":
                if metadata.get("doc_type") != value:
                    return False
            elif key == "tags":
                # Tags is a list - check intersection
                meta_tags = metadata.get("tags", [])
                if not isinstance(value, list):
                    value = [value]
                if not set(meta_tags) & set(value):
                    return False
            elif key == "source_path":
                # Partial match for path
                source = metadata.get("source_path", "")
                if value not in source:
                    return False
            else:
                # Generic exact match
                if metadata.get(key) != value:
                    return False
        
        return True


def create_hybrid_search(
    settings: Optional[Settings] = None,
    query_processor: Optional[QueryProcessor] = None,
    dense_retriever: Optional[DenseRetriever] = None,
    sparse_retriever: Optional[SparseRetriever] = None,
    fusion: Optional[RRFFusion] = None,
) -> HybridSearch:
    """Factory function to create HybridSearch with default components.
    
    This is a convenience function that creates a HybridSearch with
    default RRFFusion if not provided.
    
    Args:
        settings: Application settings.
        query_processor: QueryProcessor instance.
        dense_retriever: DenseRetriever instance.
        sparse_retriever: SparseRetriever instance.
        fusion: RRFFusion instance. If None, creates default with k=60.
        
    Returns:
        Configured HybridSearch instance.
    
    Example:
        >>> hybrid = create_hybrid_search(
        ...     settings=settings,
        ...     query_processor=QueryProcessor(),
        ...     dense_retriever=dense_retriever,
        ...     sparse_retriever=sparse_retriever,
        ... )
    """
    # Create default fusion if not provided
    if fusion is None:
        from src.core.query_engine.fusion import RRFFusion
        rrf_k = 60
        if settings is not None:
            retrieval_config = getattr(settings, 'retrieval', None)
            if retrieval_config is not None:
                rrf_k = getattr(retrieval_config, 'rrf_k', 60)
        fusion = RRFFusion(k=rrf_k)
    
    return HybridSearch(
        settings=settings,
        query_processor=query_processor,
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        fusion=fusion,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Context Expansion Methods (Parent Retrieval + GraphRAG)
# These are added as top-level helpers called by HybridSearch.search()
# ─────────────────────────────────────────────────────────────────────────────

def _expand_results_with_parents(
    results: List[RetrievalResult],
    parent_store: Any,
) -> List[RetrievalResult]:
    """Replace child chunk text with parent chunk text for context expansion.
    
    For each result that has a 'parent_id' in metadata, fetches the parent text
    from ParentStore and replaces the result text to provide broader context.
    
    Args:
        results: List of retrieval results (may include child chunks).
        parent_store: ParentStore instance for fetching parent texts.
        
    Returns:
        Updated results list with parent texts where available.
    """
    parent_ids = [r.metadata.get("parent_id") for r in results if r.metadata.get("parent_id")]
    if not parent_ids:
        return results
    
    try:
        parent_texts = parent_store.get_parent_texts(parent_ids)
    except Exception as e:
        logger.warning(f"Parent store fetch failed: {e}")
        return results
    
    expanded = []
    for r in results:
        pid = r.metadata.get("parent_id")
        if pid and pid in parent_texts:
            expanded.append(RetrievalResult(
                chunk_id=r.chunk_id,
                score=r.score,
                text=parent_texts[pid],
                metadata={**r.metadata, "context_expanded": True, "original_text_len": len(r.text)},
            ))
        else:
            expanded.append(r)
    
    logger.debug(f"Parent expansion: {sum(1 for r in expanded if r.metadata.get('context_expanded'))} results expanded")
    return expanded


def _expand_results_with_graph(
    results: List[RetrievalResult],
    query: str,
    graph_store: Any,
    max_rels_per_result: int = 3,
) -> List[RetrievalResult]:
    """Append graph relationship context to result texts.
    
    For each result, extracts entity-like terms from the query and searches
    the GraphStore for 1-hop neighbors. Appends found relationships as
    additional context to the result text.
    
    Args:
        results: List of retrieval results.
        query: Original query string for entity extraction.
        graph_store: GraphStore instance for graph lookup.
        max_rels_per_result: Maximum graph relations to append per result.
        
    Returns:
        Results with graph context appended to text where relevant.
    """
    import re
    # Extract candidate entity names from query (capitalized words and CJK terms)
    query_terms = list(set(re.findall(r'\b[A-Z][a-zA-Z]+\b|\b\w{2,}\b', query)))[:5]
    
    if not query_terms:
        return results
    
    graph_context_parts = []
    for term in query_terms:
        try:
            neighbors = graph_store.get_neighbors(term, max_hops=1)
            for rel in neighbors[:max_rels_per_result]:
                graph_context_parts.append(
                    f"[Graph] {rel['from']} -[{rel['relation']}]-> {rel['to']}: {rel.get('to_description', '')}"
                )
        except Exception:
            continue
    
    if not graph_context_parts:
        return results
    
    graph_context = "\n".join(graph_context_parts[:5])  # Limit total graph context
    expanded = []
    for r in results:
        enhanced_text = r.text + "\n\n---\n" + graph_context
        expanded.append(RetrievalResult(
            chunk_id=r.chunk_id,
            score=r.score,
            text=enhanced_text,
            metadata={**r.metadata, "graph_context_appended": True},
        ))
    
    logger.debug(f"GraphRAG: appended {len(graph_context_parts)} relations to {len(expanded)} results")
    return expanded


# Bind as instance methods to HybridSearch
def _hs_expand_with_parents(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
    """Instance method wrapper for parent expansion."""
    return _expand_results_with_parents(results, self.parent_store)


def _hs_expand_with_graph(self, results: List[RetrievalResult], query: str) -> List[RetrievalResult]:
    """Instance method wrapper for graph expansion."""
    return _expand_results_with_graph(results, query, self.graph_store)


HybridSearch._expand_with_parents = _hs_expand_with_parents  # type: ignore[attr-defined]
HybridSearch._expand_with_graph = _hs_expand_with_graph  # type: ignore[attr-defined]
