"""Evaluation runner for batch quality assessment.

EvalRunner reads a golden test set, runs HybridSearch for each test case,
optionally generates answers, then invokes the configured Evaluator(s) to
produce a structured evaluation report.

Design Principles:
- Config-Driven: Evaluator selected via settings.yaml.
- Observable: Produces EvalReport with per-query details.
- Decoupled: Works with any BaseEvaluator implementation.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.libs.evaluator.base_evaluator import BaseEvaluator

logger = logging.getLogger(__name__)


@dataclass
class GoldenTestCase:
    """A single evaluation test case from the golden test set.

    Attributes:
        query: The test query string.
        expected_chunk_ids: Ground-truth chunk IDs for IR metrics.
        expected_sources: Ground-truth source file names (optional).
        reference_answer: Reference answer text for LLM-as-Judge (optional).
    """

    query: str
    expected_chunk_ids: List[str] = field(default_factory=list)
    expected_sources: List[str] = field(default_factory=list)
    reference_answer: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GoldenTestCase:
        return cls(
            query=data["query"],
            expected_chunk_ids=data.get("expected_chunk_ids", []),
            expected_sources=data.get("expected_sources", []),
            reference_answer=data.get("reference_answer"),
        )


@dataclass
class QueryResult:
    """Result of evaluating a single test case.

    Attributes:
        query: The test query.
        retrieved_chunk_ids: IDs of chunks actually retrieved.
        generated_answer: The generated answer (if applicable).
        metrics: Evaluation metrics for this query.
        elapsed_ms: Time taken for retrieval + evaluation.
    """

    query: str
    retrieved_chunk_ids: List[str] = field(default_factory=list)
    generated_answer: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    elapsed_ms: float = 0.0


@dataclass
class EvalReport:
    """Aggregated evaluation report across all test cases.

    Attributes:
        query_results: Per-query evaluation results.
        aggregate_metrics: Averaged metrics across all queries.
        total_elapsed_ms: Total time for the entire evaluation.
        evaluator_name: Name of the evaluator used.
        test_set_path: Path to the golden test set file.
    """

    query_results: List[QueryResult] = field(default_factory=list)
    aggregate_metrics: Dict[str, float] = field(default_factory=dict)
    total_elapsed_ms: float = 0.0
    evaluator_name: str = ""
    test_set_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise report to dictionary."""
        return {
            "evaluator_name": self.evaluator_name,
            "test_set_path": self.test_set_path,
            "total_elapsed_ms": round(self.total_elapsed_ms, 1),
            "aggregate_metrics": {
                k: round(v, 4) for k, v in self.aggregate_metrics.items()
            },
            "query_count": len(self.query_results),
            "query_results": [
                {
                    "query": qr.query,
                    "retrieved_chunk_ids": qr.retrieved_chunk_ids,
                    "generated_answer": qr.generated_answer,
                    "metrics": {k: round(v, 4) for k, v in qr.metrics.items()},
                    "elapsed_ms": round(qr.elapsed_ms, 1),
                }
                for qr in self.query_results
            ],
        }


def load_test_set(path: str | Path) -> List[GoldenTestCase]:
    """Load golden test set from a JSON file.

    Args:
        path: Path to the golden test set JSON file.

    Returns:
        List of TestCase instances.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is invalid.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Golden test set not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "test_cases" not in data:
        raise ValueError(
            "Invalid golden test set format: missing 'test_cases' key."
        )

    return [GoldenTestCase.from_dict(tc) for tc in data["test_cases"]]


class EvalRunner:
    """Runs batch evaluation against a golden test set.

    This class orchestrates:
    1. Loading the golden test set
    2. Running HybridSearch for each query
    3. Optionally generating answers
    4. Invoking the evaluator to score each result
    5. Aggregating metrics into an EvalReport

    Example::

        runner = EvalRunner(
            settings=settings,
            hybrid_search=hybrid_search,
            evaluator=evaluator,
        )
        report = runner.run("tests/fixtures/golden_test_set.json")
        print(report.aggregate_metrics)
    """

    def __init__(
        self,
        settings: Any = None,
        hybrid_search: Any = None,
        evaluator: Optional[BaseEvaluator] = None,
        answer_generator: Any = None,
    ) -> None:
        """Initialize EvalRunner.

        Args:
            settings: Application settings.
            hybrid_search: HybridSearch instance for retrieval.
            evaluator: BaseEvaluator instance for scoring.
            answer_generator: Optional callable(query, chunks) -> str
                for generating answers. If None, a simple concatenation
                is used as a placeholder.
        """
        self.settings = settings
        self.hybrid_search = hybrid_search
        self.evaluator = evaluator
        self.answer_generator = answer_generator

    def run(
        self,
        test_set_path: str | Path,
        top_k: int = 10,
        collection: Optional[str] = None,
    ) -> EvalReport:
        """Run evaluation on the golden test set.

        Args:
            test_set_path: Path to golden_test_set.json.
            top_k: Number of chunks to retrieve per query.
            collection: Optional collection name filter.

        Returns:
            EvalReport with per-query and aggregate metrics.

        Raises:
            FileNotFoundError: If test set file doesn't exist.
            ValueError: If evaluator or hybrid_search is not set.
        """
        if self.evaluator is None:
            raise ValueError("EvalRunner requires an evaluator.")

        test_cases = load_test_set(test_set_path)
        if not test_cases:
            raise ValueError("Golden test set is empty.")

        logger.info(
            "Starting evaluation: %d test cases, evaluator=%s",
            len(test_cases),
            type(self.evaluator).__name__,
        )

        report = EvalReport(
            evaluator_name=type(self.evaluator).__name__,
            test_set_path=str(test_set_path),
        )

        t0 = time.monotonic()

        for idx, tc in enumerate(test_cases):
            logger.info("Evaluating [%d/%d]: %s", idx + 1, len(test_cases), tc.query[:60])
            qr = self._evaluate_single(tc, top_k=top_k, collection=collection)
            report.query_results.append(qr)

        report.total_elapsed_ms = (time.monotonic() - t0) * 1000.0
        report.aggregate_metrics = self._aggregate_metrics(report.query_results)

        logger.info(
            "Evaluation complete: %d queries, aggregate=%s",
            len(report.query_results),
            report.aggregate_metrics,
        )

        return report

    def _evaluate_single(
        self,
        test_case: GoldenTestCase,
        top_k: int = 10,
        collection: Optional[str] = None,
    ) -> QueryResult:
        """Evaluate a single test case.

        Args:
            test_case: The test case to evaluate.
            top_k: Number of results to retrieve.
            collection: Optional collection filter.

        Returns:
            QueryResult with metrics for this test case.
        """
        t0 = time.monotonic()
        qr = QueryResult(query=test_case.query)

        # Step 1: Retrieve chunks
        retrieved_chunks = self._retrieve(test_case.query, top_k, collection)
        qr.retrieved_chunk_ids = [
            self._get_chunk_id(c) for c in retrieved_chunks
        ]

        # Step 2: Generate answer (if generator available)
        answer = self._generate_answer(test_case.query, retrieved_chunks)
        qr.generated_answer = answer

        # Step 3: Build ground truth
        ground_truth = (
            {"ids": test_case.expected_chunk_ids}
            if test_case.expected_chunk_ids
            else None
        )

        # Step 4: Evaluate
        try:
            metrics = self.evaluator.evaluate(  # type: ignore[union-attr]
                query=test_case.query,
                retrieved_chunks=retrieved_chunks,
                generated_answer=answer,
                ground_truth=ground_truth,
            )
            qr.metrics = metrics
        except Exception as exc:
            logger.warning("Evaluation failed for '%s': %s", test_case.query[:40], exc)
            qr.metrics = {}

        qr.elapsed_ms = (time.monotonic() - t0) * 1000.0
        return qr

    def _retrieve(
        self,
        query: str,
        top_k: int,
        collection: Optional[str],
    ) -> List[Any]:
        """Retrieve chunks using HybridSearch.

        Falls back to an empty list if search is not configured.
        """
        if self.hybrid_search is None:
            logger.warning("No HybridSearch configured; returning empty results.")
            return []

        try:
            results = self.hybrid_search.search(
                query=query,
                top_k=top_k,
            )
            return results if isinstance(results, list) else results.results
        except Exception as exc:
            logger.warning("Retrieval failed for '%s': %s", query[:40], exc)
            return []

    def _generate_answer(self, query: str, chunks: List[Any]) -> str:
        """Generate an answer from retrieved chunks.

        If a custom answer_generator is provided, use it.
        Otherwise, concatenate chunk texts as a simple placeholder.
        """
        if self.answer_generator is not None:
            try:
                return self.answer_generator(query, chunks)
            except Exception as exc:
                logger.warning("Answer generation failed: %s", exc)

        # Fallback: concatenate chunk texts
        texts = []
        for c in chunks:
            if isinstance(c, str):
                texts.append(c)
            elif isinstance(c, dict):
                texts.append(c.get("text", str(c)))
            elif hasattr(c, "text"):
                texts.append(str(getattr(c, "text")))
            else:
                texts.append(str(c))

        return " ".join(texts[:5])  # first 5 chunks

    def _get_chunk_id(self, chunk: Any) -> str:
        """Extract chunk ID from various representations."""
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            for key in ("id", "chunk_id"):
                if key in chunk:
                    return str(chunk[key])
            return str(chunk)
        if hasattr(chunk, "chunk_id"):
            return str(getattr(chunk, "chunk_id"))
        if hasattr(chunk, "id"):
            return str(getattr(chunk, "id"))
        return str(chunk)

    @staticmethod
    def _aggregate_metrics(results: List[QueryResult]) -> Dict[str, float]:
        """Compute average metrics across all query results.

        Args:
            results: List of QueryResult with per-query metrics.

        Returns:
            Dictionary of average metric values.
        """
        if not results:
            return {}

        # Collect all metric keys
        all_keys: set[str] = set()
        for qr in results:
            all_keys.update(qr.metrics.keys())

        # Average each metric
        averages: Dict[str, float] = {}
        for key in sorted(all_keys):
            values = [qr.metrics[key] for qr in results if key in qr.metrics]
            averages[key] = sum(values) / len(values) if values else 0.0

        return averages
