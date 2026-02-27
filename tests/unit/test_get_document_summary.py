"""Unit tests for get_document_summary MCP tool.

This module tests the GetDocumentSummaryTool class that provides
document summary retrieval capabilities through the MCP protocol.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

from src.mcp_server.tools.get_document_summary import (
    GetDocumentSummaryTool,
    GetDocumentSummaryConfig,
    DocumentSummary,
    DocumentNotFoundError,
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
    settings.vector_store.collection_name = "test_collection"
    return settings


@pytest.fixture
def mock_config() -> GetDocumentSummaryConfig:
    """Create test configuration."""
    return GetDocumentSummaryConfig(
        persist_directory="./test_data/chroma",
        default_collection="test_collection",
        summary_max_length=200,
    )


@pytest.fixture
def tool_with_mock_settings(mock_settings: Mock) -> GetDocumentSummaryTool:
    """Create GetDocumentSummaryTool with mock settings."""
    return GetDocumentSummaryTool(settings=mock_settings)


@pytest.fixture
def tool_with_config(mock_config: GetDocumentSummaryConfig) -> GetDocumentSummaryTool:
    """Create GetDocumentSummaryTool with explicit config."""
    return GetDocumentSummaryTool(config=mock_config)


@pytest.fixture
def sample_chunks() -> List[Dict[str, Any]]:
    """Create sample chunk data for testing."""
    return [
        {
            'id': 'doc_abc123_0000_hash1',
            'text': '# Introduction\n\nThis is the first paragraph of the document.',
            'metadata': {
                'source_ref': 'doc_abc123',
                'source_path': '/docs/test.pdf',
                'chunk_index': 0,
                'title': 'Test Document Title',
                'doc_type': 'pdf',
            }
        },
        {
            'id': 'doc_abc123_0001_hash2',
            'text': 'This is the second chunk with more content.',
            'metadata': {
                'source_ref': 'doc_abc123',
                'source_path': '/docs/test.pdf',
                'chunk_index': 1,
                'doc_type': 'pdf',
            }
        },
        {
            'id': 'doc_abc123_0002_hash3',
            'text': 'Final chunk with conclusion.',
            'metadata': {
                'source_ref': 'doc_abc123',
                'source_path': '/docs/test.pdf',
                'chunk_index': 2,
                'doc_type': 'pdf',
            }
        },
    ]


@pytest.fixture
def mock_collection(sample_chunks: List[Dict[str, Any]]) -> Mock:
    """Create mock ChromaDB collection."""
    collection = Mock()
    
    # Setup get() method for source_ref search
    def mock_get(where=None, include=None):
        if where and where.get('source_ref') == 'doc_abc123':
            return {
                'ids': [c['id'] for c in sample_chunks],
                'documents': [c['text'] for c in sample_chunks],
                'metadatas': [c['metadata'] for c in sample_chunks],
            }
        return {'ids': [], 'documents': [], 'metadatas': []}
    
    collection.get = Mock(side_effect=mock_get)
    return collection


# =============================================================================
# Test: Tool Metadata Constants
# =============================================================================

class TestToolMetadata:
    """Tests for tool metadata constants."""
    
    def test_tool_name(self):
        """Test TOOL_NAME is correctly defined."""
        assert TOOL_NAME == "get_document_summary"
    
    def test_tool_description_not_empty(self):
        """Test TOOL_DESCRIPTION is not empty."""
        assert TOOL_DESCRIPTION
        assert len(TOOL_DESCRIPTION) > 50
    
    def test_tool_input_schema_structure(self):
        """Test TOOL_INPUT_SCHEMA has correct structure."""
        assert TOOL_INPUT_SCHEMA["type"] == "object"
        assert "properties" in TOOL_INPUT_SCHEMA
        assert "required" in TOOL_INPUT_SCHEMA
    
    def test_tool_input_schema_doc_id_required(self):
        """Test doc_id is a required parameter."""
        assert "doc_id" in TOOL_INPUT_SCHEMA["required"]
        assert "doc_id" in TOOL_INPUT_SCHEMA["properties"]
    
    def test_tool_input_schema_collection_optional(self):
        """Test collection is an optional parameter."""
        assert "collection" in TOOL_INPUT_SCHEMA["properties"]
        assert "collection" not in TOOL_INPUT_SCHEMA["required"]


# =============================================================================
# Test: DocumentSummary Dataclass
# =============================================================================

class TestDocumentSummary:
    """Tests for DocumentSummary dataclass."""
    
    def test_document_summary_creation(self):
        """Test basic DocumentSummary creation."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Test Title",
            summary="This is a summary.",
        )
        assert summary.doc_id == "doc_123"
        assert summary.title == "Test Title"
        assert summary.summary == "This is a summary."
    
    def test_document_summary_defaults(self):
        """Test DocumentSummary default values."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Title",
            summary="Summary",
        )
        assert summary.tags == []
        assert summary.source_path is None
        assert summary.chunk_count == 0
        assert summary.metadata == {}
    
    def test_document_summary_with_all_fields(self):
        """Test DocumentSummary with all fields populated."""
        summary = DocumentSummary(
            doc_id="doc_abc123",
            title="Full Document",
            summary="Complete summary.",
            tags=["python", "testing"],
            source_path="/docs/test.pdf",
            chunk_count=5,
            metadata={"author": "Test Author"},
        )
        assert summary.doc_id == "doc_abc123"
        assert summary.tags == ["python", "testing"]
        assert summary.source_path == "/docs/test.pdf"
        assert summary.chunk_count == 5
        assert summary.metadata["author"] == "Test Author"
    
    def test_document_summary_to_dict(self):
        """Test DocumentSummary.to_dict() method."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Test",
            summary="Summary",
            tags=["tag1"],
            source_path="/path/file.pdf",
            chunk_count=3,
            metadata={"key": "value"},
        )
        result = summary.to_dict()
        
        assert result["doc_id"] == "doc_123"
        assert result["title"] == "Test"
        assert result["summary"] == "Summary"
        assert result["tags"] == ["tag1"]
        assert result["source_path"] == "/path/file.pdf"
        assert result["chunk_count"] == 3
        assert result["metadata"] == {"key": "value"}


# =============================================================================
# Test: DocumentNotFoundError
# =============================================================================

class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError exception."""
    
    def test_error_with_doc_id_only(self):
        """Test error message with just doc_id."""
        error = DocumentNotFoundError("doc_123")
        assert "doc_123" in str(error)
        assert "not found" in str(error)
    
    def test_error_with_collection(self):
        """Test error message with doc_id and collection."""
        error = DocumentNotFoundError("doc_123", "my_collection")
        assert "doc_123" in str(error)
        assert "my_collection" in str(error)
    
    def test_error_attributes(self):
        """Test error has correct attributes."""
        error = DocumentNotFoundError("doc_xyz", "test_coll")
        assert error.doc_id == "doc_xyz"
        assert error.collection == "test_coll"


# =============================================================================
# Test: GetDocumentSummaryConfig
# =============================================================================

class TestGetDocumentSummaryConfig:
    """Tests for GetDocumentSummaryConfig dataclass."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = GetDocumentSummaryConfig()
        assert config.persist_directory == "./data/db/chroma"
        assert config.default_collection == "knowledge_hub"
        assert config.summary_max_length == 500
    
    def test_config_custom_values(self):
        """Test configuration with custom values."""
        config = GetDocumentSummaryConfig(
            persist_directory="/custom/path",
            default_collection="custom_collection",
            summary_max_length=200,
        )
        assert config.persist_directory == "/custom/path"
        assert config.default_collection == "custom_collection"
        assert config.summary_max_length == 200


# =============================================================================
# Test: GetDocumentSummaryTool Initialization
# =============================================================================

class TestGetDocumentSummaryToolInit:
    """Tests for GetDocumentSummaryTool initialization."""
    
    def test_init_with_settings(self, mock_settings: Mock):
        """Test initialization with settings."""
        tool = GetDocumentSummaryTool(settings=mock_settings)
        assert tool._settings is mock_settings
        assert tool._config is None
    
    def test_init_with_config(self, mock_config: GetDocumentSummaryConfig):
        """Test initialization with explicit config."""
        tool = GetDocumentSummaryTool(config=mock_config)
        assert tool._config is mock_config
        assert tool._settings is None
    
    def test_init_with_both(self, mock_settings: Mock, mock_config: GetDocumentSummaryConfig):
        """Test initialization with both settings and config."""
        tool = GetDocumentSummaryTool(settings=mock_settings, config=mock_config)
        assert tool._settings is mock_settings
        assert tool._config is mock_config
    
    def test_init_with_defaults(self):
        """Test initialization with no parameters."""
        tool = GetDocumentSummaryTool()
        assert tool._settings is None
        assert tool._config is None


# =============================================================================
# Test: Settings Property
# =============================================================================

class TestSettingsProperty:
    """Tests for the settings property lazy loading."""
    
    def test_settings_returns_provided_settings(self, mock_settings: Mock):
        """Test that provided settings are returned."""
        tool = GetDocumentSummaryTool(settings=mock_settings)
        assert tool.settings is mock_settings
    
    @patch("src.core.settings.load_settings")
    def test_settings_lazy_loads_when_none(self, mock_load: Mock):
        """Test that settings are loaded lazily when not provided."""
        mock_loaded = Mock()
        mock_load.return_value = mock_loaded
        
        tool = GetDocumentSummaryTool()
        result = tool.settings
        
        mock_load.assert_called_once()
        assert result is mock_loaded


# =============================================================================
# Test: Config Property
# =============================================================================

class TestConfigProperty:
    """Tests for the config property."""
    
    def test_config_returns_provided_config(self, mock_config: GetDocumentSummaryConfig):
        """Test that provided config is returned."""
        tool = GetDocumentSummaryTool(config=mock_config)
        assert tool.config is mock_config
    
    def test_config_derived_from_settings(self, mock_settings: Mock):
        """Test that config is derived from settings when not provided."""
        mock_settings.vector_store.persist_directory = "/settings/path"
        mock_settings.vector_store.collection_name = "settings_collection"
        
        tool = GetDocumentSummaryTool(settings=mock_settings)
        config = tool.config
        
        assert config.persist_directory == "/settings/path"
        assert config.default_collection == "settings_collection"
    
    def test_config_uses_defaults_on_missing_attributes(self):
        """Test that config uses defaults when settings attributes are missing."""
        settings = Mock()
        settings.vector_store = None  # Will cause AttributeError
        
        tool = GetDocumentSummaryTool(settings=settings)
        config = tool.config
        
        assert config.persist_directory == "./data/db/chroma"
        assert config.default_collection == "knowledge_hub"


# =============================================================================
# Test: Title Extraction
# =============================================================================

class TestTitleExtraction:
    """Tests for _extract_title method."""
    
    def test_title_from_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test title extraction from metadata."""
        metadata = {"title": "Explicit Title"}
        result = tool_with_config._extract_title(metadata, "")
        assert result == "Explicit Title"
    
    def test_title_from_markdown_heading(self, tool_with_config: GetDocumentSummaryTool):
        """Test title extraction from markdown heading."""
        metadata = {}
        text = "# Document Title\n\nContent here"
        result = tool_with_config._extract_title(metadata, text)
        assert result == "Document Title"
    
    def test_title_from_source_path(self, tool_with_config: GetDocumentSummaryTool):
        """Test title extraction from source_path."""
        metadata = {"source_path": "/docs/my_test_document.pdf"}
        result = tool_with_config._extract_title(metadata, "")
        assert result == "My Test Document"
    
    def test_title_from_source_key(self, tool_with_config: GetDocumentSummaryTool):
        """Test title extraction from 'source' key."""
        metadata = {"source": "/docs/another-document.pdf"}
        result = tool_with_config._extract_title(metadata, "")
        assert result == "Another Document"
    
    def test_title_default_untitled(self, tool_with_config: GetDocumentSummaryTool):
        """Test default title when nothing available."""
        result = tool_with_config._extract_title({}, "")
        assert result == "Untitled Document"
    
    def test_title_priority_metadata_over_heading(self, tool_with_config: GetDocumentSummaryTool):
        """Test that metadata title has priority over markdown heading."""
        metadata = {"title": "Metadata Title"}
        text = "# Markdown Title\n\nContent"
        result = tool_with_config._extract_title(metadata, text)
        assert result == "Metadata Title"


# =============================================================================
# Test: Summary Extraction
# =============================================================================

class TestSummaryExtraction:
    """Tests for _extract_summary method."""
    
    def test_summary_from_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test summary extraction from metadata."""
        chunks = [{'metadata': {'summary': 'Explicit summary'}, 'text': 'Content'}]
        result = tool_with_config._extract_summary(chunks)
        assert result == "Explicit summary"
    
    def test_summary_from_first_chunk_text(self, tool_with_config: GetDocumentSummaryTool):
        """Test summary extraction from first chunk content."""
        chunks = [{'metadata': {}, 'text': 'This is the document content.'}]
        result = tool_with_config._extract_summary(chunks)
        assert "This is the document content" in result
    
    def test_summary_skips_headers(self, tool_with_config: GetDocumentSummaryTool):
        """Test that summary skips markdown headers."""
        chunks = [{'metadata': {}, 'text': '# Title\n\n## Section\n\nActual content here.'}]
        result = tool_with_config._extract_summary(chunks)
        assert "Actual content here" in result
        assert "# Title" not in result
    
    def test_summary_truncation(self, tool_with_config: GetDocumentSummaryTool):
        """Test summary is truncated to max length."""
        long_text = "A" * 1000
        chunks = [{'metadata': {}, 'text': long_text}]
        result = tool_with_config._extract_summary(chunks)
        assert len(result) <= tool_with_config.config.summary_max_length
        assert result.endswith("...")
    
    def test_summary_empty_chunks(self, tool_with_config: GetDocumentSummaryTool):
        """Test summary with empty chunks list."""
        result = tool_with_config._extract_summary([])
        assert result == "No summary available."
    
    def test_summary_no_content(self, tool_with_config: GetDocumentSummaryTool):
        """Test summary when chunk has no text."""
        chunks = [{'metadata': {}, 'text': ''}]
        result = tool_with_config._extract_summary(chunks)
        assert "No" in result or "available" in result


# =============================================================================
# Test: Tags Extraction
# =============================================================================

class TestTagsExtraction:
    """Tests for _extract_tags method."""
    
    def test_tags_from_list(self, tool_with_config: GetDocumentSummaryTool):
        """Test tags extraction from list."""
        metadata = {'tags': ['python', 'testing', 'docs']}
        result = tool_with_config._extract_tags(metadata)
        assert 'python' in result
        assert 'testing' in result
        assert 'docs' in result
    
    def test_tags_from_comma_string(self, tool_with_config: GetDocumentSummaryTool):
        """Test tags extraction from comma-separated string."""
        metadata = {'tags': 'python, testing, docs'}
        result = tool_with_config._extract_tags(metadata)
        assert 'python' in result
        assert 'testing' in result
        assert 'docs' in result
    
    def test_tags_includes_doc_type(self, tool_with_config: GetDocumentSummaryTool):
        """Test that doc_type is added as a tag."""
        metadata = {'doc_type': 'pdf'}
        result = tool_with_config._extract_tags(metadata)
        assert 'PDF' in result
    
    def test_tags_no_duplicate_doc_type(self, tool_with_config: GetDocumentSummaryTool):
        """Test that doc_type is not duplicated if already in tags."""
        metadata = {'tags': ['PDF', 'other'], 'doc_type': 'pdf'}
        result = tool_with_config._extract_tags(metadata)
        assert result.count('PDF') == 1
    
    def test_tags_empty_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test tags extraction with no tag-related metadata."""
        result = tool_with_config._extract_tags({})
        assert result == []


# =============================================================================
# Test: Metadata Filtering
# =============================================================================

class TestMetadataFiltering:
    """Tests for _filter_metadata method."""
    
    def test_filter_removes_internal_fields(self, tool_with_config: GetDocumentSummaryTool):
        """Test that internal fields are removed."""
        metadata = {
            'source_ref': 'doc_123',
            'chunk_index': 0,
            'start_offset': 0,
            'end_offset': 100,
            'author': 'Test Author',
        }
        result = tool_with_config._filter_metadata(metadata)
        
        assert 'source_ref' not in result
        assert 'chunk_index' not in result
        assert 'author' in result
    
    def test_filter_removes_underscore_prefix(self, tool_with_config: GetDocumentSummaryTool):
        """Test that underscore-prefixed fields are removed."""
        metadata = {
            '_placeholder': 'true',
            '_internal': 'value',
            'public_field': 'value',
        }
        result = tool_with_config._filter_metadata(metadata)
        
        assert '_placeholder' not in result
        assert '_internal' not in result
        assert 'public_field' in result
    
    def test_filter_keeps_user_fields(self, tool_with_config: GetDocumentSummaryTool):
        """Test that user-relevant fields are kept."""
        metadata = {
            'author': 'John Doe',
            'created_date': '2025-01-01',
            'page_count': 10,
        }
        result = tool_with_config._filter_metadata(metadata)
        
        assert result['author'] == 'John Doe'
        assert result['created_date'] == '2025-01-01'
        assert result['page_count'] == 10


# =============================================================================
# Test: ChromaDB Integration
# =============================================================================

class TestChromaDBIntegration:
    """Tests for ChromaDB client and collection methods."""
    
    def test_get_chroma_client_success(self, tool_with_config: GetDocumentSummaryTool):
        """Test successful ChromaDB client creation with mocked import."""
        mock_client = Mock()
        mock_chromadb = Mock()
        mock_chromadb.PersistentClient.return_value = mock_client
        
        with patch.dict('sys.modules', {'chromadb': mock_chromadb, 'chromadb.config': Mock()}):
            # Reset client cache
            tool_with_config._chroma_client = None
            result = tool_with_config._get_chroma_client()
        
        assert result is mock_client
        mock_chromadb.PersistentClient.assert_called_once()
    
    def test_get_chroma_client_import_error(self, tool_with_config: GetDocumentSummaryTool):
        """Test ImportError when chromadb not installed."""
        # Reset cached client
        tool_with_config._chroma_client = None
        
        with patch.dict('sys.modules', {'chromadb': None}):
            with pytest.raises(ImportError) as exc_info:
                tool_with_config._get_chroma_client()
        
            assert "chromadb" in str(exc_info.value)
    
    def test_get_collection_success(self, tool_with_config: GetDocumentSummaryTool):
        """Test successful collection retrieval."""
        mock_client = Mock()
        mock_collection = Mock()
        mock_client.get_collection.return_value = mock_collection
        
        # Mock _get_chroma_client to return our mock client
        tool_with_config._get_chroma_client = Mock(return_value=mock_client)
        
        result = tool_with_config._get_collection("test_collection")
        
        assert result is mock_collection
        mock_client.get_collection.assert_called_once_with(name="test_collection")
    
    def test_get_collection_not_found(self, tool_with_config: GetDocumentSummaryTool):
        """Test error when collection doesn't exist."""
        mock_client = Mock()
        mock_client.get_collection.side_effect = Exception("Collection not found")
        
        # Mock _get_chroma_client to return our mock client
        tool_with_config._get_chroma_client = Mock(return_value=mock_client)
        
        with pytest.raises(ValueError) as exc_info:
            tool_with_config._get_collection("nonexistent")
        
        assert "nonexistent" in str(exc_info.value)


# =============================================================================
# Test: Document Chunk Finding
# =============================================================================

class TestFindDocumentChunks:
    """Tests for _find_document_chunks method."""
    
    def test_find_chunks_by_source_ref(
        self, 
        tool_with_config: GetDocumentSummaryTool,
        sample_chunks: List[Dict[str, Any]],
    ):
        """Test finding chunks by source_ref metadata."""
        mock_collection = Mock()
        mock_collection.get.return_value = {
            'ids': [c['id'] for c in sample_chunks],
            'documents': [c['text'] for c in sample_chunks],
            'metadatas': [c['metadata'] for c in sample_chunks],
        }
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = tool_with_config._find_document_chunks("doc_abc123")
        
        assert len(result) == 3
        mock_collection.get.assert_called()
    
    def test_find_chunks_by_id_prefix(
        self, 
        tool_with_config: GetDocumentSummaryTool,
        sample_chunks: List[Dict[str, Any]],
    ):
        """Test finding chunks by ID prefix when source_ref search fails."""
        mock_collection = Mock()
        
        # First call (source_ref search) returns empty
        # Second call (get all) returns all chunks
        mock_collection.get.side_effect = [
            {'ids': [], 'documents': [], 'metadatas': []},
            {
                'ids': [c['id'] for c in sample_chunks],
                'documents': [c['text'] for c in sample_chunks],
                'metadatas': [c['metadata'] for c in sample_chunks],
            },
        ]
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = tool_with_config._find_document_chunks("doc_abc123")
        
        assert len(result) == 3
    
    def test_find_chunks_not_found(
        self, 
        tool_with_config: GetDocumentSummaryTool,
    ):
        """Test empty result when no chunks found."""
        mock_collection = Mock()
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = tool_with_config._find_document_chunks("nonexistent_doc")
        
        assert result == []


# =============================================================================
# Test: get_document_summary Method
# =============================================================================

class TestGetDocumentSummary:
    """Tests for get_document_summary method."""
    
    def test_get_summary_success(
        self, 
        tool_with_config: GetDocumentSummaryTool,
        sample_chunks: List[Dict[str, Any]],
    ):
        """Test successful document summary retrieval."""
        mock_collection = Mock()
        mock_collection.get.return_value = {
            'ids': [c['id'] for c in sample_chunks],
            'documents': [c['text'] for c in sample_chunks],
            'metadatas': [c['metadata'] for c in sample_chunks],
        }
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = tool_with_config.get_document_summary("doc_abc123")
        
        assert isinstance(result, DocumentSummary)
        assert result.doc_id == "doc_abc123"
        assert result.title == "Test Document Title"
        assert result.chunk_count == 3
        assert result.source_path == "/docs/test.pdf"
        assert "PDF" in result.tags
    
    def test_get_summary_not_found(
        self, 
        tool_with_config: GetDocumentSummaryTool,
    ):
        """Test DocumentNotFoundError when document doesn't exist."""
        mock_collection = Mock()
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        with pytest.raises(DocumentNotFoundError) as exc_info:
            tool_with_config.get_document_summary("nonexistent_doc")
        
        assert exc_info.value.doc_id == "nonexistent_doc"
    
    def test_get_summary_chunks_sorted_by_index(
        self, 
        tool_with_config: GetDocumentSummaryTool,
    ):
        """Test that chunks are sorted by chunk_index."""
        # Provide chunks in wrong order
        unsorted_chunks = [
            {'id': 'c2', 'text': 'Second', 'metadata': {'chunk_index': 1, 'source_path': '/doc.pdf'}},
            {'id': 'c0', 'text': '# Title\nFirst', 'metadata': {'chunk_index': 0, 'source_path': '/doc.pdf'}},
            {'id': 'c1', 'text': 'Middle', 'metadata': {'chunk_index': 2, 'source_path': '/doc.pdf'}},
        ]
        
        mock_collection = Mock()
        mock_collection.get.return_value = {
            'ids': [c['id'] for c in unsorted_chunks],
            'documents': [c['text'] for c in unsorted_chunks],
            'metadatas': [c['metadata'] for c in unsorted_chunks],
        }
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = tool_with_config.get_document_summary("doc_test")
        
        # Title should be extracted from first chunk (chunk_index=0)
        assert result.title == "Title"


# =============================================================================
# Test: Response Formatting
# =============================================================================

class TestFormatResponse:
    """Tests for format_response method."""
    
    def test_format_response_includes_title(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatted response includes title."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Test Title",
            summary="Test summary",
        )
        result = tool_with_config.format_response(summary)
        
        assert "Test Title" in result
    
    def test_format_response_includes_doc_id(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatted response includes doc_id."""
        summary = DocumentSummary(
            doc_id="doc_abc123",
            title="Title",
            summary="Summary",
        )
        result = tool_with_config.format_response(summary)
        
        assert "doc_abc123" in result
    
    def test_format_response_includes_tags(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatted response includes tags."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Title",
            summary="Summary",
            tags=["python", "testing"],
        )
        result = tool_with_config.format_response(summary)
        
        assert "python" in result
        assert "testing" in result
    
    def test_format_response_includes_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatted response includes additional metadata."""
        summary = DocumentSummary(
            doc_id="doc_123",
            title="Title",
            summary="Summary",
            metadata={"author": "John Doe"},
        )
        result = tool_with_config.format_response(summary)
        
        assert "author" in result
        assert "John Doe" in result


# =============================================================================
# Test: Error Formatting
# =============================================================================

class TestFormatError:
    """Tests for format_error method."""
    
    def test_format_document_not_found_error(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatting DocumentNotFoundError."""
        error = DocumentNotFoundError("doc_123", "test_collection")
        result = tool_with_config.format_error(error)
        
        assert "Not Found" in result
        assert "doc_123" in result
    
    def test_format_value_error(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatting ValueError."""
        error = ValueError("Invalid parameter")
        result = tool_with_config.format_error(error)
        
        assert "Invalid" in result
    
    def test_format_generic_error(self, tool_with_config: GetDocumentSummaryTool):
        """Test formatting generic exception."""
        error = RuntimeError("Something went wrong")
        result = tool_with_config.format_error(error)
        
        assert "Error" in result
        assert "Something went wrong" in result


# =============================================================================
# Test: Execute Method (Async)
# =============================================================================

class TestExecuteMethod:
    """Tests for execute async method."""
    
    @pytest.mark.asyncio
    async def test_execute_success(
        self, 
        tool_with_config: GetDocumentSummaryTool,
        sample_chunks: List[Dict[str, Any]],
    ):
        """Test successful execution returns proper result."""
        mock_collection = Mock()
        mock_collection.get.return_value = {
            'ids': [c['id'] for c in sample_chunks],
            'documents': [c['text'] for c in sample_chunks],
            'metadatas': [c['metadata'] for c in sample_chunks],
        }
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = await tool_with_config.execute(doc_id="doc_abc123")
        
        assert result.isError is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert "Test Document Title" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_execute_document_not_found(
        self, 
        tool_with_config: GetDocumentSummaryTool,
    ):
        """Test execution with non-existent document."""
        mock_collection = Mock()
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}
        
        # Mock the _get_collection method
        tool_with_config._get_collection = Mock(return_value=mock_collection)
        
        result = await tool_with_config.execute(doc_id="nonexistent")
        
        assert result.isError is True
        assert "Not Found" in result.content[0].text
    
    @pytest.mark.asyncio
    async def test_execute_with_collection(
        self, 
        tool_with_config: GetDocumentSummaryTool,
        sample_chunks: List[Dict[str, Any]],
    ):
        """Test execution with specific collection."""
        mock_collection = Mock()
        mock_collection.get.return_value = {
            'ids': [c['id'] for c in sample_chunks],
            'documents': [c['text'] for c in sample_chunks],
            'metadatas': [c['metadata'] for c in sample_chunks],
        }
        
        # Mock the _get_collection method to verify collection name
        mock_get_collection = Mock(return_value=mock_collection)
        tool_with_config._get_collection = mock_get_collection
        
        result = await tool_with_config.execute(
            doc_id="doc_abc123",
            collection="custom_collection"
        )
        
        assert result.isError is False
        # Verify _get_collection was called (via _find_document_chunks)
        mock_get_collection.assert_called()


# =============================================================================
# Test: Tool Registration
# =============================================================================

class TestRegisterTool:
    """Tests for register_tool function."""
    
    def test_register_tool_calls_register(self):
        """Test that register_tool calls protocol_handler.register_tool."""
        mock_handler = Mock()
        
        register_tool(mock_handler)
        
        mock_handler.register_tool.assert_called_once()
        call_kwargs = mock_handler.register_tool.call_args
        assert call_kwargs[1]['name'] == TOOL_NAME
        assert call_kwargs[1]['description'] == TOOL_DESCRIPTION
        assert call_kwargs[1]['input_schema'] == TOOL_INPUT_SCHEMA
    
    def test_register_tool_handler_callable(self):
        """Test that registered handler is callable."""
        mock_handler = Mock()
        
        register_tool(mock_handler)
        
        call_kwargs = mock_handler.register_tool.call_args
        handler = call_kwargs[1]['handler']
        assert callable(handler)


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_empty_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test handling of empty metadata."""
        title = tool_with_config._extract_title({}, "")
        assert title == "Untitled Document"
        
        tags = tool_with_config._extract_tags({})
        assert tags == []
        
        filtered = tool_with_config._filter_metadata({})
        assert filtered == {}
    
    def test_none_values_in_metadata(self, tool_with_config: GetDocumentSummaryTool):
        """Test handling of None values in metadata."""
        metadata = {'title': None, 'source_path': None}
        title = tool_with_config._extract_title(metadata, "Content")
        # Should fall through to content-based extraction
        assert title is not None
    
    def test_unicode_content(self, tool_with_config: GetDocumentSummaryTool):
        """Test handling of Unicode content."""
        metadata = {'title': '中文标题'}
        result = tool_with_config._extract_title(metadata, "")
        assert result == '中文标题'
        
        chunks = [{'metadata': {}, 'text': '这是中文内容。'}]
        summary = tool_with_config._extract_summary(chunks)
        assert '这是中文内容' in summary
    
    def test_special_characters_in_path(self, tool_with_config: GetDocumentSummaryTool):
        """Test handling of special characters in source path."""
        metadata = {'source_path': '/docs/file (1).pdf'}
        title = tool_with_config._extract_title(metadata, "")
        assert "File" in title
    
    def test_very_long_summary_truncation(self, tool_with_config: GetDocumentSummaryTool):
        """Test that very long content is properly truncated."""
        long_content = "Word " * 1000
        chunks = [{'metadata': {}, 'text': long_content}]
        summary = tool_with_config._extract_summary(chunks)
        
        assert len(summary) <= tool_with_config.config.summary_max_length
        assert summary.endswith("...")
    
    def test_client_cached(self, tool_with_config: GetDocumentSummaryTool):
        """Test that ChromaDB client is cached after first creation."""
        mock_client = Mock()
        mock_chromadb = Mock()
        mock_chromadb.PersistentClient.return_value = mock_client
        
        with patch.dict('sys.modules', {'chromadb': mock_chromadb, 'chromadb.config': Mock()}):
            # Reset client cache
            tool_with_config._chroma_client = None
            
            # Call twice
            result1 = tool_with_config._get_chroma_client()
            result2 = tool_with_config._get_chroma_client()
            
            # Should only create once
            assert mock_chromadb.PersistentClient.call_count == 1
            assert result1 is result2
