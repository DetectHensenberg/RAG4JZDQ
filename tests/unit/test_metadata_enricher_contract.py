"""Contract tests for MetadataEnricher transform."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from src.ingestion.transform.metadata_enricher import MetadataEnricher
from src.core.types import Chunk
from src.core.settings import Settings
from src.core.trace.trace_context import TraceContext
from src.libs.llm.base_llm import Message


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_settings_llm_disabled():
    """Settings with LLM disabled."""
    settings = Mock(spec=Settings)
    settings.ingestion = Mock()
    settings.ingestion.metadata_enricher = {'use_llm': False}
    return settings


@pytest.fixture
def mock_settings_llm_enabled():
    """Settings with LLM enabled."""
    settings = Mock(spec=Settings)
    settings.ingestion = Mock()
    settings.ingestion.metadata_enricher = {'use_llm': True}
    settings.llm = Mock()
    settings.llm.provider = 'openai'
    return settings


@pytest.fixture
def sample_chunk_simple():
    """Simple text chunk."""
    return Chunk(
        id="chunk_001",
        text="This is a test document about Python programming. It covers basic concepts.",
        metadata={"source_path": "test.pdf"},
        source_ref="test.pdf#page1"
    )


@pytest.fixture
def sample_chunk_with_heading():
    """Chunk with markdown heading."""
    return Chunk(
        id="chunk_002",
        text="# Introduction to Machine Learning\n\nMachine learning is a subset of artificial intelligence. It enables systems to learn from data.",
        metadata={"source_path": "ml.pdf"},
        source_ref="ml.pdf#page1"
    )


@pytest.fixture
def sample_chunk_with_code():
    """Chunk with code identifiers."""
    return Chunk(
        id="chunk_003",
        text="The getUserById function retrieves user data. It uses async_fetch and handles errors gracefully.",
        metadata={"source_path": "code.md"},
        source_ref="code.md#section2"
    )


@pytest.fixture
def temp_prompt_file(tmp_path):
    """Create temporary prompt file."""
    prompt_file = tmp_path / "test_prompt.txt"
    prompt_file.write_text(
        "Analyze this text:\n{chunk_text}\n\n"
        "Title: <title>\nSummary: <summary>\nTags: <tags>"
    )
    return str(prompt_file)


# ============================================================================
# Rule-Based Enrichment Tests
# ============================================================================

class TestRuleBasedEnrichment:
    """Test rule-based metadata extraction."""
    
    def test_extract_title_from_heading(self, mock_settings_llm_disabled, sample_chunk_with_heading):
        """Should extract title from markdown heading."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_with_heading])
        
        assert len(result) == 1
        assert result[0].metadata['title'] == "Introduction to Machine Learning"
        assert result[0].metadata['enriched_by'] == "rule"
    
    def test_extract_title_from_first_line(self, mock_settings_llm_disabled):
        """Should use first line as title if short and appropriate."""
        chunk = Chunk(
            id="chunk_004",
            text="Quick Start Guide\n\nFollow these steps to get started.",
            metadata={"source_path": "guide.md"},
            source_ref="guide.md"
        )
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([chunk])
        
        assert result[0].metadata['title'] == "Quick Start Guide"
    
    def test_extract_title_from_sentence(self, mock_settings_llm_disabled, sample_chunk_simple):
        """Should extract first sentence as title."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_simple])
        
        # Title should be first sentence without trailing period
        assert result[0].metadata['title'] == "This is a test document about Python programming"
    
    def test_extract_summary_from_text(self, mock_settings_llm_disabled, sample_chunk_with_heading):
        """Should generate summary from first few sentences."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_with_heading])
        
        assert result[0].metadata['summary']
        assert len(result[0].metadata['summary']) > 0
        assert "Machine learning" in result[0].metadata['summary']
    
    def test_extract_tags_from_capitalized_words(self, mock_settings_llm_disabled, sample_chunk_with_heading):
        """Should extract capitalized words as tags."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_with_heading])
        
        assert 'tags' in result[0].metadata
        tags = result[0].metadata['tags']
        assert isinstance(tags, list)
        # Should find "Machine" or "Learning" or "Introduction"
        assert any(tag in ['Machine', 'Learning', 'Introduction'] for tag in tags)
    
    def test_extract_tags_from_code_identifiers(self, mock_settings_llm_disabled, sample_chunk_with_code):
        """Should extract code identifiers as tags."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_with_code])
        
        tags = result[0].metadata['tags']
        # Should find async_fetch
        assert 'async_fetch' in tags or 'getUserById' in tags
    
    def test_metadata_preserved(self, mock_settings_llm_disabled, sample_chunk_simple):
        """Should preserve existing metadata."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_simple])
        
        assert result[0].metadata['source_path'] == "test.pdf"
        assert 'title' in result[0].metadata
        assert 'summary' in result[0].metadata
        assert 'tags' in result[0].metadata
    
    def test_empty_text_handling(self, mock_settings_llm_disabled):
        """Should handle empty text gracefully."""
        chunk = Chunk(
            id="chunk_empty",
            text="",
            metadata={"source_path": "empty.txt"},
            source_ref="empty.txt"
        )
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([chunk])
        
        assert len(result) == 1
        assert result[0].metadata['title'] == "Untitled"
        assert result[0].metadata['summary'] == ""
        assert result[0].metadata['tags'] == []


# ============================================================================
# Transform Pipeline Tests
# ============================================================================

class TestTransformPipeline:
    """Test the complete transform pipeline."""
    
    def test_transform_single_chunk(self, mock_settings_llm_disabled, sample_chunk_simple):
        """Should enrich a single chunk."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([sample_chunk_simple])
        
        assert len(result) == 1
        assert result[0].id == sample_chunk_simple.id
        assert result[0].text == sample_chunk_simple.text  # Text unchanged
        assert 'title' in result[0].metadata
        assert 'summary' in result[0].metadata
        assert 'tags' in result[0].metadata
        assert result[0].metadata['enriched_by'] == "rule"
    
    def test_transform_multiple_chunks(self, mock_settings_llm_disabled):
        """Should enrich multiple chunks independently."""
        chunks = [
            Chunk(id=f"chunk_{i}", text=f"Content {i}", metadata={"source_path": f"doc{i}.txt"}, source_ref=f"doc{i}.txt")
            for i in range(5)
        ]
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform(chunks)
        
        assert len(result) == 5
        for i, chunk in enumerate(result):
            assert chunk.id == f"chunk_{i}"
            assert 'title' in chunk.metadata
            assert 'summary' in chunk.metadata
            assert 'tags' in chunk.metadata
    
    def test_transform_empty_list(self, mock_settings_llm_disabled):
        """Should handle empty chunk list."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        result = enricher.transform([])
        
        assert result == []
    
    def test_trace_recording(self, mock_settings_llm_disabled, sample_chunk_simple):
        """Should record processing info in trace context."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        trace = TraceContext(trace_id="test_trace")
        
        enricher.transform([sample_chunk_simple], trace=trace)
        
        # Check trace was recorded
        assert len(trace.stages) > 0
        stage_data = trace.get_stage_data('metadata_enricher')
        assert stage_data is not None
        assert stage_data['total_chunks'] == 1
        assert stage_data['success_count'] == 1


# ============================================================================
# LLM Enhancement Tests
# ============================================================================

class TestLLMEnhancement:
    """Test LLM-based metadata enrichment."""
    
    def test_llm_success_path(self, mock_settings_llm_enabled, sample_chunk_simple, temp_prompt_file):
        """Should use LLM when enabled and successful."""
        mock_llm = Mock()
        mock_llm.chat.return_value = (
            "Title: Python Programming Guide\n"
            "Summary: A comprehensive guide to Python programming covering basic concepts and syntax.\n"
            "Tags: Python, programming, basics, tutorial"
        )
        
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            llm=mock_llm,
            prompt_path=temp_prompt_file
        )
        
        result = enricher.transform([sample_chunk_simple])
        
        assert len(result) == 1
        assert result[0].metadata['title'] == "Python Programming Guide"
        assert "comprehensive guide" in result[0].metadata['summary']
        assert "Python" in result[0].metadata['tags']
        assert result[0].metadata['enriched_by'] == "llm"
        mock_llm.chat.assert_called_once()
    
    def test_llm_fallback_on_failure(self, mock_settings_llm_enabled, sample_chunk_simple, temp_prompt_file):
        """Should fallback to rule-based on LLM failure."""
        mock_llm = Mock()
        mock_llm.chat.side_effect = Exception("API Error")
        
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            llm=mock_llm,
            prompt_path=temp_prompt_file
        )
        
        result = enricher.transform([sample_chunk_simple])
        
        assert len(result) == 1
        assert result[0].metadata['enriched_by'] == "rule"
        assert 'enrich_fallback_reason' in result[0].metadata
        assert result[0].metadata['enrich_fallback_reason'] == "llm_failed"
        # Should still have valid metadata from rule-based
        assert result[0].metadata['title']
        assert result[0].metadata['summary']
    
    def test_llm_fallback_on_empty_response(self, mock_settings_llm_enabled, sample_chunk_simple, temp_prompt_file):
        """Should fallback to rule-based when LLM returns empty response."""
        mock_llm = Mock()
        mock_llm.chat.return_value = ""
        
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            llm=mock_llm,
            prompt_path=temp_prompt_file
        )
        
        result = enricher.transform([sample_chunk_simple])
        
        assert result[0].metadata['enriched_by'] == "rule"
        assert 'enrich_fallback_reason' in result[0].metadata
    
    def test_llm_trace_recording(self, mock_settings_llm_enabled, sample_chunk_simple, temp_prompt_file):
        """Should record LLM calls in trace context."""
        mock_llm = Mock()
        mock_llm.chat.return_value = (
            "Title: Test\nSummary: Test summary\nTags: test"
        )
        
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            llm=mock_llm,
            prompt_path=temp_prompt_file
        )
        trace = TraceContext(trace_id="test_llm_trace")
        
        enricher.transform([sample_chunk_simple], trace=trace)
        
        # Should have both llm_enrich and metadata_enricher stages
        assert trace.get_stage_data('llm_enrich') is not None
        assert trace.get_stage_data('metadata_enricher') is not None


# ============================================================================
# Prompt Loading Tests
# ============================================================================

class TestPromptLoading:
    """Test prompt template loading."""
    
    def test_load_existing_prompt(self, mock_settings_llm_enabled, temp_prompt_file):
        """Should load prompt from file."""
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            prompt_path=temp_prompt_file
        )
        
        prompt = enricher._load_prompt()
        
        assert prompt
        assert "{chunk_text}" in prompt
    
    def test_prompt_cached_after_first_load(self, mock_settings_llm_enabled, temp_prompt_file):
        """Should cache prompt after first load."""
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            prompt_path=temp_prompt_file
        )
        
        prompt1 = enricher._load_prompt()
        prompt2 = enricher._load_prompt()
        
        assert prompt1 is prompt2  # Same object (cached)
    
    def test_missing_prompt_file(self, mock_settings_llm_enabled):
        """Should raise FileNotFoundError for missing prompt."""
        enricher = MetadataEnricher(
            mock_settings_llm_enabled,
            prompt_path="/nonexistent/prompt.txt"
        )
        
        with pytest.raises(FileNotFoundError):
            enricher._load_prompt()


# ============================================================================
# Atomic Processing Tests
# ============================================================================

class TestAtomicProcessing:
    """Test that failures in one chunk don't affect others."""
    
    def test_exception_in_one_chunk_preserves_minimal_metadata(self, mock_settings_llm_disabled):
        """Should provide minimal metadata for failed chunks."""
        chunks = [
            Chunk(id="chunk_good", text="Valid content", metadata={"source_path": "good.txt"}, source_ref="good.txt"),
            Chunk(id="chunk_bad", text=None, metadata={"source_path": "bad.txt"}, source_ref="bad.txt"),  # Will cause error
            Chunk(id="chunk_good2", text="More valid content", metadata={"source_path": "good2.txt"}, source_ref="good2.txt"),
        ]
        
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        # Should not raise exception
        result = enricher.transform(chunks)
        
        assert len(result) == 3
        # First and third should be enriched normally
        assert result[0].metadata['enriched_by'] == "rule"
        assert result[2].metadata['enriched_by'] == "rule"
        # Second should have error metadata
        assert result[1].metadata['enriched_by'] == "error"
        assert 'enrich_error' in result[1].metadata
        assert result[1].metadata['title'] == 'Untitled'


# ============================================================================
# Configuration Tests
# ============================================================================

class TestConfiguration:
    """Test configuration handling."""
    
    def test_use_llm_disabled_by_default(self):
        """Should default to rule-based when LLM not configured."""
        settings = Mock(spec=Settings)
        settings.ingestion = Mock()
        settings.ingestion.metadata_enricher = {}
        
        enricher = MetadataEnricher(settings)
        
        assert enricher.use_llm is False
    
    def test_lazy_llm_initialization(self, mock_settings_llm_enabled):
        """Should initialize LLM lazily when first accessed."""
        with patch('src.ingestion.transform.metadata_enricher.LLMFactory.create') as mock_create:
            mock_llm = Mock()
            mock_create.return_value = mock_llm
            
            enricher = MetadataEnricher(mock_settings_llm_enabled)
            
            # Should not create LLM yet
            mock_create.assert_not_called()
            
            # Access llm property
            _ = enricher.llm
            
            # Now should create
            mock_create.assert_called_once()
    
    def test_llm_init_failure_disables_llm(self, mock_settings_llm_enabled):
        """Should disable LLM on initialization failure."""
        with patch('src.ingestion.transform.metadata_enricher.LLMFactory.create') as mock_create:
            mock_create.side_effect = Exception("Init failed")
            
            enricher = MetadataEnricher(mock_settings_llm_enabled)
            
            # Access llm property (will trigger init)
            _ = enricher.llm
            
            # Should disable LLM after failure
            assert enricher.use_llm is False


# ============================================================================
# Response Parsing Tests
# ============================================================================

class TestResponseParsing:
    """Test LLM response parsing."""
    
    def test_parse_well_formatted_response(self, mock_settings_llm_disabled):
        """Should parse properly formatted LLM response."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        response = (
            "Title: Data Science Fundamentals\n"
            "Summary: An introduction to data science covering statistics, machine learning, and data visualization.\n"
            "Tags: data science, statistics, machine learning, visualization"
        )
        
        metadata = enricher._parse_llm_response(response)
        
        assert metadata['title'] == "Data Science Fundamentals"
        assert "introduction to data science" in metadata['summary']
        assert "data science" in metadata['tags']
        assert len(metadata['tags']) == 4
    
    def test_parse_missing_fields(self, mock_settings_llm_disabled):
        """Should handle missing fields gracefully."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        response = "Title: Just a Title"
        
        metadata = enricher._parse_llm_response(response)
        
        assert metadata['title'] == "Just a Title"
        assert metadata['summary']  # Should have fallback
        assert isinstance(metadata['tags'], list)
    
    def test_parse_malformed_response(self, mock_settings_llm_disabled):
        """Should handle malformed response."""
        enricher = MetadataEnricher(mock_settings_llm_disabled)
        
        response = "This is not formatted correctly at all"
        
        metadata = enricher._parse_llm_response(response)
        
        assert metadata['title'] == "Untitled"  # Fallback
        assert metadata['summary']  # Should use raw response as summary
        assert isinstance(metadata['tags'], list)
