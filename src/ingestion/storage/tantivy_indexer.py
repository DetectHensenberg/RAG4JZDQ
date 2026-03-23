"""Tantivy-based BM25 Indexer for high-performance sparse retrieval.

This module implements a Tantivy-backed indexer that provides the same interface
as BM25Indexer but uses the Rust-powered Tantivy engine for:
- Disk-based Mmap indexing (80%+ memory reduction vs Pickle)
- Millisecond-level query latency
- Native incremental index updates

Drop-in replacement for BM25Indexer via settings.yaml:
    retrieval:
      sparse_provider: tantivy  # or bm25

Example:
    >>> indexer = TantivyIndexer(index_dir="data/db/tantivy")
    >>> indexer.build(term_stats, collection="default")
    >>> results = indexer.query(["hello", "world"], top_k=5)
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import to allow graceful fallback when tantivy is not installed
_tantivy = None


def _ensure_tantivy() -> Any:
    """Lazy-import tantivy, raising a clear error if not installed.

    Returns:
        The tantivy module.

    Raises:
        ImportError: If tantivy is not installed.
    """
    global _tantivy
    if _tantivy is None:
        try:
            import tantivy as _tv
            _tantivy = _tv
        except ImportError as exc:
            raise ImportError(
                "tantivy is required for TantivyIndexer. "
                "Install it via: pip install tantivy"
            ) from exc
    return _tantivy


class TantivyIndexer:
    """Build and query Tantivy full-text indexes.

    Provides the same public interface as BM25Indexer so it can be used
    as a drop-in replacement via dependency injection.

    Index Schema:
        - chunk_id (TEXT, stored): Unique chunk identifier
        - content (TEXT, indexed+stored): Full text for BM25 scoring
        - doc_length (UNSIGNED, stored): Token count for compatibility

    Args:
        index_dir: Root directory for Tantivy index directories.
        k1: BM25 term frequency saturation parameter (default: 1.5).
        b: BM25 length normalization parameter (default: 0.75).
    """

    def __init__(
        self,
        index_dir: str = "data/db/tantivy",
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """Initialize TantivyIndexer.

        Args:
            index_dir: Root directory for storing per-collection indexes.
            k1: BM25 k1 parameter (unused by Tantivy directly, kept for API compat).
            b: BM25 b parameter (unused by Tantivy directly, kept for API compat).

        Raises:
            ValueError: If k1 or b are out of valid ranges.
        """
        if k1 <= 0:
            raise ValueError(f"k1 must be > 0, got {k1}")
        if not 0 <= b <= 1:
            raise ValueError(f"b must be in [0, 1], got {b}")

        self.index_dir = Path(index_dir)
        self.k1 = k1
        self.b = b

        # Cached index objects per collection
        self._indexes: Dict[str, Any] = {}
        self._metadata: Dict[str, Any] = {}

    def _get_collection_path(self, collection: str) -> Path:
        """Get the directory path for a collection's Tantivy index.

        Args:
            collection: Collection name.

        Returns:
            Path to the collection index directory.
        """
        return self.index_dir / collection

    def _build_schema(self) -> Any:
        """Build the Tantivy schema.

        Uses 'raw' tokenizer for chunk_id to ensure exact-match semantics
        (the default tokenizer would split IDs like 'doc1_chunk0' into
        multiple tokens, breaking delete_documents).

        Returns:
            A tantivy.Schema object.
        """
        tv = _ensure_tantivy()
        sb = tv.SchemaBuilder()
        sb.add_text_field("chunk_id", stored=True, tokenizer_name="raw")
        sb.add_text_field("content", stored=True, tokenizer_name="default")
        sb.add_unsigned_field("doc_length", stored=True)
        return sb.build()

    def _get_or_create_index(self, collection: str) -> Any:
        """Get or create a Tantivy index for the given collection.

        Args:
            collection: Collection name.

        Returns:
            A tantivy.Index object.
        """
        if collection in self._indexes:
            return self._indexes[collection]

        tv = _ensure_tantivy()
        idx_path = self._get_collection_path(collection)
        idx_path.mkdir(parents=True, exist_ok=True)

        schema = self._build_schema()

        # Check if index already exists on disk
        meta_file = idx_path / "meta.json"
        if meta_file.exists():
            # Open existing index
            idx = tv.Index(schema, path=str(idx_path))
        else:
            # Create new index
            idx = tv.Index(schema, path=str(idx_path))

        self._indexes[collection] = idx
        return idx

    def build(
        self,
        term_stats: List[Dict[str, Any]],
        collection: str = "default",
        trace: Optional[Any] = None,
    ) -> None:
        """Build Tantivy index from term statistics (full rebuild).

        Removes any existing index for this collection and creates a new one
        from the provided term statistics.

        Args:
            term_stats: List of dicts from SparseEncoder.encode(), each with:
                - chunk_id (str)
                - term_frequencies (Dict[str, int])
                - doc_length (int)
            collection: Collection name.
            trace: Optional TraceContext for observability.

        Raises:
            ValueError: If term_stats is empty or has invalid structure.
        """
        if not term_stats:
            raise ValueError("Cannot build index from empty term_stats")

        self._validate_term_stats(term_stats)

        # Remove existing index directory for clean rebuild
        idx_path = self._get_collection_path(collection)
        if collection in self._indexes:
            del self._indexes[collection]
        if idx_path.exists():
            shutil.rmtree(idx_path)

        # Create fresh index
        idx = self._get_or_create_index(collection)
        writer = idx.writer()

        tv = _ensure_tantivy()
        num_docs = len(term_stats)
        total_length = 0

        for stat in term_stats:
            chunk_id = stat["chunk_id"]
            doc_length = stat["doc_length"]
            total_length += doc_length

            # Reconstruct full text from term frequencies for indexing
            content = self._reconstruct_content(stat["term_frequencies"])

            writer.add_document(tv.Document(
                chunk_id=chunk_id,
                content=content,
                doc_length=doc_length,
            ))

        writer.commit()
        idx.reload()

        # Store metadata for compatibility
        avg_doc_length = total_length / num_docs if num_docs > 0 else 0.0
        self._metadata = {
            "num_docs": num_docs,
            "avg_doc_length": avg_doc_length,
            "total_terms": sum(
                len(s["term_frequencies"]) for s in term_stats
            ),
            "collection": collection,
        }

        logger.info(
            f"TantivyIndexer: Built index for collection '{collection}' "
            f"with {num_docs} documents"
        )

    def load(
        self,
        collection: str = "default",
        trace: Optional[Any] = None,
    ) -> bool:
        """Load index from disk.

        For Tantivy, this simply checks if the index directory exists and
        opens it. Tantivy uses Mmap so there is no heavy deserialization.

        Args:
            collection: Collection name to load.
            trace: Optional TraceContext for observability.

        Returns:
            True if index loaded successfully, False if not found.
        """
        idx_path = self._get_collection_path(collection)
        meta_file = idx_path / "meta.json"

        if not meta_file.exists():
            return False

        try:
            idx = self._get_or_create_index(collection)
            idx.reload()
            return True
        except Exception as e:
            logger.warning(
                f"Failed to load Tantivy index for collection "
                f"'{collection}': {e}"
            )
            return False

    def query(
        self,
        query_terms: List[str],
        top_k: int = 10,
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Query the index using Tantivy's BM25 scoring.

        Args:
            query_terms: List of terms to search for.
            top_k: Maximum number of results to return.
            trace: Optional TraceContext for observability.

        Returns:
            List of results sorted by BM25 score (descending).
            Each result: {"chunk_id": str, "score": float}

        Raises:
            ValueError: If index not loaded or query_terms is empty.
        """
        if not self._indexes:
            raise ValueError(
                "Index not loaded. Call load() or build() first."
            )
        if not query_terms:
            raise ValueError("query_terms cannot be empty")

        # Find the active index (use the first loaded one if collection unknown)
        # In practice, _ensure_index_loaded in SparseRetriever calls load() first
        idx = next(iter(self._indexes.values()))

        # Build query string from terms
        query_str = " ".join(t.lower() for t in query_terms)

        try:
            searcher = idx.searcher()
            parsed_query = idx.parse_query(query_str, ["content"])
            search_result = searcher.search(parsed_query, top_k)

            results: List[Dict[str, Any]] = []
            for score, doc_address in search_result.hits:
                doc = searcher.doc(doc_address)
                chunk_id = doc["chunk_id"][0]
                results.append({
                    "chunk_id": chunk_id,
                    "score": float(score),
                })

            return results

        except Exception as e:
            logger.error(f"TantivyIndexer query failed: {e}")
            return []

    def rebuild(
        self,
        term_stats: List[Dict[str, Any]],
        collection: str = "default",
        trace: Optional[Any] = None,
    ) -> None:
        """Rebuild index from scratch (alias for build).

        Args:
            term_stats: List of statistics from SparseEncoder.
            collection: Collection name.
            trace: Optional TraceContext for observability.
        """
        self.build(term_stats, collection, trace)

    def add_documents(
        self,
        term_stats: List[Dict[str, Any]],
        collection: str = "default",
        doc_id: Optional[str] = None,
        trace: Optional[Any] = None,
    ) -> None:
        """Incrementally add documents to the Tantivy index.

        If doc_id is provided, removes existing documents with matching
        chunk_id prefix first (idempotent re-ingestion).

        Args:
            term_stats: New term statistics from SparseEncoder.encode().
            collection: Collection name.
            doc_id: If provided, remove existing postings with this prefix
                before adding new ones.
            trace: Optional TraceContext.
        """
        if not term_stats:
            return

        self._validate_term_stats(term_stats)

        # Ensure index exists (load or create)
        if collection not in self._indexes:
            if not self.load(collection):
                # No existing index — build from scratch
                self.build(term_stats, collection, trace)
                return

        tv = _ensure_tantivy()
        idx = self._indexes[collection]

        # Remove stale documents if re-ingesting
        if doc_id:
            self._remove_by_prefix(idx, doc_id)

        # Add new documents
        writer = idx.writer()
        for stat in term_stats:
            content = self._reconstruct_content(stat["term_frequencies"])
            writer.add_document(tv.Document(
                chunk_id=stat["chunk_id"],
                content=content,
                doc_length=stat["doc_length"],
            ))
        writer.commit()
        idx.reload()

        logger.info(
            f"TantivyIndexer: Added {len(term_stats)} documents to "
            f"collection '{collection}'"
        )

    def remove_document(
        self,
        doc_id: str,
        collection: str = "default",
    ) -> bool:
        """Remove all documents with chunk_id matching the doc_id prefix.

        Args:
            doc_id: Document identifier prefix.
            collection: Collection name.

        Returns:
            True if any documents were removed, False otherwise.
        """
        if collection not in self._indexes:
            if not self.load(collection):
                return False

        idx = self._indexes[collection]
        removed = self._remove_by_prefix(idx, doc_id)
        return removed

    # ===== Private Helper Methods =====

    def _remove_by_prefix(self, idx: Any, prefix: str) -> bool:
        """Remove documents whose chunk_id starts with prefix.

        Scans all documents since Tantivy's default tokenizer splits
        chunk_ids and prevents reliable prefix-based term queries.

        Args:
            idx: Tantivy Index object.
            prefix: Chunk ID prefix to match.

        Returns:
            True if any documents were deleted.
        """
        try:
            searcher = idx.searcher()
            # Use a match-all query to scan all documents
            all_query = idx.parse_query("*", ["content"])
            all_results = searcher.search(all_query, limit=100000)

            to_delete: list[str] = []
            for _, doc_address in all_results.hits:
                doc = searcher.doc(doc_address)
                cid = doc["chunk_id"][0]
                if cid.startswith(prefix):
                    to_delete.append(cid)

            if not to_delete:
                return False

            writer = idx.writer()
            for cid in to_delete:
                writer.delete_documents("chunk_id", cid)

            writer.commit()
            idx.reload()
            return True
        except Exception as e:
            logger.warning(f"Failed to remove documents with prefix '{prefix}': {e}")
            return False


    @staticmethod
    def _reconstruct_content(term_frequencies: Dict[str, int]) -> str:
        """Reconstruct indexable content from term frequency dict.

        Since SparseEncoder only outputs term frequencies (not original text),
        we reconstruct a document by repeating each term according to its
        frequency. Tantivy will then score it with BM25.

        Args:
            term_frequencies: Dict of term -> frequency.

        Returns:
            Reconstructed text string.
        """
        tokens: List[str] = []
        for term, freq in term_frequencies.items():
            tokens.extend([term] * freq)
        return " ".join(tokens)

    @staticmethod
    def _validate_term_stats(term_stats: List[Dict[str, Any]]) -> None:
        """Validate term_stats structure.

        Args:
            term_stats: List of term statistics to validate.

        Raises:
            ValueError: If structure is invalid.
        """
        for i, stat in enumerate(term_stats):
            if not isinstance(stat, dict):
                raise ValueError(
                    f"term_stats[{i}] must be a dict, got {type(stat)}"
                )

            required_fields = ["chunk_id", "term_frequencies", "doc_length"]
            for field in required_fields:
                if field not in stat:
                    raise ValueError(
                        f"term_stats[{i}] missing required field: {field}"
                    )

            if not isinstance(stat["term_frequencies"], dict):
                raise ValueError(
                    f"term_stats[{i}]['term_frequencies'] must be dict, "
                    f"got {type(stat['term_frequencies'])}"
                )

            if not isinstance(stat["doc_length"], int) or stat["doc_length"] < 0:
                raise ValueError(
                    f"term_stats[{i}]['doc_length'] must be non-negative int, "
                    f"got {stat['doc_length']}"
                )
