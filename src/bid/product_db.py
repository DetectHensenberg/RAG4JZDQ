"""Product parameter SQLite storage for bid assistant.

Stores extracted product parameters as dynamic KV JSON, keyed by
(vendor, model, doc_type). Supports CRUD operations for the bid
assistant's parameter extraction and comparison workflows.
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

_DB_PATH = resolve_path("data/bid_params.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS product_params (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor      TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    product_name TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    doc_type    TEXT NOT NULL DEFAULT 'official',
    doc_source  TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '[]',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_product_params_vendor_model
    ON product_params(vendor, model);
"""


@dataclass
class ProductParamRecord:
    """A single product parameter record."""

    id: int = 0
    vendor: str = ""
    model: str = ""
    product_name: str = ""
    category: str = ""
    doc_type: str = "official"
    doc_source: str = ""
    params: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


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
        conn.execute(_CREATE_INDEX)
        conn.commit()


def save_params(record: ProductParamRecord) -> int:
    """Insert or update a product parameter record. Returns the row id."""
    _ensure_table()
    now = time.time()
    with _get_conn() as conn:
        if record.id:
            conn.execute(
                """UPDATE product_params
                   SET vendor=?, model=?, product_name=?, category=?,
                       doc_type=?, doc_source=?, params_json=?, updated_at=?
                   WHERE id=?""",
                (
                    record.vendor, record.model, record.product_name,
                    record.category, record.doc_type, record.doc_source,
                    json.dumps(record.params, ensure_ascii=False),
                    now, record.id,
                ),
            )
            conn.commit()
            return record.id
        else:
            cur = conn.execute(
                """INSERT INTO product_params
                   (vendor, model, product_name, category, doc_type,
                    doc_source, params_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    record.vendor, record.model, record.product_name,
                    record.category, record.doc_type, record.doc_source,
                    json.dumps(record.params, ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0


def get_params(record_id: int) -> Optional[ProductParamRecord]:
    """Fetch a single record by id."""
    _ensure_table()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM product_params WHERE id=?", (record_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_record(row)


def list_params(
    doc_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
) -> List[ProductParamRecord]:
    """List product parameter records with optional filters."""
    _ensure_table()
    clauses: List[str] = []
    args: List[Any] = []
    if doc_type:
        clauses.append("doc_type=?")
        args.append(doc_type)
    if category:
        clauses.append("category=?")
        args.append(category)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM product_params {where} ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_record(r) for r in rows]


def delete_params(record_id: int) -> bool:
    """Delete a record by id. Returns True if deleted."""
    _ensure_table()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM product_params WHERE id=?", (record_id,))
        conn.commit()
        return cur.rowcount > 0


def _row_to_record(row: sqlite3.Row) -> ProductParamRecord:
    return ProductParamRecord(
        id=row["id"],
        vendor=row["vendor"],
        model=row["model"],
        product_name=row["product_name"],
        category=row["category"],
        doc_type=row["doc_type"],
        doc_source=row["doc_source"],
        params=json.loads(row["params_json"]) if row["params_json"] else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
