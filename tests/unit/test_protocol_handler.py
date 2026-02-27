"""Unit tests for MCP Protocol Handler.

Tests cover:
- Tool registration and schema generation
- Tool execution with various return types
- Error handling (invalid params, internal errors, unknown tools)
- JSON-RPC error codes compliance
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from mcp import types

from src.mcp_server.protocol_handler import (
    JSONRPCErrorCodes,
    ProtocolHandler,
    ToolDefinition,
    create_mcp_server,
    get_protocol_handler,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def protocol_handler() -> ProtocolHandler:
    """Create a fresh ProtocolHandler instance."""
    return ProtocolHandler(
        server_name="test-server",
        server_version="1.0.0",
    )


@pytest.fixture
def sample_tool_schema() -> Dict[str, Any]:
    """Sample JSON schema for a tool's input."""
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }


# ============================================================================
# ToolDefinition Tests
# ============================================================================


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_create_tool_definition(self, sample_tool_schema: Dict[str, Any]) -> None:
        """Should create a ToolDefinition with all required fields."""

        async def dummy_handler(**kwargs: Any) -> str:
            return "result"

        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema=sample_tool_schema,
            handler=dummy_handler,
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema == sample_tool_schema
        assert tool.handler == dummy_handler


# ============================================================================
# ProtocolHandler - Tool Registration Tests
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration functionality."""

    def test_register_tool_success(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should successfully register a tool."""

        async def handler(**kwargs: Any) -> str:
            return "result"

        protocol_handler.register_tool(
            name="search",
            description="Search the knowledge base",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        assert "search" in protocol_handler.tools
        assert protocol_handler.tools["search"].name == "search"
        assert protocol_handler.tools["search"].description == "Search the knowledge base"

    def test_register_duplicate_tool_raises_error(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should raise ValueError when registering duplicate tool name."""

        async def handler(**kwargs: Any) -> str:
            return "result"

        protocol_handler.register_tool(
            name="search",
            description="First search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        with pytest.raises(ValueError, match="Tool 'search' is already registered"):
            protocol_handler.register_tool(
                name="search",
                description="Duplicate search tool",
                input_schema=sample_tool_schema,
                handler=handler,
            )

    def test_register_multiple_tools(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should register multiple different tools."""

        async def handler1(**kwargs: Any) -> str:
            return "result1"

        async def handler2(**kwargs: Any) -> str:
            return "result2"

        protocol_handler.register_tool(
            name="tool1",
            description="First tool",
            input_schema=sample_tool_schema,
            handler=handler1,
        )
        protocol_handler.register_tool(
            name="tool2",
            description="Second tool",
            input_schema={"type": "object", "properties": {}},
            handler=handler2,
        )

        assert len(protocol_handler.tools) == 2
        assert "tool1" in protocol_handler.tools
        assert "tool2" in protocol_handler.tools


# ============================================================================
# ProtocolHandler - Tool Schema Tests
# ============================================================================


class TestGetToolSchemas:
    """Tests for get_tool_schemas method."""

    def test_empty_tools_returns_empty_list(
        self, protocol_handler: ProtocolHandler
    ) -> None:
        """Should return empty list when no tools registered."""
        schemas = protocol_handler.get_tool_schemas()
        assert schemas == []

    def test_returns_tool_schemas(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should return list of Tool objects with correct schema."""

        async def handler(**kwargs: Any) -> str:
            return "result"

        protocol_handler.register_tool(
            name="query_knowledge_hub",
            description="Query the knowledge hub",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        schemas = protocol_handler.get_tool_schemas()

        assert len(schemas) == 1
        assert isinstance(schemas[0], types.Tool)
        assert schemas[0].name == "query_knowledge_hub"
        assert schemas[0].description == "Query the knowledge hub"
        assert schemas[0].inputSchema == sample_tool_schema


# ============================================================================
# ProtocolHandler - Tool Execution Tests
# ============================================================================


class TestExecuteTool:
    """Tests for tool execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_tool_returns_string(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should wrap string return in CallToolResult."""

        async def handler(query: str, top_k: int = 5) -> str:
            return f"Found {top_k} results for: {query}"

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        result = await protocol_handler.execute_tool(
            "search", {"query": "test query", "top_k": 3}
        )

        assert isinstance(result, types.CallToolResult)
        assert result.isError is False
        assert len(result.content) == 1
        assert isinstance(result.content[0], types.TextContent)
        assert result.content[0].text == "Found 3 results for: test query"

    @pytest.mark.asyncio
    async def test_execute_tool_returns_call_tool_result(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should pass through CallToolResult directly."""

        async def handler(query: str, top_k: int = 5) -> types.CallToolResult:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="Custom result")],
                isError=False,
            )

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        result = await protocol_handler.execute_tool("search", {"query": "test"})

        assert isinstance(result, types.CallToolResult)
        assert result.content[0].text == "Custom result"

    @pytest.mark.asyncio
    async def test_execute_tool_returns_content_list(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should wrap content list in CallToolResult."""

        async def handler(query: str, top_k: int = 5) -> List[types.TextContent]:
            return [
                types.TextContent(type="text", text="Result 1"),
                types.TextContent(type="text", text="Result 2"),
            ]

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        result = await protocol_handler.execute_tool("search", {"query": "test"})

        assert len(result.content) == 2
        assert result.content[0].text == "Result 1"
        assert result.content[1].text == "Result 2"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(
        self, protocol_handler: ProtocolHandler
    ) -> None:
        """Should return error result for unknown tool."""
        result = await protocol_handler.execute_tool(
            "nonexistent_tool", {"arg": "value"}
        )

        assert isinstance(result, types.CallToolResult)
        assert result.isError is True
        assert "not found" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_with_invalid_params(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should return error for invalid parameters."""

        async def handler(query: str, top_k: int = 5) -> str:
            return f"Results for {query}"

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        # Call with unexpected keyword argument
        result = await protocol_handler.execute_tool(
            "search", {"query": "test", "invalid_param": "value"}
        )

        assert result.isError is True
        assert "invalid" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_internal_error(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should return generic error without leaking stack trace."""

        async def handler(query: str, top_k: int = 5) -> str:
            raise RuntimeError("Database connection failed")

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        result = await protocol_handler.execute_tool("search", {"query": "test"})

        assert result.isError is True
        assert "internal" in result.content[0].text.lower()
        # Should NOT leak the actual error message
        assert "database" not in result.content[0].text.lower()


# ============================================================================
# ProtocolHandler - Capabilities Tests
# ============================================================================


class TestGetCapabilities:
    """Tests for capabilities reporting."""

    def test_capabilities_with_no_tools(
        self, protocol_handler: ProtocolHandler
    ) -> None:
        """Should return empty tools capability when no tools registered."""
        caps = protocol_handler.get_capabilities()
        assert "tools" in caps
        assert caps["tools"] == {}

    def test_capabilities_with_tools(
        self, protocol_handler: ProtocolHandler, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should indicate tools capability when tools registered."""

        async def handler(**kwargs: Any) -> str:
            return "result"

        protocol_handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=handler,
        )

        caps = protocol_handler.get_capabilities()
        assert "tools" in caps


# ============================================================================
# JSON-RPC Error Codes Tests
# ============================================================================


class TestJSONRPCErrorCodes:
    """Tests for JSON-RPC error code constants."""

    def test_error_codes_are_correct(self) -> None:
        """Should have standard JSON-RPC 2.0 error codes."""
        assert JSONRPCErrorCodes.PARSE_ERROR == -32700
        assert JSONRPCErrorCodes.INVALID_REQUEST == -32600
        assert JSONRPCErrorCodes.METHOD_NOT_FOUND == -32601
        assert JSONRPCErrorCodes.INVALID_PARAMS == -32602
        assert JSONRPCErrorCodes.INTERNAL_ERROR == -32603


# ============================================================================
# create_mcp_server Factory Tests
# ============================================================================


class TestCreateMCPServer:
    """Tests for the server factory function."""

    def test_creates_server_instance(self) -> None:
        """Should create a Server instance."""
        from mcp.server.lowlevel import Server

        server = create_mcp_server("test-server", "1.0.0")

        assert isinstance(server, Server)

    def test_attaches_protocol_handler(self) -> None:
        """Should attach protocol handler to server."""
        server = create_mcp_server("test-server", "1.0.0")

        handler = get_protocol_handler(server)

        assert isinstance(handler, ProtocolHandler)
        assert handler.server_name == "test-server"
        assert handler.server_version == "1.0.0"

    def test_uses_provided_protocol_handler(
        self, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Should use provided protocol handler if given."""
        custom_handler = ProtocolHandler(
            server_name="custom",
            server_version="2.0.0",
        )

        async def tool_handler(**kwargs: Any) -> str:
            return "result"

        custom_handler.register_tool(
            name="custom_tool",
            description="Custom tool",
            input_schema=sample_tool_schema,
            handler=tool_handler,
        )

        server = create_mcp_server(
            "test-server", "1.0.0", protocol_handler=custom_handler
        )

        handler = get_protocol_handler(server)
        assert handler is custom_handler
        assert "custom_tool" in handler.tools


# ============================================================================
# Integration-like Tests (Server + ProtocolHandler)
# ============================================================================


class TestServerProtocolHandlerIntegration:
    """Tests for server and protocol handler working together."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_registered_tools(
        self, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Server's list_tools handler should return registered tools."""
        handler = ProtocolHandler(
            server_name="test-server",
            server_version="1.0.0",
        )

        async def search_handler(query: str, top_k: int = 5) -> str:
            return f"Results for {query}"

        handler.register_tool(
            name="query_knowledge_hub",
            description="Query the knowledge hub",
            input_schema=sample_tool_schema,
            handler=search_handler,
        )

        server = create_mcp_server("test-server", "1.0.0", protocol_handler=handler)

        # Verify tools are accessible through protocol handler
        tools = handler.get_tool_schemas()
        assert len(tools) == 1
        assert tools[0].name == "query_knowledge_hub"

    @pytest.mark.asyncio
    async def test_call_tool_executes_handler(
        self, sample_tool_schema: Dict[str, Any]
    ) -> None:
        """Server's call_tool handler should execute the tool."""
        handler = ProtocolHandler(
            server_name="test-server",
            server_version="1.0.0",
        )

        async def search_handler(query: str, top_k: int = 5) -> str:
            return f"Found {top_k} results for: {query}"

        handler.register_tool(
            name="search",
            description="Search tool",
            input_schema=sample_tool_schema,
            handler=search_handler,
        )

        server = create_mcp_server("test-server", "1.0.0", protocol_handler=handler)

        # Execute through protocol handler
        result = await handler.execute_tool("search", {"query": "test", "top_k": 10})

        assert result.isError is False
        assert "Found 10 results for: test" in result.content[0].text
