"""MCP Tool: query_knowledge_hub

This tool provides knowledge retrieval capabilities through the MCP protocol.
It combines HybridSearch (Dense + Sparse + RRF Fusion) with optional Reranking
to find relevant documents and return formatted results with citations.

Usage via MCP:
    Tool name: query_knowledge_hub
    Input schema:
        - query (string, required): The search query
        - top_k (integer, optional): Number of results to return (default: 5)
        - collection (string, optional): Limit search to specific collection
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import types

from src.core.response.response_builder import ResponseBuilder, MCPToolResponse
from src.core.settings import load_settings, resolve_path, Settings
from src.core.trace import TraceContext, TraceCollector
from src.core.types import RetrievalResult

if TYPE_CHECKING:
    from src.core.query_engine.hybrid_search import HybridSearch
    from src.core.query_engine.reranker import CoreReranker

logger = logging.getLogger(__name__)


# Tool metadata
TOOL_NAME = "query_knowledge_hub"
TOOL_DESCRIPTION = """Search the knowledge base for relevant documents.

This tool uses hybrid search (semantic + keyword) to find the most relevant 
documents matching your query. Results include source citations for reference.

Parameters:
- query: Your search question or keywords
- top_k: Maximum number of results (default: 5)
- collection: Limit search to a specific document collection
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query or question to find relevant documents for.",
        },
        "top_k": {
            "type": "integer",
            "description": "Maximum number of results to return.",
            "default": 5,
            "minimum": 1,
            "maximum": 20,
        },
        "collection": {
            "type": "string",
            "description": "Optional collection name to limit the search scope.",
        },
    },
    "required": ["query"],
}


@dataclass
class QueryKnowledgeHubConfig:
    """Configuration for query_knowledge_hub tool.
    
    Attributes:
        default_top_k: Default number of results if not specified
        max_top_k: Maximum allowed top_k value
        default_collection: Default collection if not specified
        enable_rerank: Whether to apply reranking
    """
    default_top_k: int = 5
    max_top_k: int = 20
    default_collection: str = "default"
    enable_rerank: bool = True


class QueryKnowledgeHubTool:
    """MCP Tool for knowledge base queries.
    
    This class encapsulates the query_knowledge_hub tool logic,
    coordinating HybridSearch and Reranker to produce formatted results.
    
    Design Principles:
    - Lazy initialization: Components created on first use
    - Error resilience: Graceful handling of search/rerank failures
    - Configurable: All parameters from settings.yaml
    
    Example:
        >>> tool = QueryKnowledgeHubTool(settings)
        >>> result = await tool.execute(query="Azure 配置", top_k=5)
        >>> print(result.content)
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        config: Optional[QueryKnowledgeHubConfig] = None,
        hybrid_search: Optional[HybridSearch] = None,
        reranker: Optional[CoreReranker] = None,
        response_builder: Optional[ResponseBuilder] = None,
    ) -> None:
        """Initialize QueryKnowledgeHubTool.
        
        Args:
            settings: Application settings. If None, loaded from default path.
            config: Tool configuration. If None, uses defaults.
            hybrid_search: Optional pre-configured HybridSearch instance.
            reranker: Optional pre-configured CoreReranker instance.
            response_builder: Optional pre-configured ResponseBuilder instance.
        """
        self._settings = settings
        self.config = config or QueryKnowledgeHubConfig()
        self._hybrid_search = hybrid_search
        self._reranker = reranker
        self._embedding_client = None
        self._response_builder = response_builder or ResponseBuilder()
        
        # Track initialization state
        self._initialized = False
        self._current_collection: Optional[str] = None
    
    @property
    def settings(self) -> Settings:
        """Get settings, loading if necessary."""
        if self._settings is None:
            self._settings = load_settings()
        return self._settings
    
    def _ensure_initialized(self, collection: str) -> None:
        """Ensure search components are initialized for the given collection.
        
        Caching strategy (balances speed vs freshness):
        - **Fully cached** (stateless, never go stale): embedding client,
          reranker, query processor, settings.
        - **Cached until collection changes**: vector store (ChromaDB
          PersistentClient reads from SQLite — sees data written by other
          processes), dense retriever, hybrid search.
        - **Auto-refreshes on every query**: BM25 sparse index — the
          ``SparseRetriever._ensure_index_loaded()`` always reloads from
          disk, so the cached SparseRetriever object is fine.
        
        Only when *collection* changes do we tear down and rebuild.
        
        Args:
            collection: Target collection name.
        """
        # Always rebuild vector_store and retriever components so that
        # data ingested by other processes (e.g. Dashboard) is visible
        # immediately without requiring an MCP Server restart.
        
        logger.info(f"Initializing query components for collection: {collection}")
        
        # Import here to avoid circular imports and allow lazy loading
        from src.core.query_engine.query_processor import QueryProcessor
        from src.core.query_engine.hybrid_search import create_hybrid_search
        from src.core.query_engine.dense_retriever import create_dense_retriever
        from src.core.query_engine.sparse_retriever import create_sparse_retriever
        from src.core.query_engine.reranker import create_core_reranker
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        
        # === Fully cached components (stateless, never go stale) ===
        if self._embedding_client is None:
            self._embedding_client = EmbeddingFactory.create(self.settings)
        
        if self._reranker is None:
            self._reranker = create_core_reranker(settings=self.settings)
        
        # === Rebuild for new collection ===
        # ChromaDB PersistentClient uses SQLite under the hood —
        # concurrent readers see committed writes from other processes
        # (dashboard ingestion), so caching the client is safe.
        vector_store = VectorStoreFactory.create(
            self.settings,
            collection_name=collection,
        )
        
        dense_retriever = create_dense_retriever(
            settings=self.settings,
            embedding_client=self._embedding_client,
            vector_store=vector_store,
        )
        
        # BM25Indexer just holds the index dir path; the SparseRetriever
        # calls _ensure_index_loaded() on every search, which always
        # reloads from disk — so it picks up dashboard-written data.
        bm25_indexer = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
        sparse_retriever = create_sparse_retriever(
            settings=self.settings,
            bm25_indexer=bm25_indexer,
            vector_store=vector_store,
        )
        sparse_retriever.default_collection = collection
        
        query_processor = QueryProcessor()
        self._hybrid_search = create_hybrid_search(
            settings=self.settings,
            query_processor=query_processor,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
        )
        
        self._current_collection = collection
        self._initialized = True
        logger.info(f"Query components initialized for collection: {collection}")
    
    async def execute(
        self,
        query: str,
        top_k: Optional[int] = None,
        collection: Optional[str] = None,
    ) -> MCPToolResponse:
        """Execute the query_knowledge_hub tool.
        
        Args:
            query: Search query string.
            top_k: Maximum results to return.
            collection: Target collection name.
            
        Returns:
            MCPToolResponse with formatted content and citations.
            
        Raises:
            ValueError: If query is empty or invalid.
        """
        # Validate query
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        # Apply defaults
        effective_top_k = min(
            top_k or self.config.default_top_k,
            self.config.max_top_k
        )
        effective_collection = collection or self.config.default_collection
        
        logger.info(
            f"Executing query_knowledge_hub: query='{query[:50]}...', "
            f"top_k={effective_top_k}, collection={effective_collection}"
        )
        
        trace = TraceContext(trace_type="query")
        trace.metadata["query"] = query[:200]
        trace.metadata["top_k"] = effective_top_k
        trace.metadata["collection"] = effective_collection
        trace.metadata["source"] = "mcp"

        try:
            # Initialize components for collection
            # Run blocking I/O (embedding API, ChromaDB, BM25) in a thread
            # to avoid blocking the async event loop / MCP stdio transport
            import time as _time
            _init_t0 = _time.monotonic()
            await asyncio.to_thread(self._ensure_initialized, effective_collection)
            _init_elapsed = (_time.monotonic() - _init_t0) * 1000.0
            trace.record_stage("initialization", {
                "collection": effective_collection,
                "cold_start": _init_elapsed > 500,  # >500ms ≈ cold
            }, elapsed_ms=_init_elapsed)
            
            # Perform hybrid search (blocking: embedding API + DB queries)
            results = await asyncio.to_thread(
                self._perform_search, query, effective_top_k, trace,
            )
            
            # Apply reranking if enabled (may call LLM API)
            if self.config.enable_rerank and results:
                results = await asyncio.to_thread(
                    self._apply_rerank, query, results, effective_top_k, trace,
                )
            
            # Build response
            response = self._response_builder.build(
                results=results,
                query=query,
                collection=effective_collection,
            )
            
            # Store final results in trace for dashboard display
            trace.metadata["final_results"] = [
                {
                    "chunk_id": r.chunk_id,
                    "score": round(r.score, 4),
                    "text": r.text or "",
                    "source": r.metadata.get("source_path", r.metadata.get("source", "")),
                    "title": r.metadata.get("title", ""),
                }
                for r in results
            ]

            logger.info(
                f"query_knowledge_hub completed: {len(results)} results, "
                f"is_empty={response.is_empty}"
            )
            
            TraceCollector().collect(trace)
            return response
            
        except Exception as e:
            logger.exception(f"query_knowledge_hub failed: {e}")
            TraceCollector().collect(trace)
            # Return error response
            return self._build_error_response(query, effective_collection, str(e))
    
    def _perform_search(
        self,
        query: str,
        top_k: int,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Perform hybrid search.
        
        Args:
            query: Search query.
            top_k: Maximum results.
            trace: Optional TraceContext for observability.
            
        Returns:
            List of RetrievalResult.
        """
        if self._hybrid_search is None:
            raise RuntimeError("HybridSearch not initialized")
        
        # Use a larger initial retrieval for reranking
        initial_top_k = top_k * 2 if self.config.enable_rerank else top_k
        
        try:
            results = self._hybrid_search.search(
                query=query,
                top_k=initial_top_k,
                filters=None,
                trace=trace,
                return_details=False,
            )
            return results if isinstance(results, list) else results.results
        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}")
            return []
    
    def _apply_rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Apply reranking to search results.
        
        Args:
            query: Original query.
            results: Search results to rerank.
            top_k: Final number of results.
            trace: Optional TraceContext for observability.
            
        Returns:
            Reranked results (or original if reranking fails).
        """
        if self._reranker is None or not self._reranker.is_enabled:
            return results[:top_k]
        
        try:
            rerank_result = self._reranker.rerank(
                query=query,
                results=results,
                top_k=top_k,
                trace=trace,
            )
            
            if rerank_result.used_fallback:
                logger.warning(
                    f"Reranker fallback: {rerank_result.fallback_reason}"
                )
            
            return rerank_result.results
        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
            return results[:top_k]
    
    def _build_error_response(
        self,
        query: str,
        collection: str,
        error_message: str,
    ) -> MCPToolResponse:
        """Build error response.
        
        Args:
            query: Original query.
            collection: Target collection.
            error_message: Error description.
            
        Returns:
            MCPToolResponse indicating error.
        """
        content = f"## 查询失败\n\n"
        content += f"查询: **{query}**\n"
        content += f"集合: `{collection}`\n\n"
        content += f"**错误信息:** {error_message}\n\n"
        content += "请检查:\n"
        content += "- 数据库连接是否正常\n"
        content += "- 集合是否已创建并包含数据\n"
        content += "- 配置文件是否正确\n"
        
        return MCPToolResponse(
            content=content,
            citations=[],
            metadata={
                "query": query,
                "collection": collection,
                "error": error_message,
            },
            is_empty=True,
        )


# Module-level tool instance (lazy-initialized)
_tool_instance: Optional[QueryKnowledgeHubTool] = None


def get_tool_instance(settings: Optional[Settings] = None) -> QueryKnowledgeHubTool:
    """Get or create the tool instance.
    
    Args:
        settings: Optional settings to use for initialization.
        
    Returns:
        QueryKnowledgeHubTool instance.
    """
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = QueryKnowledgeHubTool(settings=settings)
    return _tool_instance


async def query_knowledge_hub_handler(
    query: str,
    top_k: int = 5,
    collection: Optional[str] = None,
) -> types.CallToolResult:
    """Handler function for MCP tool registration.
    
    This function is registered with the ProtocolHandler and called
    when the MCP client invokes the query_knowledge_hub tool.
    
    Supports multimodal responses - if search results contain images,
    the response will include ImageContent blocks alongside TextContent.
    
    Args:
        query: Search query string.
        top_k: Maximum number of results.
        collection: Optional collection name.
        
    Returns:
        MCP CallToolResult with content blocks (text and optionally images).
    """
    tool = get_tool_instance()
    
    try:
        response = await tool.execute(
            query=query,
            top_k=top_k,
            collection=collection,
        )
        
        # Use to_mcp_content() which handles multimodal (text + images)
        content_blocks = response.to_mcp_content()
        
        return types.CallToolResult(
            content=content_blocks,
            isError=response.is_empty and "error" in response.metadata,
        )
        
    except ValueError as e:
        # Invalid parameters
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"参数错误: {e}",
                )
            ],
            isError=True,
        )
    except Exception as e:
        # Internal error
        logger.exception(f"query_knowledge_hub handler error: {e}")
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"内部错误: 查询处理失败",
                )
            ],
            isError=True,
        )


def register_tool(protocol_handler) -> None:
    """Register query_knowledge_hub tool with the protocol handler.
    
    Args:
        protocol_handler: ProtocolHandler instance to register with.
    """
    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=query_knowledge_hub_handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
