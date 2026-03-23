"""Solution Session SQLite persistence.

方案助手会话持久化，存储需求解析结果、大纲和生成内容。
复用 src/bid/document_db.py 的 Session+SQLite 模式。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)

_DB_PATH = resolve_path("data/db/solution.db")

# ── Schema ───────────────────────────────────────────────────────

_CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS solution_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name        TEXT DEFAULT '',
    project_type        TEXT DEFAULT '',
    source_file_path    TEXT DEFAULT '',
    source_text         TEXT DEFAULT '',
    template_file_path  TEXT DEFAULT '',
    template_outline_json TEXT DEFAULT '[]',
    requirements_json   TEXT DEFAULT '[]',
    outline_json        TEXT DEFAULT '[]',
    content_json        TEXT DEFAULT '{}',
    collection          TEXT DEFAULT 'default',
    status              TEXT DEFAULT 'draft',
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL
);
"""

_CREATE_IDX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_solution_status ON solution_sessions(status);
"""


# ── Dataclass ────────────────────────────────────────────────────


@dataclass
class SolutionSession:
    """方案生成会话.

    Attributes:
        id: 主键
        project_name: 项目名称
        project_type: 项目类型（系统集成/软件开发/网络安全等）
        source_file_path: 上传的需求文件路径
        source_text: 粘贴的需求文本（无文件时使用）
        template_file_path: 可选的方案模板 Word 路径
        template_outline: 从模板中提取的大纲结构
        requirements: 结构化需求清单
        outline: 方案大纲
        content: 各章节生成内容 {section_id: markdown}
        collection: 检索使用的知识库集合名
        status: 会话状态 draft/outlining/generating/completed
    """

    id: int = 0
    project_name: str = ""
    project_type: str = ""
    source_file_path: str = ""
    source_text: str = ""
    template_file_path: str = ""
    template_outline: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    outline: List[Dict[str, Any]] = field(default_factory=list)
    content: Dict[str, str] = field(default_factory=dict)
    collection: str = "default"
    status: str = "draft"
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典，供 API 返回."""
        return {
            "id": self.id,
            "project_name": self.project_name,
            "project_type": self.project_type,
            "source_file_path": self.source_file_path,
            "source_text": self.source_text[:200] if self.source_text else "",
            "template_file_path": self.template_file_path,
            "template_outline": self.template_outline,
            "requirements": self.requirements,
            "outline": self.outline,
            "content": self.content,
            "collection": self.collection,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── SQLite helpers ───────────────────────────────────────────────


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    """获取数据库连接上下文管理器."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _ensure_tables() -> None:
    """确保数据库表已创建."""
    with _get_conn() as conn:
        conn.execute(_CREATE_SESSIONS_TABLE)
        conn.execute(_CREATE_IDX_STATUS)
        conn.commit()


def _row_to_session(row: sqlite3.Row) -> SolutionSession:
    """将数据库行转换为 SolutionSession 对象."""
    return SolutionSession(
        id=row["id"],
        project_name=row["project_name"],
        project_type=row["project_type"],
        source_file_path=row["source_file_path"],
        source_text=row["source_text"],
        template_file_path=row["template_file_path"],
        template_outline=json.loads(row["template_outline_json"])
        if row["template_outline_json"]
        else [],
        requirements=json.loads(row["requirements_json"])
        if row["requirements_json"]
        else [],
        outline=json.loads(row["outline_json"]) if row["outline_json"] else [],
        content=json.loads(row["content_json"]) if row["content_json"] else {},
        collection=row["collection"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── CRUD ─────────────────────────────────────────────────────────


def create_session(session: SolutionSession) -> int:
    """创建新会话，返回自增 ID.

    Args:
        session: 会话对象（id 字段会被忽略）

    Returns:
        新创建的会话 ID
    """
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO solution_sessions
               (project_name, project_type, source_file_path, source_text,
                template_file_path, template_outline_json,
                requirements_json, outline_json, content_json,
                collection, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session.project_name,
                session.project_type,
                session.source_file_path,
                session.source_text,
                session.template_file_path,
                json.dumps(session.template_outline, ensure_ascii=False),
                json.dumps(session.requirements, ensure_ascii=False),
                json.dumps(session.outline, ensure_ascii=False),
                json.dumps(session.content, ensure_ascii=False),
                session.collection,
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


def update_session(session: SolutionSession) -> bool:
    """更新已有会话，返回是否成功.

    Args:
        session: 包含更新数据的会话对象（id 必须有效）

    Returns:
        True 如果更新成功
    """
    _ensure_tables()
    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE solution_sessions
               SET project_name=?, project_type=?, source_file_path=?,
                   source_text=?, template_file_path=?, template_outline_json=?,
                   requirements_json=?, outline_json=?, content_json=?,
                   collection=?, status=?, updated_at=?
               WHERE id=?""",
            (
                session.project_name,
                session.project_type,
                session.source_file_path,
                session.source_text,
                session.template_file_path,
                json.dumps(session.template_outline, ensure_ascii=False),
                json.dumps(session.requirements, ensure_ascii=False),
                json.dumps(session.outline, ensure_ascii=False),
                json.dumps(session.content, ensure_ascii=False),
                session.collection,
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


def get_session(session_id: int) -> Optional[SolutionSession]:
    """按 ID 获取单个会话.

    Args:
        session_id: 会话 ID

    Returns:
        SolutionSession 对象，不存在时返回 None
    """
    _ensure_tables()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM solution_sessions WHERE id=?", (session_id,)
        ).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def delete_session(session_id: int) -> bool:
    """删除会话，返回是否成功.

    Args:
        session_id: 要删除的会话 ID

    Returns:
        True 如果删除成功
    """
    _ensure_tables()
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM solution_sessions WHERE id=?", (session_id,)
        )
        conn.commit()
        return cur.rowcount > 0


def list_sessions(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """列出会话，支持按状态过滤和分页.

    Args:
        status: 可选状态过滤
        page: 页码（从 1 开始）
        page_size: 每页记录数

    Returns:
        包含 records, total, page, page_size 的字典
    """
    _ensure_tables()

    clauses: List[str] = []
    args: List[Any] = []

    if status:
        clauses.append("status = ?")
        args.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _get_conn() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM solution_sessions {where}", args
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        offset = (max(1, page) - 1) * page_size
        sql = f"""SELECT * FROM solution_sessions {where}
                  ORDER BY updated_at DESC LIMIT ? OFFSET ?"""
        rows = conn.execute(sql, args + [page_size, offset]).fetchall()

    return {
        "records": [_row_to_session(r).to_dict() for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
