"""Ingestion Worker - independent process for async task consumption.

Usage:
    python -m src.ingestion.worker [--config config/settings.yaml]

This worker:
1. Connects to the configured queue backend (Redis or Memory)
2. Loops: dequeue → IngestionPipeline.run() → ack/nack
3. Supports graceful shutdown via SIGTERM/SIGINT
4. Retries failed tasks up to max_retries times
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.settings import Settings, load_settings
from src.observability.logger import get_logger

logger = get_logger(__name__)


class IngestionWorker:
    """Async worker that consumes ingestion tasks from a queue.

    Supports both MemoryQueue and RedisQueue backends via the
    BaseQueue protocol.

    Args:
        settings: Application settings.
        queue: Queue backend instance (MemoryQueue or RedisQueue).
        max_retries: Maximum retry count per task.
    """

    def __init__(
        self,
        settings: Settings,
        queue: Any,
        max_retries: int = 3,
    ) -> None:
        """Initialize the IngestionWorker.

        Args:
            settings: Application settings for pipeline creation.
            queue: Queue backend (must satisfy BaseQueue protocol).
            max_retries: Max retries for failed tasks.
        """
        self.settings = settings
        self.queue = queue
        self.max_retries = max_retries
        self._running = False
        self._pipeline: Any = None

    def _get_pipeline(self, collection: str = "default") -> Any:
        """Lazily create an IngestionPipeline.

        Args:
            collection: Target collection name.

        Returns:
            An IngestionPipeline instance.
        """
        from src.ingestion.pipeline import IngestionPipeline
        return IngestionPipeline(self.settings, collection=collection)

    async def start(self) -> None:
        """Start the worker loop.

        Runs indefinitely, polling the queue for tasks, processing them
        via IngestionPipeline, and acknowledging results.
        """
        self._running = True
        logger.info("IngestionWorker: Started, waiting for tasks...")

        while self._running:
            task = await self.queue.dequeue(timeout=5.0)
            if task is None:
                continue

            task_id = task.get("task_id", "unknown")
            file_path = task.get("file_path", "")
            collection = task.get("collection", "default")
            retry_count = task.get("_retry_count", 0)

            logger.info(
                f"IngestionWorker: Processing task {task_id} "
                f"(file={file_path}, collection={collection}, "
                f"retry={retry_count})"
            )

            try:
                pipeline = self._get_pipeline(collection)
                result = await pipeline.run(
                    file_path=file_path,
                    original_filename=task.get("original_filename"),
                )

                if result.success:
                    await self.queue.ack(task_id, success=True)
                    logger.info(
                        f"IngestionWorker: Task {task_id} completed "
                        f"({result.chunk_count} chunks)"
                    )
                else:
                    error_msg = result.error or "Pipeline returned failure"
                    await self._handle_failure(task_id, error_msg, retry_count)

            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                logger.error(f"IngestionWorker: Task {task_id} error: {error_msg}")
                await self._handle_failure(task_id, error_msg, retry_count)

    async def _handle_failure(
        self, task_id: str, error: str, retry_count: int
    ) -> None:
        """Handle a failed task — retry or mark as permanently failed.

        Args:
            task_id: The task identifier.
            error: Error description.
            retry_count: Current retry attempt number.
        """
        if retry_count < self.max_retries:
            logger.warning(
                f"IngestionWorker: Task {task_id} failed "
                f"(attempt {retry_count + 1}/{self.max_retries}), "
                f"will retry"
            )
            await self.queue.ack(task_id, success=False, error=error)
        else:
            logger.error(
                f"IngestionWorker: Task {task_id} permanently failed "
                f"after {self.max_retries} attempts: {error}"
            )
            await self.queue.ack(task_id, success=False, error=error)

    def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        logger.info("IngestionWorker: Shutdown requested")
        self._running = False


async def create_queue(settings: Settings) -> Any:
    """Create the appropriate queue backend based on settings.

    Args:
        settings: Application settings.

    Returns:
        Queue instance (MemoryQueue or RedisQueue).
    """
    ingestion = getattr(settings, "ingestion", None)
    queue_backend = "memory"
    if ingestion:
        queue_backend = getattr(ingestion, "queue_backend", "memory")

    if queue_backend == "redis":
        try:
            from src.ingestion.queue.redis_queue import RedisQueue

            redis_cfg = getattr(ingestion, "redis", None) if ingestion else None
            url = getattr(redis_cfg, "url", "redis://localhost:6379/0") if redis_cfg else "redis://localhost:6379/0"
            stream_key = getattr(redis_cfg, "stream_key", "rag:ingestion:tasks") if redis_cfg else "rag:ingestion:tasks"
            group = getattr(redis_cfg, "consumer_group", "rag-workers") if redis_cfg else "rag-workers"

            queue = RedisQueue(
                url=url,
                stream_key=stream_key,
                consumer_group=group,
            )
            await queue.initialize()
            logger.info(f"IngestionWorker: Using RedisQueue ({url})")
            return queue
        except Exception as e:
            logger.warning(
                f"IngestionWorker: Redis unavailable ({e}), "
                f"falling back to MemoryQueue"
            )

    from src.ingestion.queue.memory_queue import MemoryQueue
    logger.info("IngestionWorker: Using MemoryQueue (in-process)")
    return MemoryQueue()


async def main() -> None:
    """CLI entry point for the ingestion worker."""
    import argparse

    parser = argparse.ArgumentParser(description="RAG Ingestion Worker")
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )
    args = parser.parse_args()

    settings = load_settings(args.config)
    queue = await create_queue(settings)

    worker = IngestionWorker(settings=settings, queue=queue)

    # Graceful shutdown on SIGTERM/SIGINT
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await worker.start()
    except KeyboardInterrupt:
        worker.stop()
    finally:
        if hasattr(queue, "close"):
            await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
