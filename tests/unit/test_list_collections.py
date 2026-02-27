"""Unit tests for list_collections MCP tool.

This module tests the ListCollectionsTool class that provides
collection listing capabilities through the MCP protocol.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

from src.mcp_server.tools.list_collections import (
    ListCollectionsTool,
    ListCollectionsConfig,
    CollectionInfo,
    TOOL_NAME,
    TOOL_DESCRIPTION,
    TOOL_INPUT_SCHEMA,
    register_tool,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_settings() -> Mock:
    """Create mock settings object."""
    settings = Mock()
    settings.vector_store = Mock()
    settings.vector_store.persist_directory = "./data/db/chroma"
    return settings


@pytest.fixture
def mock_config() -> ListCollectionsConfig:
    """Create test configuration."""
    return ListCollectionsConfig(
        persist_directory="./test_data/chroma",
        include_stats_default=True,
    )


@pytest.fixture
def tool_with_mock_settings(mock_settings: Mock) -> ListCollectionsTool:
    """Create ListCollectionsTool with mock settings."""
    return ListCollectionsTool(settings=mock_settings)


@pytest.fixture
def tool_with_config(mock_config: ListCollectionsConfig) -> ListCollectionsTool:
    """Create ListCollectionsTool with explicit config."""
    return ListCollectionsTool(config=mock_config)


@pytest.fixture
def sample_collections() -> List[CollectionInfo]:
    """Create sample collection info list."""
    return [
        CollectionInfo(
            name="knowledge_hub",
            count=150,
            metadata={"hnsw:space": "cosine"},
        ),
        CollectionInfo(
            name="documents",
            count=75,
            metadata={"description": "Main documents"},
        ),
        CollectionInfo(
            name="test_collection",
            count=0,
            metadata=None,
        ),
    ]


# =============================================================================
# CollectionInfo Tests
# =============================================================================

class TestCollectionInfo:
    """Tests for CollectionInfo dataclass."""
    
    def test_basic_creation(self) -> None:
        """Test basic CollectionInfo creation."""
        info = CollectionInfo(name="test_coll")
        
        assert info.name == "test_coll"
        assert info.count is None
        assert info.metadata is None
    
    def test_creation_with_all_fields(self) -> None:
        """Test CollectionInfo creation with all fields."""
        info = CollectionInfo(
            name="documents",
            count=100,
            metadata={"type": "pdf"},
        )
        
        assert info.name == "documents"
        assert info.count == 100
        assert info.metadata == {"type": "pdf"}
    
    def test_to_dict_minimal(self) -> None:
        """Test to_dict with minimal fields."""
        info = CollectionInfo(name="test")
        result = info.to_dict()
        
        assert result == {"name": "test"}
        assert "count" not in result
        assert "metadata" not in result
    
    def test_to_dict_with_count(self) -> None:
        """Test to_dict with count."""
        info = CollectionInfo(name="test", count=50)
        result = info.to_dict()
        
        assert result == {"name": "test", "count": 50}
    
    def test_to_dict_full(self) -> None:
        """Test to_dict with all fields."""
        info = CollectionInfo(
            name="docs",
            count=25,
            metadata={"source": "local"},
        )
        result = info.to_dict()
        
        assert result == {
            "name": "docs",
            "count": 25,
            "metadata": {"source": "local"},
        }
    
    def test_to_dict_empty_metadata(self) -> None:
        """Test to_dict with empty metadata dict."""
        info = CollectionInfo(name="test", metadata={})
        result = info.to_dict()
        
        # Empty metadata should not be included
        assert result == {"name": "test"}


# =============================================================================
# ListCollectionsConfig Tests
# =============================================================================

class TestListCollectionsConfig:
    """Tests for ListCollectionsConfig dataclass."""
    
    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ListCollectionsConfig()
        
        assert config.persist_directory == "./data/db/chroma"
        assert config.include_stats_default is True
    
    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ListCollectionsConfig(
            persist_directory="/custom/path",
            include_stats_default=False,
        )
        
        assert config.persist_directory == "/custom/path"
        assert config.include_stats_default is False


# =============================================================================
# ListCollectionsTool Initialization Tests
# =============================================================================

class TestListCollectionsToolInit:
    """Tests for ListCollectionsTool initialization."""
    
    def test_init_with_settings(self, mock_settings: Mock) -> None:
        """Test initialization with settings."""
        tool = ListCollectionsTool(settings=mock_settings)
        
        assert tool._settings == mock_settings
        assert tool._config is None
    
    def test_init_with_config(self, mock_config: ListCollectionsConfig) -> None:
        """Test initialization with explicit config."""
        tool = ListCollectionsTool(config=mock_config)
        
        assert tool._settings is None
        assert tool._config == mock_config
    
    def test_init_no_args(self) -> None:
        """Test initialization without arguments."""
        tool = ListCollectionsTool()
        
        assert tool._settings is None
        assert tool._config is None
    
    def test_settings_lazy_load(self) -> None:
        """Test that settings are loaded lazily."""
        tool = ListCollectionsTool()
        
        with patch('src.core.settings.load_settings') as mock_load:
            mock_settings = Mock()
            mock_load.return_value = mock_settings
            
            # Access settings property
            result = tool.settings
            
            mock_load.assert_called_once()
            assert result == mock_settings
    
    def test_config_derived_from_settings(self, mock_settings: Mock) -> None:
        """Test that config is derived from settings."""
        tool = ListCollectionsTool(settings=mock_settings)
        
        config = tool.config
        
        assert config.persist_directory == "./data/db/chroma"
    
    def test_config_fallback_no_vector_store(self) -> None:
        """Test config fallback when vector_store config missing."""
        settings = Mock(spec=[])  # No vector_store attribute
        tool = ListCollectionsTool(settings=settings)
        
        config = tool.config
        
        assert config.persist_directory == "./data/db/chroma"


# =============================================================================
# ListCollectionsTool ChromaDB Client Tests
# =============================================================================

class TestListCollectionsToolChromaClient:
    """Tests for ChromaDB client management."""
    
    def test_get_chroma_client_chromadb_not_installed(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test error when chromadb is not installed."""
        with patch.dict('sys.modules', {'chromadb': None}):
            with patch('builtins.__import__', side_effect=ImportError("No chromadb")):
                with pytest.raises(ImportError) as exc_info:
                    tool_with_config._get_chroma_client()
        
                assert "chromadb package is required" in str(exc_info.value)
    
    @patch('chromadb.PersistentClient')
    @patch('chromadb.config.Settings')
    def test_get_chroma_client_success(
        self,
        mock_chroma_settings: Mock,
        mock_client_class: Mock,
        tool_with_config: ListCollectionsTool,
        tmp_path: Path,
    ) -> None:
        """Test successful ChromaDB client creation."""
        # Update config to use temp path
        tool_with_config._config = ListCollectionsConfig(
            persist_directory=str(tmp_path / "chroma")
        )
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        result = tool_with_config._get_chroma_client()
        
        assert result == mock_client
        mock_client_class.assert_called_once()
    
    @patch('chromadb.PersistentClient')
    @patch('chromadb.config.Settings')
    def test_get_chroma_client_creates_directory(
        self,
        mock_chroma_settings: Mock,
        mock_client_class: Mock,
        tool_with_config: ListCollectionsTool,
        tmp_path: Path,
    ) -> None:
        """Test that missing directory is created."""
        new_path = tmp_path / "new_chroma_dir"
        tool_with_config._config = ListCollectionsConfig(
            persist_directory=str(new_path)
        )
        
        mock_client_class.return_value = Mock()
        
        tool_with_config._get_chroma_client()
        
        assert new_path.exists()
    
    @patch('chromadb.PersistentClient')
    @patch('chromadb.config.Settings')
    def test_get_chroma_client_init_failure(
        self,
        mock_chroma_settings: Mock,
        mock_client_class: Mock,
        tool_with_config: ListCollectionsTool,
        tmp_path: Path,
    ) -> None:
        """Test error handling when client init fails."""
        tool_with_config._config = ListCollectionsConfig(
            persist_directory=str(tmp_path)
        )
        
        mock_client_class.side_effect = Exception("Connection failed")
        
        with pytest.raises(RuntimeError) as exc_info:
            tool_with_config._get_chroma_client()
        
        assert "Failed to initialize ChromaDB client" in str(exc_info.value)


# =============================================================================
# ListCollectionsTool list_collections Method Tests
# =============================================================================

class TestListCollectionsMethod:
    """Tests for list_collections method."""
    
    def test_list_collections_empty(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test listing when no collections exist."""
        mock_client = Mock()
        mock_client.list_collections.return_value = []
        
        with patch.object(tool_with_config, '_get_chroma_client', return_value=mock_client):
            result = tool_with_config.list_collections()
        
        assert result == []
    
    def test_list_collections_with_stats(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test listing collections with statistics."""
        mock_coll1 = Mock()
        mock_coll1.name = "collection1"
        mock_coll1.metadata = {"type": "docs"}
        mock_coll1.count.return_value = 100
        
        mock_coll2 = Mock()
        mock_coll2.name = "collection2"
        mock_coll2.metadata = {}
        mock_coll2.count.return_value = 50
        
        mock_client = Mock()
        mock_client.list_collections.return_value = [mock_coll1, mock_coll2]
        
        with patch.object(tool_with_config, '_get_chroma_client', return_value=mock_client):
            result = tool_with_config.list_collections(include_stats=True)
        
        assert len(result) == 2
        assert result[0].name == "collection1"
        assert result[0].count == 100
        assert result[0].metadata == {"type": "docs"}
        assert result[1].name == "collection2"
        assert result[1].count == 50
    
    def test_list_collections_without_stats(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test listing collections without statistics."""
        mock_coll = Mock()
        mock_coll.name = "test"
        mock_coll.metadata = None
        
        mock_client = Mock()
        mock_client.list_collections.return_value = [mock_coll]
        
        with patch.object(tool_with_config, '_get_chroma_client', return_value=mock_client):
            result = tool_with_config.list_collections(include_stats=False)
        
        assert len(result) == 1
        assert result[0].name == "test"
        assert result[0].count is None  # Not fetched
        mock_coll.count.assert_not_called()
    
    def test_list_collections_count_error_graceful(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test graceful handling when count() fails."""
        mock_coll = Mock()
        mock_coll.name = "problematic"
        mock_coll.metadata = {}
        mock_coll.count.side_effect = Exception("Count failed")
        
        mock_client = Mock()
        mock_client.list_collections.return_value = [mock_coll]
        
        with patch.object(tool_with_config, '_get_chroma_client', return_value=mock_client):
            result = tool_with_config.list_collections(include_stats=True)
        
        # Should still return collection, but with None count
        assert len(result) == 1
        assert result[0].name == "problematic"
        assert result[0].count is None
    
    def test_list_collections_client_error(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test error handling when client fails."""
        with patch.object(
            tool_with_config,
            '_get_chroma_client',
            side_effect=RuntimeError("Client error")
        ):
            result = tool_with_config.list_collections()
        
        assert result == []
    
    def test_list_collections_list_error(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test error handling when list_collections fails."""
        mock_client = Mock()
        mock_client.list_collections.side_effect = Exception("List failed")
        
        with patch.object(tool_with_config, '_get_chroma_client', return_value=mock_client):
            result = tool_with_config.list_collections()
        
        assert result == []


# =============================================================================
# ListCollectionsTool format_response Method Tests
# =============================================================================

class TestFormatResponse:
    """Tests for format_response method."""
    
    def test_format_empty_collections(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test formatting empty collection list."""
        result = tool_with_config.format_response([])
        
        assert result == "No collections found in the knowledge base."
    
    def test_format_single_collection(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test formatting single collection."""
        collections = [CollectionInfo(name="docs", count=50)]
        result = tool_with_config.format_response(collections)
        
        assert "## Available Collections (1 total)" in result
        assert "1. **docs** - 50 documents" in result
    
    def test_format_multiple_collections(
        self,
        tool_with_config: ListCollectionsTool,
        sample_collections: List[CollectionInfo]
    ) -> None:
        """Test formatting multiple collections."""
        result = tool_with_config.format_response(sample_collections)
        
        assert "## Available Collections (3 total)" in result
        assert "1. **knowledge_hub** - 150 documents" in result
        assert "2. **documents** - 75 documents" in result
        assert "3. **test_collection** - 0 documents" in result
    
    def test_format_with_metadata(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test formatting with user metadata."""
        collections = [
            CollectionInfo(
                name="research",
                count=30,
                metadata={"category": "papers", "year": 2024},
            )
        ]
        result = tool_with_config.format_response(collections)
        
        assert "**research**" in result
        assert "30 documents" in result
        assert "category=papers" in result
        assert "year=2024" in result
    
    def test_format_filters_internal_metadata(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test that internal metadata is filtered out."""
        collections = [
            CollectionInfo(
                name="test",
                count=10,
                metadata={
                    "hnsw:space": "cosine",
                    "_internal": "value",
                    "user_field": "visible",
                },
            )
        ]
        result = tool_with_config.format_response(collections)
        
        # Internal metadata should be filtered
        assert "hnsw:space" not in result
        assert "_internal" not in result
        # User metadata should be visible
        assert "user_field=visible" in result
    
    def test_format_without_count(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test formatting when count is None."""
        collections = [CollectionInfo(name="no_count")]
        result = tool_with_config.format_response(collections)
        
        assert "1. **no_count**" in result
        assert "documents" not in result  # No count shown


# =============================================================================
# ListCollectionsTool execute Method Tests
# =============================================================================

class TestExecuteMethod:
    """Tests for async execute method."""
    
    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        tool_with_config: ListCollectionsTool,
        sample_collections: List[CollectionInfo]
    ) -> None:
        """Test successful execution."""
        with patch.object(
            tool_with_config,
            'list_collections',
            return_value=sample_collections
        ):
            result = await tool_with_config.execute(include_stats=True)
        
        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert "Available Collections (3 total)" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_execute_empty_result(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test execution with no collections."""
        with patch.object(tool_with_config, 'list_collections', return_value=[]):
            result = await tool_with_config.execute()
        
        assert result.isError is False
        assert "No collections found" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_execute_error(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test execution error handling."""
        with patch.object(
            tool_with_config,
            'list_collections',
            side_effect=Exception("Unexpected error")
        ):
            result = await tool_with_config.execute()
        
        assert result.isError is True
        assert "Error listing collections" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_execute_passes_include_stats(
        self,
        tool_with_config: ListCollectionsTool
    ) -> None:
        """Test that include_stats is passed correctly."""
        mock_list = Mock(return_value=[])
        
        with patch.object(tool_with_config, 'list_collections', mock_list):
            await tool_with_config.execute(include_stats=False)
        
        mock_list.assert_called_once_with(include_stats=False)


# =============================================================================
# register_tool Function Tests
# =============================================================================

class TestRegisterTool:
    """Tests for register_tool function."""
    
    def test_register_tool_success(self) -> None:
        """Test successful tool registration."""
        mock_handler = Mock()
        
        register_tool(mock_handler)
        
        mock_handler.register_tool.assert_called_once()
        call_args = mock_handler.register_tool.call_args
        
        assert call_args.kwargs['name'] == TOOL_NAME
        assert call_args.kwargs['description'] == TOOL_DESCRIPTION
        assert call_args.kwargs['input_schema'] == TOOL_INPUT_SCHEMA
        assert callable(call_args.kwargs['handler'])
    
    @pytest.mark.asyncio
    async def test_registered_handler_callable(self) -> None:
        """Test that registered handler is callable."""
        mock_handler = Mock()
        
        register_tool(mock_handler)
        
        # Get the registered handler
        handler = mock_handler.register_tool.call_args.kwargs['handler']
        
        # Mock the tool's execute method
        with patch.object(
            ListCollectionsTool,
            'execute',
            new_callable=AsyncMock
        ) as mock_execute:
            mock_result = Mock()
            mock_execute.return_value = mock_result
            
            result = await handler(include_stats=True)
            
            # Handler should have been called
            assert result == mock_result


# =============================================================================
# Tool Metadata Tests
# =============================================================================

class TestToolMetadata:
    """Tests for tool metadata constants."""
    
    def test_tool_name(self) -> None:
        """Test tool name constant."""
        assert TOOL_NAME == "list_collections"
    
    def test_tool_description_content(self) -> None:
        """Test tool description contains key info."""
        assert "collection" in TOOL_DESCRIPTION.lower()
        assert "knowledge base" in TOOL_DESCRIPTION.lower()
    
    def test_input_schema_structure(self) -> None:
        """Test input schema has correct structure."""
        assert TOOL_INPUT_SCHEMA["type"] == "object"
        assert "properties" in TOOL_INPUT_SCHEMA
        assert "include_stats" in TOOL_INPUT_SCHEMA["properties"]
    
    def test_input_schema_include_stats(self) -> None:
        """Test include_stats property schema."""
        prop = TOOL_INPUT_SCHEMA["properties"]["include_stats"]
        
        assert prop["type"] == "boolean"
        assert prop["default"] is True
        assert "description" in prop
    
    def test_no_required_params(self) -> None:
        """Test that no parameters are required."""
        assert TOOL_INPUT_SCHEMA["required"] == []
