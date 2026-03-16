"""Repair ChromaDB HNSW index by removing only binary index files.

SQLite data (embeddings, metadata, queue) is preserved.
ChromaDB will rebuild the HNSW index on next startup from stored data.

Usage: python scripts/repair_hnsw.py
  - Make sure the FastAPI backend is STOPPED before running this.
"""
import shutil
import sqlite3
from pathlib import Path


def repair_hnsw(chroma_dir: str = "data/db/chroma") -> None:
    chroma_path = Path(chroma_dir)
    db_path = chroma_path / "chroma.sqlite3"

    if not db_path.exists():
        print(f"ERROR: {db_path} not found. Nothing to repair.")
        return

    # Step 1: Report current state
    conn = sqlite3.connect(str(db_path))
    emb_count = conn.execute("SELECT count(*) FROM embeddings").fetchone()[0]
    queue_count = conn.execute("SELECT count(*) FROM embeddings_queue").fetchone()[0]
    conn.close()
    print(f"SQLite embeddings: {emb_count}")
    print(f"SQLite queue: {queue_count}")

    # Step 2: Find and remove HNSW binary directories (UUID-named folders)
    removed = []
    for item in chroma_path.iterdir():
        if item.is_dir() and len(item.name) == 36 and "-" in item.name:
            # This is a UUID-named directory containing HNSW binary files
            bin_files = list(item.glob("*.bin"))
            print(f"Found HNSW segment: {item.name} ({len(bin_files)} bin files)")
            shutil.rmtree(str(item))
            removed.append(item.name)
            print(f"  Removed HNSW binary files for segment {item.name}")

    if not removed:
        print("No HNSW segment directories found to repair.")
        return

    print(f"\nRepair complete. Removed {len(removed)} HNSW segment(s).")
    print(f"SQLite data preserved: {emb_count} embeddings + {queue_count} queued.")
    print("Restart the backend — ChromaDB will rebuild the HNSW index automatically.")


if __name__ == "__main__":
    repair_hnsw()
