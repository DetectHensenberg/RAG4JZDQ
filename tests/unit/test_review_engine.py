"""Unit tests for bid review engine — rule scanning, LLM parsing, table parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.bid.review_engine import (
    DisqualItem,
    extract_text_from_file,
    parse_review_table,
    rule_based_scan,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bid_test_data"


class TestRuleBasedScan:
    """Test the regex/keyword-based first pass scanner."""

    def test_star_items(self) -> None:
        text = "★ 系统应支持不少于1000个终端。\n★ 响应时间不超过3秒。\n普通要求。"
        items = rule_based_scan(text)
        star_items = [i for i in items if i.category == "★号"]
        assert len(star_items) >= 2

    def test_disqualification_keywords(self) -> None:
        text = "投标保证金须在截止时间前到账，否则废标。投标文件须加盖公章，不满足则按无效投标处理。"
        items = rule_based_scan(text)
        assert len(items) >= 2
        texts = " ".join(i.requirement for i in items)
        assert "废标" in texts or "无效投标" in texts

    def test_section_keywords(self) -> None:
        text = "第二章 符合性审查\n1. 投标文件须按规定格式编制。\n2. 须加盖公章。"
        items = rule_based_scan(text)
        conformity = [i for i in items if i.category == "符合性"]
        assert len(conformity) >= 1

    def test_qualification_review(self) -> None:
        text = "资格性审查要求：投标人须提供营业执照。未通过资格性审查的，按无效投标处理。"
        items = rule_based_scan(text)
        categories = [i.category for i in items]
        assert "资格性" in categories

    def test_empty_text(self) -> None:
        items = rule_based_scan("")
        assert items == []

    def test_no_matches(self) -> None:
        text = "这是一段普通的文本，没有任何废标相关内容。天气很好。"
        items = rule_based_scan(text)
        assert len(items) == 0

    def test_deduplication(self) -> None:
        text = "★ 系统响应时间不超过3秒。\n★ 系统响应时间不超过3秒。"
        items = rule_based_scan(text)
        star_items = [i for i in items if i.category == "★号"]
        assert len(star_items) == 1  # should deduplicate

    def test_source_section_populated(self) -> None:
        text = "第三章 资格性审查\n投标人须提供营业执照，否则废标。\n第四章 技术要求\n★ 系统支持1000终端。"
        items = rule_based_scan(text)
        assert len(items) >= 2
        for item in items:
            assert item.source_section != "", f"source_section empty for: {item.requirement}"

    def test_category_infer_guarantee(self) -> None:
        text = "第二章 投标须知\n投标保证金须在截止时间前到账，否则废标。"
        items = rule_based_scan(text)
        guarantee_items = [i for i in items if "保证金" in i.requirement]
        assert len(guarantee_items) >= 1
        assert guarantee_items[0].category == "资格性"

    def test_category_infer_quality(self) -> None:
        text = "第五章 商务条款\n严禁在未经验收、验收已过期或验收不合格的情况下投入使用，否则由此产生的后果由使用方负责。"
        items = rule_based_scan(text)
        quality_items = [i for i in items if "验收" in i.requirement]
        assert len(quality_items) >= 1
        assert quality_items[0].category == "实质性"

    def test_scan_mock_tender_docx(self) -> None:
        docx_path = FIXTURES_DIR / "mock_tender.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")
        text = extract_text_from_file(str(docx_path))
        assert len(text) > 100

        items = rule_based_scan(text)
        assert len(items) >= 3

        categories = set(i.category for i in items)
        assert "★号" in categories

        # Verify source_section is populated for most items
        with_section = [i for i in items if i.source_section]
        assert len(with_section) >= len(items) // 2, \
            f"Only {len(with_section)}/{len(items)} items have source_section"

        # Verify no excessive "其他" category
        other_count = sum(1 for i in items if i.category == "其他")
        assert other_count <= len(items) // 2, \
            f"Too many '其他' items: {other_count}/{len(items)}"


class TestParseReviewTable:
    """Test Markdown table parsing from review report."""

    def test_basic_table(self) -> None:
        md = """## 审查报告

| 序号 | 类型 | 废标项要求 | 响应状态 | 风险等级 | 详细说明 |
|------|------|-----------|---------|---------|---------|
| 1 | 符合性 | 投标文件格式 | ✅已响应 | 低 | 格式正确 |
| 2 | ★号 | 终端接入1000个 | ⚠️不完整 | 中 | 仅提及500个 |
| 3 | 资格性 | ISO9001认证 | ❌缺失 | 高 | 未找到相关内容 |
"""
        rows = parse_review_table(md)
        assert len(rows) == 3

        assert rows[0]["status"] == "responded"
        assert rows[0]["risk"] == "low"

        assert rows[1]["status"] == "incomplete"
        assert rows[1]["risk"] == "medium"

        assert rows[2]["status"] == "missing"
        assert rows[2]["risk"] == "high"

    def test_empty_text(self) -> None:
        assert parse_review_table("") == []

    def test_no_table(self) -> None:
        assert parse_review_table("这是纯文本，没有表格。") == []

    def test_partial_status_match(self) -> None:
        md = """| 序号 | 类型 | 要求 | 状态 | 风险 | 说明 |
|---|---|---|---|---|---|
| 1 | 实质性 | 存储100TB | 已响应 | 低 | OK |
"""
        rows = parse_review_table(md)
        assert len(rows) >= 1
        assert rows[0]["status"] == "responded"


class TestExtractTextFromFile:
    """Test document text extraction."""

    def test_extract_docx(self) -> None:
        docx_path = FIXTURES_DIR / "mock_tender.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")
        text = extract_text_from_file(str(docx_path))
        assert "招标文件" in text
        assert "符合性审查" in text
        assert "★" in text

    def test_extract_bid_docx(self) -> None:
        docx_path = FIXTURES_DIR / "mock_bid.docx"
        if not docx_path.exists():
            pytest.skip("Test fixture not generated")
        text = extract_text_from_file(str(docx_path))
        assert "投标文件" in text
        assert "九洲科技" in text

    def test_unsupported_format(self) -> None:
        with pytest.raises(ValueError, match="不支持"):
            extract_text_from_file("test.txt")


class TestDisqualItem:
    """Test DisqualItem dataclass."""

    def test_auto_id(self) -> None:
        item = DisqualItem(category="★号", requirement="测试要求")
        assert item.id != ""
        assert len(item.id) == 8

    def test_to_dict(self) -> None:
        item = DisqualItem(id="abc", category="符合性", requirement="格式要求")
        d = item.to_dict()
        assert d["id"] == "abc"
        assert d["category"] == "符合性"
        assert d["requirement"] == "格式要求"
