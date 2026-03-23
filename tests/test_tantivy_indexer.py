"""Unit tests for TantivyIndexer.

Tests cover:
- T1: Schema construction and initialization
- T2: build() and query() core functionality
- T3: add_documents() and remove_document() incremental ops
- T5: Migration script compatibility
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.ingestion.storage.tantivy_indexer import TantivyIndexer


@pytest.fixture
def tmp_index_dir() -> str:
    """Create a temporary directory for test indexes.

    Yields:
        Path to temp directory (cleaned up after test).
    """
    d = tempfile.mkdtemp(prefix="tantivy_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_term_stats() -> List[Dict[str, Any]]:
    """Sample term statistics for testing.

    Returns:
        List of term_stats dicts mimicking SparseEncoder output.
    """
    return [
        {
            "chunk_id": "doc1_chunk0",
            "term_frequencies": {"机器": 3, "学习": 2, "算法": 1},
            "doc_length": 6,
        },
        {
            "chunk_id": "doc1_chunk1",
            "term_frequencies": {"深度": 2, "学习": 1, "神经": 3, "网络": 2},
            "doc_length": 8,
        },
        {
            "chunk_id": "doc2_chunk0",
            "term_frequencies": {"自然": 2, "语言": 2, "处理": 1, "机器": 1},
            "doc_length": 6,
        },
    ]


class TestTantivyIndexerInit:
    """T1: Schema construction and initialization tests."""

    def test_init_default_params(self, tmp_index_dir: str) -> None:
        """Test default initialization."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        assert indexer.k1 == 1.5
        assert indexer.b == 0.75
        assert indexer.index_dir == Path(tmp_index_dir)

    def test_init_custom_params(self, tmp_index_dir: str) -> None:
        """Test initialization with custom BM25 parameters."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir, k1=2.0, b=0.5)
        assert indexer.k1 == 2.0
        assert indexer.b == 0.5

    def test_init_invalid_k1(self, tmp_index_dir: str) -> None:
        """Test that invalid k1 raises ValueError."""
        with pytest.raises(ValueError, match="k1 must be > 0"):
            TantivyIndexer(index_dir=tmp_index_dir, k1=-1.0)

    def test_init_invalid_b(self, tmp_index_dir: str) -> None:
        """Test that invalid b raises ValueError."""
        with pytest.raises(ValueError, match="b must be in"):
            TantivyIndexer(index_dir=tmp_index_dir, b=1.5)


class TestTantivyBuildAndQuery:
    """T2: build() and query() core functionality tests."""

    def test_build_creates_index(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test that build creates an index on disk."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        idx_path = Path(tmp_index_dir) / "test"
        assert idx_path.exists()
        assert (idx_path / "meta.json").exists()

    def test_build_empty_raises(self, tmp_index_dir: str) -> None:
        """Test that build with empty term_stats raises ValueError."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        with pytest.raises(ValueError, match="empty"):
            indexer.build([], collection="test")

    def test_query_returns_results(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test that query returns scored results."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        results = indexer.query(["学习"], top_k=5)
        assert len(results) > 0
        assert all("chunk_id" in r and "score" in r for r in results)

    def test_query_scores_descending(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test that query results are sorted by score descending."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        results = indexer.query(["机器", "学习"], top_k=5)
        if len(results) >= 2:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_query_top_k_limit(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test that top_k limits number of results."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        results = indexer.query(["学习"], top_k=1)
        assert len(results) <= 1

    def test_query_no_match(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test query with terms not in index returns empty."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        results = indexer.query(["zzz_nonexistent_term_zzz"], top_k=5)
        assert len(results) == 0

    def test_query_empty_terms_raises(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test that empty query terms raises ValueError."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="test")

        with pytest.raises(ValueError, match="empty"):
            indexer.query([], top_k=5)


class TestTantivyLoadAndPersist:
    """T2 continued: load() and persistence tests."""

    def test_load_existing_index(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test loading a previously built index."""
        # Build with one instance
        indexer1 = TantivyIndexer(index_dir=tmp_index_dir)
        indexer1.build(sample_term_stats, collection="persist_test")

        # Load with a fresh instance
        indexer2 = TantivyIndexer(index_dir=tmp_index_dir)
        loaded = indexer2.load(collection="persist_test")
        assert loaded is True

        results = indexer2.query(["学习"], top_k=5)
        assert len(results) > 0

    def test_load_nonexistent_returns_false(self, tmp_index_dir: str) -> None:
        """Test that loading missing index returns False."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        assert indexer.load("nonexistent") is False


class TestTantivyIncremental:
    """T3: add_documents() and remove_document() tests."""

    def test_add_documents_to_existing(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test adding documents to an existing index."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats[:2], collection="incr")

        new_stats = [sample_term_stats[2]]
        indexer.add_documents(new_stats, collection="incr")

        results = indexer.query(["自然", "语言"], top_k=5)
        chunk_ids = [r["chunk_id"] for r in results]
        assert "doc2_chunk0" in chunk_ids

    def test_add_documents_creates_new_if_missing(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test add_documents creates index when none exists."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.add_documents(sample_term_stats, collection="new_coll")

        results = indexer.query(["机器"], top_k=5)
        assert len(results) > 0

    def test_remove_document(
        self, tmp_index_dir: str, sample_term_stats: List[Dict[str, Any]]
    ) -> None:
        """Test removing documents by prefix."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        indexer.build(sample_term_stats, collection="rm_test")

        # Verify doc1_chunk0 exists
        pre = indexer.query(["机器"], top_k=10)
        pre_ids = [r["chunk_id"] for r in pre]
        assert "doc1_chunk0" in pre_ids

        # Remove by prefix
        removed = indexer.remove_document("doc1_chunk0", collection="rm_test")
        assert removed is True

        # Verify doc1_chunk0 is gone
        post = indexer.query(["机器"], top_k=10)
        post_ids = [r["chunk_id"] for r in post]
        assert "doc1_chunk0" not in post_ids


class TestTantivyValidation:
    """Input validation tests."""

    def test_invalid_term_stats_missing_field(self, tmp_index_dir: str) -> None:
        """Test that missing required fields in term_stats raises error."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        with pytest.raises(ValueError, match="missing required field"):
            indexer.build([{"chunk_id": "x"}], collection="test")

    def test_invalid_term_stats_bad_type(self, tmp_index_dir: str) -> None:
        """Test that non-dict term_stats raises error."""
        indexer = TantivyIndexer(index_dir=tmp_index_dir)
        with pytest.raises(ValueError, match="must be a dict"):
            indexer.build(["not_a_dict"], collection="test")  # type: ignore
