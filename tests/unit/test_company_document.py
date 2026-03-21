"""Unit tests for company document CRUD and PDF parsing."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bid.document_db import (
    CompanyDocument,
    clear_company_docs,
    delete_company_doc,
    get_company_doc,
    get_company_doc_by_key,
    list_company_docs,
    upsert_company_doc,
)


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path: Path):
    """Redirect bid_document DB to a temp file for each test."""
    temp_db = tmp_path / "test_bid_document.db"
    with patch("src.bid.document_db._DB_PATH", temp_db):
        with patch("src.bid.document_db._MATERIALS_DIR", tmp_path / "materials"):
            yield


class TestCompanyDocumentCRUD:
    """Test basic CRUD operations for company documents."""

    def test_upsert_insert(self) -> None:
        """Test inserting a new document."""
        doc = CompanyDocument(
            doc_key="business_license",
            doc_name="营业执照",
            category="license",
            content="营业执照内容...",
            page_start=1,
            page_end=2,
            source_file="test.pdf",
        )
        doc_id = upsert_company_doc(doc)
        assert doc_id > 0
        assert doc.id == doc_id
        assert doc.created_at > 0
        assert doc.updated_at > 0

    def test_upsert_update(self) -> None:
        """Test updating an existing document by doc_key."""
        doc = CompanyDocument(
            doc_key="tax_cert",
            doc_name="完税证明",
            category="financial",
            content="原始内容",
            page_start=10,
            page_end=12,
        )
        doc_id = upsert_company_doc(doc)

        # Update with same key
        doc2 = CompanyDocument(
            doc_key="tax_cert",
            doc_name="完税证明（更新）",
            category="financial",
            content="更新后的内容",
            page_start=10,
            page_end=15,
        )
        doc_id2 = upsert_company_doc(doc2)
        assert doc_id2 == doc_id  # Same ID since same key

        fetched = get_company_doc(doc_id)
        assert fetched is not None
        assert fetched.doc_name == "完税证明（更新）"
        assert fetched.content == "更新后的内容"
        assert fetched.page_end == 15

    def test_get_by_key(self) -> None:
        """Test fetching a document by its unique key."""
        doc = CompanyDocument(
            doc_key="audit_report",
            doc_name="审计报告",
            category="financial",
        )
        upsert_company_doc(doc)

        fetched = get_company_doc_by_key("audit_report")
        assert fetched is not None
        assert fetched.doc_name == "审计报告"

        # Non-existent key
        assert get_company_doc_by_key("nonexistent") is None

    def test_list_all(self) -> None:
        """Test listing all documents."""
        docs = [
            CompanyDocument(doc_key="doc1", doc_name="文档1", category="license", page_start=1),
            CompanyDocument(doc_key="doc2", doc_name="文档2", category="financial", page_start=5),
            CompanyDocument(doc_key="doc3", doc_name="文档3", category="declaration", page_start=10),
        ]
        for d in docs:
            upsert_company_doc(d)

        all_docs = list_company_docs()
        assert len(all_docs) == 3
        # Should be sorted by page_start
        assert all_docs[0].doc_key == "doc1"
        assert all_docs[1].doc_key == "doc2"
        assert all_docs[2].doc_key == "doc3"

    def test_list_by_category(self) -> None:
        """Test filtering documents by category."""
        docs = [
            CompanyDocument(doc_key="lic1", doc_name="证照1", category="license"),
            CompanyDocument(doc_key="fin1", doc_name="财务1", category="financial"),
            CompanyDocument(doc_key="lic2", doc_name="证照2", category="license"),
        ]
        for d in docs:
            upsert_company_doc(d)

        license_docs = list_company_docs(category="license")
        assert len(license_docs) == 2
        assert all(d.category == "license" for d in license_docs)

    def test_delete(self) -> None:
        """Test deleting a document."""
        doc = CompanyDocument(doc_key="to_delete", doc_name="待删除")
        doc_id = upsert_company_doc(doc)

        assert get_company_doc(doc_id) is not None
        deleted = delete_company_doc(doc_id)
        assert deleted is True
        assert get_company_doc(doc_id) is None

        # Delete non-existent
        assert delete_company_doc(999) is False

    def test_clear_all(self) -> None:
        """Test clearing all documents."""
        for i in range(5):
            upsert_company_doc(CompanyDocument(doc_key=f"doc{i}", doc_name=f"文档{i}"))

        assert len(list_company_docs()) == 5
        count = clear_company_docs()
        assert count == 5
        assert len(list_company_docs()) == 0


class TestCompanyDocParser:
    """Test PDF parsing logic (with mocked LLM and PDF extraction)."""

    def test_extract_toc_text_mock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test extracting text from PDF for TOC analysis (mocked)."""
        import fitz

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(str(pdf_path))
        doc.close()

        # Mock get_text to return Chinese content
        def mock_get_text(self):
            return "目录\n1. 营业执照 ..................... 1\n2. 审计报告 ..................... 5"

        monkeypatch.setattr(fitz.Page, "get_text", mock_get_text)

        from src.bid.company_doc_parser import extract_toc_text

        text = extract_toc_text(str(pdf_path), max_pages=5)
        assert "目录" in text
        assert "PDF共1页" in text

    def test_extract_page_text_mock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test extracting text from specific pages (mocked)."""
        import fitz

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        for i in range(5):
            doc.new_page(width=595, height=842)
        doc.save(str(pdf_path))
        doc.close()

        # Mock get_text to return different content per page
        page_contents = [
            "第1页内容",
            "第2页内容",
            "第3页内容",
            "第4页内容",
            "第5页内容",
        ]

        def mock_get_text(self):
            idx = self.number  # 0-indexed
            return page_contents[idx] if idx < len(page_contents) else ""

        monkeypatch.setattr(fitz.Page, "get_text", mock_get_text)

        from src.bid.company_doc_parser import extract_page_text

        text = extract_page_text(str(pdf_path), 2, 4)
        assert "第2页内容" in text
        assert "第3页内容" in text
        assert "第4页内容" in text
        assert "第1页内容" not in text
        assert "第5页内容" not in text

    @pytest.mark.asyncio
    async def test_identify_sections(self, tmp_path: Path) -> None:
        """Test LLM-based section identification."""
        import fitz

        # Create minimal test PDF
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(str(pdf_path))
        doc.close()

        # Mock LLM response
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''[
            {"doc_key": "business_license", "doc_name": "营业执照", "category": "license", "page_start": 1, "page_end": 4},
            {"doc_key": "audit_report", "doc_name": "财务审计报告", "category": "financial", "page_start": 5, "page_end": 9},
            {"doc_key": "tax_cert", "doc_name": "完税证明", "category": "financial", "page_start": 10, "page_end": 12}
        ]'''
        mock_llm.chat.return_value = mock_response

        from src.bid.company_doc_parser import identify_sections

        sections = await identify_sections(str(pdf_path), mock_llm)

        assert len(sections) == 3
        assert sections[0].doc_key == "business_license"
        assert sections[0].doc_name == "营业执照"
        assert sections[0].page_start == 1
        assert sections[1].category == "financial"

    @pytest.mark.asyncio
    async def test_parse_and_import(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test full parse and import workflow."""
        import fitz

        # Create minimal test PDF
        pdf_path = tmp_path / "qualification.pdf"
        doc = fitz.open()
        for i in range(10):
            doc.new_page(width=595, height=842)
        doc.save(str(pdf_path))
        doc.close()

        # Mock get_text to return content per page
        def mock_get_text(self):
            idx = self.number
            if idx == 0:
                return "目录\n1. 营业执照 ... 2\n2. 审计报告 ... 5"
            elif idx < 4:
                return f"营业执照内容 第{idx + 1}页"
            else:
                return f"审计报告内容 第{idx + 1}页"

        monkeypatch.setattr(fitz.Page, "get_text", mock_get_text)

        # Mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''[
            {"doc_key": "license", "doc_name": "营业执照", "category": "license", "page_start": 2, "page_end": 4},
            {"doc_key": "audit", "doc_name": "审计报告", "category": "financial", "page_start": 5, "page_end": 10}
        ]'''
        mock_llm.chat.return_value = mock_response

        from src.bid.company_doc_parser import parse_and_import

        results = await parse_and_import(str(pdf_path), mock_llm, clear_existing=True)

        assert len(results) == 2
        assert results[0]["doc_key"] == "license"
        assert "营业执照内容" in results[0]["content"]
        assert results[1]["doc_key"] == "audit"

        # Verify database
        all_docs = list_company_docs()
        assert len(all_docs) == 2
