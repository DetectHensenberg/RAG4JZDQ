"""Unit tests for HybridSearch incremental features.

Covers three new pipeline steps added to HybridSearch:
1. _apply_filename_boost  — boost scores for filename-matching chunks
2. _diversify_by_source   — limit chunks per source document
3. _inject_title_matches  — guarantee title-matching docs appear in results

These methods are tested in isolation (no DB / network) by constructing
a minimal HybridSearch instance with mocked dependencies.
"""

from __future__ import annotations

from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.core.types import RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    chunk_id: str,
    score: float,
    source_path: str,
    text: str = "chunk text",
    extra_meta: Dict | None = None,
) -> RetrievalResult:
    meta = {"source_path": source_path}
    if extra_meta:
        meta.update(extra_meta)
    return RetrievalResult(chunk_id=chunk_id, score=score, text=text, metadata=meta)


def _build_hybrid_search():
    """Build a minimal HybridSearch with all dependencies mocked out."""
    with patch("src.core.query_engine.hybrid_search.HybridSearch.__init__", return_value=None):
        from src.core.query_engine.hybrid_search import HybridSearch
        hs = HybridSearch.__new__(HybridSearch)
        return hs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hs():
    """Return a lightweight HybridSearch instance for method testing."""
    return _build_hybrid_search()


@pytest.fixture
def mixed_results() -> List[RetrievalResult]:
    """10 results from 3 source files, some with '数据仓库' in filename."""
    return [
        _make_result("c1", 0.90, "docs/企业数据仓库体系.pptx"),
        _make_result("c2", 0.85, "docs/企业数据仓库体系.pptx"),
        _make_result("c3", 0.80, "docs/大数据湖项目.docx"),
        _make_result("c4", 0.75, "docs/大数据湖项目.docx"),
        _make_result("c5", 0.70, "docs/大数据湖项目.docx"),
        _make_result("c6", 0.65, "docs/数据仓库-数据建模过程.pdf"),
        _make_result("c7", 0.60, "docs/数据仓库-数据建模过程.pdf"),
        _make_result("c8", 0.55, "docs/AI中台.pptx"),
        _make_result("c9", 0.50, "docs/AI中台.pptx"),
        _make_result("c10", 0.45, "docs/AI中台.pptx"),
    ]


# ===========================================================================
# _apply_filename_boost
# ===========================================================================

class TestApplyFilenameBoost:
    """Tests for HybridSearch._apply_filename_boost."""

    def test_matching_chunks_score_multiplied(self, hs: object, mixed_results: list) -> None:
        """Chunks whose filename contains a query keyword get score * 1.5."""
        boosted = hs._apply_filename_boost(mixed_results, "数据仓库")
        for r in boosted:
            stem = r.metadata["source_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if "数据仓库" in stem:
                assert r.metadata.get("filename_boosted") is True
            else:
                assert "filename_boosted" not in r.metadata

    def test_boosted_score_value(self, hs: object) -> None:
        """Boosted score == original * boost_factor."""
        results = [_make_result("a", 0.5, "docs/数据仓库.pdf")]
        boosted = hs._apply_filename_boost(results, "数据仓库", boost_factor=2.0)
        assert boosted[0].score == pytest.approx(1.0)

    def test_results_sorted_after_boost(self, hs: object) -> None:
        """After boost, results are sorted descending by score."""
        results = [
            _make_result("a", 0.9, "docs/other.pdf"),
            _make_result("b", 0.5, "docs/数据仓库.pdf"),
        ]
        boosted = hs._apply_filename_boost(results, "数据仓库", boost_factor=2.0)
        scores = [r.score for r in boosted]
        assert scores == sorted(scores, reverse=True)

    def test_no_match_returns_same_order(self, hs: object, mixed_results: list) -> None:
        """When no filename matches, results are unchanged."""
        boosted = hs._apply_filename_boost(mixed_results, "量子计算")
        assert [r.chunk_id for r in boosted] == [r.chunk_id for r in mixed_results]

    def test_empty_results(self, hs: object) -> None:
        """Empty list in → empty list out."""
        assert hs._apply_filename_boost([], "数据仓库") == []

    def test_empty_query(self, hs: object, mixed_results: list) -> None:
        """Empty query returns results unchanged."""
        result = hs._apply_filename_boost(mixed_results, "")
        assert len(result) == len(mixed_results)

    def test_short_query_keyword(self, hs: object) -> None:
        """Single char keywords < 2 are ignored; whole query used as fallback."""
        results = [_make_result("a", 0.5, "docs/A.pdf")]
        boosted = hs._apply_filename_boost(results, "A")
        # 'A' < 2 chars, but fallback uses whole query
        assert len(boosted) == 1

    def test_windows_backslash_path(self, hs: object) -> None:
        """Filename extraction works with Windows backslash paths."""
        results = [_make_result("a", 0.5, r"D:\docs\数据仓库.pdf")]
        boosted = hs._apply_filename_boost(results, "数据仓库")
        assert boosted[0].metadata.get("filename_boosted") is True

    def test_custom_boost_factor(self, hs: object) -> None:
        """Custom boost_factor is applied correctly."""
        results = [_make_result("a", 1.0, "docs/数据仓库.pdf")]
        boosted = hs._apply_filename_boost(results, "数据仓库", boost_factor=3.0)
        assert boosted[0].score == pytest.approx(3.0)


# ===========================================================================
# _diversify_by_source
# ===========================================================================

class TestDiversifyBySource:
    """Tests for HybridSearch._diversify_by_source."""

    def test_limits_per_source(self, hs: object, mixed_results: list) -> None:
        """At most max_per_source chunks per source are kept."""
        diversified = hs._diversify_by_source(mixed_results, max_per_source=2)
        from collections import Counter
        counts = Counter(r.metadata["source_path"] for r in diversified)
        assert all(c <= 2 for c in counts.values())

    def test_preserves_score_order(self, hs: object, mixed_results: list) -> None:
        """Diversification preserves the original score ordering."""
        diversified = hs._diversify_by_source(mixed_results, max_per_source=1)
        scores = [r.score for r in diversified]
        assert scores == sorted(scores, reverse=True)

    def test_max_per_source_1(self, hs: object, mixed_results: list) -> None:
        """max_per_source=1 keeps exactly one chunk per source."""
        diversified = hs._diversify_by_source(mixed_results, max_per_source=1)
        sources = [r.metadata["source_path"] for r in diversified]
        assert len(sources) == len(set(sources))

    def test_no_reduction_needed(self, hs: object) -> None:
        """When all chunks are from distinct sources, nothing is removed."""
        results = [
            _make_result("a", 0.9, "docs/a.pdf"),
            _make_result("b", 0.8, "docs/b.pdf"),
        ]
        diversified = hs._diversify_by_source(results, max_per_source=2)
        assert len(diversified) == 2

    def test_empty_results(self, hs: object) -> None:
        assert hs._diversify_by_source([], max_per_source=2) == []

    def test_max_per_source_zero(self, hs: object, mixed_results: list) -> None:
        """max_per_source <= 0 returns input unchanged."""
        result = hs._diversify_by_source(mixed_results, max_per_source=0)
        assert result is mixed_results

    def test_result_count_reduced(self, hs: object, mixed_results: list) -> None:
        """With max_per_source=2, the 10 results (3 sources) shrink."""
        diversified = hs._diversify_by_source(mixed_results, max_per_source=2)
        # 4 sources * 2 = 8 max, but some sources have < 2 → total ≤ 8
        assert len(diversified) < len(mixed_results)


# ===========================================================================
# _inject_title_matches
# ===========================================================================

class TestInjectTitleMatches:
    """Tests for HybridSearch._inject_title_matches."""

    def test_missing_title_match_injected(self, hs: object) -> None:
        """A title-matching doc absent from results is injected."""
        results = [_make_result("c1", 0.9, "docs/other.pdf")]
        all_candidates = [
            _make_result("c1", 0.9, "docs/other.pdf"),
            _make_result("c2", 0.5, "docs/数据仓库.pdf"),
        ]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        ids = [r.chunk_id for r in injected]
        assert "c2" in ids

    def test_already_present_not_duplicated(self, hs: object) -> None:
        """If title-matching source is already in results, no duplicate."""
        results = [_make_result("c1", 0.9, "docs/数据仓库.pdf")]
        all_candidates = [_make_result("c1", 0.9, "docs/数据仓库.pdf")]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        assert len(injected) == 1

    def test_injected_appended_at_end(self, hs: object) -> None:
        """Injected chunks go after existing results."""
        results = [
            _make_result("c1", 0.9, "docs/a.pdf"),
            _make_result("c2", 0.8, "docs/b.pdf"),
        ]
        all_candidates = results + [_make_result("c3", 0.3, "docs/数据仓库.pdf")]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        assert injected[-1].chunk_id == "c3"
        assert len(injected) == 3

    def test_one_chunk_per_missing_source(self, hs: object) -> None:
        """At most 1 chunk injected per missing title-matching source."""
        results = [_make_result("c1", 0.9, "docs/a.pdf")]
        all_candidates = [
            _make_result("c1", 0.9, "docs/a.pdf"),
            _make_result("c2", 0.5, "docs/数据仓库.pdf"),
            _make_result("c3", 0.4, "docs/数据仓库.pdf"),  # same source, should not inject twice
        ]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        wh_chunks = [r for r in injected if "数据仓库" in r.metadata["source_path"]]
        assert len(wh_chunks) == 1

    def test_empty_query(self, hs: object) -> None:
        """Empty query returns results unchanged."""
        results = [_make_result("c1", 0.9, "docs/a.pdf")]
        assert hs._inject_title_matches(results, results, "") is results

    def test_empty_candidates(self, hs: object) -> None:
        """Empty candidate pool returns results unchanged."""
        results = [_make_result("c1", 0.9, "docs/a.pdf")]
        assert hs._inject_title_matches(results, [], "数据仓库") is results

    def test_windows_path(self, hs: object) -> None:
        """Injection works with Windows-style backslash paths."""
        results = [_make_result("c1", 0.9, r"D:\docs\other.pdf")]
        all_candidates = [
            _make_result("c1", 0.9, r"D:\docs\other.pdf"),
            _make_result("c2", 0.3, r"D:\docs\数据仓库-建模.pdf"),
        ]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        assert len(injected) == 2

    def test_multiple_missing_sources(self, hs: object) -> None:
        """Multiple title-matching sources are all injected."""
        results = [_make_result("c1", 0.9, "docs/other.pdf")]
        all_candidates = [
            _make_result("c1", 0.9, "docs/other.pdf"),
            _make_result("c2", 0.5, "docs/数据仓库A.pdf"),
            _make_result("c3", 0.4, "docs/数据仓库B.pdf"),
        ]
        injected = hs._inject_title_matches(results, all_candidates, "数据仓库")
        assert len(injected) == 3
