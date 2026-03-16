"""Rebuild ChromaDB collection: re-embed documents from SQLite metadata.

Since HNSW binary files (which stored vectors) are gone, this script:
1. Reads document IDs, metadata, and text from ChromaDB's SQLite
2. Re-generates embeddings via the project's embedding API
3. Creates a fresh ChromaDB collection with the new vectors

This is MUCH faster than full re-ingestion because it skips:
  - File loading / OCR / PDF parsing
  - Chunking / splitting
  - LLM refinement / enrichment / captioning

IMPORTANT: Stop the FastAPI backend before running this script!

Usage: python scripts/rebuild_collection.py
"""
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHROMA_DIR = "data/db/chroma"
COLLECTION_NAME = "default"
EMBED_BATCH = 10
UPSERT_BATCH = 50


def read_records_from_sqlite(db_path: str) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """Read IDs, metadata, and documents from ChromaDB's SQLite."""
    conn = sqlite3.connect(db_path)

    row = conn.execute(
        "SELECT id FROM collections WHERE name = ?", (COLLECTION_NAME,)
    ).fetchone()
    if not row:
        print(f"Collection '{COLLECTION_NAME}' not found.")
        conn.close()
        return [], [], []

    collection_id = row[0]
    print(f"  Collection ID: {collection_id}")

    # Get the metadata segment ID for this collection
    seg_row = conn.execute(
        "SELECT id FROM segments WHERE collection = ? AND scope = 'METADATA'",
        (collection_id,),
    ).fetchone()
    segment_id = seg_row[0] if seg_row else None
    print(f"  Metadata segment: {segment_id}")

    # Get embedding IDs
    emb_rows = conn.execute(
        "SELECT embedding_id FROM embeddings WHERE segment_id = ? ORDER BY rowid",
        (segment_id,),
    ).fetchall()
    ids = [r[0] for r in emb_rows]
    id_to_idx = {eid: i for i, eid in enumerate(ids)}
    print(f"  Embedding IDs: {len(ids)}")

    # Read metadata
    metadatas: List[Dict[str, Any]] = [{} for _ in ids]
    meta_rows = conn.execute(
        "SELECT id, key, string_value, int_value, float_value, bool_value "
        "FROM embedding_metadata"
    ).fetchall()
    for emb_id, key, str_val, int_val, float_val, bool_val in meta_rows:
        if emb_id in id_to_idx:
            idx = id_to_idx[emb_id]
            if str_val is not None:
                metadatas[idx][key] = str_val
            elif int_val is not None:
                metadatas[idx][key] = int_val
            elif float_val is not None:
                metadatas[idx][key] = float_val
            elif bool_val is not None:
                metadatas[idx][key] = bool(bool_val)
    print(f"  Metadata entries: {len(meta_rows)}")

    # Read documents from fulltext content table
    documents: List[str] = ["" for _ in ids]
    try:
        doc_rows = conn.execute(
            "SELECT rowid, c0 FROM embedding_fulltext_search_content"
        ).fetchall()
        for rowid, content in doc_rows:
            idx = rowid  # ChromaDB uses 0-based rowid mapping
            if 0 <= idx < len(documents):
                documents[idx] = content or ""
        non_empty = sum(1 for d in documents if d.strip())
        print(f"  Documents with text: {non_empty}/{len(documents)}")
    except Exception as e:
        print(f"  Warning: Could not read documents: {e}")

    conn.close()
    return ids, metadatas, documents


def rebuild_collection() -> None:
    """Rebuild ChromaDB collection by re-embedding from SQLite data."""
    db_path = str(Path(CHROMA_DIR) / "chroma.sqlite3")

    if not Path(db_path).exists():
        print("ERROR: ChromaDB SQLite database not found.")
        return

    print("=" * 60)
    print("ChromaDB Collection Rebuild (re-embed from SQLite)")
    print("=" * 60)
    print()

    # Step 1: Read data
    print("Step 1: Reading records from SQLite...")
    ids, metadatas, documents = read_records_from_sqlite(db_path)
    if not ids:
        print("No data found. Exiting.")
        return
    print()

    # Step 2: Load embedding model
    print("Step 2: Loading embedding model...")
    from src.core.settings import load_settings
    settings = load_settings(Path("config/settings.yaml"))
    from src.libs.embedding.embedding_factory import EmbeddingFactory
    embedder = EmbeddingFactory.create(settings)
    print(f"  Provider: {settings.embedding.provider}")
    print(f"  Model: {settings.embedding.model}")
    print()

    # Step 3: Re-embed all documents
    # Use document text for embedding; fall back to metadata 'text' field
    texts_to_embed: List[str] = []
    for i, (doc, meta) in enumerate(zip(documents, metadatas)):
        text = doc.strip() if doc.strip() else meta.get("text", "")
        if not text:
            text = ids[i]  # Last resort: use ID
        texts_to_embed.append(text)

    print(f"Step 3: Re-embedding {len(texts_to_embed)} documents (batch={EMBED_BATCH})...")
    all_vectors: List[List[float]] = []
    t0 = time.monotonic()

    for start in range(0, len(texts_to_embed), EMBED_BATCH):
        end = min(start + EMBED_BATCH, len(texts_to_embed))
        batch_texts = texts_to_embed[start:end]
        try:
            vectors = embedder.embed(batch_texts)
            all_vectors.extend(vectors)
        except Exception as e:
            print(f"\n  ERROR embedding batch {start}-{end}: {e}")
            # Fill with zeros so indices stay aligned
            all_vectors.extend([[0.0] * 1024 for _ in batch_texts])

        done = min(end, len(texts_to_embed))
        elapsed = time.monotonic() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"  [{done}/{len(texts_to_embed)}] {rate:.0f} docs/sec", end="\r")

    embed_time = time.monotonic() - t0
    dim = len(all_vectors[0]) if all_vectors else 0
    print(f"\n  Embedding done in {embed_time:.1f}s, dim={dim}")
    print()

    # Step 4: Delete old collection and create fresh one
    print("Step 4: Recreating collection...")
    import shutil
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    # Fully remove old chroma dir to ensure clean state
    chroma_path = Path(CHROMA_DIR)
    if chroma_path.exists():
        shutil.rmtree(str(chroma_path))
        chroma_path.mkdir(parents=True, exist_ok=True)
    print("  Old data cleared")

    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
            is_persistent=True,
        ),
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"  Fresh collection '{COLLECTION_NAME}' created")
    print()

    # Step 5: Upsert all data
    print(f"Step 5: Upserting {len(ids)} records (batch={UPSERT_BATCH})...")
    inserted = 0
    failed = 0
    t1 = time.monotonic()

    for start in range(0, len(ids), UPSERT_BATCH):
        end = min(start + UPSERT_BATCH, len(ids))
        batch_ids = ids[start:end]
        batch_emb = all_vectors[start:end]
        batch_meta = metadatas[start:end]
        batch_doc = documents[start:end]

        # ChromaDB requires non-empty metadata
        for i, m in enumerate(batch_meta):
            if not m:
                batch_meta[i] = {"_placeholder": "true"}

        try:
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_emb,
                metadatas=batch_meta,
                documents=batch_doc,
            )
            inserted += len(batch_ids)
            elapsed = time.monotonic() - t1
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  [{inserted}/{len(ids)}] {rate:.0f} records/sec", end="\r")
        except Exception as e:
            failed += len(batch_ids)
            print(f"\n  ERROR at batch {start}-{end}: {e}")

    upsert_time = time.monotonic() - t1
    print()
    print()

    # Step 6: Verify
    print("Step 6: Verification...")
    final_count = collection.count()
    print(f"  Collection count: {final_count}")
    try:
        r = collection.peek(limit=3)
        print(f"  Peek: OK ({len(r['ids'])} records)")
    except Exception as e:
        print(f"  Peek: FAILED ({e})")

    total_time = time.monotonic() - t0
    print()
    print("=" * 60)
    print(f"Rebuild complete!")
    print(f"  Embed time:  {embed_time:.1f}s")
    print(f"  Upsert time: {upsert_time:.1f}s")
    print(f"  Total time:  {total_time:.1f}s")
    print(f"  Records: {inserted} inserted, {failed} failed")
    print(f"  Final count: {final_count}")
    print("=" * 60)


if __name__ == "__main__":
    rebuild_collection()
