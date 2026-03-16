"""Unit tests for rebuild_ingestion_history helpers.

Tests cover:
- _clean_chunk: image ref and description removal
- _is_junk_title: junk title detection (short, slide N, hex, table markers)
- extract_title_from_chunks: title extraction priority
  - Slide 1-3 headings
  - Markdown headings
  - First meaningful text line
  - Fallback to "(无标题)"
- ensure_history_table: SQLite table creation
- _compute_file_hash: SHA256 file content hashing
"""

import hashlib
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.rebuild_ingestion_history import (
    _clean_chunk,
    _compute_file_hash,
    _is_junk_title,
    ensure_history_table,
    extract_title_from_chunks,
)


# ---------------------------------------------------------------------------
# Tests: _clean_chunk
# ---------------------------------------------------------------------------

class TestCleanChunk:
    """Tests for image reference and description removal."""

    def test_removes_image_tag(self) -> None:
        text = "Hello [IMAGE: page1_img2.png] world"
        assert "[IMAGE:" not in _clean_chunk(text)
        assert "Hello" in _clean_chunk(text)

    def test_removes_description_tag(self) -> None:
        text = "Title (Description: A photo of a building\nwith trees) more text"
        result = _clean_chunk(text)
        assert "Description:" not in result
        assert "more text" in result

    def test_removes_markdown_image(self) -> None:
        text = "See ![alt text](http://example.com/img.png) here"
        result = _clean_chunk(text)
        assert "![" not in result
        assert "See" in result

    def test_preserves_normal_text(self) -> None:
        text = "This is a normal paragraph with no images."
        assert _clean_chunk(text) == text

    def test_handles_empty_string(self) -> None:
        assert _clean_chunk("") == ""


# ---------------------------------------------------------------------------
# Tests: _is_junk_title
# ---------------------------------------------------------------------------

class TestIsJunkTitle:
    """Tests for junk title detection."""

    def test_short_titles_are_junk(self) -> None:
        assert _is_junk_title("ab") is True
        assert _is_junk_title("abc") is True

    def test_slide_keyword_is_junk(self) -> None:
        assert _is_junk_title("slide") is True
        assert _is_junk_title("Slide") is True
        assert _is_junk_title("Slide 1") is True
        assert _is_junk_title("SLIDE 42") is True

    def test_chinese_junk_keywords(self) -> None:
        assert _is_junk_title("目录") is True
        assert _is_junk_title("附录") is True
        assert _is_junk_title("结语") is True
        assert _is_junk_title("核心概念") is True

    def test_hex_string_is_junk(self) -> None:
        assert _is_junk_title("1458b6b0_96_3") is True
        assert _is_junk_title("abcdef12") is True

    def test_table_markers_are_junk(self) -> None:
        assert _is_junk_title("| Column1 | Column2") is True
        assert _is_junk_title("---") is True

    def test_meaningful_titles_are_not_junk(self) -> None:
        assert _is_junk_title("数据治理整体方案") is False
        assert _is_junk_title("AI Agent 架构和发展趋势") is False
        assert _is_junk_title("Enterprise Data Governance") is False

    def test_contents_keyword_is_junk(self) -> None:
        assert _is_junk_title("contents") is True
        assert _is_junk_title("Contents") is True


# ---------------------------------------------------------------------------
# Tests: extract_title_from_chunks
# ---------------------------------------------------------------------------

class TestExtractTitleFromChunks:
    """Tests for title extraction priority logic."""

    def test_extracts_slide_heading(self) -> None:
        """Priority 1: heading from Slide 1-3 section."""
        chunks = [
            (0, "## Slide 1\n\n### 数据治理整体方案\n\nSome content"),
            (1, "## Slide 2\n\nMore content"),
        ]
        assert extract_title_from_chunks(chunks) == "数据治理整体方案"

    def test_extracts_slide2_heading(self) -> None:
        chunks = [
            (0, "## Slide 1\n\n### 目录\n\nSome content"),  # junk
            (1, "## Slide 2\n\n### 智能制造解决方案\n\nDetails"),
        ]
        assert extract_title_from_chunks(chunks) == "智能制造解决方案"

    def test_extracts_markdown_heading(self) -> None:
        """Priority 2: first markdown heading that isn't junk."""
        chunks = [
            (0, "Some intro text\n# 企业数字化转型规划\n\nParagraph"),
            (1, "## Details"),
        ]
        assert extract_title_from_chunks(chunks) == "企业数字化转型规划"

    def test_skips_junk_headings(self) -> None:
        """Should skip junk headings and find a good one."""
        chunks = [
            (0, "# 目录\n\n## 附录\n\n## 数据资产管理方法论"),
        ]
        assert extract_title_from_chunks(chunks) == "数据资产管理方法论"

    def test_extracts_first_meaningful_line(self) -> None:
        """Priority 3: first meaningful text line from early chunks."""
        chunks = [
            (0, "short\nab\n这是一篇关于数据治理的详细分析报告"),
        ]
        assert "数据治理" in extract_title_from_chunks(chunks)

    def test_fallback_to_no_title(self) -> None:
        """Should return '(无标题)' when no good title found."""
        chunks = [
            (0, "abc"),
            (1, "---"),
            (2, "| x | y |"),
        ]
        assert extract_title_from_chunks(chunks) == "(无标题)"

    def test_chunks_sorted_by_index(self) -> None:
        """Should sort chunks by index before scanning."""
        chunks = [
            (5, "## Late content"),
            (0, "# 第一章 项目概述"),
            (2, "Middle content"),
        ]
        assert extract_title_from_chunks(chunks) == "第一章 项目概述"

    def test_title_truncated_to_100_chars(self) -> None:
        """Titles longer than 100 chars should be truncated."""
        long_title = "A" * 200
        chunks = [(0, f"# {long_title}")]
        result = extract_title_from_chunks(chunks)
        assert len(result) <= 100

    def test_image_refs_cleaned_before_extraction(self) -> None:
        """Image references should be stripped before extracting title."""
        chunks = [
            (0, "[IMAGE: logo.png]\n(Description: A company logo)\n# 智能超算解决方案"),
        ]
        assert extract_title_from_chunks(chunks) == "智能超算解决方案"

    def test_empty_chunks_returns_no_title(self) -> None:
        chunks: list[tuple[int, str]] = []
        assert extract_title_from_chunks(chunks) == "(无标题)"


# ---------------------------------------------------------------------------
# Tests: ensure_history_table
# ---------------------------------------------------------------------------

class TestEnsureHistoryTable:
    """Tests for SQLite table creation."""

    def test_creates_table(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ensure_history_table(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ingestion_history'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_creates_index(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ensure_history_table(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_status'"
            )
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_idempotent(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ensure_history_table(db_path)
            ensure_history_table(db_path)  # should not raise
            conn = sqlite3.connect(db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='ingestion_history'"
            ).fetchone()[0]
            assert count == 1
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_wal_mode_enabled(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ensure_history_table(db_path)
            conn = sqlite3.connect(db_path)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests: _compute_file_hash
# ---------------------------------------------------------------------------

class TestComputeFileHash:
    """Tests for SHA256 file content hashing."""

    def test_hash_matches_hashlib(self) -> None:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"test content for hashing")
            path = f.name
        try:
            result = _compute_file_hash(path)
            expected = hashlib.sha256(b"test content for hashing").hexdigest()
            assert result == expected
        finally:
            Path(path).unlink(missing_ok=True)

    def test_hash_consistent(self) -> None:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"consistent content")
            path = f.name
        try:
            assert _compute_file_hash(path) == _compute_file_hash(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_hash_length(self) -> None:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"x")
            path = f.name
        try:
            assert len(_compute_file_hash(path)) == 64
        finally:
            Path(path).unlink(missing_ok=True)

    def test_different_content_different_hash(self) -> None:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix="_a") as f1:
            f1.write(b"content A")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix="_b") as f2:
            f2.write(b"content B")
            path2 = f2.name
        try:
            assert _compute_file_hash(path1) != _compute_file_hash(path2)
        finally:
            Path(path1).unlink(missing_ok=True)
            Path(path2).unlink(missing_ok=True)
