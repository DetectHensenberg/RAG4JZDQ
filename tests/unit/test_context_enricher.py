"""Unit tests for ContextEnricher transform."""

from unittest.mock import MagicMock
import pytest

from src.core.types import Chunk
from src.ingestion.transform.context_enricher import ContextEnricher


class TestContextEnricher:
    """Tests for ContextEnricher class."""

    @pytest.fixture
    def mock_settings_enabled(self):
        settings = MagicMock()
        settings.ingestion = MagicMock()
        settings.ingestion.context_enricher = MagicMock()
        settings.ingestion.context_enricher.enabled = True
        return settings

    @pytest.fixture
    def mock_settings_disabled(self):
        settings = MagicMock()
        settings.ingestion = MagicMock()
        settings.ingestion.context_enricher = MagicMock()
        settings.ingestion.context_enricher.enabled = False
        return settings

    @pytest.fixture
    def sample_chunks(self):
        return [
            Chunk(
                id="chunk1",
                text="This is chunk 1 content.",
                metadata={"source_path": "/docs/report.pdf"}
            ),
            Chunk(
                id="chunk2",
                text="This is chunk 2 content.",
                metadata={"source_path": "/docs/manual.docx"}
            ),
        ]

    def test_transform_adds_embedding_text(self, mock_settings_enabled, sample_chunks):
        enricher = ContextEnricher(mock_settings_enabled)
        result = enricher.transform(sample_chunks)
        
        assert len(result) == 2
        assert result[0].metadata["embedding_text"] == "[文档: report] This is chunk 1 content."
        assert result[1].metadata["embedding_text"] == "[文档: manual] This is chunk 2 content."

    def test_transform_disabled_skips_enrichment(self, mock_settings_disabled, sample_chunks):
        enricher = ContextEnricher(mock_settings_disabled)
        result = enricher.transform(sample_chunks)
        
        assert len(result) == 2
        assert "embedding_text" not in result[0].metadata
        assert "embedding_text" not in result[1].metadata

    def test_transform_empty_source_path_skips(self, mock_settings_enabled):
        chunks = [
            Chunk(id="chunk1", text="Content", metadata={"source_path": ""}),
        ]
        enricher = ContextEnricher(mock_settings_enabled)
        result = enricher.transform(chunks)
        
        assert "embedding_text" not in result[0].metadata

    def test_transform_empty_chunks_returns_empty(self, mock_settings_enabled):
        enricher = ContextEnricher(mock_settings_enabled)
        result = enricher.transform([])
        assert result == []

    def test_original_text_preserved(self, mock_settings_enabled, sample_chunks):
        enricher = ContextEnricher(mock_settings_enabled)
        result = enricher.transform(sample_chunks)
        
        assert result[0].text == "This is chunk 1 content."
        assert result[1].text == "This is chunk 2 content."
