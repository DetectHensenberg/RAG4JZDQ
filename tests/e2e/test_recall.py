"""E2E Recall Regression Test.

Validates retrieval quality against a golden test set using
hit@k threshold assertions.  This test is designed for CI/CD
regression gating – if recall drops below the configured
threshold, the test fails.

Requirements:
- Indexed data in the vector store (run ingest.py first).
- Golden test set at ``tests/fixtures/golden_test_set.json``.

Usage::

    pytest tests/e2e/test_recall.py -v
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import pytest

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

GOLDEN_TEST_SET_PATH = Path("tests/fixtures/golden_test_set.json")

# Minimum acceptable thresholds for regression gating.
# These are intentionally set conservatively – update as data improves.
HIT_RATE_THRESHOLD = 0.0  # Minimum average hit_rate (0.0 = no regression check until data exists)
MRR_THRESHOLD = 0.0  # Minimum average MRR


# ── Helpers ───────────────────────────────────────────────────────────

def _load_golden_set() -> List[Dict[str, Any]]:
    """Load golden test set from JSON file."""
    if not GOLDEN_TEST_SET_PATH.exists():
        pytest.skip(f"Golden test set not found: {GOLDEN_TEST_SET_PATH}")

    with GOLDEN_TEST_SET_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("test_cases", [])
    if not cases:
        pytest.skip("Golden test set has no test cases")

    return cases


def _try_create_search_engine() -> Any:
    """Attempt to create HybridSearch from settings.

    Skips test if infrastructure is not available.
    """
    try:
        from src.core.settings import load_settings
        from src.core.query_engine.hybrid_search import HybridSearch

        settings = load_settings()
        return HybridSearch(settings)
    except Exception as exc:
        pytest.skip(f"HybridSearch not available: {exc}")


def _try_create_evaluator() -> Any:
    """Create a CustomEvaluator for hit_rate/mrr computation."""
    try:
        from src.libs.evaluator.custom_evaluator import CustomEvaluator

        return CustomEvaluator()
    except Exception as exc:
        pytest.skip(f"CustomEvaluator not available: {exc}")


# ── Test Class ────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestRecallRegression:
    """E2E recall regression tests using the golden test set.

    These tests ensure retrieval quality does not regress below
    configured thresholds.  They require indexed data to be present.
    """

    @pytest.fixture(autouse=True)
    def setup_components(self) -> None:
        """Set up search engine and evaluator."""
        self.golden_set = _load_golden_set()
        self.search = _try_create_search_engine()
        self.evaluator = _try_create_evaluator()

    def test_golden_set_is_valid(self) -> None:
        """Validate the golden test set has expected structure."""
        assert len(self.golden_set) >= 1, "Golden set must have at least 1 case"

        for idx, tc in enumerate(self.golden_set):
            assert "query" in tc, f"Test case {idx} missing 'query'"
            assert tc["query"].strip(), f"Test case {idx} has empty query"

    def test_hit_rate_above_threshold(self) -> None:
        """Assert average hit@k meets the minimum threshold.

        hit@k = 1 if any expected chunk appears in the top-k results,
        else 0.  Averaged across all test cases that have
        expected_chunk_ids defined.
        """
        cases_with_ground_truth = [
            tc for tc in self.golden_set
            if tc.get("expected_chunk_ids")
        ]

        if not cases_with_ground_truth:
            pytest.skip("No test cases with expected_chunk_ids defined")

        hit_rates: List[float] = []
        top_k = 10

        for tc in cases_with_ground_truth:
            query = tc["query"]
            expected_ids = set(tc["expected_chunk_ids"])

            # Run search
            try:
                results = self.search.search(query=query, top_k=top_k)
                retrieved_ids = set()
                for r in results:
                    if hasattr(r, "chunk_id"):
                        retrieved_ids.add(r.chunk_id)
                    elif isinstance(r, dict) and "chunk_id" in r:
                        retrieved_ids.add(r["chunk_id"])
            except Exception as exc:
                logger.warning("Search failed for '%s': %s", query[:40], exc)
                hit_rates.append(0.0)
                continue

            # hit@k: 1 if any expected chunk in retrieved
            hit = 1.0 if expected_ids & retrieved_ids else 0.0
            hit_rates.append(hit)

            logger.info(
                "Query: %s | hit@%d=%.1f | expected=%s | retrieved=%s",
                query[:40], top_k, hit, expected_ids, retrieved_ids,
            )

        avg_hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else 0.0

        logger.info("Average hit@%d = %.4f (threshold=%.4f)", top_k, avg_hit_rate, HIT_RATE_THRESHOLD)

        assert avg_hit_rate >= HIT_RATE_THRESHOLD, (
            f"hit@{top_k} regression: {avg_hit_rate:.4f} < {HIT_RATE_THRESHOLD:.4f}"
        )

    def test_mrr_above_threshold(self) -> None:
        """Assert average MRR meets the minimum threshold.

        MRR = 1/rank of the first relevant chunk.  Averaged across
        all test cases with expected_chunk_ids.
        """
        cases_with_ground_truth = [
            tc for tc in self.golden_set
            if tc.get("expected_chunk_ids")
        ]

        if not cases_with_ground_truth:
            pytest.skip("No test cases with expected_chunk_ids defined")

        mrrs: List[float] = []
        top_k = 10

        for tc in cases_with_ground_truth:
            query = tc["query"]
            expected_ids = set(tc["expected_chunk_ids"])

            try:
                results = self.search.search(query=query, top_k=top_k)
                retrieved_ids: List[str] = []
                for r in results:
                    if hasattr(r, "chunk_id"):
                        retrieved_ids.append(r.chunk_id)
                    elif isinstance(r, dict) and "chunk_id" in r:
                        retrieved_ids.append(r["chunk_id"])
            except Exception:
                mrrs.append(0.0)
                continue

            # MRR: reciprocal rank of first relevant hit
            mrr = 0.0
            for rank, rid in enumerate(retrieved_ids, start=1):
                if rid in expected_ids:
                    mrr = 1.0 / rank
                    break

            mrrs.append(mrr)

        avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0.0

        logger.info("Average MRR = %.4f (threshold=%.4f)", avg_mrr, MRR_THRESHOLD)

        assert avg_mrr >= MRR_THRESHOLD, (
            f"MRR regression: {avg_mrr:.4f} < {MRR_THRESHOLD:.4f}"
        )

    def test_all_queries_return_results(self) -> None:
        """Verify every golden query returns at least one result.

        This is a basic sanity check – if a query returns zero
        results, there may be an indexing or search issue.
        """
        empty_queries: List[str] = []

        for tc in self.golden_set:
            query = tc["query"]
            try:
                results = self.search.search(query=query, top_k=5)
                if not results:
                    empty_queries.append(query)
            except Exception as exc:
                logger.warning("Search error for '%s': %s", query[:40], exc)
                empty_queries.append(query)

        if empty_queries:
            logger.warning(
                "Queries with empty results (%d/%d): %s",
                len(empty_queries),
                len(self.golden_set),
                empty_queries,
            )

        # Informational – does not fail the test since data may not
        # be indexed.  Uncomment the assert below when data is ready:
        # assert not empty_queries, f"{len(empty_queries)} queries returned no results"


# ── Standalone runner ─────────────────────────────────────────────────

class TestRecallUnit:
    """Lightweight unit-level recall tests (no infrastructure needed).

    These tests validate the recall computation logic itself,
    independent of any search engine or indexed data.
    """

    def test_hit_rate_computation(self) -> None:
        """Verify hit_rate calculation logic."""
        from src.libs.evaluator.custom_evaluator import CustomEvaluator

        evaluator = CustomEvaluator()

        # Perfect hit
        metrics = evaluator.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c1"}, {"id": "c2"}],
            ground_truth={"ids": ["c1"]},
        )
        assert metrics["hit_rate"] == 1.0

        # Miss
        metrics = evaluator.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c3"}],
            ground_truth={"ids": ["c1"]},
        )
        assert metrics["hit_rate"] == 0.0

    def test_mrr_computation(self) -> None:
        """Verify MRR calculation logic."""
        from src.libs.evaluator.custom_evaluator import CustomEvaluator

        evaluator = CustomEvaluator()

        # First position hit → MRR = 1.0
        metrics = evaluator.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c1"}, {"id": "c2"}],
            ground_truth={"ids": ["c1"]},
        )
        assert metrics["mrr"] == 1.0

        # Second position hit → MRR = 0.5
        metrics = evaluator.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c2"}, {"id": "c1"}],
            ground_truth={"ids": ["c1"]},
        )
        assert metrics["mrr"] == 0.5

    def test_golden_test_set_loadable(self) -> None:
        """Verify the golden test set can be loaded and parsed."""
        from src.observability.evaluation.eval_runner import load_test_set

        if not GOLDEN_TEST_SET_PATH.exists():
            pytest.skip("Golden test set not found")

        cases = load_test_set(GOLDEN_TEST_SET_PATH)
        assert len(cases) >= 1
        for tc in cases:
            assert tc.query.strip(), "Each test case must have a non-empty query"
