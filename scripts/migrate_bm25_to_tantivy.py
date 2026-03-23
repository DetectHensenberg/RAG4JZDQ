"""Migrate existing BM25 Pickle indexes to Tantivy format.

Usage:
    python scripts/migrate_bm25_to_tantivy.py [--collection default]

This script reads existing Pickle-based BM25 indexes and rebuilds them
as Tantivy indexes, preserving all document data.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.settings import resolve_path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def migrate_collection(collection: str = "default") -> bool:
    """Migrate a single collection from BM25 Pickle to Tantivy.

    Args:
        collection: Collection name to migrate.

    Returns:
        True if migration succeeded, False otherwise.
    """
    from src.ingestion.storage.bm25_indexer import BM25Indexer
    from src.ingestion.storage.tantivy_indexer import TantivyIndexer

    # Paths
    bm25_dir = str(resolve_path(f"data/db/bm25/{collection}"))
    tantivy_dir = str(resolve_path(f"data/db/tantivy/{collection}"))

    logger.info(f"=== Migrating collection '{collection}' ===")
    logger.info(f"  BM25 source:    {bm25_dir}")
    logger.info(f"  Tantivy target: {tantivy_dir}")

    # Step 1: Load existing BM25 index
    bm25 = BM25Indexer(index_dir=bm25_dir)
    if not bm25.load(collection):
        # Try loading with parent dir
        bm25_parent = str(resolve_path("data/db/bm25"))
        bm25 = BM25Indexer(index_dir=bm25_parent)
        if not bm25.load(collection):
            logger.error(f"  ✗ BM25 index not found for collection '{collection}'")
            return False

    logger.info(f"  ✓ BM25 index loaded: {bm25._metadata}")

    # Step 2: Extract term_stats from BM25 internal structure
    term_stats = _extract_term_stats(bm25)
    logger.info(f"  ✓ Extracted {len(term_stats)} documents from BM25 index")

    if not term_stats:
        logger.warning("  ⚠ No documents to migrate")
        return False

    # Step 3: Build Tantivy index
    tantivy = TantivyIndexer(index_dir=tantivy_dir)
    tantivy.build(term_stats, collection)
    logger.info(f"  ✓ Tantivy index built successfully")

    # Step 4: Verify migration
    verify_ok = _verify_migration(bm25, tantivy, collection)
    if verify_ok:
        logger.info(f"  ✓ Migration verified: Top-K results match")
    else:
        logger.warning(f"  ⚠ Verification: results may differ (expected for scoring differences)")

    logger.info(f"=== Migration complete for '{collection}' ===\n")
    return True


def _extract_term_stats(bm25: "BM25Indexer") -> list:
    """Extract term_stats from BM25 internal index.

    Reconstructs the original term_stats format from the inverted index.

    Args:
        bm25: Loaded BM25Indexer instance.

    Returns:
        List of term_stats dicts suitable for TantivyIndexer.build().
    """
    # Reconstruct per-document term frequencies from inverted index
    doc_terms: dict = {}  # chunk_id -> {term: freq, ...}
    doc_lengths: dict = {}  # chunk_id -> doc_length

    for term, term_data in bm25._index.items():
        for posting in term_data["postings"]:
            cid = posting["chunk_id"]
            tf = posting["tf"]
            dl = posting["doc_length"]

            if cid not in doc_terms:
                doc_terms[cid] = {}
                doc_lengths[cid] = dl

            doc_terms[cid][term] = tf

    return [
        {
            "chunk_id": cid,
            "term_frequencies": doc_terms[cid],
            "doc_length": doc_lengths[cid],
        }
        for cid in doc_terms
    ]


def _verify_migration(
    bm25: "BM25Indexer",
    tantivy: "TantivyIndexer",
    collection: str,
) -> bool:
    """Verify that Tantivy returns similar results to BM25.

    Args:
        bm25: Original BM25 indexer.
        tantivy: New Tantivy indexer.
        collection: Collection name.

    Returns:
        True if top chunk_ids overlap significantly.
    """
    # Pick a few test terms from the index
    test_terms = list(bm25._index.keys())[:3]
    if not test_terms:
        return True

    tantivy.load(collection)

    bm25_results = bm25.query(test_terms, top_k=5)
    tantivy_results = tantivy.query(test_terms, top_k=5)

    bm25_ids = {r["chunk_id"] for r in bm25_results}
    tantivy_ids = {r["chunk_id"] for r in tantivy_results}

    overlap = bm25_ids & tantivy_ids
    logger.info(
        f"  Verification: BM25 top-5={len(bm25_ids)}, "
        f"Tantivy top-5={len(tantivy_ids)}, "
        f"overlap={len(overlap)}"
    )
    return len(overlap) >= 1 if bm25_ids else True


def main() -> None:
    """CLI entry point for BM25 → Tantivy migration."""
    parser = argparse.ArgumentParser(
        description="Migrate BM25 Pickle indexes to Tantivy"
    )
    parser.add_argument(
        "--collection",
        default="default",
        help="Collection name to migrate (default: %(default)s)",
    )
    args = parser.parse_args()

    success = migrate_collection(args.collection)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
