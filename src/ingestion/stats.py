"""Ingestion statistics tracking and persistence.

This module provides statistics collection for the ingestion pipeline,
including document counts, chunk metrics, and failure tracking.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Statistics for a single ingestion run."""
    
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source_path: str = ""
    status: str = "success"  # success, failed, skipped
    
    # Document metrics
    doc_count: int = 0
    chunk_count: int = 0
    image_count: int = 0
    vector_count: int = 0
    
    # Chunk metrics
    avg_chunk_size: float = 0.0
    min_chunk_size: int = 0
    max_chunk_size: int = 0
    empty_chunk_count: int = 0
    
    # Timing
    duration_ms: float = 0.0
    
    # Error info
    error_message: Optional[str] = None


@dataclass
class AggregatedStats:
    """Aggregated statistics across all ingestion runs."""
    
    total_docs: int = 0
    total_chunks: int = 0
    total_images: int = 0
    total_vectors: int = 0
    
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    
    avg_chunk_size: float = 0.0
    avg_duration_ms: float = 0.0
    
    last_ingestion: Optional[str] = None
    recent_errors: List[str] = field(default_factory=list)


class IngestionStatsTracker:
    """Tracks and persists ingestion statistics to SQLite."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize stats tracker.
        
        Args:
            db_path: Path to SQLite database. Defaults to data/db/ingestion_stats.db
        """
        if db_path is None:
            db_path = str(resolve_path("data/db/ingestion_stats.db"))
        
        self.db_path = db_path
        self._ensure_db()
    
    def _ensure_db(self) -> None:
        """Create database and tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source_path TEXT,
                    status TEXT NOT NULL,
                    doc_count INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    image_count INTEGER DEFAULT 0,
                    vector_count INTEGER DEFAULT 0,
                    avg_chunk_size REAL DEFAULT 0,
                    min_chunk_size INTEGER DEFAULT 0,
                    max_chunk_size INTEGER DEFAULT 0,
                    empty_chunk_count INTEGER DEFAULT 0,
                    duration_ms REAL DEFAULT 0,
                    error_message TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON ingestion_stats(timestamp)
            """)
            conn.commit()
    
    def record(self, stats: IngestionStats) -> None:
        """Record a single ingestion run's statistics.
        
        Args:
            stats: Statistics from the ingestion run
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO ingestion_stats (
                        timestamp, source_path, status,
                        doc_count, chunk_count, image_count, vector_count,
                        avg_chunk_size, min_chunk_size, max_chunk_size, empty_chunk_count,
                        duration_ms, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stats.timestamp,
                    stats.source_path,
                    stats.status,
                    stats.doc_count,
                    stats.chunk_count,
                    stats.image_count,
                    stats.vector_count,
                    stats.avg_chunk_size,
                    stats.min_chunk_size,
                    stats.max_chunk_size,
                    stats.empty_chunk_count,
                    stats.duration_ms,
                    stats.error_message,
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record ingestion stats: {e}")
    
    def get_aggregated(self, days: int = 30) -> AggregatedStats:
        """Get aggregated statistics for the specified time period.
        
        Args:
            days: Number of days to aggregate (default 30)
            
        Returns:
            Aggregated statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get totals
                row = conn.execute("""
                    SELECT 
                        SUM(doc_count) as total_docs,
                        SUM(chunk_count) as total_chunks,
                        SUM(image_count) as total_images,
                        SUM(vector_count) as total_vectors,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                        SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped_count,
                        AVG(avg_chunk_size) as avg_chunk_size,
                        AVG(duration_ms) as avg_duration_ms,
                        MAX(timestamp) as last_ingestion
                    FROM ingestion_stats
                    WHERE timestamp >= datetime('now', ?)
                """, (f"-{days} days",)).fetchone()
                
                # Get recent errors
                errors = conn.execute("""
                    SELECT error_message 
                    FROM ingestion_stats 
                    WHERE status = 'failed' AND error_message IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 5
                """).fetchall()
                
                return AggregatedStats(
                    total_docs=row["total_docs"] or 0,
                    total_chunks=row["total_chunks"] or 0,
                    total_images=row["total_images"] or 0,
                    total_vectors=row["total_vectors"] or 0,
                    success_count=row["success_count"] or 0,
                    failed_count=row["failed_count"] or 0,
                    skipped_count=row["skipped_count"] or 0,
                    avg_chunk_size=round(row["avg_chunk_size"] or 0, 2),
                    avg_duration_ms=round(row["avg_duration_ms"] or 0, 2),
                    last_ingestion=row["last_ingestion"],
                    recent_errors=[e["error_message"] for e in errors],
                )
        except Exception as e:
            logger.warning(f"Failed to get aggregated stats: {e}")
            return AggregatedStats()
    
    def to_dict(self, days: int = 30) -> dict:
        """Get aggregated statistics as a dictionary.
        
        Args:
            days: Number of days to aggregate
            
        Returns:
            Dictionary of aggregated statistics
        """
        return asdict(self.get_aggregated(days))


# Global singleton
_stats_tracker: Optional[IngestionStatsTracker] = None


def get_stats_tracker() -> IngestionStatsTracker:
    """Get the global stats tracker instance."""
    global _stats_tracker
    if _stats_tracker is None:
        _stats_tracker = IngestionStatsTracker()
    return _stats_tracker
