"""Unit tests for Data Management API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
from fastapi.testclient import TestClient


class TestDataManageEndpoints:
    """Test data management API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create temporary data directory structure."""
        data_dir = tmp_path / "data"
        db_dir = data_dir / "db"
        chroma_dir = db_dir / "chroma"
        bm25_dir = db_dir / "bm25"
        images_dir = data_dir / "images"
        logs_dir = tmp_path / "logs"
        
        # Create directories
        chroma_dir.mkdir(parents=True)
        bm25_dir.mkdir(parents=True)
        images_dir.mkdir(parents=True)
        logs_dir.mkdir(parents=True)
        
        # Create some dummy files
        (chroma_dir / "chroma.sqlite3").write_bytes(b"test data")
        (bm25_dir / "default").mkdir()
        (bm25_dir / "default" / "index.pkl").write_bytes(b"bm25 index")
        (images_dir / "test.png").write_bytes(b"image data")
        (db_dir / "ingestion_history.db").write_bytes(b"history")
        (db_dir / "image_index.db").write_bytes(b"image index")
        (logs_dir / "traces.jsonl").write_text('{"trace": "test"}\n')
        
        return tmp_path

    def test_clear_all_endpoint_exists(self, client):
        """Clear-all endpoint should exist."""
        response = client.delete(
            "/api/data-manage/clear-all",
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_clear_all_returns_success(self, client):
        """Should return success response."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve:
            # Mock paths to temp directory
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if "chroma" in p or "bm25" in p or "images" in p:
                        path.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                
                response = client.delete(
                    "/api/data-manage/clear-all",
                    headers={"X-API-Key": "dev"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert "data" in data
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_all_resets_deps(self, client):
        """Should call reset_all to clear cached instances."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("api.deps.reset_all") as mock_reset:
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                
                response = client.delete(
                    "/api/data-manage/clear-all",
                    headers={"X-API-Key": "dev"},
                )
                # reset_all should be called
                mock_reset.assert_called_once()
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_collection_endpoint_exists(self, client):
        """Clear-collection endpoint should exist."""
        response = client.delete(
            "/api/data-manage/collection/default",
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_clear_collection_returns_success(self, client):
        """Should return success for collection clear."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("chromadb.PersistentClient") as mock_client_class:
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                
                # Mock ChromaDB client
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                mock_client.delete_collection.return_value = None
                
                response = client.delete(
                    "/api/data-manage/collection/test_collection",
                    headers={"X-API-Key": "dev"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert data["data"]["collection"] == "test_collection"
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_collection_deletes_from_chroma(self, client):
        """Should delete collection from ChromaDB."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("chromadb.PersistentClient") as mock_client_class, \
             patch("api.deps.reset_all"):
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                
                # Mock ChromaDB client
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                response = client.delete(
                    "/api/data-manage/collection/my_collection",
                    headers={"X-API-Key": "dev"},
                )
                
                # Verify delete_collection was called
                mock_client.delete_collection.assert_called_once_with("my_collection")
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_all_handles_missing_directories(self, client):
        """Should handle missing directories gracefully."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("api.deps.reset_all"):
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    # Return path that doesn't exist
                    path = temp_base / "nonexistent" / p
                    return path
                
                mock_resolve.side_effect = make_path
                
                response = client.delete(
                    "/api/data-manage/clear-all",
                    headers={"X-API-Key": "dev"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_all_handles_errors(self, client):
        """Should handle errors and report them."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("api.routers.data_manage.shutil") as mock_shutil, \
             patch("api.deps.reset_all"):
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    # Create actual directory so rmtree gets called
                    path.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                # Make rmtree raise an error
                mock_shutil.rmtree.side_effect = PermissionError("Access denied")
                
                response = client.delete(
                    "/api/data-manage/clear-all",
                    headers={"X-API-Key": "dev"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                # Should have errors reported
                assert len(data["data"]["errors"]) > 0
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)


class TestDataManageSecurity:
    """Test security aspects of data management API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    def test_clear_all_with_valid_api_key(self, client):
        """Should accept valid API key."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("api.deps.reset_all"):
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                
                response = client.delete(
                    "/api/data-manage/clear-all",
                    headers={"X-API-Key": "dev"},
                )
                # Should succeed with valid API key
                assert response.status_code == 200
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)

    def test_clear_collection_with_valid_api_key(self, client):
        """Should accept valid API key."""
        with patch("api.routers.data_manage.resolve_path") as mock_resolve, \
             patch("chromadb.PersistentClient") as mock_client_class, \
             patch("api.deps.reset_all"):
            
            temp_base = Path(tempfile.mkdtemp())
            try:
                def make_path(p):
                    path = temp_base / p
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return path
                
                mock_resolve.side_effect = make_path
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                response = client.delete(
                    "/api/data-manage/collection/default",
                    headers={"X-API-Key": "dev"},
                )
                # Should succeed with valid API key
                assert response.status_code == 200
            finally:
                shutil.rmtree(temp_base, ignore_errors=True)
