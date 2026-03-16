"""Unit tests for CoreReranker._results_to_candidates.

Covers the incremental changes:
1. Filename stem is prepended to chunk text  → ``[stem] text``
2. Text is truncated to RERANK_MAX_TEXT_LEN (256 chars)
3. Metadata is copied, not mutated
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.core.types import RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    chunk_id: str = "c1",
    score: float = 0.5,
    source_path: str = "docs/report.pdf",
    text: str = "chunk text",
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=text,
        metadata={"source_path": source_path},
    )


def _build_reranker():
    """Build a CoreReranker with all dependencies mocked out."""
    with patch(
        "src.core.query_engine.reranker.CoreReranker.__init__",
        return_value=None,
    ):
        from src.core.query_engine.reranker import CoreReranker

        cr = CoreReranker.__new__(CoreReranker)
        cr.RERANK_MAX_TEXT_LEN = 256
        return cr


@pytest.fixture
def reranker():
    return _build_reranker()


# ===========================================================================
# Filename prepend
# ===========================================================================

class TestFilenamePrepend:
    """Source filename stem is prepended as ``[stem] text``."""

    def test_basic_prepend(self, reranker: object) -> None:
        results = [_make_result(source_path="docs/数据仓库-建模.pdf", text="内容")]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["text"].startswith("[数据仓库-建模]")

    def test_unix_path(self, reranker: object) -> None:
        results = [_make_result(source_path="/home/user/docs/report.pdf")]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["text"].startswith("[report]")

    def test_windows_path(self, reranker: object) -> None:
        results = [_make_result(source_path=r"D:\docs\数据仓库.pdf")]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["text"].startswith("[数据仓库]")

    def test_no_extension(self, reranker: object) -> None:
        results = [_make_result(source_path="docs/README")]
        cands = reranker._results_to_candidates(results)
        # No '.' in filename → stem is the whole filename
        assert cands[0]["text"].startswith("[README]")

    def test_empty_source_path(self, reranker: object) -> None:
        """No source_path → no prefix, raw text used."""
        results = [_make_result(source_path="", text="raw")]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["text"] == "raw"

    def test_missing_source_path_key(self, reranker: object) -> None:
        """If source_path key is absent, no prefix."""
        r = RetrievalResult(chunk_id="c1", score=0.5, text="raw", metadata={})
        cands = reranker._results_to_candidates([r])
        assert cands[0]["text"] == "raw"


# ===========================================================================
# Text truncation
# ===========================================================================

class TestTextTruncation:
    """Text (including prefix) is truncated to RERANK_MAX_TEXT_LEN."""

    def test_long_text_truncated(self, reranker: object) -> None:
        long_text = "A" * 500
        results = [_make_result(text=long_text)]
        cands = reranker._results_to_candidates(results)
        assert len(cands[0]["text"]) == 256

    def test_short_text_not_truncated(self, reranker: object) -> None:
        results = [_make_result(text="short")]
        cands = reranker._results_to_candidates(results)
        # "[report] short" < 256
        assert len(cands[0]["text"]) < 256

    def test_prefix_counts_toward_limit(self, reranker: object) -> None:
        """The [filename] prefix is part of the 256-char budget."""
        long_name = "A" * 100
        results = [_make_result(source_path=f"docs/{long_name}.pdf", text="B" * 300)]
        cands = reranker._results_to_candidates(results)
        assert len(cands[0]["text"]) == 256
        # Prefix is included
        assert cands[0]["text"].startswith(f"[{long_name}]")


# ===========================================================================
# Metadata and field preservation
# ===========================================================================

class TestCandidateFields:
    """Candidate dicts have correct id, score, metadata."""

    def test_id_preserved(self, reranker: object) -> None:
        results = [_make_result(chunk_id="my_chunk")]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["id"] == "my_chunk"

    def test_score_preserved(self, reranker: object) -> None:
        results = [_make_result(score=0.42)]
        cands = reranker._results_to_candidates(results)
        assert cands[0]["score"] == pytest.approx(0.42)

    def test_metadata_copied(self, reranker: object) -> None:
        """Metadata is a copy — mutating candidate doesn't affect original."""
        results = [_make_result()]
        cands = reranker._results_to_candidates(results)
        cands[0]["metadata"]["injected"] = True
        assert "injected" not in results[0].metadata

    def test_multiple_results(self, reranker: object) -> None:
        results = [
            _make_result(chunk_id="a", score=0.9, source_path="docs/a.pdf"),
            _make_result(chunk_id="b", score=0.5, source_path="docs/b.pdf"),
        ]
        cands = reranker._results_to_candidates(results)
        assert len(cands) == 2
        assert cands[0]["id"] == "a"
        assert cands[1]["id"] == "b"

    def test_empty_results(self, reranker: object) -> None:
        assert reranker._results_to_candidates([]) == []
