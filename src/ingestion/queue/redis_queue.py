"""Redis Streams-based persistent queue for ingestion tasks.

Uses Redis Streams (XADD/XREADGROUP/XACK) for:
- Durable task persistence across process restarts
- Consumer group support for horizontal scaling
- Built-in message acknowledgment and retry semantics
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RedisQueue:
    """Redis Streams implementation for ingestion task queuing.

    Requires a running Redis 6.2+ instance. Falls back to MemoryQueue
    if Redis is unavailable (handled by the factory layer).

    Example:
        >>> q = RedisQueue(url="redis://localhost:6379/0")
        >>> await q.initialize()
        >>> task_id = await q.enqueue({"file_path": "a.pdf", "collection": "default"})
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        stream_key: str = "rag:ingestion:tasks",
        consumer_group: str = "rag-workers",
        consumer_name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        """Initialize RedisQueue.

        Args:
            url: Redis connection URL.
            stream_key: Redis Stream key name.
            consumer_group: Consumer group name.
            consumer_name: Unique consumer name (auto-generated if None).
            max_retries: Maximum retry attempts for failed tasks.
        """
        self.url = url
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"worker-{uuid.uuid4().hex[:8]}"
        self.max_retries = max_retries
        self._redis: Any = None
        self._status_key = f"{stream_key}:status"

    async def initialize(self) -> None:
        """Connect to Redis and create consumer group.

        Must be called before any other operations.

        Raises:
            ConnectionError: If Redis is not reachable.
        """
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            self.url,
            decode_responses=True,
        )

        # Verify connection
        await self._redis.ping()
        logger.info(f"RedisQueue: Connected to {self.url}")

        # Create consumer group (idempotent)
        try:
            await self._redis.xgroup_create(
                self.stream_key,
                self.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                f"RedisQueue: Created consumer group '{self.consumer_group}'"
            )
        except Exception:
            # Group already exists — safe to ignore
            pass

    async def enqueue(self, task_data: Dict[str, Any]) -> str:
        """Add a task to the Redis Stream.

        Args:
            task_data: Dict with at least 'file_path' and 'collection'.

        Returns:
            A unique task_id string.

        Raises:
            RuntimeError: If Redis is not initialized.
        """
        self._ensure_connected()

        task_id = str(uuid.uuid4())
        entry = {
            "task_id": task_id,
            "data": json.dumps(task_data),
            "created_at": str(time.time()),
            "retry_count": "0",
        }

        await self._redis.xadd(self.stream_key, entry)

        # Track status
        await self._redis.hset(self._status_key, task_id, "pending")
        logger.info(f"RedisQueue: Enqueued task {task_id}")
        return task_id

    async def dequeue(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Read the next message from the consumer group.

        Args:
            timeout: Blocking wait time in seconds.

        Returns:
            Task dict with 'task_id', or None if no tasks available.

        Raises:
            RuntimeError: If Redis is not initialized.
        """
        self._ensure_connected()

        block_ms = int(timeout * 1000)
        results = await self._redis.xreadgroup(
            groupname=self.consumer_group,
            consumername=self.consumer_name,
            streams={self.stream_key: ">"},
            count=1,
            block=block_ms,
        )

        if not results:
            return None

        # results = [[stream_key, [(message_id, fields)]]]
        _, messages = results[0]
        if not messages:
            return None

        msg_id, fields = messages[0]
        task_id = fields["task_id"]
        task_data = json.loads(fields["data"])
        task_data["task_id"] = task_id
        task_data["_msg_id"] = msg_id
        task_data["_retry_count"] = int(fields.get("retry_count", "0"))

        # Update status
        await self._redis.hset(self._status_key, task_id, "processing")
        return task_data

    async def get_status(self, task_id: str) -> Optional[str]:
        """Get the current status of a task.

        Args:
            task_id: The task identifier.

        Returns:
            Status string or None if not found.
        """
        self._ensure_connected()
        return await self._redis.hget(self._status_key, task_id)

    async def ack(self, task_id: str, success: bool = True, error: str = "") -> None:
        """Acknowledge task completion or failure.

        Args:
            task_id: The task identifier.
            success: True if task succeeded, False if failed.
            error: Error message if failed.
        """
        self._ensure_connected()

        status = "done" if success else "failed"
        await self._redis.hset(self._status_key, task_id, status)

        if error:
            await self._redis.hset(
                f"{self._status_key}:errors", task_id, error
            )

        logger.info(f"RedisQueue: Task {task_id} → {status}")

    async def get_pending_count(self) -> int:
        """Return the number of pending messages in the stream.

        Returns:
            Approximate count of pending messages.
        """
        self._ensure_connected()
        return await self._redis.xlen(self.stream_key)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("RedisQueue: Connection closed")

    def _ensure_connected(self) -> None:
        """Validate that Redis client is initialized.

        Raises:
            RuntimeError: If initialize() has not been called.
        """
        if self._redis is None:
            raise RuntimeError(
                "RedisQueue not initialized. Call await initialize() first."
            )
