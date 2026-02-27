"""MCP Tool: list_collections

This tool provides collection listing capabilities through the MCP protocol.
It lists all available collections in the vector store with statistics.

Usage via MCP:
    Tool name: list_collections
    Input schema:
        - include_stats (boolean, optional): Include statistics for each collection
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import types

if TYPE_CHECKING:
    from src.mcp_server.protocol_handler import ProtocolHandler
    from src.core.settings import Settings

logger = logging.getLogger(__name__)


# Tool metadata
TOOL_NAME = "list_collections"
TOOL_DESCRIPTION = """List all available document collections in the knowledge base.

Returns information about each collection including:
- Collection name
- Document count (if include_stats=true)
- Collection metadata

Use this tool to discover available collections before querying.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "include_stats": {
            "type": "boolean",
            "description": "Whether to include statistics (document count) for each collection.",
            "default": True,
        },
    },
    "required": [],
}


@dataclass
class CollectionInfo:
    """Information about a single collection.
    
    Attributes:
        name: Collection name
        count: Number of documents/chunks in the collection (optional)
        metadata: Collection metadata dictionary
    """
    name: str
    count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result: Dict[str, Any] = {"name": self.name}
        if self.count is not None:
            result["count"] = self.count
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class ListCollectionsConfig:
    """Configuration for list_collections tool.
    
    Attributes:
        persist_directory: Path to ChromaDB storage directory
        include_stats_default: Default value for include_stats parameter
    """
    persist_directory: str = "./data/db/chroma"
    include_stats_default: bool = True


class ListCollectionsTool:
    """MCP Tool for listing knowledge base collections.
    
    This class encapsulates the list_collections tool logic,
    querying the vector store to enumerate available collections.
    
    Design Principles:
    - Config-Driven: Paths from settings.yaml
    - Error Resilience: Graceful handling of missing directories
    - Observable: Logging for debugging
    
    Example:
        >>> tool = ListCollectionsTool(settings)
        >>> result = await tool.execute(include_stats=True)
        >>> print(result)
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        config: Optional[ListCollectionsConfig] = None,
    ) -> None:
        """Initialize ListCollectionsTool.
        
        Args:
            settings: Application settings. If None, loaded from default path.
            config: Tool configuration. If None, derived from settings.
        """
        self._settings = settings
        self._config = config
        
    @property
    def settings(self) -> Settings:
        """Get settings, loading if necessary."""
        if self._settings is None:
            from src.core.settings import load_settings
            self._settings = load_settings()
        return self._settings
    
    @property
    def config(self) -> ListCollectionsConfig:
        """Get configuration, deriving from settings if necessary."""
        if self._config is None:
            try:
                persist_dir = getattr(
                    self.settings.vector_store,
                    'persist_directory',
                    './data/db/chroma'
                )
            except AttributeError:
                persist_dir = './data/db/chroma'
            
            self._config = ListCollectionsConfig(
                persist_directory=persist_dir
            )
        return self._config
    
    def _get_chroma_client(self) -> Any:
        """Get or create ChromaDB client.
        
        Returns:
            ChromaDB PersistentClient instance.
            
        Raises:
            ImportError: If chromadb is not installed.
            RuntimeError: If client creation fails.
        """
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError:
            raise ImportError(
                "chromadb package is required for list_collections. "
                "Install it with: pip install chromadb"
            )
        
        persist_path = Path(self.config.persist_directory).resolve()
        
        if not persist_path.exists():
            logger.warning(f"ChromaDB directory does not exist: {persist_path}")
            # Return client anyway - it will just have no collections
            persist_path.mkdir(parents=True, exist_ok=True)
        
        try:
            client = chromadb.PersistentClient(
                path=str(persist_path),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )
            return client
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize ChromaDB client at '{persist_path}': {e}"
            ) from e
    
    def list_collections(
        self,
        include_stats: bool = True
    ) -> List[CollectionInfo]:
        """List all available collections.
        
        Args:
            include_stats: Whether to include document counts.
            
        Returns:
            List of CollectionInfo objects.
        """
        try:
            client = self._get_chroma_client()
        except (ImportError, RuntimeError) as e:
            logger.error(f"Failed to get ChromaDB client: {e}")
            return []
        
        collections_info: List[CollectionInfo] = []
        
        try:
            # Get all collections from ChromaDB
            collections = client.list_collections()
            
            for collection in collections:
                info = CollectionInfo(
                    name=collection.name,
                    metadata=collection.metadata
                )
                
                if include_stats:
                    try:
                        info.count = collection.count()
                    except Exception as e:
                        logger.warning(
                            f"Failed to get count for collection '{collection.name}': {e}"
                        )
                        info.count = None
                
                collections_info.append(info)
                
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
        
        logger.info(f"Found {len(collections_info)} collections")
        return collections_info
    
    def format_response(
        self,
        collections: List[CollectionInfo]
    ) -> str:
        """Format collections list as a readable string.
        
        Args:
            collections: List of CollectionInfo objects.
            
        Returns:
            Formatted string suitable for MCP response.
        """
        if not collections:
            return "No collections found in the knowledge base."
        
        lines = [
            f"## Available Collections ({len(collections)} total)\n"
        ]
        
        for i, coll in enumerate(collections, 1):
            line = f"{i}. **{coll.name}**"
            
            if coll.count is not None:
                line += f" - {coll.count} documents"
            
            if coll.metadata:
                # Filter out internal metadata
                user_metadata = {
                    k: v for k, v in coll.metadata.items()
                    if not k.startswith('_') and not k.startswith('hnsw:')
                }
                if user_metadata:
                    meta_str = ", ".join(f"{k}={v}" for k, v in user_metadata.items())
                    line += f" ({meta_str})"
            
            lines.append(line)
        
        return "\n".join(lines)
    
    async def execute(
        self,
        include_stats: bool = True,
    ) -> types.CallToolResult:
        """Execute the list_collections tool.
        
        Args:
            include_stats: Whether to include statistics for each collection.
            
        Returns:
            CallToolResult with formatted collection list.
        """
        logger.info(f"Executing list_collections (include_stats={include_stats})")
        
        try:
            # Run blocking ChromaDB I/O in a thread to avoid blocking
            # the async event loop / MCP stdio transport
            collections = await asyncio.to_thread(
                self.list_collections, include_stats,
            )
            response_text = self.format_response(collections)
            
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=response_text,
                    )
                ],
                isError=False,
            )
            
        except Exception as e:
            logger.exception("Error executing list_collections")
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Error listing collections: {str(e)}",
                    )
                ],
                isError=True,
            )


def register_tool(protocol_handler: ProtocolHandler) -> None:
    """Register the list_collections tool with the protocol handler.
    
    This function is called by _register_default_tools() in protocol_handler.py
    to register this tool when the MCP server starts.
    
    Args:
        protocol_handler: ProtocolHandler instance to register with.
    """
    tool = ListCollectionsTool()
    
    async def handler(
        include_stats: bool = True,
    ) -> types.CallToolResult:
        """Handler function for MCP tool calls."""
        return await tool.execute(include_stats=include_stats)
    
    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=handler,
    )
    
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
