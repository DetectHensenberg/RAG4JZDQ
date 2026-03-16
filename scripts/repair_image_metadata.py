"""Repair image_refs in ChromaDB metadata from chunk text [IMAGE:] placeholders.

After rebuild_collection, image_refs/image_captions were lost.
This script:
1. Scans chunk documents for [IMAGE: id] placeholders
2. Looks up image paths in image_index.db
3. Updates ChromaDB metadata with image_refs (comma-separated IDs)

Usage: python scripts/repair_image_metadata.py
"""

import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHROMA_DIR = "data/db/chroma"
COLLECTION_NAME = "default"
IMAGE_DB = "data/db/image_index.db"
BATCH_SIZE = 200

IMAGE_PATTERN = re.compile(r"\[IMAGE:\s*([^\]]+)\]")


def load_image_index() -> Dict[str, str]:
    """Load image_id -> file_path mapping from image_index.db."""
    conn = sqlite3.connect(IMAGE_DB)
    rows = conn.execute("SELECT image_id, file_path FROM image_index").fetchall()
    conn.close()
    mapping = {r[0]: r[1] for r in rows}
    print(f"  Loaded {len(mapping)} image index entries")
    return mapping


def repair() -> None:
    """Scan chunks and restore image_refs metadata."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    print("=" * 60)
    print("Repair Image Metadata in ChromaDB")
    print("=" * 60)
    print()

    # Step 1: Load image index
    print("Step 1: Loading image index...")
    img_index = load_image_index()
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

    # Step 3: Scan and update
    print("Step 3: Scanning chunks for [IMAGE:] and updating metadata...")
    updated = 0
    chunks_with_images = 0
    total_refs = 0

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
            if not doc_text:
                continue

            # Find [IMAGE: id] in chunk text
            matches = IMAGE_PATTERN.findall(doc_text)
            if not matches:
                continue

            image_ids = [m.strip() for m in matches]
            chunks_with_images += 1
            total_refs += len(image_ids)

            # Check if already has image_refs
            existing = old_meta.get("image_refs", "") if old_meta else ""
            new_refs = ",".join(image_ids)
            if existing == new_refs:
                continue

            # Build updated metadata
            new_meta: Dict = {"image_refs": new_refs}

            ids_to_update.append(eid)
            metas_to_update.append(new_meta)

        if ids_to_update:
            collection.update(
                ids=ids_to_update,
                metadatas=metas_to_update,
            )
            updated += len(ids_to_update)

        done = min(offset + BATCH_SIZE, total)
        print(
            f"  [{done}/{total}] chunks_with_images={chunks_with_images}, "
            f"updated={updated}, total_refs={total_refs}",
            end="\r",
        )

    print()
    print()

    # Step 4: Verify
    print("Step 4: Verification...")
    sample = collection.get(
        where={"image_refs": {"$ne": ""}},
        limit=5,
        include=["metadatas"],
    )
    for eid, meta in zip(sample["ids"], sample["metadatas"]):
        refs = meta.get("image_refs", "NONE")
        print(f"  {eid} -> image_refs={refs[:80]}")

    print()
    print("=" * 60)
    print(f"Repair complete!")
    print(f"  Chunks with images: {chunks_with_images}")
    print(f"  Updated:            {updated}")
    print(f"  Total image refs:   {total_refs}")
    print("=" * 60)


if __name__ == "__main__":
    repair()
