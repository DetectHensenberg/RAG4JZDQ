"""Repair ChromaDB metadata: restore source_path from embedding ID prefixes.

After rebuild_collection.py, metadata was lost (all '_placeholder').
This script reconstructs source_path and chunk_index by matching
the SHA256(file_path)[:8] prefix in each embedding ID back to real files.

Usage: python scripts/repair_metadata.py
"""

import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SOURCE_DIR = r"D:\WorkSpace\知识库"
CHROMA_DIR = "data/db/chroma"
COLLECTION_NAME = "default"
ALLOWED_EXTS = {".pdf", ".pptx", ".docx", ".md", ".txt", ".csv", ".xlsx"}
BATCH_SIZE = 200


def build_path_hash_map(source_dir: str) -> Dict[str, str]:
    """Build mapping: SHA256(file_path)[:8] -> file_path string."""
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"  ERROR: {source_dir} does not exist!")
        return {}

    files = [
        f for f in source_path.rglob("*")
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTS
    ]
    print(f"  Scanned {len(files)} eligible files")

    hash_map: Dict[str, str] = {}
    for fpath in files:
        path_str = str(fpath)
        prefix = hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:8]
        hash_map[prefix] = path_str

    return hash_map


def repair() -> None:
    """Repair metadata in ChromaDB collection."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    print("=" * 60)
    print("Repair ChromaDB Metadata (restore source_path)")
    print("=" * 60)
    print()

    # Step 1: Build path hash map
    print("Step 1: Building file path hash map...")
    hash_map = build_path_hash_map(SOURCE_DIR)
    print(f"  Unique path prefixes: {len(hash_map)}")
    print()

    # Step 2: Open ChromaDB
    print("Step 2: Opening ChromaDB...")
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
            is_persistent=True,
        ),
    )
    collection = client.get_collection(COLLECTION_NAME)
    total = collection.count()
    print(f"  Collection: {COLLECTION_NAME}, count: {total}")
    print()

    # Step 3: Fetch all IDs and current metadata
    print("Step 3: Fetching all records and repairing metadata...")
    updated = 0
    unmatched = 0
    already_ok = 0

    for offset in range(0, total, BATCH_SIZE):
        result = collection.get(
            limit=BATCH_SIZE,
            offset=offset,
            include=["metadatas", "documents"],
        )
        batch_ids = result["ids"]
        batch_metas = result["metadatas"]
        batch_docs = result["documents"]

        ids_to_update: List[str] = []
        metas_to_update: List[Dict] = []

        for eid, old_meta, doc_text in zip(batch_ids, batch_metas, batch_docs):
            # Check if metadata already has source_path
            if old_meta and old_meta.get("source_path") and old_meta["source_path"] != "未知":
                already_ok += 1
                continue

            # Parse embedding ID: {source_hash}_{chunk_index:04d}_{content_hash}
            parts = eid.split("_")
            if len(parts) < 3:
                unmatched += 1
                continue

            source_hash = parts[0]
            try:
                chunk_index = int(parts[1])
            except ValueError:
                unmatched += 1
                continue

            # Match source_hash to file path
            source_path = hash_map.get(source_hash, "")

            # Build repaired metadata
            new_meta = {
                "source_path": source_path if source_path else f"unknown_{source_hash}",
                "chunk_index": chunk_index,
                "chunk_id": eid,
            }

            # Extract image_refs from document text
            if doc_text:
                image_refs = re.findall(r"\[IMAGE:\s*([^\]]+)\]", doc_text)
                if image_refs:
                    # ChromaDB doesn't support list values in metadata,
                    # store as comma-separated string
                    new_meta["image_refs"] = ",".join(r.strip() for r in image_refs)

            ids_to_update.append(eid)
            metas_to_update.append(new_meta)

        # Batch update
        if ids_to_update:
            collection.update(
                ids=ids_to_update,
                metadatas=metas_to_update,
            )
            updated += len(ids_to_update)

        done = min(offset + BATCH_SIZE, total)
        print(f"  [{done}/{total}] updated={updated}, ok={already_ok}, unmatched={unmatched}", end="\r")

    print()
    print()

    # Step 4: Verify
    print("Step 4: Verification...")
    sample = collection.peek(limit=5)
    for eid, meta in zip(sample["ids"], sample["metadatas"]):
        src = meta.get("source_path", "MISSING")
        idx = meta.get("chunk_index", "MISSING")
        src_short = Path(src).name if src and not src.startswith("unknown") else src
        print(f"  {eid} -> source={src_short}, chunk_index={idx}")

    print()
    print("=" * 60)
    print(f"Repair complete!")
    print(f"  Updated:   {updated}")
    print(f"  Already OK: {already_ok}")
    print(f"  Unmatched: {unmatched}")
    print(f"  Total:     {total}")
    print("=" * 60)


if __name__ == "__main__":
    repair()
