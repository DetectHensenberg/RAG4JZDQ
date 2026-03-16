"""ChromaDB HNSW index backup and restore manager.

Disaster recovery strategy:
  - On backend startup: backup current HNSW index (if healthy)
  - After each successful ingestion: verify index health, then backup
  - On corruption detected: auto-restore from latest good backup
  - Keep up to MAX_SNAPSHOTS rotating backups

Only backs up the HNSW binary directory (~42MB), not the full SQLite
database (~144MB), keeping it fast and lightweight.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_SNAPSHOTS = 3


class ChromaBackupManager:
    """Manages HNSW index backup and restore for ChromaDB.

    Args:
        chroma_dir: Path to ChromaDB persist directory.
        backup_dir: Path to store backups.
    """

    def __init__(
        self,
        chroma_dir: str | Path,
        backup_dir: Optional[str | Path] = None,
    ) -> None:
        self.chroma_dir = Path(chroma_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else self.chroma_dir.parent / "chroma_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _find_hnsw_dirs(self) -> list[Path]:
        """Find UUID-named HNSW segment directories in chroma_dir."""
        return [
            d for d in self.chroma_dir.iterdir()
            if d.is_dir() and len(d.name) == 36 and "-" in d.name
        ]

    def _is_hnsw_healthy(self) -> bool:
        """Check HNSW binary files look valid (without ChromaDB API).

        Validates:
          - header.bin exists and is exactly 100 bytes
          - data_level0.bin exists and is > 1KB
          - index_metadata.pickle exists and is > 100 bytes
        """
        for hnsw_dir in self._find_hnsw_dirs():
            header = hnsw_dir / "header.bin"
            data = hnsw_dir / "data_level0.bin"
            meta = hnsw_dir / "index_metadata.pickle"
            if not header.exists() or header.stat().st_size != 100:
                logger.warning(f"HNSW unhealthy: bad header.bin in {hnsw_dir.name}")
                return False
            if not data.exists() or data.stat().st_size < 1024:
                logger.warning(f"HNSW unhealthy: bad data_level0.bin in {hnsw_dir.name}")
                return False
            if not meta.exists() or meta.stat().st_size < 100:
                logger.warning(f"HNSW unhealthy: bad index_metadata.pickle in {hnsw_dir.name}")
                return False
        return True

    def _list_snapshots(self) -> list[Path]:
        """List existing snapshots sorted by timestamp (oldest first)."""
        snapshots = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith("hnsw_")],
            key=lambda p: p.name,
        )
        return snapshots

    def backup(self, label: str = "") -> Optional[Path]:
        """Backup HNSW binary files to a timestamped snapshot directory.

        Args:
            label: Optional label appended to snapshot name (e.g. 'startup', 'ingest').

        Returns:
            Path to the created snapshot, or None if nothing to backup.
        """
        hnsw_dirs = self._find_hnsw_dirs()
        if not hnsw_dirs:
            logger.debug("No HNSW segment found, skipping backup")
            return None

        if not self._is_hnsw_healthy():
            logger.warning("HNSW files appear corrupted, skipping backup")
            return None

        ts = time.strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        snapshot_name = f"hnsw_{ts}{suffix}"
        snapshot_path = self.backup_dir / snapshot_name
        snapshot_path.mkdir(parents=True, exist_ok=True)

        total_size = 0
        for hnsw_dir in hnsw_dirs:
            dest = snapshot_path / hnsw_dir.name
            shutil.copytree(str(hnsw_dir), str(dest))
            dir_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
            total_size += dir_size

        logger.info(
            f"HNSW backup created: {snapshot_name} "
            f"({total_size / 1024 / 1024:.1f}MB, {len(hnsw_dirs)} segment(s))"
        )

        # Rotate: keep only MAX_SNAPSHOTS
        self._rotate_snapshots()

        return snapshot_path

    def _rotate_snapshots(self) -> None:
        """Remove oldest snapshots beyond MAX_SNAPSHOTS.

        Protects non-startup backups: always keeps at least one
        'ingest' or 'manual' backup if available.
        """
        snapshots = self._list_snapshots()
        while len(snapshots) > MAX_SNAPSHOTS:
            # Find the oldest deletable snapshot (prefer deleting startup backups)
            deleted = False
            for i, snap in enumerate(snapshots):
                if "_startup" in snap.name:
                    shutil.rmtree(str(snap), ignore_errors=True)
                    logger.info(f"Rotated out old backup: {snap.name}")
                    snapshots.pop(i)
                    deleted = True
                    break
            if not deleted:
                # All are non-startup; remove the oldest
                oldest = snapshots.pop(0)
                shutil.rmtree(str(oldest), ignore_errors=True)
                logger.info(f"Rotated out old backup: {oldest.name}")

    def restore_latest(self) -> bool:
        """Restore HNSW from the latest good backup.

        Removes current (corrupted) HNSW dirs and copies from backup.

        Returns:
            True if restore succeeded, False if no backup available.
        """
        snapshots = self._list_snapshots()
        if not snapshots:
            logger.warning("No HNSW backups available for restore")
            return False

        # Try from newest to oldest
        for snapshot in reversed(snapshots):
            hnsw_subdirs = [
                d for d in snapshot.iterdir()
                if d.is_dir() and len(d.name) == 36 and "-" in d.name
            ]
            if not hnsw_subdirs:
                continue

            # Remove current corrupted HNSW dirs
            for d in self._find_hnsw_dirs():
                shutil.rmtree(str(d), ignore_errors=True)

            # Copy from backup
            restored = 0
            for src_dir in hnsw_subdirs:
                dest = self.chroma_dir / src_dir.name
                try:
                    shutil.copytree(str(src_dir), str(dest))
                    restored += 1
                except Exception as e:
                    logger.error(f"Failed to restore {src_dir.name}: {e}")

            if restored > 0:
                logger.info(
                    f"HNSW restored from backup: {snapshot.name} "
                    f"({restored} segment(s))"
                )
                return True

        logger.warning("All backups failed to restore")
        return False

    def verify_and_backup(self, collection: object, label: str = "ingest") -> bool:
        """Verify HNSW index health, then backup if healthy.

        Args:
            collection: ChromaDB collection object to test.
            label: Label for the backup snapshot.

        Returns:
            True if index is healthy and backup succeeded.
        """
        try:
            count = collection.count()  # type: ignore[union-attr]
            if count == 0:
                logger.debug("Collection empty, skipping backup")
                return False

            collection.peek(limit=1)  # type: ignore[union-attr]
            logger.debug(f"HNSW health check passed (count={count})")
        except Exception as e:
            logger.warning(f"HNSW health check failed, NOT backing up: {e}")
            return False

        self.backup(label=label)
        return True
