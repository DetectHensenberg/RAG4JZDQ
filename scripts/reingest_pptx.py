"""Re-ingest all PPTX documents with high-quality LibreOffice slide rendering.

Pipeline force=True automatically:
- Deletes old chunks for the same source_path (no orphan duplicates)
- Skips SHA256 integrity check
- Re-extracts images via LibreOffice 300 DPI rendering

Usage: python scripts/reingest_pptx.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.settings import load_settings
from src.ingestion.pipeline import IngestionPipeline

KNOWLEDGE_BASE = Path(r"D:\WorkSpace\知识库")


def reingest_pptx_files() -> None:
    """Scan filesystem for PPTX and re-ingest via pipeline (force=True)."""
    print("=" * 60)
    print("PPTX Re-ingestion with LibreOffice High-Quality Rendering")
    print("=" * 60)
    print()

    pptx_files = sorted(str(p) for p in KNOWLEDGE_BASE.rglob("*.pptx") if p.is_file())
    print(f"Found {len(pptx_files)} PPTX files")
    if not pptx_files:
        return
    print()

    settings = load_settings(Path("config/settings.yaml"))
    pipeline = IngestionPipeline(
        settings, collection="default", force=True, skip_llm_transform=True
    )

    success = 0
    failed = 0
    t0 = time.monotonic()

    for i, src in enumerate(pptx_files, 1):
        name = Path(src).name
        print(f"  [{i}/{len(pptx_files)}] {name}...")
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
    print(f"  Success: {success}/{len(pptx_files)}")
    print(f"  Failed:  {failed}/{len(pptx_files)}")
    print(f"  Time:    {elapsed:.1f}s ({elapsed / max(len(pptx_files), 1):.1f}s per file)")
    print("=" * 60)


if __name__ == "__main__":
    reingest_pptx_files()
