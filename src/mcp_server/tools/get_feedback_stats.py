"""MCP Tool: get_feedback_stats

This tool provides aggregate statistics on user feedback, such as
total feedback count, positive/negative breakdown, and satisfaction rate.
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
TOOL_NAME = "get_feedback_stats"
TOOL_DESCRIPTION = """Get aggregate statistics for user feedback (thumbs up/down).

Returns:
- total_feedbacks: Total number of feedback entries.
- positive_count: Number of thumbs up (1) ratings.
- negative_count: Number of thumbs down (-1) ratings.
- satisfaction_rate_percent: Percentage of positive feedback.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {},  # No input parameters needed
}


@dataclass
class GetFeedbackStatsTool:
    """Tool for retrieving feedback statistics.
    
    Handles the 'get_feedback_stats' MCP call by querying FeedbackStore.
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
            db_path = resolve_path("data/db/feedback.db")
            self._feedback_store = FeedbackStore(db_path)
        return self._feedback_store

    async def execute(self) -> types.CallToolResult:
        """Execute the stats retrieval.
            
        Returns:
            MCP CallToolResult with JSON formatted stats.
        """
        try:
            logger.info("Retrieving feedback statistics")
            stats = self.feedback_store.get_stats()
            
            import json
            stats_json = json.dumps(stats, indent=2, ensure_ascii=False)
            
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"## 运营反馈统计\n\n```json\n{stats_json}\n```",
                    )
                ],
                isError=False,
            )
            
        except Exception as e:
            logger.exception(f"Error retrieving feedback stats: {e}")
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"获取统计失败: {str(e)}",
                    )
                ],
                isError=True,
            )


# Global tool instance for the handler
_tool_instance: Optional[GetFeedbackStatsTool] = None


async def get_feedback_stats_handler(arguments: Dict[str, Any]) -> types.CallToolResult:
    """Handler function for get_feedback_stats MCP tool."""
    global _tool_instance
    if _tool_instance is None:
        _tool_instance = GetFeedbackStatsTool()
        
    return await _tool_instance.execute()


def register_tool(protocol_handler) -> None:
    """Register get_feedback_stats tool with the protocol handler."""
    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=get_feedback_stats_handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
