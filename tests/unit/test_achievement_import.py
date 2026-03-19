"""Unit tests for achievement batch import (Excel/CSV)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.bid.achievement_db import list_achievements
from src.bid.achievement_import import import_csv, import_excel, import_file


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bid_test_data"


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path: Path):
    """Redirect DB + suppress ChromaDB."""
    temp_db = tmp_path / "test_ach.db"
    with patch("src.bid.achievement_db._DB_PATH", temp_db):
        with patch("src.bid.achievement_db._sync_to_chroma"):
            with patch("src.bid.achievement_db._delete_from_chroma"):
                yield


class TestExcelImport:

    def test_import_xlsx(self) -> None:
        xlsx_path = FIXTURES_DIR / "mock_achievements.xlsx"
        if not xlsx_path.exists():
            pytest.skip("Test fixture not generated")
        content = xlsx_path.read_bytes()
        result = import_excel(content)
        assert result.success_count == 7
        assert result.error_count == 0

        listed = list_achievements()
        assert listed.total == 7

    def test_import_xlsx_via_import_file(self) -> None:
        xlsx_path = FIXTURES_DIR / "mock_achievements.xlsx"
        if not xlsx_path.exists():
            pytest.skip("Test fixture not generated")
        result = import_file("data.xlsx", xlsx_path.read_bytes())
        assert result.success_count == 7


class TestCSVImport:

    def test_import_csv(self) -> None:
        csv_path = FIXTURES_DIR / "mock_achievements.csv"
        if not csv_path.exists():
            pytest.skip("Test fixture not generated")
        content = csv_path.read_bytes()
        result = import_csv(content)
        assert result.success_count == 2
        assert result.error_count == 0

    def test_import_csv_via_import_file(self) -> None:
        csv_path = FIXTURES_DIR / "mock_achievements.csv"
        if not csv_path.exists():
            pytest.skip("Test fixture not generated")
        result = import_file("data.csv", csv_path.read_bytes())
        assert result.success_count == 2

    def test_import_csv_missing_header(self) -> None:
        content = b"col1,col2\nval1,val2\n"
        result = import_csv(content)
        assert result.success_count == 0
        assert any("\u9879\u76ee\u540d\u79f0" in e for e in result.errors)

    def test_import_csv_empty_name(self) -> None:
        content = "项目名称,项目金额\n,500\n".encode("utf-8-sig")
        result = import_csv(content)
        assert result.success_count == 0
        assert result.error_count == 1


class TestUnsupportedFormat:

    def test_unsupported_extension(self) -> None:
        result = import_file("data.json", b"{}")
        assert result.success_count == 0
        assert any("不支持" in e for e in result.errors)
