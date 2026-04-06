"""SQLModel ORM table definitions for the RAG platform.

Provides typed, validated data models that replace raw SQL string operations.
All models inherit from SQLModel for Pydantic + SQLAlchemy dual compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class QAHistory(SQLModel, table=True):
    """问答历史记录表。"""

    __tablename__ = "qa_history"

    id: int = Field(primary_key=True)
    question: str
    answer: str
    references_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=datetime.now)


class IngestRecord(SQLModel, table=True):
    """文件摄取记录表 — 追踪已处理过的文件及其哈希。"""

    __tablename__ = "ingest_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_path: str = Field(index=True)
    source_hash: str = ""
    collection: str = Field(default="default", index=True)
    chunk_count: int = 0
    status: str = "completed"
    created_at: datetime = Field(default_factory=datetime.now)


class EvalResult(SQLModel, table=True):
    """评估结果记录表。"""

    __tablename__ = "eval_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    collection: str = "default"
    metric_name: str = ""
    metric_value: float = 0.0
    queries_json: str = "[]"
    created_at: datetime = Field(default_factory=datetime.now)
