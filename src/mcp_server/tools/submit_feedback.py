"""MCP Tool: submit_feedback

This tool allows users to submit positive/negative feedback (thumbs up/down)
for a specific RAG response, identified by its unique trace_id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp import types

from src.core.settings import load_settings, resolve_path, Settings
from src.ingestion.storage.feedback_store import FeedbackStore

logger = logging.getLogger(__name__)

# Tool metadata
TOOL_NAME = "submit_feedback"
TOOL_DESCRIPTION = """Submit user feedback (thumbs up/down) for a specific RAG response.

Use this tool to record whether a response was helpful or not. 
This data helps improve retrieval quality over time.

Parameters:
- trace_id: The unique ID associated with the response (found in metadata).
- rating: 1 for thumbs up (helpful), -1 for thumbs down (not helpful).
- comment: Optional text feedback or reason for the rating.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "trace_id": {
            "type": "string",
            "description": "The unique trace_id of the response being rated.",
        },
        "rating": {
            "type": "integer",
            "description": "Feedback rating: 1 (helpful) or -1 (not helpful).",
            "enum": [1, -1],
        },
        "comment": {
            "type": "string",
            "description": "Optional text comment providing more detail about the feedback.",
        },
    },
    "required": ["trace_id", "rating"],
}


@dataclass
class SubmitFeedbackTool:
    """Tool for capturing user feedback.
    
    Handles the 'submit_feedback' MCP call by persisting data to FeedbackStore.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize with application settings."""
        self._settings = settings
        self._feedback_store: Optional[FeedbackStore] = None

    @property
    def settings(self) -> Settings:
        """Get settings, loading if necessary."""
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    @property
    def feedback_store(self) -> FeedbackStore:
        """Get or create FeedbackStore instance."""
        if self._feedback_store is None:
            # Use data/db/feedback.db as the default storage
            db_path = resolve_path("data/db/feedback.db")
            self._feedback_store = FeedbackStore(db_path)
        return self._feedback_store

    async def execute(
        self,
        trace_id: str,
        rating: int,
        comment: Optional[str] = None
    ) -> types.CallToolResult:
        """Execute the feedback submission.
        
        Args:
            trace_id: ID of the trace to rate.
            rating: 1 or -1.
            comment: Optional text.
            
        Returns:
            MCP CallToolResult.
        """
        try:
            logger.info(f"Submitting feedback for trace {trace_id}: rating={rating}")
            
            # Record feedback in SQLite asynchronously
            await self.feedback_store.async_upsert_feedback(
                trace_id=trace_id,
                rating=rating,
                comment=comment
            )
            
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"成功提交反馈（Rating: {rating}）。感谢您的反馈！",
                    )
                ],
                isError=False,
            )
            
        except Exception as e:
            logger.exception(f"Error submitting feedback: {e}")
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"提交反馈失败: {str(e)}",
                    )
                ],
                isError=True,
            )


# Global tool instance for the handler
_tool_instance: Optional[SubmitFeedbackTool] = None


async def submit_feedback_handler(arguments: Dict[str, Any]) -> types.CallToolResult:
    """Handler function for submit_feedback MCP tool."""
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = SubmitFeedbackTool()
        
    try:
        # Extract arguments
        trace_id = arguments.get("trace_id")
        rating = arguments.get("rating")
        comment = arguments.get("comment")
        
        if trace_id is None or rating is None:
            raise ValueError("Missing required arguments: trace_id, rating")
            
        return await _tool_instance.execute(
            trace_id=trace_id,
            rating=int(rating),
            comment=comment
        )
    except Exception as e:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"参数错误: {e}",
                )
            ],
            isError=True,
        )


def register_tool(protocol_handler) -> None:
    """Register submit_feedback tool with the protocol handler."""
    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=submit_feedback_handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
