"""Unit tests for BM25Indexer.

Tests cover:
- Index building from term statistics
- IDF calculation accuracy
- Query functionality with BM25 scoring
- Index persistence (save/load roundtrip)
- Rebuild and incremental update scenarios
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from src.ingestion.storage.bm25_indexer import BM25Indexer


class TestBM25IndexerBasics:
    """Test basic BM25Indexer functionality."""
    
    def test_indexer_initialization_default(self):
        """Test default initialization."""
        indexer = BM25Indexer()
        
        assert indexer.k1 == 1.5
        assert indexer.b == 0.75
        assert os.path.normpath(str(indexer.index_dir)) == os.path.normpath("data/db/bm25")
    
    def test_indexer_initialization_custom(self):
        """Test initialization with custom parameters."""
        indexer = BM25Indexer(
            index_dir="custom/path",
            k1=2.0,
            b=0.5
        )
        
        assert indexer.k1 == 2.0
        assert indexer.b == 0.5
        assert os.path.normpath(str(indexer.index_dir)) == os.path.normpath("custom/path")
    
    def test_indexer_initialization_invalid_k1(self):
        """Test that invalid k1 raises ValueError."""
        with pytest.raises(ValueError, match="k1 must be > 0"):
            BM25Indexer(k1=0)
        
        with pytest.raises(ValueError, match="k1 must be > 0"):
            BM25Indexer(k1=-1.0)
    
    def test_indexer_initialization_invalid_b(self):
        """Test that invalid b raises ValueError."""
        with pytest.raises(ValueError, match="b must be in"):
            BM25Indexer(b=-0.1)
        
        with pytest.raises(ValueError, match="b must be in"):
            BM25Indexer(b=1.5)


class TestBM25IndexBuilding:
    """Test index building functionality."""
    
    def test_build_simple_index(self, tmp_path):
        """Test building a simple index from term statistics."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {
                "chunk_id": "doc1",
                "term_frequencies": {"hello": 2, "world": 1},
                "doc_length": 3
            },
            {
                "chunk_id": "doc2",
                "term_frequencies": {"hello": 1, "python": 1},
                "doc_length": 2
            }
        ]
        
        indexer.build(term_stats, collection="test")
        
        # Check metadata
        assert indexer._metadata["num_docs"] == 2
        assert indexer._metadata["avg_doc_length"] == 2.5
        assert indexer._metadata["total_terms"] == 3  # hello, world, python
        
        # Check index structure
        assert "hello" in indexer._index
        assert "world" in indexer._index
        assert "python" in indexer._index
        
        # Check hello posting list (appears in both docs)
        hello_data = indexer._index["hello"]
        assert hello_data["df"] == 2
        assert len(hello_data["postings"]) == 2
    
    def test_build_empty_term_stats_raises(self, tmp_path):
        """Test that building with empty term_stats raises ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        with pytest.raises(ValueError, match="Cannot build index from empty"):
            indexer.build([])
    
    def test_build_invalid_structure_raises(self, tmp_path):
        """Test that invalid term_stats structure raises ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Missing chunk_id
        with pytest.raises(ValueError, match="missing required field: chunk_id"):
            indexer.build([{"term_frequencies": {}, "doc_length": 0}])
        
        # Missing term_frequencies
        with pytest.raises(ValueError, match="missing required field: term_frequencies"):
            indexer.build([{"chunk_id": "1", "doc_length": 0}])
        
        # Missing doc_length
        with pytest.raises(ValueError, match="missing required field: doc_length"):
            indexer.build([{"chunk_id": "1", "term_frequencies": {}}])
    
    def test_build_invalid_types_raises(self, tmp_path):
        """Test that invalid field types raise ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # term_frequencies not a dict
        with pytest.raises(ValueError, match="term_frequencies.*must be dict"):
            indexer.build([
                {"chunk_id": "1", "term_frequencies": "invalid", "doc_length": 0}
            ])
        
        # doc_length not an int
        with pytest.raises(ValueError, match="doc_length.*must be non-negative int"):
            indexer.build([
                {"chunk_id": "1", "term_frequencies": {}, "doc_length": "invalid"}
            ])
        
        # Negative doc_length
        with pytest.raises(ValueError, match="doc_length.*must be non-negative int"):
            indexer.build([
                {"chunk_id": "1", "term_frequencies": {}, "doc_length": -1}
            ])


class TestIDFCalculation:
    """Test IDF calculation accuracy."""
    
    def test_idf_calculation_formula(self, tmp_path):
        """Test that IDF is calculated correctly using BM25 formula.
        
        Formula: IDF(term) = log((N - df + 0.5) / (df + 0.5))
        """
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # N=3 docs, df=1 (term appears in 1 doc)
        # Expected IDF = log((3 - 1 + 0.5) / (1 + 0.5)) = log(2.5 / 1.5) = log(1.6667)
        import math
        expected_idf = math.log((3 - 1 + 0.5) / (1 + 0.5))
        
        actual_idf = indexer._calculate_idf(num_docs=3, df=1)
        
        assert abs(actual_idf - expected_idf) < 0.0001
    
    def test_idf_rare_vs_common_terms(self, tmp_path):
        """Test that rare terms have higher IDF than common terms."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "1", "term_frequencies": {"rare": 1, "common": 1}, "doc_length": 2},
            {"chunk_id": "2", "term_frequencies": {"common": 1}, "doc_length": 1},
            {"chunk_id": "3", "term_frequencies": {"common": 1}, "doc_length": 1},
        ]
        
        indexer.build(term_stats, collection="test")
        
        # "rare" appears in 1/3 docs, "common" appears in 3/3 docs
        rare_idf = indexer._index["rare"]["idf"]
        common_idf = indexer._index["common"]["idf"]
        
        # Rare terms should have higher IDF
        assert rare_idf > common_idf


class TestBM25Querying:
    """Test BM25 query functionality."""
    
    def test_query_returns_sorted_results(self, tmp_path):
        """Test that query returns results sorted by BM25 score."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Use a clearer scenario: one doc with query terms, others without
        term_stats = [
            {"chunk_id": "relevant", "term_frequencies": {"machine": 3, "learning": 2}, "doc_length": 5},
            {"chunk_id": "partial", "term_frequencies": {"machine": 1}, "doc_length": 3},
            {"chunk_id": "irrelevant", "term_frequencies": {"python": 2}, "doc_length": 2},
        ]
        
        indexer.build(term_stats, collection="test")
        
        results = indexer.query(["machine", "learning"], top_k=3)
        
        # Should return 2 results (relevant and partial contain query terms)
        assert len(results) == 2
        
        # Results should be sorted by score descending
        assert results[0]["score"] >= results[1]["score"]
        
        # "relevant" contains both terms, should rank first
        assert results[0]["chunk_id"] == "relevant"
        # "partial" contains only one term, should rank second
        assert results[1]["chunk_id"] == "partial"
    
    def test_query_respects_top_k(self, tmp_path):
        """Test that query respects top_k parameter."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": f"doc{i}", "term_frequencies": {"test": 1}, "doc_length": 1}
            for i in range(10)
        ]
        
        indexer.build(term_stats, collection="test")
        
        results = indexer.query(["test"], top_k=3)
        
        assert len(results) == 3
    
    def test_query_term_not_in_corpus(self, tmp_path):
        """Test querying for term not in corpus returns empty."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "doc1", "term_frequencies": {"hello": 1}, "doc_length": 1}
        ]
        
        indexer.build(term_stats, collection="test")
        
        results = indexer.query(["nonexistent"], top_k=10)
        
        assert len(results) == 0
    
    def test_query_before_build_raises(self):
        """Test that querying before build raises ValueError."""
        indexer = BM25Indexer()
        
        with pytest.raises(ValueError, match="Index not loaded"):
            indexer.query(["test"])
    
    def test_query_empty_terms_raises(self, tmp_path):
        """Test that querying with empty terms raises ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "doc1", "term_frequencies": {"test": 1}, "doc_length": 1}
        ]
        indexer.build(term_stats, collection="test")
        
        with pytest.raises(ValueError, match="query_terms cannot be empty"):
            indexer.query([])


class TestIndexPersistence:
    """Test index save/load functionality."""
    
    def test_save_and_load_roundtrip(self, tmp_path):
        """Test that saved index can be loaded and produces same results."""
        indexer1 = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "doc1", "term_frequencies": {"hello": 2, "world": 1}, "doc_length": 3},
            {"chunk_id": "doc2", "term_frequencies": {"hello": 1, "python": 1}, "doc_length": 2}
        ]
        
        indexer1.build(term_stats, collection="test")
        
        # Query with first indexer
        results1 = indexer1.query(["hello"], top_k=2)
        
        # Create new indexer and load
        indexer2 = BM25Indexer(index_dir=str(tmp_path))
        loaded = indexer2.load(collection="test")
        
        assert loaded is True
        
        # Query with loaded indexer
        results2 = indexer2.query(["hello"], top_k=2)
        
        # Results should be identical
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1["chunk_id"] == r2["chunk_id"]
            assert abs(r1["score"] - r2["score"]) < 0.0001
    
    def test_load_nonexistent_index(self, tmp_path):
        """Test loading non-existent index returns False."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        loaded = indexer.load(collection="nonexistent")
        
        assert loaded is False
    
    def test_load_corrupted_index_raises(self, tmp_path):
        """Test loading corrupted index raises ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Create corrupted index file
        index_path = tmp_path / "corrupted_bm25.json"
        index_path.write_text("not valid json{")
        
        with pytest.raises(ValueError, match="Corrupted index file"):
            indexer.load(collection="corrupted")
    
    def test_load_invalid_structure_raises(self, tmp_path):
        """Test loading index with invalid structure raises ValueError."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Create index file with missing fields
        index_path = tmp_path / "invalid_bm25.json"
        index_path.write_text(json.dumps({"metadata": {}}))  # Missing "index"
        
        with pytest.raises(ValueError, match="Invalid index file structure"):
            indexer.load(collection="invalid")
    
    def test_index_file_created_in_correct_location(self, tmp_path):
        """Test that index file is created in the correct directory."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "doc1", "term_frequencies": {"test": 1}, "doc_length": 1}
        ]
        
        indexer.build(term_stats, collection="my_collection")
        
        expected_path = tmp_path / "my_collection_bm25.json"
        assert expected_path.exists()
        
        # Verify it's valid JSON
        with open(expected_path) as f:
            data = json.load(f)
        
        assert "metadata" in data
        assert "index" in data


class TestRebuildFunctionality:
    """Test rebuild and update scenarios."""
    
    def test_rebuild_replaces_old_index(self, tmp_path):
        """Test that rebuild completely replaces old index."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Build initial index
        term_stats1 = [
            {"chunk_id": "doc1", "term_frequencies": {"old": 1}, "doc_length": 1}
        ]
        indexer.build(term_stats1, collection="test")
        
        # Rebuild with new data
        term_stats2 = [
            {"chunk_id": "doc2", "term_frequencies": {"new": 1}, "doc_length": 1}
        ]
        indexer.rebuild(term_stats2, collection="test")
        
        # Old term should not exist
        results_old = indexer.query(["old"], top_k=10)
        assert len(results_old) == 0
        
        # New term should exist
        results_new = indexer.query(["new"], top_k=10)
        assert len(results_new) == 1
        assert results_new[0]["chunk_id"] == "doc2"
    
    def test_rebuild_is_deterministic(self, tmp_path):
        """Test that rebuilding same data produces same index."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "doc1", "term_frequencies": {"test": 2}, "doc_length": 2},
            {"chunk_id": "doc2", "term_frequencies": {"test": 1}, "doc_length": 1}
        ]
        
        # Build twice
        indexer.build(term_stats, collection="test1")
        results1 = indexer.query(["test"], top_k=2)
        
        indexer.rebuild(term_stats, collection="test2")
        results2 = indexer.query(["test"], top_k=2)
        
        # Results should be identical
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1["chunk_id"] == r2["chunk_id"]
            assert abs(r1["score"] - r2["score"]) < 0.0001


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_document_corpus(self, tmp_path):
        """Test indexing and querying a single-document corpus.
        
        Note: In a single-document corpus where the term appears in all documents,
        IDF can be negative per BM25 formula: log((N - df + 0.5) / (df + 0.5))
        When N=1, df=1: log((1-1+0.5)/(1+0.5)) = log(0.5/1.5) = log(0.33) < 0
        This is expected behavior for BM25.
        """
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "only_doc", "term_frequencies": {"hello": 1}, "doc_length": 1}
        ]
        
        indexer.build(term_stats, collection="test")
        results = indexer.query(["hello"], top_k=1)
        
        assert len(results) == 1
        assert results[0]["chunk_id"] == "only_doc"
        # Score can be negative for single-document corpus (expected BM25 behavior)
        assert isinstance(results[0]["score"], float)
    
    def test_empty_document(self, tmp_path):
        """Test handling document with zero terms (edge case)."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {"chunk_id": "empty", "term_frequencies": {}, "doc_length": 0},
            {"chunk_id": "normal", "term_frequencies": {"test": 1}, "doc_length": 1}
        ]
        
        # Should not raise
        indexer.build(term_stats, collection="test")
        
        # Query should still work
        results = indexer.query(["test"], top_k=10)
        assert len(results) == 1
        assert results[0]["chunk_id"] == "normal"
    
    def test_very_long_posting_list(self, tmp_path):
        """Test handling term that appears in many documents."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        # Create 100 docs all containing "common"
        term_stats = [
            {"chunk_id": f"doc{i}", "term_frequencies": {"common": 1}, "doc_length": 1}
            for i in range(100)
        ]
        
        indexer.build(term_stats, collection="test")
        
        # Should handle large posting list
        assert indexer._index["common"]["df"] == 100
        assert len(indexer._index["common"]["postings"]) == 100
        
        # Query should work
        results = indexer.query(["common"], top_k=10)
        assert len(results) == 10  # Respects top_k
    
    def test_special_characters_in_terms(self, tmp_path):
        """Test handling terms with special characters."""
        indexer = BM25Indexer(index_dir=str(tmp_path))
        
        term_stats = [
            {
                "chunk_id": "doc1",
                "term_frequencies": {"hello-world": 1, "test_case": 1},
                "doc_length": 2
            }
        ]
        
        indexer.build(term_stats, collection="test")
        
        # Should be able to query with special characters
        results = indexer.query(["hello-world"], top_k=1)
        assert len(results) == 1
        
        results = indexer.query(["test_case"], top_k=1)
        assert len(results) == 1
