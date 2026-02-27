"""MCP Protocol Handler for JSON-RPC 2.0 message handling.

This module provides the ProtocolHandler class that encapsulates:
- Tool registration and schema management
- JSON-RPC error code handling
- Capability negotiation during initialize
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mcp import types
from mcp.server.lowlevel import Server

from src.observability.logger import get_logger


# JSON-RPC 2.0 Error Codes
class JSONRPCErrorCodes:
    """Standard JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class ProtocolHandler:
    """Handles MCP protocol operations including tool registration and execution.

    This class encapsulates:
    - Tool registration with schema validation
    - Tool execution with error handling
    - Capability declaration for initialize response

    Attributes:
        server_name: Name of the MCP server.
        server_version: Version string of the server.
        tools: Registry of available tools.
    """

    server_name: str
    server_version: str
    tools: Dict[str, ToolDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize logger after dataclass initialization."""
        self._logger = get_logger(log_level="INFO")

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Register a tool with the protocol handler.

        Args:
            name: Unique name for the tool.
            description: Human-readable description of what the tool does.
            input_schema: JSON Schema for the tool's input parameters.
            handler: Async function that executes the tool logic.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if name in self.tools:
            raise ValueError(f"Tool '{name}' is already registered")

        self.tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )
        self._logger.info("Registered tool: %s", name)

    def get_tool_schemas(self) -> List[types.Tool]:
        """Get list of tool schemas for tools/list response.

        Returns:
            List of Tool objects with name, description, and inputSchema.
        """
        return [
            types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
            )
            for tool in self.tools.values()
        ]

    async def execute_tool(
        self, name: str, arguments: Dict[str, Any]
    ) -> types.CallToolResult:
        """Execute a registered tool by name.

        Args:
            name: Name of the tool to execute.
            arguments: Arguments to pass to the tool handler.

        Returns:
            CallToolResult with content blocks or error indication.

        Raises:
            ValueError: If tool is not found.
        """
        if name not in self.tools:
            self._logger.warning("Tool not found: %s", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Error: Tool '{name}' not found",
                    )
                ],
                isError=True,
            )

        tool = self.tools[name]
        try:
            self._logger.info("Executing tool: %s", name)
            result = await tool.handler(**arguments)

            # Handle different return types
            if isinstance(result, types.CallToolResult):
                return result
            if isinstance(result, str):
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=result)],
                    isError=False,
                )
            if isinstance(result, list):
                return types.CallToolResult(content=result, isError=False)
            # Default: convert to string
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(result))],
                isError=False,
            )

        except TypeError as e:
            # Invalid parameters
            self._logger.error("Invalid params for tool %s: %s", name, e)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Error: Invalid parameters - {e}",
                    )
                ],
                isError=True,
            )
        except Exception as e:
            # Internal error - don't leak stack trace
            self._logger.exception("Internal error executing tool %s", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Error: Internal server error while executing '{name}'",
                    )
                ],
                isError=True,
            )

    def get_capabilities(self) -> Dict[str, Any]:
        """Get server capabilities for initialize response.

        Returns:
            Dictionary of server capabilities.
        """
        return {
            "tools": {} if self.tools else {},
        }


def _register_default_tools(protocol_handler: ProtocolHandler) -> None:
    """Register all default MCP tools with the protocol handler.

    Args:
        protocol_handler: ProtocolHandler instance to register tools with.
    """
    # Import and register query_knowledge_hub tool
    from src.mcp_server.tools.query_knowledge_hub import register_tool as register_query_tool
    register_query_tool(protocol_handler)
    
    # Import and register list_collections tool
    from src.mcp_server.tools.list_collections import register_tool as register_list_tool
    register_list_tool(protocol_handler)
    
    # Import and register get_document_summary tool
    from src.mcp_server.tools.get_document_summary import register_tool as register_summary_tool
    register_summary_tool(protocol_handler)


def create_mcp_server(
    server_name: str,
    server_version: str,
    protocol_handler: Optional[ProtocolHandler] = None,
    register_tools: bool = True,
) -> Server:
    """Create and configure an MCP server with the protocol handler.

    This factory function creates a low-level MCP Server instance and
    registers the necessary handlers for tools/list and tools/call.

    Args:
        server_name: Name of the server.
        server_version: Version string.
        protocol_handler: Optional pre-configured protocol handler.
            If None, a new one will be created.
        register_tools: Whether to register default tools (default: True).

    Returns:
        Configured Server instance ready to run.
    """
    if protocol_handler is None:
        protocol_handler = ProtocolHandler(
            server_name=server_name,
            server_version=server_version,
        )

    # Register default tools if requested
    if register_tools:
        _register_default_tools(protocol_handler)

    # Create low-level server
    server = Server(server_name)

    # Register tools/list handler
    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """Handle tools/list request."""
        return protocol_handler.get_tool_schemas()

    # Register tools/call handler
    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: Dict[str, Any]
    ) -> types.CallToolResult:
        """Handle tools/call request."""
        return await protocol_handler.execute_tool(name, arguments)

    # Store protocol handler on server for access
    server._protocol_handler = protocol_handler  # type: ignore[attr-defined]

    return server


def get_protocol_handler(server: Server) -> ProtocolHandler:
    """Get the protocol handler from a server instance.

    Args:
        server: Server instance created by create_mcp_server.

    Returns:
        The ProtocolHandler associated with the server.

    Raises:
        AttributeError: If server was not created with create_mcp_server.
    """
    return server._protocol_handler  # type: ignore[attr-defined]
