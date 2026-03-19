"""Achievement (业绩) SQLite storage with ChromaDB dual-write.

Stores structured achievement records (project name, amount, dates, contacts)
in SQLite for filtering/sorting/CRUD, and syncs text summaries to a ChromaDB
`achievements` collection for semantic search.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)

_DB_PATH = resolve_path("data/bid_achievements.db")

# ── Schema ───────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS achievements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name     TEXT NOT NULL DEFAULT '',
    project_content  TEXT NOT NULL DEFAULT '',
    amount           REAL,
    sign_date        TEXT NOT NULL DEFAULT '',
    acceptance_date  TEXT NOT NULL DEFAULT '',
    client_contact   TEXT NOT NULL DEFAULT '',
    client_phone     TEXT NOT NULL DEFAULT '',
    tags_json        TEXT NOT NULL DEFAULT '[]',
    attachments_json TEXT NOT NULL DEFAULT '[]',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
"""

_CREATE_IDX_NAME = """
CREATE INDEX IF NOT EXISTS idx_achievements_name
    ON achievements(project_name);
"""

_CREATE_IDX_DATE = """
CREATE INDEX IF NOT EXISTS idx_achievements_sign_date
    ON achievements(sign_date);
"""


# ── Dataclass ────────────────────────────────────────────────────


@dataclass
class AchievementRecord:
    """A single achievement record."""

    id: int = 0
    project_name: str = ""
    project_content: str = ""
    amount: Optional[float] = None
    sign_date: str = ""
    acceptance_date: str = ""
    client_contact: str = ""
    client_phone: str = ""
    tags: List[str] = field(default_factory=list)
    attachments: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for API responses."""
        return {
            "id": self.id,
            "project_name": self.project_name,
            "project_content": self.project_content,
            "amount": self.amount,
            "sign_date": self.sign_date,
            "acceptance_date": self.acceptance_date,
            "client_contact": self.client_contact,
            "client_phone": self.client_phone,
            "tags": self.tags,
            "attachments": self.attachments,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── SQLite helpers ───────────────────────────────────────────────


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _ensure_table() -> None:
    with _get_conn() as conn:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_IDX_NAME)
        conn.execute(_CREATE_IDX_DATE)
        conn.commit()


def _row_to_record(row: sqlite3.Row) -> AchievementRecord:
    return AchievementRecord(
        id=row["id"],
        project_name=row["project_name"],
        project_content=row["project_content"],
        amount=row["amount"],
        sign_date=row["sign_date"],
        acceptance_date=row["acceptance_date"],
        client_contact=row["client_contact"],
        client_phone=row["client_phone"],
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        attachments=json.loads(row["attachments_json"]) if row["attachments_json"] else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── ChromaDB dual-write helpers ──────────────────────────────────

_CHROMA_COLLECTION = "achievements"


def _get_chroma_collection() -> Any:
    """Get or create the ChromaDB achievements collection.

    Uses a relative path to avoid the non-ASCII path bug in ChromaDB Rust backend.
    """
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path="./data/db/chroma",
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        return client.get_or_create_collection(
            name=_CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as e:
        logger.warning(f"ChromaDB sync unavailable: {e}")
        return None


def _sync_to_chroma(record: AchievementRecord) -> None:
    """Upsert a record's text summary into ChromaDB for semantic search."""
    col = _get_chroma_collection()
    if col is None:
        return
    try:
        text = f"{record.project_name} {record.project_content}"
        metadata: Dict[str, Any] = {
            "record_id": record.id,
            "amount": record.amount or 0,
            "sign_date": record.sign_date,
            "acceptance_date": record.acceptance_date,
            "client_contact": record.client_contact,
            "tags": json.dumps(record.tags, ensure_ascii=False),
        }
        doc_id = f"achievement_{record.id}"
        col.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
    except Exception as e:
        logger.warning(f"ChromaDB upsert failed for achievement {record.id}: {e}")


def _delete_from_chroma(record_id: int) -> None:
    """Remove a record from ChromaDB."""
    col = _get_chroma_collection()
    if col is None:
        return
    try:
        col.delete(ids=[f"achievement_{record_id}"])
    except Exception as e:
        logger.warning(f"ChromaDB delete failed for achievement {record_id}: {e}")


# ── CRUD operations ──────────────────────────────────────────────


def create_achievement(record: AchievementRecord) -> int:
    """Insert a new achievement record. Returns the row id."""
    _ensure_table()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO achievements
               (project_name, project_content, amount, sign_date,
                acceptance_date, client_contact, client_phone,
                tags_json, attachments_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.project_name,
                record.project_content,
                record.amount,
                record.sign_date,
                record.acceptance_date,
                record.client_contact,
                record.client_phone,
                json.dumps(record.tags, ensure_ascii=False),
                json.dumps(record.attachments, ensure_ascii=False),
                now, now,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid or 0

    record.id = new_id
    record.created_at = now
    record.updated_at = now
    _sync_to_chroma(record)
    return new_id


def update_achievement(record: AchievementRecord) -> bool:
    """Update an existing achievement record. Returns True if updated."""
    _ensure_table()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE achievements
               SET project_name=?, project_content=?, amount=?,
                   sign_date=?, acceptance_date=?,
                   client_contact=?, client_phone=?,
                   tags_json=?, attachments_json=?, updated_at=?
               WHERE id=?""",
            (
                record.project_name,
                record.project_content,
                record.amount,
                record.sign_date,
                record.acceptance_date,
                record.client_contact,
                record.client_phone,
                json.dumps(record.tags, ensure_ascii=False),
                json.dumps(record.attachments, ensure_ascii=False),
                now, record.id,
            ),
        )
        conn.commit()
        updated = cur.rowcount > 0

    if updated:
        record.updated_at = now
        _sync_to_chroma(record)
    return updated


def delete_achievement(record_id: int) -> bool:
    """Delete a record by id. Returns True if deleted."""
    _ensure_table()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM achievements WHERE id=?", (record_id,))
        conn.commit()
        deleted = cur.rowcount > 0

    if deleted:
        _delete_from_chroma(record_id)
    return deleted


def get_achievement(record_id: int) -> Optional[AchievementRecord]:
    """Fetch a single record by id."""
    _ensure_table()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM achievements WHERE id=?", (record_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_record(row)


@dataclass
class ListFilter:
    """Filter parameters for list_achievements."""

    keyword: str = ""
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: str = ""
    end_date: str = ""
    tags: List[str] = field(default_factory=list)
    page: int = 1
    page_size: int = 20
    sort_by: str = "updated_at"
    sort_order: str = "desc"


@dataclass
class ListResult:
    """Paginated list result."""

    records: List[AchievementRecord]
    total: int
    page: int
    page_size: int


def list_achievements(f: Optional[ListFilter] = None) -> ListResult:
    """List achievement records with filtering, sorting, and pagination."""
    _ensure_table()
    f = f or ListFilter()

    clauses: List[str] = []
    args: List[Any] = []

    if f.keyword:
        clauses.append("(project_name LIKE ? OR project_content LIKE ?)")
        kw = f"%{f.keyword}%"
        args.extend([kw, kw])
    if f.min_amount is not None:
        clauses.append("amount >= ?")
        args.append(f.min_amount)
    if f.max_amount is not None:
        clauses.append("amount <= ?")
        args.append(f.max_amount)
    if f.start_date:
        clauses.append("sign_date >= ?")
        args.append(f.start_date)
    if f.end_date:
        clauses.append("sign_date <= ?")
        args.append(f.end_date)
    if f.tags:
        for tag in f.tags:
            clauses.append("tags_json LIKE ?")
            args.append(f"%{tag}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    # Whitelist sort columns
    valid_sorts = {"updated_at", "created_at", "amount", "sign_date", "project_name"}
    sort_col = f.sort_by if f.sort_by in valid_sorts else "updated_at"
    sort_dir = "ASC" if f.sort_order.lower() == "asc" else "DESC"

    with _get_conn() as conn:
        # Count
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM achievements {where}", args
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        # Page
        offset = (max(1, f.page) - 1) * f.page_size
        sql = (
            f"SELECT * FROM achievements {where} "
            f"ORDER BY {sort_col} {sort_dir} "
            f"LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, args + [f.page_size, offset]).fetchall()

    return ListResult(
        records=[_row_to_record(r) for r in rows],
        total=total,
        page=f.page,
        page_size=f.page_size,
    )


def semantic_search(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Search achievements via ChromaDB semantic similarity.

    Returns list of dicts with record_id, score, and text.
    """
    col = _get_chroma_collection()
    if col is None:
        logger.warning("ChromaDB unavailable, falling back to keyword search")
        return []

    try:
        results = col.query(query_texts=[query], n_results=top_k)
        hits: List[Dict[str, Any]] = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0
                score = max(0.0, 1.0 - distance)
                hits.append({
                    "record_id": meta.get("record_id", 0),
                    "score": round(score, 4),
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": meta,
                })
        return hits
    except Exception as e:
        logger.exception(f"ChromaDB semantic search failed: {e}")
        return []
