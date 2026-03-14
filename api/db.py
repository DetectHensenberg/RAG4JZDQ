"""Database connection utilities — context manager for safe SQLite access.

Provides a unified way to open, use, and close SQLite connections with
WAL mode, ensuring connections are always properly released even when
exceptions occur.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


@contextmanager
def get_connection(
    db_path: str | Path,
    *,
    wal: bool = True,
    row_factory: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a SQLite connection and ensures cleanup.

    Args:
        db_path: Path to the SQLite database file.
        wal: Enable WAL journal mode (default True).
        row_factory: If True, set ``row_factory = sqlite3.Row`` for
            dict-like row access.

    Yields:
        An open :class:`sqlite3.Connection`.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL;")
        if row_factory:
            conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()
