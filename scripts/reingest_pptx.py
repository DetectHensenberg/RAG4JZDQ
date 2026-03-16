"""Re-ingest all PPTX documents with high-quality LibreOffice slide rendering.

Steps:
1. Find all PPTX source_paths in ChromaDB
2. Delete their old chunks from ChromaDB
3. Clear ingestion_history entries so pipeline won't skip them
4. Delete old image directories for those documents
5. Re-ingest each PPTX through the full pipeline

IMPORTANT: Stop the FastAPI backend before running this script!

Usage: python scripts/reingest_pptx.py
"""
import hashlib
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.settings import load_settings, resolve_path
from src.ingestion.pipeline import IngestionPipeline

CHROMA_DIR = "data/db/chroma"
COLLECTION_NAME = "default"


def find_pptx_sources() -> List[str]:
    """Find all PPTX source_paths stored in ChromaDB."""
    db_path = str(Path(CHROMA_DIR) / "chroma.sqlite3")
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT DISTINCT string_value FROM embedding_metadata "
        "WHERE key = 'source_path' AND (string_value LIKE '%.pptx' OR string_value LIKE '%.ppt')",
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def find_chunk_ids_for_sources(sources: List[str]) -> List[str]:
    """Find all chunk IDs in ChromaDB that belong to the given source_paths."""
    db_path = str(Path(CHROMA_DIR) / "chroma.sqlite3")
    conn = sqlite3.connect(db_path)

    # embedding_metadata.id is the integer rowid from embeddings table.
    # We need to join to get the actual string embedding_id (= chunk ID).
    placeholders = ",".join("?" for _ in sources)
    rows = conn.execute(
        f"SELECT DISTINCT e.embedding_id FROM embedding_metadata m "
        f"JOIN embeddings e ON e.id = m.id "
        f"WHERE m.key = 'source_path' AND m.string_value IN ({placeholders})",
        sources,
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def delete_chunks_from_chroma(chunk_ids: List[str]) -> int:
    """Delete chunks from ChromaDB by ID using the chromadb client."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )
    collection = client.get_collection(COLLECTION_NAME)

    deleted = 0
    batch_size = 100
    for i in range(0, len(chunk_ids), batch_size):
        batch = chunk_ids[i : i + batch_size]
        collection.delete(ids=batch)
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(chunk_ids)} chunks", end="\r")

    # Force close to release lock
    del collection
    del client
    print()
    return deleted


def clear_ingestion_history(sources: List[str]) -> int:
    """Remove entries from ingestion_history.db so pipeline won't skip files."""
    db_path = str(resolve_path("data/db/ingestion_history.db"))
    if not Path(db_path).exists():
        return 0

    conn = sqlite3.connect(db_path)
    # Compute SHA256 for each source file and delete matching records
    cleared = 0
    for src in sources:
        p = Path(src)
        if not p.exists():
            continue
        sha256 = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        cur = conn.execute("DELETE FROM ingestion_history WHERE file_hash = ?", (file_hash,))
        cleared += cur.rowcount
    conn.commit()
    conn.close()
    return cleared


def delete_old_images(sources: List[str]) -> int:
    """Delete old image directories for PPTX documents."""
    images_root = resolve_path("data/images/default")
    deleted_dirs = 0
    for src in sources:
        p = Path(src)
        if not p.exists():
            continue
        sha256 = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        doc_hash = sha256.hexdigest()
        img_dir = images_root / doc_hash
        if img_dir.exists():
            shutil.rmtree(str(img_dir))
            deleted_dirs += 1
    return deleted_dirs


def reingest_pptx_files() -> None:
    """Main re-ingestion workflow."""
    print("=" * 60)
    print("PPTX Re-ingestion with LibreOffice High-Quality Rendering")
    print("=" * 60)
    print()

    # Step 1: Find PPTX files from filesystem
    KNOWLEDGE_BASE = Path(r"D:\WorkSpace\知识库")
    print("Step 1: Scanning filesystem for PPTX files...")
    existing = sorted(
        str(p) for p in KNOWLEDGE_BASE.rglob("*.pptx") if p.is_file()
    )
    print(f"  Found {len(existing)} PPTX files")
    print()

    if not existing:
        print("No PPTX files found. Exiting.")
        return

    # Step 2: Delete old chunks (if any remain)
    print("Step 2: Checking for old PPTX chunks in ChromaDB...")
    try:
        chunk_ids = find_chunk_ids_for_sources(existing)
        print(f"  Found {len(chunk_ids)} old chunks")
        if chunk_ids:
            deleted = delete_chunks_from_chroma(chunk_ids)
            print(f"  Deleted {deleted} chunks")
        else:
            print("  No old chunks to delete (already cleaned)")
    except Exception as e:
        print(f"  Skip: {e}")
    print()

    # Step 3: Clear ingestion history
    print("Step 3: Clearing ingestion history for PPTX files...")
    cleared = clear_ingestion_history(existing)
    print(f"  Cleared {cleared} history entries")
    print()

    # Step 4: Delete old images
    print("Step 4: Deleting old low-quality images...")
    deleted_dirs = delete_old_images(existing)
    print(f"  Deleted {deleted_dirs} image directories")
    print()

    # Step 5: Re-ingest
    print(f"Step 5: Re-ingesting {len(existing)} PPTX files...")
    print("  (LibreOffice renders each slide as 300 DPI PNG)")
    print()

    settings = load_settings(Path("config/settings.yaml"))
    pipeline = IngestionPipeline(settings, collection="default", force=True)

    success = 0
    failed = 0
    t0 = time.monotonic()

    for i, src in enumerate(existing, 1):
        name = Path(src).name
        print(f"  [{i}/{len(existing)}] {name}...")
        try:
            result = pipeline.run(src, original_filename=src)
            if result.success:
                imgs = result.stages.get("loading", {}).get("image_count", 0)
                chunks = result.stages.get("chunking", {}).get("chunk_count", 0)
                print(f"           ✓ {chunks} chunks, {imgs} images")
                success += 1
            else:
                print(f"           ✗ Pipeline returned failure")
                failed += 1
        except Exception as e:
            print(f"           ✗ Error: {e}")
            failed += 1

    elapsed = time.monotonic() - t0
    print()
    print("=" * 60)
    print(f"Re-ingestion complete!")
    print(f"  Success: {success}/{len(existing)}")
    print(f"  Failed:  {failed}/{len(existing)}")
    print(f"  Time:    {elapsed:.1f}s ({elapsed/len(existing):.1f}s per file)")
    print("=" * 60)


if __name__ == "__main__":
    reingest_pptx_files()
