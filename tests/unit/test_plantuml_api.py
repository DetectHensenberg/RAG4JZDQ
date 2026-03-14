"""Unit tests for PlantUML rendering API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


class TestPlantUMLEndpoints:
    """Test PlantUML rendering endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    def test_render_endpoint_exists(self, client):
        """POST /api/plantuml/render should exist."""
        # Just check the endpoint is reachable (may fail on Kroki call)
        response = client.post(
            "/api/plantuml/render",
            json={"code": "@startuml\nA --> B\n@enduml", "format": "svg"},
            headers={"X-API-Key": "dev"},
        )
        # Should not return 404
        assert response.status_code != 404

    def test_render_request_model_validation(self, client):
        """Request should require 'code' field."""
        response = client.post(
            "/api/plantuml/render",
            json={"format": "svg"},  # Missing 'code'
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 422  # Validation error

    def test_render_default_format_is_svg(self, client):
        """Default format should be SVG."""
        from api.routers.plantuml import PlantUMLRequest
        
        req = PlantUMLRequest(code="test")
        assert req.format == "svg"

    def test_render_accepts_png_format(self, client):
        """Should accept PNG format."""
        from api.routers.plantuml import PlantUMLRequest
        
        req = PlantUMLRequest(code="test", format="png")
        assert req.format == "png"

    @patch("httpx.AsyncClient")
    def test_render_returns_svg_on_success(self, mock_client, client):
        """Should return SVG content on successful render."""
        # Mock the async context manager
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<svg>test</svg>"
        
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render",
            json={"code": "@startuml\nA --> B\n@enduml"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/svg+xml"

    @patch("httpx.AsyncClient")
    def test_render_returns_png_on_png_format(self, mock_client, client):
        """Should return PNG content when format is png."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"\x89PNG"  # PNG magic bytes
        
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render",
            json={"code": "@startuml\nA --> B\n@enduml", "format": "png"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    @patch("httpx.AsyncClient")
    def test_render_handles_kroki_error(self, mock_client, client):
        """Should handle Kroki API errors gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Syntax error in PlantUML"
        
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render",
            json={"code": "invalid plantuml"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 400

    @patch("httpx.AsyncClient")
    def test_render_handles_timeout(self, mock_client, client):
        """Should handle timeout gracefully."""
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render",
            json={"code": "@startuml\nA --> B\n@enduml"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 504


class TestPlantUMLEncoding:
    """Test PlantUML encoding function."""

    def test_encode_simple_text(self):
        """Should encode simple text without error."""
        from api.routers.plantuml import _encode_plantuml
        
        result = _encode_plantuml("@startuml\nA --> B\n@enduml")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_chinese_text(self):
        """Should encode Chinese text correctly."""
        from api.routers.plantuml import _encode_plantuml
        
        result = _encode_plantuml("@startuml\n用户 --> 系统\n@enduml")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_produces_urlsafe_output(self):
        """Output should be URL-safe base64."""
        from api.routers.plantuml import _encode_plantuml
        
        result = _encode_plantuml("@startuml\nA --> B\n@enduml")
        # URL-safe base64 uses - and _ instead of + and /
        # May include = padding
        import re
        assert re.match(r'^[A-Za-z0-9_\-+=]+$', result) is not None


class TestPlantUMLRequestModel:
    """Test PlantUMLRequest Pydantic model."""

    def test_model_accepts_valid_data(self):
        """Should accept valid request data."""
        from api.routers.plantuml import PlantUMLRequest
        
        req = PlantUMLRequest(code="test code", format="svg")
        assert req.code == "test code"
        assert req.format == "svg"

    def test_model_defaults_format_to_svg(self):
        """Format should default to svg."""
        from api.routers.plantuml import PlantUMLRequest
        
        req = PlantUMLRequest(code="test")
        assert req.format == "svg"

    def test_model_validates_format_values(self):
        """Should accept valid format values."""
        from api.routers.plantuml import PlantUMLRequest
        
        # These should work
        req_svg = PlantUMLRequest(code="test", format="svg")
        req_png = PlantUMLRequest(code="test", format="png")
        
        assert req_svg.format == "svg"
        assert req_png.format == "png"

    def test_model_requires_code(self):
        """Code field should be required."""
        from pydantic import ValidationError
        from api.routers.plantuml import PlantUMLRequest
        
        with pytest.raises(ValidationError):
            PlantUMLRequest(format="svg")  # Missing code


class TestPlantUMLRenderBase64:
    """Test render-base64 endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    @patch("httpx.AsyncClient")
    def test_render_base64_returns_json(self, mock_client, client):
        """Should return JSON with base64 data URI."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<svg>test</svg>"
        
        # Create async mock that returns the response (uses GET)
        async def mock_get(*args, **kwargs):
            return mock_response
        
        mock_async_client = MagicMock()
        mock_async_client.get = mock_get
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render-base64",
            json={"code": "@startuml\nA --> B\n@enduml"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "data_uri" in data["data"]
        assert data["data"]["data_uri"].startswith("data:image/svg+xml;base64,")

    @patch("httpx.AsyncClient")
    def test_render_base64_handles_error(self, mock_client, client):
        """Should return error JSON on failure."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Error"
        
        async def mock_post(*args, **kwargs):
            return mock_response
        
        mock_async_client = MagicMock()
        mock_async_client.post = mock_post
        mock_client.return_value.__aenter__.return_value = mock_async_client
        
        response = client.post(
            "/api/plantuml/render-base64",
            json={"code": "invalid"},
            headers={"X-API-Key": "dev"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
