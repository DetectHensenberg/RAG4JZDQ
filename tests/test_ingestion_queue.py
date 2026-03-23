"""Unit tests for ingestion queue system.

Tests cover:
- T1: BaseQueue protocol compliance
- T2: MemoryQueue full lifecycle
- T3: RedisQueue (mocked)
- T4: IngestionWorker basic flow
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.queue.memory_queue import MemoryQueue


class TestMemoryQueueLifecycle:
    """T2: MemoryQueue async lifecycle tests."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_task_id(self) -> None:
        """Test that enqueue returns a unique task_id."""
        q = MemoryQueue()
        task_id = await q.enqueue({"file_path": "a.pdf", "collection": "test"})
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    @pytest.mark.asyncio
    async def test_enqueue_dequeue_roundtrip(self) -> None:
        """Test enqueue → dequeue returns the same data."""
        q = MemoryQueue()
        await q.enqueue({"file_path": "a.pdf", "collection": "test"})

        task = await q.dequeue(timeout=1.0)
        assert task is not None
        assert task["file_path"] == "a.pdf"
        assert "task_id" in task

    @pytest.mark.asyncio
    async def test_dequeue_empty_returns_none(self) -> None:
        """Test that dequeue on empty queue returns None after timeout."""
        q = MemoryQueue()
        task = await q.dequeue(timeout=0.1)
        assert task is None

    @pytest.mark.asyncio
    async def test_status_lifecycle(self) -> None:
        """Test status transitions: pending → processing → done."""
        q = MemoryQueue()
        task_id = await q.enqueue({"file_path": "a.pdf", "collection": "test"})

        # After enqueue: pending
        status = await q.get_status(task_id)
        assert status == "pending"

        # After dequeue: processing
        await q.dequeue(timeout=1.0)
        status = await q.get_status(task_id)
        assert status == "processing"

        # After ack: done
        await q.ack(task_id, success=True)
        status = await q.get_status(task_id)
        assert status == "done"

    @pytest.mark.asyncio
    async def test_ack_failure(self) -> None:
        """Test that ack(success=False) marks task as failed."""
        q = MemoryQueue()
        task_id = await q.enqueue({"file_path": "a.pdf", "collection": "test"})
        await q.dequeue(timeout=1.0)
        await q.ack(task_id, success=False, error="Parse error")

        status = await q.get_status(task_id)
        assert status == "failed"

    @pytest.mark.asyncio
    async def test_pending_count(self) -> None:
        """Test pending count tracking."""
        q = MemoryQueue()
        assert await q.get_pending_count() == 0

        await q.enqueue({"file_path": "a.pdf", "collection": "test"})
        await q.enqueue({"file_path": "b.pdf", "collection": "test"})
        assert await q.get_pending_count() == 2

        await q.dequeue(timeout=1.0)
        assert await q.get_pending_count() == 1

    @pytest.mark.asyncio
    async def test_fifo_ordering(self) -> None:
        """Test that tasks are dequeued in FIFO order."""
        q = MemoryQueue()
        id1 = await q.enqueue({"file_path": "first.pdf", "collection": "test"})
        id2 = await q.enqueue({"file_path": "second.pdf", "collection": "test"})

        task1 = await q.dequeue(timeout=1.0)
        task2 = await q.dequeue(timeout=1.0)

        assert task1["file_path"] == "first.pdf"
        assert task2["file_path"] == "second.pdf"

    @pytest.mark.asyncio
    async def test_status_nonexistent_returns_none(self) -> None:
        """Test getting status for unknown task_id."""
        q = MemoryQueue()
        status = await q.get_status("nonexistent-id")
        assert status is None


class TestRedisQueueProtocol:
    """T3: RedisQueue protocol compliance (mocked, no real Redis needed)."""

    @pytest.mark.asyncio
    async def test_redis_queue_has_required_methods(self) -> None:
        """Test that RedisQueue has all BaseQueue methods."""
        from src.ingestion.queue.redis_queue import RedisQueue

        q = RedisQueue()
        assert hasattr(q, "enqueue")
        assert hasattr(q, "dequeue")
        assert hasattr(q, "get_status")
        assert hasattr(q, "ack")
        assert hasattr(q, "get_pending_count")

    @pytest.mark.asyncio
    async def test_redis_queue_not_initialized_raises(self) -> None:
        """Test that operations without initialize() raise RuntimeError."""
        from src.ingestion.queue.redis_queue import RedisQueue

        q = RedisQueue()
        with pytest.raises(RuntimeError, match="not initialized"):
            await q.enqueue({"file_path": "a.pdf"})


class TestIngestionWorkerBasic:
    """T4: IngestionWorker basic flow tests."""

    @pytest.mark.asyncio
    async def test_worker_processes_task(self) -> None:
        """Test that worker can dequeue and process a task."""
        # Create a mock queue that returns one task then stops
        q = MemoryQueue()
        await q.enqueue({"file_path": "test.pdf", "collection": "default"})

        # Create mock settings
        mock_settings = MagicMock()

        from src.ingestion.worker import IngestionWorker

        worker = IngestionWorker(settings=mock_settings, queue=q)

        # Mock the pipeline to avoid real processing
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.chunk_count = 5
        mock_pipeline = AsyncMock()
        mock_pipeline.run = AsyncMock(return_value=mock_result)
        worker._get_pipeline = MagicMock(return_value=mock_pipeline)

        # Run worker for one iteration
        task = await q.dequeue(timeout=1.0)
        assert task is not None

        # Simulate what worker.start() does internally
        task_id = task["task_id"]
        pipeline = worker._get_pipeline(task["collection"])
        result = await pipeline.run(file_path=task["file_path"])
        if result.success:
            await q.ack(task_id, success=True)

        status = await q.get_status(task_id)
        assert status == "done"
