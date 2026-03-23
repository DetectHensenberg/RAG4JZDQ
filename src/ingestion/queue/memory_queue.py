"""In-memory async queue for ingestion tasks.

Lightweight fallback when Redis is not available. Uses asyncio.Queue
for O(1) enqueue/dequeue and a simple dict for status tracking.

Not persistent — all tasks are lost on process restart.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MemoryQueue:
    """In-memory queue implementation using asyncio.Queue.

    Suitable for single-process development and testing.
    For production use with persistence, use RedisQueue.

    Example:
        >>> q = MemoryQueue()
        >>> task_id = await q.enqueue({"file_path": "docs/a.pdf", "collection": "default"})
        >>> task = await q.dequeue(timeout=1.0)
        >>> await q.ack(task["task_id"], success=True)
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Initialize MemoryQueue.

        Args:
            maxsize: Maximum queue size (0 = unlimited).
        """
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._status: Dict[str, str] = {}
        self._errors: Dict[str, str] = {}

    async def enqueue(self, task_data: Dict[str, Any]) -> str:
        """Add a task to the queue.

        Args:
            task_data: Dict with at least 'file_path' and 'collection'.

        Returns:
            A unique task_id string.
        """
        task_id = str(uuid.uuid4())
        task = {**task_data, "task_id": task_id}
        await self._queue.put(task)
        self._status[task_id] = "pending"
        logger.info(f"MemoryQueue: Enqueued task {task_id}")
        return task_id

    async def dequeue(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Fetch the next pending task from the queue.

        Args:
            timeout: Max seconds to wait for a task.

        Returns:
            Task dict with 'task_id', or None if no tasks available.
        """
        try:
            task = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            task_id = task["task_id"]
            self._status[task_id] = "processing"
            return task
        except asyncio.TimeoutError:
            return None

    async def get_status(self, task_id: str) -> Optional[str]:
        """Get the current status of a task.

        Args:
            task_id: The task identifier.

        Returns:
            Status string or None if not found.
        """
        return self._status.get(task_id)

    async def ack(self, task_id: str, success: bool = True, error: str = "") -> None:
        """Acknowledge task completion or failure.

        Args:
            task_id: The task identifier.
            success: True if task succeeded, False if failed.
            error: Error message if failed.
        """
        if success:
            self._status[task_id] = "done"
        else:
            self._status[task_id] = "failed"
            self._errors[task_id] = error
        logger.info(
            f"MemoryQueue: Task {task_id} → {'done' if success else 'failed'}"
        )

    async def get_pending_count(self) -> int:
        """Return the number of pending tasks.

        Returns:
            Count of pending tasks in queue.
        """
        return self._queue.qsize()
