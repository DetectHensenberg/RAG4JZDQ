"""Base Queue protocol for ingestion task dispatch.

Defines the common interface for all queue backends (Memory, Redis).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class BaseQueue(Protocol):
    """Protocol defining the interface for ingestion task queues.

    All queue backends must implement these methods to ensure
    compatibility with the IngestionWorker.

    Task lifecycle: enqueue → dequeue → (process) → ack/nack
    """

    async def enqueue(self, task_data: Dict[str, Any]) -> str:
        """Add a task to the queue.

        Args:
            task_data: Dict with at least 'file_path' and 'collection'.

        Returns:
            A unique task_id string.
        """
        ...

    async def dequeue(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Fetch the next pending task from the queue.

        Args:
            timeout: Max seconds to wait for a task.

        Returns:
            Task dict with 'task_id' added, or None if no tasks available.
        """
        ...

    async def get_status(self, task_id: str) -> Optional[str]:
        """Get the current status of a task.

        Args:
            task_id: The task identifier.

        Returns:
            Status string: 'pending', 'processing', 'done', 'failed',
            or None if not found.
        """
        ...

    async def ack(self, task_id: str, success: bool = True, error: str = "") -> None:
        """Acknowledge task completion or failure.

        Args:
            task_id: The task identifier.
            success: True if task succeeded, False if failed.
            error: Error message if failed.
        """
        ...

    async def get_pending_count(self) -> int:
        """Return the number of pending tasks.

        Returns:
            Count of pending tasks.
        """
        ...
