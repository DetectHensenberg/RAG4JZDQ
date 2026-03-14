"""Unit tests for Query API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


class TestQueryEndpoints:
    """Test query API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @pytest.fixture
    def mock_hybrid_search(self):
        """Create mock HybridSearch."""
        mock = MagicMock()
        mock.search.return_value = []
        return mock

    def test_query_endpoint_exists(self, client):
        """Query endpoint should exist."""
        response = client.post(
            "/api/query",
            json={"query": "test"},
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_query_request_validation(self, client):
        """Should validate request body."""
        # Missing query
        response = client.post(
            "/api/query",
            json={},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 422

    def test_query_default_collection(self, client, mock_hybrid_search):
        """Should use default collection if not specified."""
        with patch("api.routers.query.get_hybrid_search", return_value=mock_hybrid_search):
            response = client.post(
                "/api/query",
                json={"query": "test query"},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "results" in data["data"]
            assert "latency_ms" in data["data"]

    def test_query_custom_collection(self, client, mock_hybrid_search):
        """Should accept custom collection."""
        with patch("api.routers.query.get_hybrid_search", return_value=mock_hybrid_search):
            response = client.post(
                "/api/query",
                json={"query": "test", "collection": "custom_col", "top_k": 5},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    def test_query_returns_results(self, client):
        """Should return search results."""
        mock_result = MagicMock()
        mock_result.text = "Test content"
        mock_result.score = 0.85
        mock_result.metadata = {"source_path": "test.pdf", "page": 1}
        mock_result.chunk_id = "abc123"

        mock_search = MagicMock()
        mock_search.search.return_value = [mock_result]

        with patch("api.routers.query.get_hybrid_search", return_value=mock_search):
            response = client.post(
                "/api/query",
                json={"query": "test query", "top_k": 10},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert len(data["data"]["results"]) == 1
            result = data["data"]["results"][0]
            assert result["score"] == 0.85
            assert result["source_path"] == "test.pdf"

    def test_query_empty_results(self, client, mock_hybrid_search):
        """Should handle empty results gracefully."""
        mock_hybrid_search.search.return_value = []
        
        with patch("api.routers.query.get_hybrid_search", return_value=mock_hybrid_search):
            response = client.post(
                "/api/query",
                json={"query": "nonexistent"},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["data"]["results"] == []

    def test_query_handles_error(self, client):
        """Should handle search errors gracefully."""
        mock_search = MagicMock()
        mock_search.search.side_effect = Exception("Search failed")

        with patch("api.routers.query.get_hybrid_search", return_value=mock_search):
            response = client.post(
                "/api/query",
                json={"query": "test"},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is False
            assert "message" in data

    def test_query_top_k_parameter(self, client, mock_hybrid_search):
        """Should pass top_k to search."""
        mock_hybrid_search.search.return_value = []

        with patch("api.routers.query.get_hybrid_search", return_value=mock_hybrid_search):
            response = client.post(
                "/api/query",
                json={"query": "test", "top_k": 20},
                headers={"X-API-Key": "dev"},
            )
            assert response.status_code == 200
            # Verify top_k was passed
            mock_hybrid_search.search.assert_called_once()
            call_kwargs = mock_hybrid_search.search.call_args
            assert call_kwargs[1]["top_k"] == 20


class TestQueryRequestModel:
    """Test QueryRequest Pydantic model."""

    def test_model_defaults(self):
        """Should have default values."""
        from api.routers.query import QueryRequest
        
        req = QueryRequest(query="test")
        assert req.collection == "default"
        assert req.top_k == 10

    def test_model_accepts_custom_values(self):
        """Should accept custom values."""
        from api.routers.query import QueryRequest
        
        req = QueryRequest(query="test", collection="custom", top_k=50)
        assert req.query == "test"
        assert req.collection == "custom"
        assert req.top_k == 50

    def test_model_requires_query(self):
        """Should require query field."""
        from api.routers.query import QueryRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            QueryRequest()
