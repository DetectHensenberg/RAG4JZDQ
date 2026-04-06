"""Database engine and session management for SQLModel ORM.

Provides a centralized SQLite engine factory with async session support.
Uses SQLModel's create_engine for full Pydantic/SQLAlchemy interop.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import Session, SQLModel, create_engine

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default database path
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = resolve_path("data/rag_platform.db")

# ---------------------------------------------------------------------------
# Sync engine (for startup migrations / simple operations)
# ---------------------------------------------------------------------------
_sync_engine = None


def get_sync_engine(db_path: Path | str | None = None):
    """Return a cached synchronous SQLModel engine.

    Args:
        db_path: Optional override for the database file path.

    Returns:
        A SQLAlchemy engine instance.
    """
    global _sync_engine
    if _sync_engine is not None and db_path is None:
        return _sync_engine

    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    if db_path is None:
        _sync_engine = engine
    return engine


# ---------------------------------------------------------------------------
# Async engine (for FastAPI request lifecycle)
# ---------------------------------------------------------------------------
_async_engine = None


def get_async_engine(db_path: Path | str | None = None):
    """Return a cached asynchronous engine (aiosqlite-backed).

    Args:
        db_path: Optional override for the database file path.

    Returns:
        An async SQLAlchemy engine instance.
    """
    global _async_engine
    if _async_engine is not None and db_path is None:
        return _async_engine

    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    if db_path is None:
        _async_engine = engine
    return engine


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------
@contextmanager
def get_session(db_path: Path | str | None = None) -> Generator[Session, None, None]:
    """Context manager yielding a synchronous SQLModel session.

    Args:
        db_path: Optional override for the database file path.

    Yields:
        A SQLModel Session with automatic commit/rollback.
    """
    engine = get_sync_engine(db_path)
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@asynccontextmanager
async def get_async_session(
    db_path: Path | str | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding an async SQLAlchemy session.

    Args:
        db_path: Optional override for the database file path.

    Yields:
        An AsyncSession with automatic commit/rollback.
    """
    engine = get_async_engine(db_path)
    async with AsyncSession(engine) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
def init_db(db_path: Path | str | None = None) -> None:
    """Create all SQLModel tables if they don't exist.

    Args:
        db_path: Optional override for the database file path.
    """
    engine = get_sync_engine(db_path)
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables initialized")
