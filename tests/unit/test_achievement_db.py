"""Unit tests for achievement database CRUD and filtering."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.bid.achievement_db import (
    AchievementRecord,
    ListFilter,
    _DB_PATH,
    create_achievement,
    delete_achievement,
    get_achievement,
    list_achievements,
    update_achievement,
)


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path: Path):
    """Redirect achievement DB to a temp file for each test."""
    temp_db = tmp_path / "test_achievements.db"
    with patch("src.bid.achievement_db._DB_PATH", temp_db):
        # Also patch ChromaDB sync to avoid side effects
        with patch("src.bid.achievement_db._sync_to_chroma"):
            with patch("src.bid.achievement_db._delete_from_chroma"):
                yield


class TestAchievementCRUD:
    """Test basic CRUD operations."""

    def test_create_and_get(self) -> None:
        record = AchievementRecord(
            project_name="智慧城市项目",
            project_content="城市综合管理平台建设",
            amount=500.0,
            sign_date="2023-06-15",
            acceptance_date="2024-03-20",
            client_contact="张三",
            client_phone="13800138000",
            tags=["智慧城市", "集成"],
        )
        new_id = create_achievement(record)
        assert new_id > 0

        fetched = get_achievement(new_id)
        assert fetched is not None
        assert fetched.project_name == "智慧城市项目"
        assert fetched.amount == 500.0
        assert fetched.tags == ["智慧城市", "集成"]
        assert fetched.created_at > 0
        assert fetched.updated_at > 0

    def test_update(self) -> None:
        record = AchievementRecord(project_name="原始项目名")
        new_id = create_achievement(record)

        fetched = get_achievement(new_id)
        assert fetched is not None
        fetched.project_name = "更新后的项目名"
        fetched.amount = 999.9
        result = update_achievement(fetched)
        assert result is True

        updated = get_achievement(new_id)
        assert updated is not None
        assert updated.project_name == "更新后的项目名"
        assert updated.amount == 999.9

    def test_delete(self) -> None:
        record = AchievementRecord(project_name="待删除项目")
        new_id = create_achievement(record)
        assert get_achievement(new_id) is not None

        result = delete_achievement(new_id)
        assert result is True
        assert get_achievement(new_id) is None

    def test_delete_nonexistent(self) -> None:
        result = delete_achievement(99999)
        assert result is False

    def test_get_nonexistent(self) -> None:
        assert get_achievement(99999) is None

    def test_to_dict(self) -> None:
        record = AchievementRecord(
            id=1,
            project_name="测试",
            amount=100.0,
            tags=["tag1"],
        )
        d = record.to_dict()
        assert d["id"] == 1
        assert d["project_name"] == "测试"
        assert d["amount"] == 100.0
        assert d["tags"] == ["tag1"]


class TestAchievementList:
    """Test listing with filters, sorting, and pagination."""

    @pytest.fixture(autouse=True)
    def _seed_data(self) -> None:
        records = [
            AchievementRecord(project_name="智慧交通A", project_content="交通管理", amount=800, sign_date="2022-03-15", tags=["交通"]),
            AchievementRecord(project_name="智慧园区B", project_content="园区安防", amount=650, sign_date="2023-01-10", tags=["安防"]),
            AchievementRecord(project_name="数据中心C", project_content="数据中心建设", amount=520, sign_date="2023-06-01", tags=["数据中心"]),
            AchievementRecord(project_name="智慧城管D", project_content="城市管理", amount=380, sign_date="2022-09-01", tags=["智慧城市"]),
            AchievementRecord(project_name="应急指挥E", project_content="应急指挥调度", amount=450, sign_date="2023-04-20", tags=["应急"]),
        ]
        for r in records:
            create_achievement(r)

    def test_list_all(self) -> None:
        result = list_achievements()
        assert result.total == 5
        assert len(result.records) == 5

    def test_keyword_filter(self) -> None:
        result = list_achievements(ListFilter(keyword="智慧"))
        assert result.total == 3  # 智慧交通A, 智慧园区B, 智慧城管D... wait
        # Actually "智慧交通A", "智慧城管D" match project_name; "智慧园区B" also matches
        names = [r.project_name for r in result.records]
        assert all("智慧" in n for n in names)

    def test_amount_filter(self) -> None:
        result = list_achievements(ListFilter(min_amount=500))
        assert result.total == 3  # 800, 650, 520
        assert all(r.amount >= 500 for r in result.records)

    def test_amount_range_filter(self) -> None:
        result = list_achievements(ListFilter(min_amount=400, max_amount=700))
        assert result.total == 3  # 650, 520, 450

    def test_date_filter(self) -> None:
        result = list_achievements(ListFilter(start_date="2023-01-01"))
        assert result.total == 3  # B(2023-01-10), C(2023-06-01), E(2023-04-20)

    def test_pagination(self) -> None:
        result = list_achievements(ListFilter(page=1, page_size=2))
        assert result.total == 5
        assert len(result.records) == 2
        assert result.page == 1

        result2 = list_achievements(ListFilter(page=2, page_size=2))
        assert len(result2.records) == 2

        result3 = list_achievements(ListFilter(page=3, page_size=2))
        assert len(result3.records) == 1

    def test_sort_by_amount_asc(self) -> None:
        result = list_achievements(ListFilter(sort_by="amount", sort_order="asc"))
        amounts = [r.amount for r in result.records]
        assert amounts == sorted(amounts)

    def test_sort_by_amount_desc(self) -> None:
        result = list_achievements(ListFilter(sort_by="amount", sort_order="desc"))
        amounts = [r.amount for r in result.records]
        assert amounts == sorted(amounts, reverse=True)
