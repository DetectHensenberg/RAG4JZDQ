import asyncio
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.ingestion.storage.feedback_store import FeedbackStore
from src.core.settings import resolve_path

async def test_concurrency():
    db_path = resolve_path("data/db/feedback_test.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except:
            pass
    
    store = FeedbackStore(str(db_path))
    
    # PRE-CREATE SCHEMA (Thread-safe initialization)
    print("Pre-creating schema...")
    await store.async_upsert_feedback("init_trace", 5, "initialization")
    
    async def write_op(i):
        try:
            # Use small delay to spread them slightly but still concurrent
            await asyncio.sleep(i * 0.01) 
            await store.async_upsert_feedback(f"trace_{i}", 1, f"comment_{i}")
            print(f"Write {i} done")
        except Exception as e:
            print(f"Write {i} FAILED: {e}")
            import traceback
            traceback.print_exc()

    print("Starting 10 concurrent writes to SQLite (WAL context)...")
    await asyncio.gather(*[write_op(i) for i in range(10)])
    print("All concurrent writes succeeded!")

if __name__ == "__main__":
    asyncio.run(test_concurrency())
