"""Integration tests for bid review API — simulates full frontend Step Wizard workflow.

Uses mock DOCX tender/bid documents to test the complete flow:
Step 1: Parse tender → Step 2: Identify items → Step 3: Parse bid → Step 4: Check (SSE)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bid_test_data"


@pytest.fixture()
def client():
    """Create a TestClient."""
    from api.main import app
    return TestClient(app, headers={"X-API-Key": "dev"})


@pytest.fixture()
def mock_llm():
    """Mock LLM that returns structured responses for identify and check."""
    llm = MagicMock(spec=["chat", "generate"])

    # For identify-items: return structured JSON
    identify_response = json.dumps({
        "items": [
            {
                "category": "符合性",
                "requirement": "投标文件须加盖投标人公章及法定代表人签字或盖章",
                "source_section": "第二章",
                "original_text": "投标文件须加盖投标人公章及法定代表人签字或盖章"
            },
            {
                "category": "★号",
                "requirement": "系统应支持不少于1000个终端设备同时在线接入",
                "source_section": "第四章",
                "original_text": "★ 系统应支持不少于1000个终端设备同时在线接入"
            },
            {
                "category": "资格性",
                "requirement": "投标人须具有信息系统集成及服务资质证书（三级及以上）",
                "source_section": "第一章",
                "original_text": "投标人须具有信息系统集成及服务资质证书（三级及以上）"
            },
            {
                "category": "★号",
                "requirement": "系统响应时间不超过3秒",
                "source_section": "第四章",
                "original_text": "★ 系统响应时间不超过3秒"
            },
            {
                "category": "实质性",
                "requirement": "投标保证金须在截止时间前到账",
                "source_section": "第二章",
                "original_text": "投标保证金须在投标截止时间前到账，否则废标"
            },
        ]
    }, ensure_ascii=False)
    llm.chat = MagicMock(return_value=identify_response)

    # For check: return streaming markdown report
    check_report = """## 废标项审查报告

### 一、总体评估

共核查 5 条废标项，其中 3 项已响应，1 项不完整，1 项缺失。整体响应率 60%，存在高风险项。

### 二、逐项核查表

| 序号 | 类型 | 废标项要求 | 响应状态 | 风险等级 | 详细说明 |
|------|------|-----------|---------|---------|---------|
| 1 | 符合性 | 投标文件须加盖公章 | ✅已响应 | 低 | 已加盖公章 |
| 2 | ★号 | 终端接入1000个 | ✅已响应 | 低 | 支持2000个终端 |
| 3 | 资格性 | 集成资质三级及以上 | ✅已响应 | 低 | 持有二级资质 |
| 4 | ★号 | 响应时间不超过3秒 | ✅已响应 | 低 | 不超过2秒 |
| 5 | 实质性 | ISO9001认证 | ❌缺失 | 高 | 投标文件中未找到相关认证材料 |

### 三、高风险项汇总

1. **ISO9001质量管理体系认证** — 投标文件中缺失，需立即补充

### 四、改进建议

- 补充ISO9001质量管理体系认证证书
"""
    llm.stream_chat = None  # force fallback to chat for check

    return llm, identify_response, check_report


class TestParseTender:
    """Step 1: Upload and parse tender document."""

    def test_parse_tender_docx(self, client: TestClient) -> None:
        docx_path = FIXTURES_DIR / "mock_tender.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")

        with open(docx_path, "rb") as f:
            resp = client.post(
                "/api/bid-review/parse-tender",
                files=[("files", ("tender.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["char_count"] > 100
        assert "招标文件" in data["data"]["text"]
        assert "符合性审查" in data["data"]["text"]
        assert "★" in data["data"]["text"]

    def test_parse_tender_unsupported(self, client: TestClient) -> None:
        resp = client.post(
            "/api/bid-review/parse-tender",
            files=[("files", ("bad.txt", b"plain text", "text/plain"))],
        )
        data = resp.json()
        assert data["ok"] is False
        assert "不支持" in data["message"]


class TestIdentifyItems:
    """Step 2: Identify disqualification items via rules + LLM."""

    def test_identify_items(self, client: TestClient, mock_llm) -> None:
        llm, identify_response, _ = mock_llm

        # First parse the tender to get text
        docx_path = FIXTURES_DIR / "mock_tender.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")

        with open(docx_path, "rb") as f:
            parse_resp = client.post(
                "/api/bid-review/parse-tender",
                files=[("files", ("tender.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )
        tender_text = parse_resp.json()["data"]["text"]

        # Mock the LLM for identification
        with patch("api.deps.get_llm", return_value=llm):
            resp = client.post("/api/bid-review/identify-items", json={
                "text": tender_text,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        items = data["data"]
        assert len(items) >= 3
        categories = set(i["category"] for i in items)
        assert "★号" in categories


class TestParseBid:
    """Step 3: Upload and parse bid document."""

    def test_parse_bid_docx(self, client: TestClient) -> None:
        docx_path = FIXTURES_DIR / "mock_bid.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")

        with open(docx_path, "rb") as f:
            resp = client.post(
                "/api/bid-review/parse-bid",
                files=[("files", ("bid.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "投标文件" in data["data"]["text"]
        assert "九洲科技" in data["data"]["text"]


class TestCheckBid:
    """Step 4: SSE streaming check."""

    def test_check_stream(self, client: TestClient, mock_llm) -> None:
        llm, _, check_report = mock_llm
        # Override chat to return the check report
        llm.chat = MagicMock(return_value=check_report)

        items = [
            {"id": "a1", "category": "符合性", "requirement": "投标文件须加盖公章", "source_section": "", "source_page": 0, "original_text": ""},
            {"id": "a2", "category": "★号", "requirement": "终端接入1000个", "source_section": "", "source_page": 0, "original_text": ""},
            {"id": "a3", "category": "实质性", "requirement": "ISO9001认证", "source_section": "", "source_page": 0, "original_text": ""},
        ]

        with patch("api.deps.get_llm", return_value=llm):
            resp = client.post("/api/bid-review/check", json={
                "items": items,
                "bid_text": "投标文件内容，已加盖公章，支持2000个终端接入。",
            })

        assert resp.status_code == 200

        # Parse SSE events
        events = []
        for line in resp.text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass

        assert len(events) >= 2  # at least tokens + done

        # Find the done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        done = done_events[0]

        assert "answer" in done
        assert "table_data" in done
        assert len(done["table_data"]) >= 3

        # Verify table data parsing
        statuses = [r["status"] for r in done["table_data"]]
        assert "responded" in statuses
        assert "missing" in statuses


class TestFullWorkflow:
    """End-to-end: Parse tender → Identify → Parse bid → Check.

    Simulates the complete Step Wizard UI flow.
    """

    def test_full_review_workflow(self, client: TestClient, mock_llm) -> None:
        llm, identify_response, check_report = mock_llm

        tender_path = FIXTURES_DIR / "mock_tender.docx"
        bid_path = FIXTURES_DIR / "mock_bid.docx"
        if not tender_path.exists() or not bid_path.exists():
            pytest.skip("Test fixtures not generated")

        # ── Step 1: Parse tender ──
        with open(tender_path, "rb") as f:
            resp = client.post(
                "/api/bid-review/parse-tender",
                files=[("files", ("tender.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )
        assert resp.json()["ok"] is True
        tender_text = resp.json()["data"]["text"]
        assert len(tender_text) > 100

        # ── Step 2: Identify items ──
        with patch("api.deps.get_llm", return_value=llm):
            resp = client.post("/api/bid-review/identify-items", json={
                "text": tender_text,
            })
        assert resp.json()["ok"] is True
        items = resp.json()["data"]
        assert len(items) >= 3

        # Simulate user editing: remove one item, add one
        items = items[:4]  # keep first 4
        items.append({
            "id": "user-added",
            "category": "其他",
            "requirement": "用户手动添加的废标项",
            "source_section": "补充",
            "source_page": 0,
            "original_text": "",
        })

        # ── Step 3: Parse bid ──
        with open(bid_path, "rb") as f:
            resp = client.post(
                "/api/bid-review/parse-bid",
                files=[("files", ("bid.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )
        assert resp.json()["ok"] is True
        bid_text = resp.json()["data"]["text"]
        assert "九洲科技" in bid_text

        # ── Step 4: Check ──
        llm.chat = MagicMock(return_value=check_report)
        with patch("api.deps.get_llm", return_value=llm):
            resp = client.post("/api/bid-review/check", json={
                "items": items,
                "bid_text": bid_text,
            })
        assert resp.status_code == 200

        events = []
        for line in resp.text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1

        table_data = done_events[0]["table_data"]
        assert len(table_data) >= 1

        # Verify we got meaningful risk levels
        risks = set(r["risk"] for r in table_data)
        assert len(risks) >= 1  # at least some risk classification
