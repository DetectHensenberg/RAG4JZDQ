"""Unit tests for Knowledge API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
from fastapi.testclient import TestClient


class TestKnowledgeEndpoints:
    """Test knowledge base API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @pytest.fixture
    def temp_folder(self, tmp_path):
        """Create temporary folder with test files."""
        folder = tmp_path / "knowledge"
        folder.mkdir()
        
        # Create test files
        (folder / "test.md").write_text("# Test Document\nThis is a test.")
        (folder / "test.txt").write_text("Plain text file")
        (folder / "test.pdf").write_bytes(b"%PDF-1.4\n%test pdf content")
        
        return folder

    def test_scan_folder_endpoint_exists(self, client):
        """Scan endpoint should exist."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "test"},
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_scan_folder_empty_path(self, client):
        """Should reject empty path."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": ""},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "路径" in data["message"]

    def test_scan_folder_nonexistent(self, client):
        """Should handle nonexistent path."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "/nonexistent/path/12345"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_scan_folder_valid(self, client, temp_folder):
        """Should scan valid folder."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": str(temp_folder)},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "files" in data["data"]
        assert "total" in data["data"]

    def test_scan_folder_traversal_attack(self, client):
        """Should block path traversal attacks."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "../../../etc/passwd"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "非法" in data["message"]

    def test_ingest_endpoint_exists(self, client):
        """Ingest endpoint should exist."""
        response = client.post(
            "/api/knowledge/ingest",
            json={"folder_path": "test"},
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_ingest_empty_path(self, client):
        """Should reject empty path."""
        response = client.post(
            "/api/knowledge/ingest",
            json={"folder_path": "", "collection": "default"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_ingest_nonexistent_folder(self, client):
        """Should handle nonexistent folder."""
        response = client.post(
            "/api/knowledge/ingest",
            json={"folder_path": "/nonexistent/path/xyz", "collection": "default"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_progress_endpoint_uses_get(self, client):
        """Progress endpoint should use GET method."""
        # This tests that the endpoint accepts GET, not POST
        response = client.get(
            "/api/knowledge/progress/nonexistent",
            headers={"X-API-Key": "dev"},
        )
        # Should not return 405 Method Not Allowed
        assert response.status_code != 405

    def test_progress_nonexistent_task(self, client):
        """Should handle nonexistent task."""
        response = client.get(
            "/api/knowledge/progress/nonexistent123",
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "任务" in data["message"]


class TestKnowledgeFileTypes:
    """Test file type filtering."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @pytest.fixture
    def temp_folder_with_various_files(self, tmp_path):
        """Create folder with various file types."""
        folder = tmp_path / "mixed"
        folder.mkdir()
        
        # Allowed types
        (folder / "doc.pdf").write_bytes(b"%PDF-1.4\ntest")
        (folder / "doc.md").write_text("# Markdown")
        (folder / "doc.txt").write_text("Plain text")
        (folder / "doc.docx").write_bytes(b"PK\x03\x04")  # ZIP header (docx)
        (folder / "doc.pptx").write_bytes(b"PK\x03\x04")  # ZIP header (pptx)
        
        # Disallowed types
        (folder / "script.exe").write_bytes(b"MZ")  # Executable
        (folder / "data.json").write_text("{}")
        (folder / "image.png").write_bytes(b"\x89PNG")
        
        return folder

    def test_scan_filters_by_extension(self, client, temp_folder_with_various_files):
        """Should only return allowed file types."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": str(temp_folder_with_various_files)},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        
        # Check extensions
        extensions = {Path(f["name"]).suffix.lower() for f in data["data"]["files"]}
        # Should only have allowed extensions
        allowed = {".pdf", ".md", ".txt", ".docx", ".pptx"}
        assert extensions.issubset(allowed)


class TestKnowledgeSecurity:
    """Test security aspects of knowledge API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    def test_scan_blocks_double_dot(self, client):
        """Should block path with .."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "C:\\Users\\..\\Windows"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_scan_blocks_url_encoded_traversal(self, client):
        """Should block URL-encoded traversal."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "%2e%2e%2f%2e%2e%2fetc"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_scan_blocks_tilde(self, client):
        """Should block tilde expansion."""
        response = client.post(
            "/api/knowledge/scan",
            json={"folder_path": "~/.ssh"},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
