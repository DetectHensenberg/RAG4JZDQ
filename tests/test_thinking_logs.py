import asyncio
import logging
import sys
import io
import os
from unittest.mock import MagicMock, patch

# Ensure current directory is in PYTHONPATH
sys.path.insert(0, os.getcwd())

print("DEBUG: All imports successful")

from src.core.settings import load_settings, DEFAULT_SETTINGS_PATH
from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool
from src.core.query_engine.hybrid_search import HybridSearch
from src.core.types import RetrievalResult, ProcessedQuery

async def test_thinking_logs():
    print("DEBUG: Inside test_thinking_logs")
    
    # Setup logging to capture stderr
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    stderr_capture = io.StringIO()
    
    print("DEBUG: Loading settings...")
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    
    # Create real HybridSearch but mock its retrievers
    print("DEBUG: Setting up HybridSearch with mocked components...")
    mock_dense = MagicMock()
    mock_dense.retrieve.return_value = [RetrievalResult(chunk_id="d1", score=0.9, text="dense", metadata={})]
    
    mock_sparse = MagicMock()
    mock_sparse.retrieve.return_value = [RetrievalResult(chunk_id="s1", score=0.8, text="sparse", metadata={})]
    
    mock_reranker = MagicMock()
    from src.core.query_engine.reranker import RerankResult
    mock_reranker.rerank.return_value = RerankResult(
        results=[RetrievalResult(chunk_id="r1", score=0.95, text="reranked", metadata={})],
        used_fallback=False,
        reranker_type="test"
    )

    # Mock QueryProcessor
    mock_processor = MagicMock()
    mock_processor.process.return_value = ProcessedQuery(
        original_query="test",
        keywords=["test"],
        filters={},
        intent_weights=[0.5, 0.5]
    )

    real_engine = HybridSearch(
        settings=settings,
        query_processor=mock_processor,
        dense_retriever=mock_dense,
        sparse_retriever=mock_sparse,
        reranker=mock_reranker
    )
    
    # Mock strategy router
    from src.core.query_engine.strategy_router import RoutingDecision
    mock_router = MagicMock()
    mock_router.route.return_value = RoutingDecision(
        use_parent_retrieval=True, 
        use_graph_rag=True,
        reasoning="Testing"
    )
    real_engine.strategy_router = mock_router
    real_engine.parent_store = MagicMock()
    real_engine.parent_store.get_parent_texts.return_value = {"p1": "parent text"}
    real_engine.graph_store = MagicMock()
    real_engine.graph_store.get_neighbors.return_value = []

    print("DEBUG: Creating tool...")
    tool = QueryKnowledgeHubTool(settings=settings)
    tool.engine = real_engine

    # Now redirect stderr to capture [Thinking] logs
    sys.stderr = stderr_capture

    print("DEBUG: Executing tool...")
    try:
        await tool.execute(query="如何配置 OpenAI？")
        print("DEBUG: Tool execution finished")
    except Exception as e:
        sys.stderr = sys.__stderr__
        print(f"DEBUG: Tool execution failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Restore stderr
    sys.stderr = sys.__stderr__
    
    # Combine captures
    all_logs = stderr_capture.getvalue() + log_capture.getvalue()
    
    # Verify [Thinking] logs
    thinking_logs = [
        "Initializing: Setting up retrieval components",
        "Retrieving: Processing query and searching indexes",
        "Reranking: Scoring",
        "Routing: Optimizing retrieval strategy",
        "Expanding: Augmenting with Graph/Parent",
        "Finalizing: Assembling formatted response"
    ]
    
    print("\n--- Thinking Logs Verification ---")
    found_count = 0
    for log in thinking_logs:
        if log in all_logs:
            print(f"[X] Found: {log}")
            found_count += 1
        else:
            print(f"[ ] Missing: {log}")
    
    if found_count == len(thinking_logs):
        print("\nAll thinking stages found! Verification PASSED.")
    else:
        print(f"\nVerification FAILED. Found {found_count}/{len(thinking_logs)} stages.")
        # print("\n--- Captured logs ---")
        # print(all_logs)

if __name__ == "__main__":
    asyncio.run(test_thinking_logs())
