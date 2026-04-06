"""资料助手 — 下载任务管理器。

管理下载任务的创建、状态跟踪和持久化 (SQLite)。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.core.settings import resolve_path

logger = logging.getLogger(__name__)

# ── 数据库路径 ────────────────────────────────────────────────────
_DB_PATH = str(resolve_path("data/db/material_tasks.db"))


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    LOGGING_IN = "logging_in"
    SEARCHING = "searching"
    FILTERING = "filtering"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadTask:
    """下载任务数据模型。

    Attributes:
        id: 任务唯一标识 (UUID)
        platform: 平台名称
        keywords: 搜索关键词列表
        dest_dir: 目标下载目录
        max_results: 最大下载数量
        status: 任务状态
        total_found: 搜索到的总数
        filtered_count: LLM 筛选后数量
        downloaded_count: 已下载数量
        failed_count: 下载失败数量
        progress_percent: 任务进度百分比 (0-100)
        progress_message: 当前进度消息
        results: 下载结果 (JSON 序列化)
        error: 错误信息
        created_at: 创建时间 (UNIX 时间戳)
        updated_at: 更新时间 (UNIX 时间戳)
    """

    id: str = ""
    platform: str = ""
    keywords: list[str] = field(default_factory=list)
    dest_dir: str = ""
    max_results: int = 30
    status: TaskStatus = TaskStatus.PENDING
    total_found: int = 0
    filtered_count: int = 0
    downloaded_count: int = 0
    failed_count: int = 0
    progress_percent: float = 0.0
    progress_message: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "id": self.id,
            "platform": self.platform,
            "keywords": self.keywords,
            "dest_dir": self.dest_dir,
            "max_results": self.max_results,
            "status": self.status.value,
            "total_found": self.total_found,
            "filtered_count": self.filtered_count,
            "downloaded_count": self.downloaded_count,
            "failed_count": self.failed_count,
            "progress_percent": self.progress_percent,
            "progress_message": self.progress_message,
            "results": self.results,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskManager:
    """下载任务管理器。

    提供任务 CRUD 操作，使用 SQLite 持久化。
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        """初始化任务管理器。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """创建任务表（如不存在）。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS material_tasks (
                    id          TEXT PRIMARY KEY,
                    platform    TEXT NOT NULL,
                    keywords    TEXT NOT NULL,
                    dest_dir    TEXT NOT NULL,
                    max_results INTEGER DEFAULT 30,
                    status      TEXT DEFAULT 'pending',
                    total_found     INTEGER DEFAULT 0,
                    filtered_count  INTEGER DEFAULT 0,
                    downloaded_count INTEGER DEFAULT 0,
                    failed_count    INTEGER DEFAULT 0,
                    progress_percent REAL DEFAULT 0.0,
                    progress_message TEXT DEFAULT '',
                    results     TEXT DEFAULT '[]',
                    error       TEXT DEFAULT '',
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                )
            """)
            conn.commit()

    def create_task(
        self,
        platform: str,
        keywords: list[str],
        dest_dir: str,
        max_results: int = 30,
    ) -> DownloadTask:
        """创建新的下载任务。

        Args:
            platform: 平台名称。
            keywords: 搜索关键词。
            dest_dir: 目标目录。
            max_results: 最大下载数量。

        Returns:
            新创建的任务对象。
        """
        now = time.time()
        task = DownloadTask(
            id=str(uuid.uuid4())[:8],
            platform=platform,
            keywords=keywords,
            dest_dir=dest_dir,
            max_results=max_results,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO material_tasks
                   (id, platform, keywords, dest_dir, max_results,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    task.platform,
                    json.dumps(task.keywords, ensure_ascii=False),
                    task.dest_dir,
                    task.max_results,
                    task.status.value,
                    task.created_at,
                    task.updated_at,
                ),
            )
            conn.commit()

        logger.info(
            f"Task created: id={task.id}, platform={platform}, "
            f"keywords={keywords}, dest={dest_dir}"
        )
        return task

    def update_task(self, task: DownloadTask) -> None:
        """更新任务状态。

        Args:
            task: 更新后的任务对象。
        """
        task.updated_at = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE material_tasks SET
                   status=?, total_found=?, filtered_count=?,
                   downloaded_count=?, failed_count=?,
                   progress_percent=?, progress_message=?,
                   results=?, error=?, updated_at=?
                   WHERE id=?""",
                (
                    task.status.value,
                    task.total_found,
                    task.filtered_count,
                    task.downloaded_count,
                    task.failed_count,
                    task.progress_percent,
                    task.progress_message,
                    json.dumps(task.results, ensure_ascii=False),
                    task.error,
                    task.updated_at,
                    task.id,
                ),
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        """根据 ID 获取任务。

        Args:
            task_id: 任务 ID。

        Returns:
            任务对象，不存在时返回 None。
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM material_tasks WHERE id=?", (task_id,)
            ).fetchone()

        if not row:
            return None

        return self._row_to_task(row)

    def list_tasks(self, limit: int = 50) -> list[DownloadTask]:
        """列出最近的任务。

        Args:
            limit: 返回数量上限。

        Returns:
            任务列表（按创建时间倒序）。
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM material_tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [self._row_to_task(r) for r in rows]

    def delete_task(self, task_id: str) -> bool:
        """删除任务。

        Args:
            task_id: 任务 ID。

        Returns:
            是否成功删除。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM material_tasks WHERE id=?", (task_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> DownloadTask:
        """将数据库行转换为任务对象。"""
        return DownloadTask(
            id=row["id"],
            platform=row["platform"],
            keywords=json.loads(row["keywords"]),
            dest_dir=row["dest_dir"],
            max_results=row["max_results"],
            status=TaskStatus(row["status"]),
            total_found=row["total_found"],
            filtered_count=row["filtered_count"],
            downloaded_count=row["downloaded_count"],
            failed_count=row["failed_count"],
            progress_percent=row["progress_percent"],
            progress_message=row["progress_message"],
            results=json.loads(row["results"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
