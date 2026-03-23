"""FeedbackStore - SQLite-based storage for user thumbs up/down feedback."""

import sqlite_utils
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.storage.sqlite_manager import SQLiteManager
from src.observability.logger import get_logger

logger = get_logger(__name__)


class FeedbackStore:
    """SQLite-based storage for recording user feedback on RAG responses.
    
    This store tracks thumbs up/down ratings and optional comments,
    linking them to the specific trace_id of the original query.
    """
    
    def __init__(self, db_path: str | Path):
        """Initialize FeedbackStore with a SQLite database.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        # Use SQLiteManager static helper to ensure WAL and busy_timeout
        self.db = SQLiteManager.initialize_db(self.db_path)
        
        self._init_schema()
        logger.info(f"FeedbackStore initialized at {self.db_path}")

    def _init_schema(self) -> None:
        """Initialize database schema if not already exists."""
        if "feedback" not in self.db.table_names():
            self.db["feedback"].create({
                "id": int,              # Primary key (auto-increment)
                "trace_id": str,        # Associated request trace ID
                "rating": int,          # 1 for positive, -1 for negative
                "comment": str,         # Optional user feedback text
                "query": str,           # Original query (denormalized for stats)
                "timestamp": str,       # ISO-8601 UTC timestamp
            }, pk="id")
            # Unique index on trace_id to support upserts per request
            self.db["feedback"].create_index(["trace_id"], unique=True)
            self.db["feedback"].create_index(["rating"])
            logger.info("Feedback table schema initialized")

    def upsert_feedback(
        self,
        trace_id: str,
        rating: int,
        comment: Optional[str] = None,
        query: Optional[str] = None
    ) -> None:
        """Record or update user feedback for a given trace.
        
        Args:
            trace_id: Unique identifier for the query trace.
            rating: Feedback value (1 for positive, -1 for negative).
            comment: Optional text comment from user.
            query: Optional original query string for reporting.
        """
        data = {
            "trace_id": trace_id,
            "rating": rating,
            "comment": comment or "",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if query:
            data["query"] = query

        # Use upsert to handle multiple feedback clicks for the same response
        self.db["feedback"].upsert(data, pk="trace_id", alter=True)
        logger.info(f"Feedback recorded for trace {trace_id}: rating={rating}")

    async def async_upsert_feedback(
        self,
        trace_id: str,
        rating: int,
        comment: Optional[str] = None,
        query: Optional[str] = None
    ) -> None:
        """Asynchronous version of upsert_feedback."""
        import asyncio
        await asyncio.to_thread(
            self.upsert_feedback, trace_id, rating, comment, query
        )

    def get_stats(self) -> Dict[str, Any]:
        """Compute aggregate feedback statistics.
        
        Returns:
            Dictionary containing total, positive, and negative feedback counts.
        """
        try:
            total = self.db["feedback"].count
            positive = len(list(self.db["feedback"].rows_where("rating > 0")))
            negative = len(list(self.db["feedback"].rows_where("rating < 0")))
            
            satisfaction_rate = (positive / total * 100) if total > 0 else 0.0
            
            return {
                "total_feedbacks": total,
                "positive_count": positive,
                "negative_count": negative,
                "satisfaction_rate_percent": round(satisfaction_rate, 2)
            }
        except Exception as e:
            logger.error(f"Failed to compute feedback stats: {e}")
            return {
                "total_feedbacks": 0,
                "positive_count": 0,
                "negative_count": 0,
                "satisfaction_rate_percent": 0.0
            }

    def get_feedback_by_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback details for a specific trace.
        
        Args:
            trace_id: Trace ID to look up.
            
        Returns:
            Dictionary of feedback data or None if not found.
        """
        results = list(self.db["feedback"].rows_where("trace_id = ?", [trace_id]))
        return results[0] if results else None
