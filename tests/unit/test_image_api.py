"""Unit tests for image API endpoints."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class TestImageEndpoints:
    """Test image serving endpoints in data router."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @pytest.fixture
    def mock_image_storage(self):
        """Mock ImageStorage for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test image
            img_path = Path(tmpdir) / "test_image.png"
            # Minimal PNG (1x1 transparent)
            png_data = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
            img_path.write_bytes(png_data)
            
            mock_storage = MagicMock()
            mock_storage.get_image_path.return_value = str(img_path)
            mock_storage.aget_image_path = AsyncMock(return_value=str(img_path))
            
            yield mock_storage, str(img_path)

    def test_get_image_returns_base64_data(self, client, mock_image_storage):
        """GET /api/data/images/{image_id} should return base64 encoded image."""
        mock_storage, img_path = mock_image_storage
        
        # Patch at the point of use (inside the function)
        with patch("src.ingestion.storage.image_storage.ImageStorage", return_value=mock_storage):
            response = client.get(
                "/api/data/images/test_image",
                headers={"X-API-Key": "dev"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "data" in data
            assert "base64" in data["data"]
            assert "mime_type" in data["data"]
            assert data["data"]["mime_type"] == "image/png"

    def test_get_image_raw_returns_binary(self, client, mock_image_storage):
        """GET /api/data/images/{image_id}/raw should return raw binary image."""
        mock_storage, img_path = mock_image_storage
        
        with patch("src.ingestion.storage.image_storage.ImageStorage", return_value=mock_storage):
            response = client.get(
                "/api/data/images/test_image/raw",
                headers={"X-API-Key": "dev"},
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert len(response.content) > 0

    def test_get_image_not_found(self, client):
        """GET /api/data/images/{image_id} should return 404 for missing image."""
        mock_storage = MagicMock()
        mock_storage.get_image_path.return_value = None
        mock_storage.aget_image_path = AsyncMock(return_value=None)
        
        with patch("src.ingestion.storage.image_storage.ImageStorage", return_value=mock_storage):
            response = client.get(
                "/api/data/images/nonexistent",
                headers={"X-API-Key": "dev"},
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is False
            assert "not found" in data["message"].lower()

    def test_get_image_raw_not_found(self, client):
        """GET /api/data/images/{image_id}/raw should return 404 for missing image."""
        mock_storage = MagicMock()
        mock_storage.get_image_path.return_value = None
        mock_storage.aget_image_path = AsyncMock(return_value=None)
        
        with patch("src.ingestion.storage.image_storage.ImageStorage", return_value=mock_storage):
            response = client.get(
                "/api/data/images/nonexistent/raw",
                headers={"X-API-Key": "dev"},
            )
            
            assert response.status_code == 404

    def test_image_mime_type_detection_jpg(self, client):
        """Should detect correct MIME type for JPG images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal valid JPEG file
            jpg_path = Path(tmpdir) / "test.jpg"
            # Minimal JPEG header (valid JPEG SOI + EOI)
            jpg_data = bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
                0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
                0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9
            ])
            jpg_path.write_bytes(jpg_data)
            
            mock_storage = MagicMock()
            mock_storage.get_image_path.return_value = str(jpg_path)
            mock_storage.aget_image_path = AsyncMock(return_value=str(jpg_path))
            
            with patch("src.ingestion.storage.image_storage.ImageStorage", return_value=mock_storage):
                response = client.get(
                    "/api/data/images/test_jpg",
                    headers={"X-API-Key": "dev"},
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["data"]["mime_type"] == "image/jpeg"


class TestImageRelevanceThreshold:
    """Test that image relevance threshold is properly applied."""

    def test_threshold_constant_exists(self):
        """IMAGE_RELEVANCE_THRESHOLD should be defined."""
        from api.routers.chat import IMAGE_RELEVANCE_THRESHOLD
        
        assert IMAGE_RELEVANCE_THRESHOLD is not None
        assert 0 < IMAGE_RELEVANCE_THRESHOLD < 1

    def test_threshold_value_reasonable(self):
        """Threshold should be a reasonable value."""
        from api.routers.chat import IMAGE_RELEVANCE_THRESHOLD
        
        # 0.10 is the current value
        assert IMAGE_RELEVANCE_THRESHOLD == pytest.approx(0.10, rel=0.01)
