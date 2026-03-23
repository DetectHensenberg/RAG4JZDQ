"""
MCP Server Tools.

This package contains the MCP tool definitions exposed to clients.
"""

from src.mcp_server.tools.query_knowledge_hub import (
    TOOL_NAME as QUERY_KNOWLEDGE_HUB_NAME,
    TOOL_DESCRIPTION as QUERY_KNOWLEDGE_HUB_DESCRIPTION,
    TOOL_INPUT_SCHEMA as QUERY_KNOWLEDGE_HUB_SCHEMA,
    QueryKnowledgeHubTool,
    query_knowledge_hub_handler,
    register_tool as register_query_knowledge_hub,
)
from src.mcp_server.tools.submit_feedback import (
    TOOL_NAME as SUBMIT_FEEDBACK_NAME,
    TOOL_DESCRIPTION as SUBMIT_FEEDBACK_DESCRIPTION,
    TOOL_INPUT_SCHEMA as SUBMIT_FEEDBACK_SCHEMA,
    register_tool as register_submit_feedback,
)
from src.mcp_server.tools.get_feedback_stats import (
    TOOL_NAME as GET_FEEDBACK_STATS_NAME,
    TOOL_DESCRIPTION as GET_FEEDBACK_STATS_DESCRIPTION,
    TOOL_INPUT_SCHEMA as GET_FEEDBACK_STATS_SCHEMA,
    register_tool as register_get_feedback_stats,
)

__all__ = [
    "QUERY_KNOWLEDGE_HUB_NAME",
    "QUERY_KNOWLEDGE_HUB_DESCRIPTION",
    "QUERY_KNOWLEDGE_HUB_SCHEMA",
    "QueryKnowledgeHubTool",
    "query_knowledge_hub_handler",
    "register_query_knowledge_hub",
    "SUBMIT_FEEDBACK_NAME",
    "register_submit_feedback",
    "GET_FEEDBACK_STATS_NAME",
    "register_get_feedback_stats",
]
