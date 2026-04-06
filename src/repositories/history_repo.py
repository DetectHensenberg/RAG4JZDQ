"""History repository — typed data access for QA history records.

Encapsulates all CRUD operations on the qa_history table behind
a clean async interface, replacing scattered raw SQL in routers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from sqlmodel import select

from src.repositories.database import get_async_session, get_session, init_db
from src.repositories.models import QAHistory

logger = logging.getLogger(__name__)


class HistoryRepository:
    """Repository for QAHistory CRUD operations.

    All public methods are async-first for FastAPI compatibility.
    A sync ``save_sync`` escape hatch is provided for non-async contexts.
    """

    async def save(self, question: str, answer: str, refs: list) -> None:
        """Persist a new QA history record.

        Args:
            question: The user's original question.
            answer: The generated answer text.
            refs: List of reference source metadata dicts.
        """
        try:
            async with get_async_session() as session:
                record = QAHistory(
                    id=int(time.time() * 1000),
                    question=question,
                    answer=answer,
                    references_json=json.dumps(refs, ensure_ascii=False),
                )
                session.add(record)
        except Exception as e:
            logger.warning(f"Failed to save QA history: {e}")

    def save_sync(self, question: str, answer: str, refs: list) -> None:
        """Synchronous version for non-async callers.

        Args:
            question: The user's original question.
            answer: The generated answer text.
            refs: List of reference source metadata dicts.
        """
        try:
            with get_session() as session:
                record = QAHistory(
                    id=int(time.time() * 1000),
                    question=question,
                    answer=answer,
                    references_json=json.dumps(refs, ensure_ascii=False),
                )
                session.add(record)
        except Exception as e:
            logger.warning(f"Failed to save QA history (sync): {e}")

    async def list_recent(self, limit: int = 50) -> list[dict]:
        """Return the most recent QA history entries.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of history dicts sorted oldest-first.
        """
        async with get_async_session() as session:
            statement = (
                select(QAHistory).order_by(QAHistory.id.desc()).limit(limit)  # type: ignore[union-attr]
            )
            result = await session.execute(statement)
            rows = result.scalars().all()

        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "references": json.loads(r.references_json) if r.references_json else [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reversed(rows)
        ]

    async def clear_all(self) -> None:
        """Delete all QA history records."""
        async with get_async_session() as session:
            from sqlalchemy import text

            await session.execute(text("DELETE FROM qa_history"))
