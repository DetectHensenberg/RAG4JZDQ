"""Unit tests for ChromaDB HNSW backup and restore manager.

Tests cover:
- HNSW directory discovery (_find_hnsw_dirs)
- HNSW health validation (_is_hnsw_healthy)
- Backup creation with timestamped snapshots
- Backup skipped when HNSW is unhealthy
- Snapshot rotation with startup-label protection
- Restore from latest backup (newest-first)
- Restore returns False when no backups exist
- verify_and_backup integration with collection mock
"""

import shutil
import tempfile
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from src.libs.vector_store.chroma_backup import ChromaBackupManager, MAX_SNAPSHOTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UUID_SEG = "36db8d3f-3d5a-4a1d-955c-ce83a401e38c"


def _make_healthy_hnsw(chroma_dir: Path, uuid: str = UUID_SEG) -> Path:
    """Create a fake but healthy HNSW segment directory."""
    seg = chroma_dir / uuid
    seg.mkdir(parents=True, exist_ok=True)
    (seg / "header.bin").write_bytes(b"\x00" * 100)
    (seg / "data_level0.bin").write_bytes(b"\x00" * 2048)
    (seg / "index_metadata.pickle").write_bytes(b"\x00" * 200)
    (seg / "length.bin").write_bytes(b"\x00" * 40)
    return seg


def _make_corrupted_hnsw(chroma_dir: Path, uuid: str = UUID_SEG) -> Path:
    """Create a corrupted HNSW segment (header.bin wrong size)."""
    seg = chroma_dir / uuid
    seg.mkdir(parents=True, exist_ok=True)
    (seg / "header.bin").write_bytes(b"\x00" * 50)  # wrong size
    (seg / "data_level0.bin").write_bytes(b"\x00" * 2048)
    (seg / "index_metadata.pickle").write_bytes(b"\x00" * 200)
    return seg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dirs() -> Generator[tuple[Path, Path], None, None]:
    """Create temporary chroma and backup directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chroma_dir = Path(tmpdir) / "chroma"
        chroma_dir.mkdir()
        backup_dir = Path(tmpdir) / "backups"
        backup_dir.mkdir()
        yield chroma_dir, backup_dir


@pytest.fixture
def mgr(temp_dirs: tuple[Path, Path]) -> ChromaBackupManager:
    """Create a ChromaBackupManager with temp directories."""
    chroma_dir, backup_dir = temp_dirs
    return ChromaBackupManager(chroma_dir=chroma_dir, backup_dir=backup_dir)


# ---------------------------------------------------------------------------
# Tests: _find_hnsw_dirs
# ---------------------------------------------------------------------------

class TestFindHnswDirs:
    """Tests for HNSW directory discovery."""

    def test_finds_uuid_dir(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        dirs = mgr._find_hnsw_dirs()
        assert len(dirs) == 1
        assert dirs[0].name == UUID_SEG

    def test_ignores_non_uuid_dirs(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        (chroma_dir / "not-a-uuid").mkdir()
        (chroma_dir / "short").mkdir()
        dirs = mgr._find_hnsw_dirs()
        assert len(dirs) == 0

    def test_empty_chroma_dir(self, mgr: ChromaBackupManager) -> None:
        dirs = mgr._find_hnsw_dirs()
        assert dirs == []


# ---------------------------------------------------------------------------
# Tests: _is_hnsw_healthy
# ---------------------------------------------------------------------------

class TestIsHnswHealthy:
    """Tests for HNSW health validation."""

    def test_healthy_returns_true(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        assert mgr._is_hnsw_healthy() is True

    def test_missing_header_returns_false(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        seg = chroma_dir / UUID_SEG
        seg.mkdir(parents=True)
        (seg / "data_level0.bin").write_bytes(b"\x00" * 2048)
        (seg / "index_metadata.pickle").write_bytes(b"\x00" * 200)
        assert mgr._is_hnsw_healthy() is False

    def test_wrong_header_size_returns_false(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_corrupted_hnsw(chroma_dir)
        assert mgr._is_hnsw_healthy() is False

    def test_small_data_file_returns_false(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        seg = chroma_dir / UUID_SEG
        seg.mkdir(parents=True)
        (seg / "header.bin").write_bytes(b"\x00" * 100)
        (seg / "data_level0.bin").write_bytes(b"\x00" * 10)  # too small
        (seg / "index_metadata.pickle").write_bytes(b"\x00" * 200)
        assert mgr._is_hnsw_healthy() is False

    def test_small_metadata_returns_false(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        seg = chroma_dir / UUID_SEG
        seg.mkdir(parents=True)
        (seg / "header.bin").write_bytes(b"\x00" * 100)
        (seg / "data_level0.bin").write_bytes(b"\x00" * 2048)
        (seg / "index_metadata.pickle").write_bytes(b"\x00" * 10)  # too small
        assert mgr._is_hnsw_healthy() is False

    def test_no_hnsw_dirs_returns_true(self, mgr: ChromaBackupManager) -> None:
        """No dirs = vacuously healthy (nothing to check)."""
        assert mgr._is_hnsw_healthy() is True


# ---------------------------------------------------------------------------
# Tests: backup
# ---------------------------------------------------------------------------

class TestBackup:
    """Tests for backup creation."""

    def test_backup_creates_snapshot(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, backup_dir = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        result = mgr.backup(label="test")
        assert result is not None
        assert result.exists()
        assert "_test" in result.name
        # Snapshot should contain the UUID dir
        assert (result / UUID_SEG).exists()

    def test_backup_with_label(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        result = mgr.backup(label="startup")
        assert result is not None
        assert "_startup" in result.name

    def test_backup_without_label(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        result = mgr.backup()
        assert result is not None
        assert result.name.startswith("hnsw_")

    def test_backup_skipped_when_no_hnsw(self, mgr: ChromaBackupManager) -> None:
        result = mgr.backup(label="test")
        assert result is None

    def test_backup_skipped_when_corrupted(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_corrupted_hnsw(chroma_dir)
        result = mgr.backup(label="test")
        assert result is None

    def test_backup_copies_all_files(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        result = mgr.backup(label="copy")
        assert result is not None
        seg_backup = result / UUID_SEG
        assert (seg_backup / "header.bin").exists()
        assert (seg_backup / "data_level0.bin").exists()
        assert (seg_backup / "index_metadata.pickle").exists()


# ---------------------------------------------------------------------------
# Tests: _rotate_snapshots
# ---------------------------------------------------------------------------

class TestRotateSnapshots:
    """Tests for snapshot rotation with label protection."""

    def test_keeps_max_snapshots(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        for i in range(MAX_SNAPSHOTS + 2):
            mgr.backup(label=f"iter{i}")
            time.sleep(0.05)  # ensure unique timestamps
        snaps = mgr._list_snapshots()
        assert len(snaps) <= MAX_SNAPSHOTS

    def test_prefers_deleting_startup_backups(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        """Rotation should delete _startup backups first to protect _ingest/_manual."""
        _, backup_dir = temp_dirs
        # Manually create labeled snapshots
        (backup_dir / "hnsw_20260101_000001_startup").mkdir()
        (backup_dir / "hnsw_20260101_000002_startup").mkdir()
        (backup_dir / "hnsw_20260101_000003_manual").mkdir()
        (backup_dir / "hnsw_20260101_000004_ingest").mkdir()

        mgr._rotate_snapshots()
        remaining = mgr._list_snapshots()
        names = [s.name for s in remaining]

        assert len(remaining) == MAX_SNAPSHOTS
        # The manual and ingest backups should survive
        assert "hnsw_20260101_000003_manual" in names
        assert "hnsw_20260101_000004_ingest" in names

    def test_deletes_oldest_when_no_startup(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        _, backup_dir = temp_dirs
        (backup_dir / "hnsw_20260101_000001_ingest").mkdir()
        (backup_dir / "hnsw_20260101_000002_manual").mkdir()
        (backup_dir / "hnsw_20260101_000003_ingest").mkdir()
        (backup_dir / "hnsw_20260101_000004_ingest").mkdir()

        mgr._rotate_snapshots()
        remaining = mgr._list_snapshots()
        assert len(remaining) == MAX_SNAPSHOTS
        # Oldest ingest should be removed
        names = [s.name for s in remaining]
        assert "hnsw_20260101_000001_ingest" not in names


# ---------------------------------------------------------------------------
# Tests: restore_latest
# ---------------------------------------------------------------------------

class TestRestoreLatest:
    """Tests for HNSW restore from backup."""

    def test_restore_from_backup(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        mgr.backup(label="good")

        # Corrupt the current HNSW
        seg = chroma_dir / UUID_SEG
        shutil.rmtree(str(seg))
        assert not seg.exists()

        # Restore
        result = mgr.restore_latest()
        assert result is True
        assert seg.exists()
        assert (seg / "header.bin").exists()

    def test_restore_uses_newest_first(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, backup_dir = temp_dirs

        # Manually create two snapshots with known timestamps
        old_snap = backup_dir / "hnsw_20260101_000001_old"
        old_seg = old_snap / UUID_SEG
        old_seg.mkdir(parents=True)
        (old_seg / "header.bin").write_bytes(b"\x00" * 100)
        (old_seg / "marker.txt").write_text("old")

        new_snap = backup_dir / "hnsw_20260101_000002_new"
        new_seg = new_snap / UUID_SEG
        new_seg.mkdir(parents=True)
        (new_seg / "header.bin").write_bytes(b"\x00" * 100)
        (new_seg / "marker.txt").write_text("newest")

        # Ensure chroma dir has no HNSW (simulates corruption / deletion)
        mgr.restore_latest()
        assert (chroma_dir / UUID_SEG / "marker.txt").read_text() == "newest"

    def test_restore_no_backups(self, mgr: ChromaBackupManager) -> None:
        result = mgr.restore_latest()
        assert result is False

    def test_restore_replaces_corrupted_dirs(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)
        mgr.backup(label="healthy")

        # Corrupt the existing files
        seg = chroma_dir / UUID_SEG
        (seg / "header.bin").write_bytes(b"corrupted")

        result = mgr.restore_latest()
        assert result is True
        # header.bin should be restored to correct 100-byte size
        assert (seg / "header.bin").stat().st_size == 100


# ---------------------------------------------------------------------------
# Tests: verify_and_backup
# ---------------------------------------------------------------------------

class TestVerifyAndBackup:
    """Tests for verify_and_backup with mocked collection."""

    def test_healthy_collection_triggers_backup(self, mgr: ChromaBackupManager, temp_dirs: tuple[Path, Path]) -> None:
        chroma_dir, _ = temp_dirs
        _make_healthy_hnsw(chroma_dir)

        mock_col = MagicMock()
        mock_col.count.return_value = 100
        mock_col.peek.return_value = {"ids": ["id1"]}

        result = mgr.verify_and_backup(mock_col, label="test")
        assert result is True
        assert len(mgr._list_snapshots()) == 1

    def test_empty_collection_skips_backup(self, mgr: ChromaBackupManager) -> None:
        mock_col = MagicMock()
        mock_col.count.return_value = 0

        result = mgr.verify_and_backup(mock_col)
        assert result is False

    def test_failed_peek_skips_backup(self, mgr: ChromaBackupManager) -> None:
        mock_col = MagicMock()
        mock_col.count.return_value = 100
        mock_col.peek.side_effect = RuntimeError("HNSW error")

        result = mgr.verify_and_backup(mock_col)
        assert result is False
