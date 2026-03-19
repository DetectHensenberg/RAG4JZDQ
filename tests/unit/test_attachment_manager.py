"""Unit tests for attachment manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.bid.attachment_manager import (
    delete_all_attachments,
    delete_attachment,
    get_attachment_path,
    list_attachments,
    save_attachment,
)


@pytest.fixture(autouse=True)
def _use_temp_dir(tmp_path: Path):
    """Redirect attachments root to temp directory."""
    with patch("src.bid.attachment_manager._ATTACHMENTS_ROOT", tmp_path / "attachments"):
        yield


class TestAttachmentManager:

    def test_save_and_list(self) -> None:
        info = save_attachment(1, "contract.pdf", b"fake-pdf-content")
        assert info.filename == "contract.pdf"
        assert info.size == len(b"fake-pdf-content")

        items = list_attachments(1)
        assert len(items) == 1
        assert items[0].filename == "contract.pdf"

    def test_save_multiple(self) -> None:
        save_attachment(1, "a.pdf", b"aaa")
        save_attachment(1, "b.docx", b"bbbbb")
        items = list_attachments(1)
        assert len(items) == 2

    def test_get_path(self) -> None:
        save_attachment(2, "test.pdf", b"data")
        path = get_attachment_path(2, "test.pdf")
        assert path is not None
        assert path.is_file()

    def test_get_path_nonexistent(self) -> None:
        path = get_attachment_path(999, "nope.pdf")
        assert path is None

    def test_delete_single(self) -> None:
        save_attachment(3, "file.pdf", b"data")
        assert delete_attachment(3, "file.pdf") is True
        assert list_attachments(3) == []

    def test_delete_nonexistent(self) -> None:
        assert delete_attachment(999, "nope.pdf") is False

    def test_delete_all(self) -> None:
        save_attachment(4, "a.pdf", b"aaa")
        save_attachment(4, "b.pdf", b"bbb")
        count = delete_all_attachments(4)
        assert count == 2
        assert list_attachments(4) == []

    def test_list_empty_record(self) -> None:
        assert list_attachments(999) == []

    def test_safe_filename(self) -> None:
        info = save_attachment(5, "../../evil.txt", b"hack")
        assert info.filename == "evil.txt"
        assert ".." not in info.filename
