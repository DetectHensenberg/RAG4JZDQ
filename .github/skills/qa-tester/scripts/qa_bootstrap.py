#!/usr/bin/env python3
"""QA Bootstrap — Set up / tear down system states for QA testing.

Usage:
    python .github/skills/qa-tester/scripts/qa_bootstrap.py [command]

Commands:
    baseline   Set up Baseline state (default collection + test_col + traces)
    clear      Clear all data → Empty state
    status     Show current system state
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_documents"
DATA_DIR = REPO_ROOT / "data"
LOGS_DIR = REPO_ROOT / "logs"
TRACES_FILE = LOGS_DIR / "traces.jsonl"

# Baseline documents
BASELINE_DEFAULT = [
    FIXTURES_DIR / "simple.pdf",
    FIXTURES_DIR / "with_images.pdf",
]
BASELINE_TEST_COL = [
    FIXTURES_DIR / "complex_technical_doc.pdf",
]

# Baseline queries (to generate query traces)
BASELINE_QUERIES = [
    ("What is hybrid search and how does it work", "default"),
    ("What is Modular RAG", "default"),
    ("Explain the chunking strategy", "default"),
    ("Retrieval-Augmented Generation modular architecture", "test_col"),
    ("Sample Document PDF loader", "default"),
]


def run_cmd(args: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess command from REPO_ROOT."""
    return subprocess.run(
        [sys.executable] + args,
        cwd=str(REPO_ROOT),
        check=check,
        capture_output=capture,
        text=True,
    )


def clear_all() -> None:
    """Clear all data → Empty state."""
    print("🗑️  Clearing all data...")

    # Clear Chroma
    chroma_dir = DATA_DIR / "db" / "chroma"
    if chroma_dir.exists():
        for item in chroma_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        print("   ✅ Chroma data cleared")

    # Clear BM25
    bm25_dir = DATA_DIR / "db" / "bm25"
    if bm25_dir.exists():
        for item in bm25_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        print("   ✅ BM25 data cleared")

    # Clear images
    images_dir = DATA_DIR / "images"
    if images_dir.exists():
        for item in images_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        print("   ✅ Image data cleared")

    # Clear file integrity DB
    integrity_db = DATA_DIR / "db" / "ingestion_history.db"
    if integrity_db.exists():
        integrity_db.unlink()
        print("   ✅ File integrity DB cleared")

    # Clear traces
    if TRACES_FILE.exists():
        TRACES_FILE.write_text("")
        print("   ✅ Traces cleared")

    print("✅ System is now in Empty state")


def setup_baseline() -> None:
    """Set up Baseline state: ingest docs + run queries to generate traces."""
    print("📦 Setting up Baseline state...")
    print()

    # Step 1: Clear existing data
    clear_all()
    print()

    # Step 2: Ingest default collection
    print("📄 Ingesting default collection (simple.pdf + with_images.pdf)...")
    for pdf in BASELINE_DEFAULT:
        if not pdf.exists():
            print(f"   ⚠️  File not found: {pdf}")
            continue
        print(f"   → {pdf.name}")
        result = run_cmd(
            [str(SCRIPTS_DIR / "ingest.py"), "--path", str(pdf), "--collection", "default", "--force"],
            check=False,
        )
        if result.returncode != 0:
            print(f"   ❌ Failed to ingest {pdf.name} (exit code: {result.returncode})")
        else:
            print(f"   ✅ {pdf.name}")

    print()

    # Step 3: Ingest test_col collection
    print("📄 Ingesting test_col collection (complex_technical_doc.pdf)...")
    for pdf in BASELINE_TEST_COL:
        if not pdf.exists():
            print(f"   ⚠️  File not found: {pdf}")
            continue
        print(f"   → {pdf.name}")
        result = run_cmd(
            [str(SCRIPTS_DIR / "ingest.py"), "--path", str(pdf), "--collection", "test_col", "--force"],
            check=False,
        )
        if result.returncode != 0:
            print(f"   ❌ Failed to ingest {pdf.name} (exit code: {result.returncode})")
        else:
            print(f"   ✅ {pdf.name}")

    print()

    # Step 4: Run queries to generate query traces
    print("🔍 Running baseline queries to generate traces...")
    for query_item in BASELINE_QUERIES:
        if isinstance(query_item, tuple):
            query, collection = query_item
        else:
            query, collection = query_item, "default"
        print(f"   → \"{query}\" (collection={collection})")
        cmd = [str(SCRIPTS_DIR / "query.py"), "--query", query, "--collection", collection]
        result = run_cmd(cmd, check=False)
        if result.returncode != 0:
            print(f"   ❌ Query failed (exit code: {result.returncode})")
        else:
            print(f"   ✅ Done")

    print()
    print("✅ System is now in Baseline state")
    print("   default: simple.pdf + with_images.pdf")
    print("   test_col: complex_technical_doc.pdf")
    print("   traces: ingestion + query traces generated")


def show_status() -> None:
    """Show current system state."""
    print("📊 System Status")
    print("=" * 50)

    # Check Chroma
    chroma_dir = DATA_DIR / "db" / "chroma"
    if chroma_dir.exists():
        files = list(chroma_dir.rglob("*"))
        print(f"   Chroma: {len(files)} files")
    else:
        print("   Chroma: empty")

    # Check BM25
    bm25_dir = DATA_DIR / "db" / "bm25"
    if bm25_dir.exists():
        files = list(bm25_dir.rglob("*"))
        print(f"   BM25: {len(files)} files")
    else:
        print("   BM25: empty")

    # Check images
    images_dir = DATA_DIR / "images"
    if images_dir.exists():
        imgs = list(images_dir.rglob("*.png")) + list(images_dir.rglob("*.jpg"))
        print(f"   Images: {len(imgs)} files")
    else:
        print("   Images: empty")

    # Check traces
    if TRACES_FILE.exists():
        lines = [l for l in TRACES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"   Traces: {len(lines)} entries")
    else:
        print("   Traces: none")


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Bootstrap — manage system state")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["baseline", "clear", "status"],
        help="Command to execute (default: status)",
    )
    args = parser.parse_args()

    if args.command == "baseline":
        setup_baseline()
    elif args.command == "clear":
        clear_all()
    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()
