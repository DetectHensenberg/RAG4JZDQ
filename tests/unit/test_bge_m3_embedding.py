"""Unit tests for BGE-M3 Embedding provider."""

from unittest.mock import MagicMock, patch
import pytest


class TestBGEM3Embedding:
    """Tests for BGEM3Embedding class."""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.embedding.bge_m3 = MagicMock()
        settings.embedding.bge_m3.model = "BAAI/bge-m3"
        settings.embedding.bge_m3.use_fp16 = True
        settings.embedding.bge_m3.device = "cpu"
        return settings

    @pytest.fixture
    def mock_model(self):
        model = MagicMock()
        model.encode.return_value = {
            "dense_vecs": [[0.1] * 1024, [0.2] * 1024],
            "lexical_weights": [{1: 0.5}, {2: 0.3}],
        }
        return model

    def test_embed_returns_dense_vectors(self, mock_settings, mock_model):
        from src.libs.embedding.bge_m3_embedding import BGEM3Embedding
        embedding = BGEM3Embedding(mock_settings)
        embedding._model = mock_model
        result = embedding.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 1024

    def test_embed_with_sparse_returns_tuple(self, mock_settings, mock_model):
        from src.libs.embedding.bge_m3_embedding import BGEM3Embedding
        embedding = BGEM3Embedding(mock_settings)
        embedding._model = mock_model
        dense, sparse = embedding.embed_with_sparse(["hello"])
        assert isinstance(dense, list)
        assert isinstance(sparse, list)

    def test_get_dimension_returns_1024(self, mock_settings):
        from src.libs.embedding.bge_m3_embedding import BGEM3Embedding
        embedding = BGEM3Embedding(mock_settings)
        assert embedding.get_dimension() == 1024

    def test_empty_texts_raises_error(self, mock_settings):
        from src.libs.embedding.bge_m3_embedding import BGEM3Embedding
        embedding = BGEM3Embedding(mock_settings)
        with pytest.raises(ValueError):
            embedding.embed([])
