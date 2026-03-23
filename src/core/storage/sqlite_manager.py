"""SQLiteManager - Centralized SQLite connection management for performance and concurrency."""

import logging
from pathlib import Path
from typing import Optional

import sqlite_utils
from src.core.settings import Settings, SQLiteSettings

logger = logging.getLogger(__name__)


class SQLiteManager:
    """Manages SQLite database connections with optimized PRAGMA settings.
    
    This class ensures all SQLite databases used by the RAG system
    are configured for maximum concurrency and reliability, especially
    on Windows platforms.
    """
    
    def __init__(self, settings: Settings):
        """Initialize with application settings."""
        self.settings = settings
        self.sqlite_config = getattr(settings, "sqlite", SQLiteSettings())

    def get_database(self, db_path: str | Path) -> sqlite_utils.Database:
        """Create and configure a sqlite_utils.Database instance."""
        import sqlite3
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use a connection with check_same_thread=False for multi-threaded async use
        conn = sqlite3.connect(str(path), check_same_thread=False)
        db = sqlite_utils.Database(conn)
        
        # Apply performance and concurrency pragmas
        try:
            db.conn.execute(f"PRAGMA journal_mode={self.sqlite_config.journal_mode}")
            db.conn.execute(f"PRAGMA busy_timeout={self.sqlite_config.busy_timeout}")
            db.conn.execute(f"PRAGMA synchronous={self.sqlite_config.synchronous}")
            db.conn.execute("PRAGMA cache_size=-2000")
            db.conn.execute("PRAGMA temp_store=MEMORY")
        except Exception as e:
            logger.warning(f"Failed to apply SQLite pragmas for {db_path}: {e}")
            
        return db

    @staticmethod
    def initialize_db(db_path: str | Path, busy_timeout: int = 20000) -> sqlite_utils.Database:
        """Static helper for direct initialization without settings object."""
        import sqlite3
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Consistent check_same_thread=False for async safety
        conn = sqlite3.connect(str(path), check_same_thread=False)
        db = sqlite_utils.Database(conn)
        db.conn.execute(f"PRAGMA busy_timeout={busy_timeout}")
        db.conn.execute("PRAGMA journal_mode=WAL")
        return db
