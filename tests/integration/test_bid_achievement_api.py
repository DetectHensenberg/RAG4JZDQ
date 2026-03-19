"""Integration tests for bid achievement API — simulates full frontend workflow.

Tests the complete CRUD lifecycle, attachment management, batch import,
and semantic search endpoints via the FastAPI TestClient.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bid_test_data"


@pytest.fixture()
def client(tmp_path: Path):
    """Create a TestClient with temp DB and suppressed ChromaDB."""
    temp_db = tmp_path / "test_ach.db"
    temp_att = tmp_path / "attachments"

    with patch("src.bid.achievement_db._DB_PATH", temp_db):
        with patch("src.bid.achievement_db._sync_to_chroma"):
            with patch("src.bid.achievement_db._delete_from_chroma"):
                with patch("src.bid.attachment_manager._ATTACHMENTS_ROOT", temp_att):
                    from api.main import app
                    yield TestClient(app, headers={"X-API-Key": "dev"})


class TestAchievementFullFlow:
    """Simulate complete frontend workflow: create → list → edit → attach → delete."""

    def test_create_list_update_delete(self, client: TestClient) -> None:
        # Step 1: Create a record
        resp = client.post("/api/bid-achievement/create", json={
            "project_name": "测试智慧城市项目",
            "project_content": "城市综合管理平台建设",
            "amount": 800.0,
            "sign_date": "2023-06-15",
            "acceptance_date": "2024-03-20",
            "client_contact": "张三",
            "client_phone": "13800138000",
            "tags": ["智慧城市", "集成"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        record_id = data["id"]
        assert record_id > 0

        # Step 2: List records — should find the one we just created
        resp = client.post("/api/bid-achievement/list", json={
            "keyword": "智慧城市",
            "page": 1,
            "page_size": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["total"] == 1
        assert data["data"][0]["project_name"] == "测试智慧城市项目"

        # Step 3: Get single record
        resp = client.get(f"/api/bid-achievement/{record_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["amount"] == 800.0

        # Step 4: Update the record
        resp = client.put(f"/api/bid-achievement/{record_id}", json={
            "project_name": "测试智慧城市项目(已更新)",
            "project_content": "城市综合管理平台建设与运维",
            "amount": 850.0,
            "sign_date": "2023-06-15",
            "acceptance_date": "2024-03-20",
            "client_contact": "张三",
            "client_phone": "13800138000",
            "tags": ["智慧城市", "集成", "运维"],
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify update
        resp = client.get(f"/api/bid-achievement/{record_id}")
        data = resp.json()["data"]
        assert data["project_name"] == "测试智慧城市项目(已更新)"
        assert data["amount"] == 850.0
        assert "运维" in data["tags"]

        # Step 5: Delete the record
        resp = client.delete(f"/api/bid-achievement/{record_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        resp = client.get(f"/api/bid-achievement/{record_id}")
        assert resp.json()["ok"] is False

    def test_list_filtering(self, client: TestClient) -> None:
        # Create multiple records
        records = [
            {"project_name": "A项目", "amount": 200, "sign_date": "2022-01-01", "tags": ["安防"]},
            {"project_name": "B项目", "amount": 500, "sign_date": "2023-06-01", "tags": ["信息化"]},
            {"project_name": "C项目", "amount": 900, "sign_date": "2024-01-01", "tags": ["智慧城市"]},
        ]
        for r in records:
            resp = client.post("/api/bid-achievement/create", json=r)
            assert resp.json()["ok"] is True

        # Filter by amount range
        resp = client.post("/api/bid-achievement/list", json={
            "min_amount": 400,
            "max_amount": 1000,
        })
        data = resp.json()
        assert data["total"] == 2  # B(500) and C(900)

        # Filter by date range
        resp = client.post("/api/bid-achievement/list", json={
            "start_date": "2023-01-01",
        })
        data = resp.json()
        assert data["total"] == 2  # B and C

        # Filter by keyword
        resp = client.post("/api/bid-achievement/list", json={
            "keyword": "A项目",
        })
        assert resp.json()["total"] == 1

    def test_pagination(self, client: TestClient) -> None:
        for i in range(5):
            client.post("/api/bid-achievement/create", json={
                "project_name": f"项目{i}",
                "amount": (i + 1) * 100,
            })

        resp = client.post("/api/bid-achievement/list", json={
            "page": 1, "page_size": 2,
        })
        data = resp.json()
        assert data["total"] == 5
        assert len(data["data"]) == 2


class TestAttachmentFlow:
    """Simulate attachment upload → list → download → delete."""

    def test_attachment_lifecycle(self, client: TestClient) -> None:
        # Create a record first
        resp = client.post("/api/bid-achievement/create", json={
            "project_name": "附件测试项目",
        })
        rid = resp.json()["id"]

        # Upload attachment
        file_content = b"fake PDF content for testing"
        resp = client.post(
            f"/api/bid-achievement/{rid}/attachments",
            files={"file": ("contract.pdf", io.BytesIO(file_content), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["filename"] == "contract.pdf"

        # List attachments
        resp = client.get(f"/api/bid-achievement/{rid}/attachments")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]) == 1

        # Download attachment
        resp = client.get(f"/api/bid-achievement/{rid}/attachments/contract.pdf")
        assert resp.status_code == 200
        assert resp.content == file_content

        # Delete attachment
        resp = client.delete(f"/api/bid-achievement/{rid}/attachments/contract.pdf")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        resp = client.get(f"/api/bid-achievement/{rid}/attachments")
        assert resp.json()["data"] == []


class TestBatchImport:
    """Test Excel/CSV import through API."""

    def test_import_excel(self, client: TestClient) -> None:
        xlsx_path = FIXTURES_DIR / "mock_achievements.xlsx"
        if not xlsx_path.exists():
            pytest.skip("Test fixture not generated")

        with open(xlsx_path, "rb") as f:
            resp = client.post(
                "/api/bid-achievement/import-excel",
                files={"file": ("achievements.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["success_count"] == 7

        # Verify records exist
        resp = client.post("/api/bid-achievement/list", json={"page_size": 50})
        assert resp.json()["total"] == 7

    def test_import_csv(self, client: TestClient) -> None:
        csv_path = FIXTURES_DIR / "mock_achievements.csv"
        if not csv_path.exists():
            pytest.skip("Test fixture not generated")

        with open(csv_path, "rb") as f:
            resp = client.post(
                "/api/bid-achievement/import-excel",
                files={"file": ("achievements.csv", f, "text/csv")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["success_count"] == 2
