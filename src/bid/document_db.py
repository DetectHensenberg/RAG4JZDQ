"""Bid Document (商务文件) SQLite storage with ChromaDB dual-write.

Stores bid materials (资质证书、财务报表、声明函、证照等) and document templates
in SQLite for CRUD, and syncs text content to ChromaDB `bid_materials` collection
for semantic search.
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

_DB_PATH = resolve_path("data/bid_document.db")
_MATERIALS_DIR = resolve_path("data/bid_materials")
_CHROMA_COLLECTION = "bid_materials"

# ── Schema ───────────────────────────────────────────────────────

_CREATE_MATERIALS_TABLE = """
CREATE TABLE IF NOT EXISTS bid_materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL DEFAULT '',
    category         TEXT NOT NULL DEFAULT 'other',
    file_path        TEXT DEFAULT '',
    content          TEXT DEFAULT '',
    valid_from       TEXT DEFAULT '',
    valid_to         TEXT DEFAULT '',
    metadata_json    TEXT DEFAULT '{}',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
"""

_CREATE_TEMPLATES_TABLE = """
CREATE TABLE IF NOT EXISTS bid_templates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL DEFAULT '',
    template_type    TEXT NOT NULL DEFAULT 'other',
    content          TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
"""

_CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS document_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name     TEXT DEFAULT '',
    project_code     TEXT DEFAULT '',
    tender_file_path TEXT DEFAULT '',
    clauses_json     TEXT DEFAULT '[]',
    outline_json     TEXT DEFAULT '[]',
    content_json     TEXT DEFAULT '{}',
    status           TEXT DEFAULT 'draft',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
"""

_CREATE_COMPANY_DOCS_TABLE = """
CREATE TABLE IF NOT EXISTS company_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_key       TEXT NOT NULL UNIQUE,
    doc_name      TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT 'other',
    content       TEXT DEFAULT '',
    page_start    INTEGER DEFAULT 0,
    page_end      INTEGER DEFAULT 0,
    source_file   TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
"""

_CREATE_IDX_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_materials_category ON bid_materials(category);
"""

_CREATE_IDX_TEMPLATE_TYPE = """
CREATE INDEX IF NOT EXISTS idx_templates_type ON bid_templates(template_type);
"""

_CREATE_IDX_COMPANY_DOC_KEY = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_doc_key ON company_documents(doc_key);
"""


# ── Dataclasses ─────────────────────────────────────────────────


@dataclass
class BidMaterial:
    """A single bid material record (资质证书、证照等)."""

    id: int = 0
    name: str = ""
    category: str = "other"  # certificate/financial/declaration/license/template/other
    file_path: str = ""
    content: str = ""
    valid_from: str = ""
    valid_to: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "file_path": self.file_path,
            "content": self.content,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BidTemplate:
    """A document template (承诺书、声明函模板等)."""

    id: int = 0
    name: str = ""
    template_type: str = "other"  # commitment/declaration/introduction/outline/other
    content: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "template_type": self.template_type,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class CompanyDocument:
    """A company qualification document (我司资格性响应文件)."""

    id: int = 0
    doc_key: str = ""
    doc_name: str = ""
    category: str = "other"  # certificate/financial/declaration/license/other
    content: str = ""
    page_start: int = 0
    page_end: int = 0
    source_file: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_key": self.doc_key,
            "doc_name": self.doc_name,
            "category": self.category,
            "content": self.content,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "source_file": self.source_file,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DocumentSession:
    """A document writing session (商务文件编写会话)."""

    id: int = 0
    project_name: str = ""
    project_code: str = ""
    tender_file_path: str = ""
    clauses: List[Dict[str, Any]] = field(default_factory=list)
    outline: List[Dict[str, Any]] = field(default_factory=list)
    content: Dict[str, str] = field(default_factory=dict)
    status: str = "draft"  # draft/completed
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_name": self.project_name,
            "project_code": self.project_code,
            "tender_file_path": self.tender_file_path,
            "clauses": self.clauses,
            "outline": self.outline,
            "content": self.content,
            "status": self.status,
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


def _ensure_tables() -> None:
    with _get_conn() as conn:
        conn.execute(_CREATE_MATERIALS_TABLE)
        conn.execute(_CREATE_TEMPLATES_TABLE)
        conn.execute(_CREATE_SESSIONS_TABLE)
        conn.execute(_CREATE_COMPANY_DOCS_TABLE)
        conn.execute(_CREATE_IDX_CATEGORY)
        conn.execute(_CREATE_IDX_TEMPLATE_TYPE)
        conn.execute(_CREATE_IDX_COMPANY_DOC_KEY)
        conn.commit()


def _row_to_material(row: sqlite3.Row) -> BidMaterial:
    return BidMaterial(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        file_path=row["file_path"],
        content=row["content"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_template(row: sqlite3.Row) -> BidTemplate:
    return BidTemplate(
        id=row["id"],
        name=row["name"],
        template_type=row["template_type"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_session(row: sqlite3.Row) -> DocumentSession:
    return DocumentSession(
        id=row["id"],
        project_name=row["project_name"],
        project_code=row["project_code"],
        tender_file_path=row["tender_file_path"],
        clauses=json.loads(row["clauses_json"]) if row["clauses_json"] else [],
        outline=json.loads(row["outline_json"]) if row["outline_json"] else [],
        content=json.loads(row["content_json"]) if row["content_json"] else {},
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── ChromaDB dual-write helpers ──────────────────────────────────


def _get_chroma_collection() -> Any:
    """Get or create the ChromaDB bid_materials collection."""
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


def _sync_material_to_chroma(material: BidMaterial) -> None:
    """Upsert a material's text content into ChromaDB for semantic search."""
    col = _get_chroma_collection()
    if col is None:
        return
    try:
        text = f"{material.name} {material.content}"
        if not text.strip():
            return
        metadata: Dict[str, Any] = {
            "record_id": material.id,
            "category": material.category,
            "valid_from": material.valid_from,
            "valid_to": material.valid_to,
        }
        doc_id = f"material_{material.id}"
        col.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
    except Exception as e:
        logger.warning(f"ChromaDB upsert failed for material {material.id}: {e}")


def _delete_material_from_chroma(material_id: int) -> None:
    """Remove a material from ChromaDB."""
    col = _get_chroma_collection()
    if col is None:
        return
    try:
        col.delete(ids=[f"material_{material_id}"])
    except Exception as e:
        logger.warning(f"ChromaDB delete failed for material {material_id}: {e}")


# ── Material CRUD ────────────────────────────────────────────────


def create_material(material: BidMaterial) -> int:
    """Insert a new material record. Returns the row id."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bid_materials
               (name, category, file_path, content, valid_from, valid_to,
                metadata_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                material.name,
                material.category,
                material.file_path,
                material.content,
                material.valid_from,
                material.valid_to,
                json.dumps(material.metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid or 0

    material.id = new_id
    material.created_at = now
    material.updated_at = now
    _sync_material_to_chroma(material)
    return new_id


def update_material(material: BidMaterial) -> bool:
    """Update an existing material record. Returns True if updated."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE bid_materials
               SET name=?, category=?, file_path=?, content=?,
                   valid_from=?, valid_to=?, metadata_json=?, updated_at=?
               WHERE id=?""",
            (
                material.name,
                material.category,
                material.file_path,
                material.content,
                material.valid_from,
                material.valid_to,
                json.dumps(material.metadata, ensure_ascii=False),
                now,
                material.id,
            ),
        )
        conn.commit()
        updated = cur.rowcount > 0

    if updated:
        material.updated_at = now
        _sync_material_to_chroma(material)
    return updated


def delete_material(material_id: int) -> bool:
    """Delete a material by id. Returns True if deleted."""
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM bid_materials WHERE id=?", (material_id,))
        conn.commit()
        deleted = cur.rowcount > 0

    if deleted:
        _delete_material_from_chroma(material_id)
    return deleted


def get_material(material_id: int) -> Optional[BidMaterial]:
    """Fetch a single material by id."""
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM bid_materials WHERE id=?", (material_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_material(row)


def list_materials(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """List materials with optional filtering and pagination."""
    _ensure_tables()

    clauses: List[str] = []
    args: List[Any] = []

    if category:
        clauses.append("category = ?")
        args.append(category)
    if keyword:
        clauses.append("(name LIKE ? OR content LIKE ?)")
        kw = f"%{keyword}%"
        args.extend([kw, kw])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _get_conn() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM bid_materials {where}", args
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        offset = (max(1, page) - 1) * page_size
        sql = f"""SELECT * FROM bid_materials {where}
                  ORDER BY updated_at DESC LIMIT ? OFFSET ?"""
        rows = conn.execute(sql, args + [page_size, offset]).fetchall()

    return {
        "records": [_row_to_material(r).to_dict() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def search_materials(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Search materials via ChromaDB semantic similarity."""
    col = _get_chroma_collection()
    if col is None:
        logger.warning("ChromaDB unavailable for material search")
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
                    "material_id": meta.get("record_id", 0),
                    "score": round(score, 4),
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "category": meta.get("category", ""),
                })
        return hits
    except Exception as e:
        logger.exception(f"ChromaDB material search failed: {e}")
        return []


# ── Template CRUD ────────────────────────────────────────────────


def create_template(template: BidTemplate) -> int:
    """Insert a new template record. Returns the row id."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bid_templates
               (name, template_type, content, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            (template.name, template.template_type, template.content, now, now),
        )
        conn.commit()
        new_id = cur.lastrowid or 0

    template.id = new_id
    template.created_at = now
    template.updated_at = now
    return new_id


def update_template(template: BidTemplate) -> bool:
    """Update an existing template record. Returns True if updated."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE bid_templates
               SET name=?, template_type=?, content=?, updated_at=?
               WHERE id=?""",
            (template.name, template.template_type, template.content, now, template.id),
        )
        conn.commit()
        updated = cur.rowcount > 0

    if updated:
        template.updated_at = now
    return updated


def delete_template(template_id: int) -> bool:
    """Delete a template by id. Returns True if deleted."""
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM bid_templates WHERE id=?", (template_id,))
        conn.commit()
        return cur.rowcount > 0


def get_template(template_id: int) -> Optional[BidTemplate]:
    """Fetch a single template by id."""
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM bid_templates WHERE id=?", (template_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_template(row)


def list_templates(
    template_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """List templates with optional filtering and pagination."""
    _ensure_tables()

    clauses: List[str] = []
    args: List[Any] = []

    if template_type:
        clauses.append("template_type = ?")
        args.append(template_type)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _get_conn() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM bid_templates {where}", args
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        offset = (max(1, page) - 1) * page_size
        sql = f"""SELECT * FROM bid_templates {where}
                  ORDER BY updated_at DESC LIMIT ? OFFSET ?"""
        rows = conn.execute(sql, args + [page_size, offset]).fetchall()

    return {
        "records": [_row_to_template(r).to_dict() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Session CRUD ─────────────────────────────────────────────────


def create_session(session: DocumentSession) -> int:
    """Insert a new session record. Returns the row id."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO document_sessions
               (project_name, project_code, tender_file_path,
                clauses_json, outline_json, content_json, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session.project_name,
                session.project_code,
                session.tender_file_path,
                json.dumps(session.clauses, ensure_ascii=False),
                json.dumps(session.outline, ensure_ascii=False),
                json.dumps(session.content, ensure_ascii=False),
                session.status,
                now,
                now,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid or 0

    session.id = new_id
    session.created_at = now
    session.updated_at = now
    return new_id


def update_session(session: DocumentSession) -> bool:
    """Update an existing session record. Returns True if updated."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE document_sessions
               SET project_name=?, project_code=?, tender_file_path=?,
                   clauses_json=?, outline_json=?, content_json=?,
                   status=?, updated_at=?
               WHERE id=?""",
            (
                session.project_name,
                session.project_code,
                session.tender_file_path,
                json.dumps(session.clauses, ensure_ascii=False),
                json.dumps(session.outline, ensure_ascii=False),
                json.dumps(session.content, ensure_ascii=False),
                session.status,
                now,
                session.id,
            ),
        )
        conn.commit()
        updated = cur.rowcount > 0

    if updated:
        session.updated_at = now
    return updated


def delete_session(session_id: int) -> bool:
    """Delete a session by id. Returns True if deleted."""
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM document_sessions WHERE id=?", (session_id,))
        conn.commit()
        return cur.rowcount > 0


def get_session(session_id: int) -> Optional[DocumentSession]:
    """Fetch a single session by id."""
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM document_sessions WHERE id=?", (session_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def list_sessions(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """List sessions with optional filtering and pagination."""
    _ensure_tables()

    clauses: List[str] = []
    args: List[Any] = []

    if status:
        clauses.append("status = ?")
        args.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _get_conn() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM document_sessions {where}", args
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        offset = (max(1, page) - 1) * page_size
        sql = f"""SELECT * FROM document_sessions {where}
                  ORDER BY updated_at DESC LIMIT ? OFFSET ?"""
        rows = conn.execute(sql, args + [page_size, offset]).fetchall()

    return {
        "records": [_row_to_session(r).to_dict() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_materials_dir() -> Path:
    """Get the materials storage directory, creating if needed."""
    _MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    return _MATERIALS_DIR


# ── CompanyDocument helpers ─────────────────────────────────────


def _row_to_company_doc(row: sqlite3.Row) -> CompanyDocument:
    return CompanyDocument(
        id=row["id"],
        doc_key=row["doc_key"],
        doc_name=row["doc_name"],
        category=row["category"],
        content=row["content"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        source_file=row["source_file"],
        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── CompanyDocument CRUD ────────────────────────────────────────


def upsert_company_doc(doc: CompanyDocument) -> int:
    """Insert or update a company document by doc_key. Returns the row id."""
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM company_documents WHERE doc_key=?", (doc.doc_key,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE company_documents
                   SET doc_name=?, category=?, content=?, page_start=?, page_end=?,
                       source_file=?, metadata_json=?, updated_at=?
                   WHERE doc_key=?""",
                (
                    doc.doc_name, doc.category, doc.content,
                    doc.page_start, doc.page_end, doc.source_file,
                    json.dumps(doc.metadata, ensure_ascii=False),
                    now, doc.doc_key,
                ),
            )
            conn.commit()
            doc.id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO company_documents
                   (doc_key, doc_name, category, content, page_start, page_end,
                    source_file, metadata_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc.doc_key, doc.doc_name, doc.category, doc.content,
                    doc.page_start, doc.page_end, doc.source_file,
                    json.dumps(doc.metadata, ensure_ascii=False),
                    now, now,
                ),
            )
            conn.commit()
            doc.id = cur.lastrowid or 0
            doc.created_at = now
    doc.updated_at = now
    return doc.id


def delete_company_doc(doc_id: int) -> bool:
    """Delete a company document by id."""
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM company_documents WHERE id=?", (doc_id,))
        conn.commit()
        return cur.rowcount > 0


def get_company_doc(doc_id: int) -> Optional[CompanyDocument]:
    """Fetch a single company document by id."""
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM company_documents WHERE id=?", (doc_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_company_doc(row)


def get_company_doc_by_key(doc_key: str) -> Optional[CompanyDocument]:
    """Fetch a company document by its unique key."""
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM company_documents WHERE doc_key=?", (doc_key,)
        ).fetchone()
    if not row:
        return None
    return _row_to_company_doc(row)


def list_company_docs(category: Optional[str] = None) -> List[CompanyDocument]:
    """List all company documents, optionally filtered by category."""
    _ensure_tables()
    if category:
        sql = "SELECT * FROM company_documents WHERE category=? ORDER BY page_start"
        args: list[Any] = [category]
    else:
        sql = "SELECT * FROM company_documents ORDER BY page_start"
        args = []
    with _get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_company_doc(r) for r in rows]


def clear_company_docs() -> int:
    """Delete all company documents. Returns count deleted."""
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM company_documents")
        conn.commit()
        return cur.rowcount
