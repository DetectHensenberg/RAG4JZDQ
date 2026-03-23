import asyncio
import os
import sys
import unittest
from pathlib import Path

# Ensure current directory is in PYTHONPATH
sys.path.insert(0, os.getcwd())

from src.ingestion.storage.feedback_store import FeedbackStore
from src.mcp_server.tools.submit_feedback import submit_feedback_handler
from src.mcp_server.tools.get_feedback_stats import get_feedback_stats_handler

class TestFeedbackLoop(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_path = Path("data/db/test_feedback.db")
        if self.db_path.exists():
            self.db_path.unlink()
        self.store = FeedbackStore(self.db_path)

    def tearDown(self):
        # Close connection to avoid [WinError 32] on Windows
        if hasattr(self, 'store') and self.store.db:
            self.store.db.conn.close()
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except PermissionError:
                pass # Fallback for Windows

    def test_store_upsert(self):
        trace_id = "test-trace-123"
        
        # Initial feedback
        self.store.upsert_feedback(trace_id, 1, "Good answer", "What is RAG?")
        feedback = self.store.get_feedback_by_trace(trace_id)
        self.assertEqual(feedback["rating"], 1)
        self.assertEqual(feedback["comment"], "Good answer")
        
        # Update feedback (Upsert)
        self.store.upsert_feedback(trace_id, -1, "Changed my mind", "What is RAG?")
        feedback = self.store.get_feedback_by_trace(trace_id)
        self.assertEqual(feedback["rating"], -1)
        self.assertEqual(feedback["comment"], "Changed my mind")
        
        # Check stats
        stats = self.store.get_stats()
        self.assertEqual(stats["total_feedbacks"], 1)
        self.assertEqual(stats["negative_count"], 1)
        self.assertEqual(stats["positive_count"], 0)

    async def test_mcp_handlers(self):
        # Override the tool's store to use our test DB
        from src.mcp_server.tools import submit_feedback, get_feedback_stats
        
        # We need to ensure the global instances are initialized with our test DB
        # For testing purposes, we can manually inject the store
        submit_feedback._tool_instance = submit_feedback.SubmitFeedbackTool()
        submit_feedback._tool_instance._feedback_store = self.store
        
        get_feedback_stats._tool_instance = get_feedback_stats.GetFeedbackStatsTool()
        get_feedback_stats._tool_instance._feedback_store = self.store

        # 1. Submit positive feedback via handler
        res1 = await submit_feedback_handler({
            "trace_id": "mcp-trace-001",
            "rating": 1,
            "comment": "Helpful tool"
        })
        self.assertFalse(res1.isError)
        self.assertIn("成功提交反馈", res1.content[0].text)

        # 2. Submit negative feedback
        await submit_feedback_handler({
            "trace_id": "mcp-trace-002",
            "rating": -1
        })

        # 3. Get stats via handler
        res_stats = await get_feedback_stats_handler({})
        self.assertFalse(res_stats.isError)
        self.assertIn('"total_feedbacks": 2', res_stats.content[0].text)
        self.assertIn('"positive_count": 1', res_stats.content[0].text)
        self.assertIn('"negative_count": 1', res_stats.content[0].text)

if __name__ == "__main__":
    unittest.main()
