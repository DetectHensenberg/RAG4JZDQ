"""Rebuild ingestion_history.db by matching source files to ChromaDB.

The pipeline generates embedding IDs as:
    SHA256(source_path_string)[:8] + "_" + chunk_index + "_" + content_hash

So we compute SHA256 of each file's path string, match against ChromaDB
prefixes, and rebuild ingestion_history with real file paths and hashes.

Usage: python scripts/rebuild_ingestion_history.py
"""

import hashlib
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SOURCE_DIR = r"D:\WorkSpace\知识库"
CHROMA_DIR = "data/db/chroma"
HISTORY_DB = "data/db/ingestion_history.db"
COLLECTION = "default"
ALLOWED_EXTS = {".pdf", ".pptx", ".docx", ".md", ".txt", ".csv", ".xlsx"}


def _clean_chunk(text: str) -> str:
    """Remove image refs and descriptions from chunk text."""
    cleaned = re.sub(r"\[IMAGE:.*?\]", "", text)
    cleaned = re.sub(r"\(Description:.*?\)", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned)
    return cleaned


def _is_junk_title(t: str) -> bool:
    """Check if extracted title is low-quality."""
    t = t.strip()
    if len(t) < 4:
        return True
    junk = {"slide", "目录", "contents", "页面标题", "结构描述", "文字内容",
            "图像内容", "整体结构", "结构与组件", "核心概念", "结语",
            "附录", "获得奖项", "建设背景", "用户端", "应用案例", "作业设计"}
    if t.lower().rstrip("0123456789 ") in junk:
        return True
    if re.fullmatch(r"slide\s*\d+", t, re.IGNORECASE):
        return True
    if re.fullmatch(r"[\d_a-f]+", t):
        return True
    if t.startswith("|") or t.startswith("---"):
        return True
    return False


def extract_title_from_chunks(chunks: list[tuple[int, str]]) -> str:
    """Extract the best document title by scanning all chunks.

    Priority:
      1. Heading from Slide 1-3 content
      2. First markdown # heading that isn't junk
      3. First non-junk text line from early chunks
    """
    sorted_chunks = sorted(chunks, key=lambda x: x[0])

    # Pass 1: find headings in Slide 1-3 sections
    for _, text in sorted_chunks:
        cleaned = _clean_chunk(text)
        # Look for "## Slide 1" or "## Slide 2" sections with a ### heading
        slide_match = re.search(
            r"##\s+Slide\s+[1-3]\b.*?###\s+(.+?)(?:\n|$)", cleaned, re.DOTALL
        )
        if slide_match:
            title = slide_match.group(1).strip()
            title = re.sub(r"\s+", " ", title)[:100]
            if not _is_junk_title(title):
                return title

    # Pass 2: first good markdown heading from any chunk
    for _, text in sorted_chunks[:20]:
        cleaned = _clean_chunk(text)
        for m in re.finditer(r"^#{1,3}\s+(.+)", cleaned, re.MULTILINE):
            title = m.group(1).strip()
            title = re.sub(r"\s+", " ", title)[:100]
            if not _is_junk_title(title):
                return title

    # Pass 3: first meaningful text line from early chunks
    for _, text in sorted_chunks[:10]:
        cleaned = _clean_chunk(text)
        for line in cleaned.split("\n"):
            line = line.strip()
            line = re.sub(r"\s+", " ", line)
            if len(line) > 8 and not _is_junk_title(line):
                return line[:100]

    return "(无标题)"


def ensure_history_table(db_path: str) -> None:
    """Create ingestion_history table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_history (
            file_hash TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL,
            collection TEXT,
            error_msg TEXT,
            processed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_status
        ON ingestion_history(status)
    """)
    conn.commit()
    conn.close()


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA256 of file content (same as pipeline integrity checker)."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def rebuild() -> None:
    """Rebuild ingestion history by matching source files to ChromaDB."""
    print("=" * 60)
    print("Rebuild ingestion_history from source files + ChromaDB")
    print("=" * 60)
    print()

    # Step 1: Get unique path-hash prefixes from ChromaDB embedding IDs
    print("Step 1: Reading ChromaDB embedding ID prefixes...")
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_collection(COLLECTION)
    all_ids = col.get(include=[])["ids"]

    prefix_counts: Dict[str, int] = {}
    for eid in all_ids:
        prefix = eid.split("_")[0]
        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    print(f"  Total embeddings: {len(all_ids)}")
    print(f"  Unique file prefixes: {len(prefix_counts)}")
    print()

    # Step 2: Scan source files, compute path-based hash to match
    # Pipeline uses: SHA256(source_path_string)[:8] as the prefix
    print(f"Step 2: Scanning {SOURCE_DIR} and matching by path hash...")
    source_path = Path(SOURCE_DIR)
    if not source_path.exists():
        print(f"  ERROR: {SOURCE_DIR} does not exist!")
        return

    files = [
        f for f in source_path.rglob("*")
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTS
    ]
    print(f"  Found {len(files)} eligible files")

    matched = []
    unmatched_prefixes = set(prefix_counts.keys())

    for fpath in files:
        path_hash = hashlib.sha256(str(fpath).encode("utf-8")).hexdigest()[:8]
        if path_hash in prefix_counts:
            # Compute real file content hash for ingestion_history
            file_hash = _compute_file_hash(str(fpath))
            chunk_count = prefix_counts[path_hash]
            matched.append((file_hash, str(fpath), chunk_count))
            unmatched_prefixes.discard(path_hash)

    print(f"  Matched: {len(matched)} / {len(prefix_counts)} files")
    if unmatched_prefixes:
        print(f"  Unmatched prefixes: {len(unmatched_prefixes)} (temp uploads or moved files)")
    print()

    # Step 3: Show matches
    print("Step 3: Matched files:")
    for file_hash, file_path, chunk_count in matched:
        name = Path(file_path).name
        print(f"  {file_hash[:8]}  ({chunk_count:4d} chunks) | {name}")
    print()

    # Step 4: Write to ingestion_history.db
    print("Step 4: Writing to ingestion_history.db...")
    ensure_history_table(HISTORY_DB)

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(HISTORY_DB)

    # Clear old recovered records first
    conn.execute("DELETE FROM ingestion_history")

    for file_hash, file_path, _ in matched:
        conn.execute(
            "INSERT OR REPLACE INTO ingestion_history "
            "(file_hash, file_path, status, collection, error_msg, processed_at, updated_at) "
            "VALUES (?, ?, 'success', ?, NULL, ?, ?)",
            (file_hash, file_path, COLLECTION, now, now),
        )

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM ingestion_history").fetchone()[0]
    conn.close()

    print(f"  Inserted: {len(matched)} records")
    print(f"  Total in DB: {total}")
    print()

    print("=" * 60)
    print(f"Done! {len(matched)}/{len(prefix_counts)} documents restored")
    if unmatched_prefixes:
        print(f"  {len(unmatched_prefixes)} unmatched (may need manual re-ingestion)")
    print("=" * 60)


if __name__ == "__main__":
    rebuild()
