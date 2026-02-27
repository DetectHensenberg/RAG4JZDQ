"""Unit tests for CompositeEvaluator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.libs.evaluator.base_evaluator import BaseEvaluator
from src.observability.evaluation.composite_evaluator import CompositeEvaluator


class FakeEvaluatorA(BaseEvaluator):
    """Fake evaluator returning fixed metrics."""

    def evaluate(
        self,
        query: str,
        retrieved_chunks: List[Any],
        generated_answer: Optional[str] = None,
        ground_truth: Optional[Any] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, float]:
        return {"hit_rate": 1.0, "mrr": 0.5}


class FakeEvaluatorB(BaseEvaluator):
    """Fake evaluator returning different metrics."""

    def evaluate(
        self,
        query: str,
        retrieved_chunks: List[Any],
        generated_answer: Optional[str] = None,
        ground_truth: Optional[Any] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, float]:
        return {"faithfulness": 0.92, "answer_relevancy": 0.88}


class FailingEvaluator(BaseEvaluator):
    """Evaluator that always raises."""

    def evaluate(
        self,
        query: str,
        retrieved_chunks: List[Any],
        generated_answer: Optional[str] = None,
        ground_truth: Optional[Any] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, float]:
        raise RuntimeError("I always fail")


class TestCompositeEvaluatorInit:
    """Tests for CompositeEvaluator initialisation."""

    def test_init_with_evaluators(self) -> None:
        composite = CompositeEvaluator(evaluators=[FakeEvaluatorA(), FakeEvaluatorB()])
        assert len(composite.evaluators) == 2

    def test_init_empty_evaluators_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one sub-evaluator"):
            CompositeEvaluator(evaluators=[])

    def test_init_no_evaluators_no_settings_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one sub-evaluator"):
            CompositeEvaluator(evaluators=None, settings=None)


class TestCompositeEvaluatorEvaluate:
    """Tests for evaluate() method."""

    def test_merge_metrics_from_two_evaluators(self) -> None:
        composite = CompositeEvaluator(evaluators=[FakeEvaluatorA(), FakeEvaluatorB()])

        metrics = composite.evaluate(
            query="test query",
            retrieved_chunks=[{"id": "c1"}],
            generated_answer="answer",
            ground_truth=["c1"],
        )

        assert metrics == {
            "hit_rate": 1.0,
            "mrr": 0.5,
            "faithfulness": 0.92,
            "answer_relevancy": 0.88,
        }

    def test_partial_failure_returns_successful_metrics(self) -> None:
        composite = CompositeEvaluator(
            evaluators=[FakeEvaluatorA(), FailingEvaluator()]
        )

        metrics = composite.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c1"}],
        )

        # FakeEvaluatorA succeeded, FailingEvaluator silently failed
        assert metrics == {"hit_rate": 1.0, "mrr": 0.5}

    def test_all_fail_raises_runtime_error(self) -> None:
        composite = CompositeEvaluator(evaluators=[FailingEvaluator()])

        with pytest.raises(RuntimeError, match="All sub-evaluators failed"):
            composite.evaluate(query="test", retrieved_chunks=[{"id": "c1"}])

    def test_duplicate_metric_key_last_wins(self) -> None:
        """When two evaluators produce the same key, the later one wins."""

        class EvalOverride(BaseEvaluator):
            def evaluate(self, query, retrieved_chunks, **kwargs):
                return {"hit_rate": 0.99}

        composite = CompositeEvaluator(
            evaluators=[FakeEvaluatorA(), EvalOverride()]
        )

        metrics = composite.evaluate(query="test", retrieved_chunks=[{"id": "c1"}])

        assert metrics["hit_rate"] == 0.99  # overridden
        assert metrics["mrr"] == 0.5  # from FakeEvaluatorA

    def test_validate_empty_query_raises(self) -> None:
        composite = CompositeEvaluator(evaluators=[FakeEvaluatorA()])

        with pytest.raises(ValueError, match="Query cannot be empty"):
            composite.evaluate(query="  ", retrieved_chunks=[{"id": "c1"}])

    def test_validate_empty_chunks_raises(self) -> None:
        composite = CompositeEvaluator(evaluators=[FakeEvaluatorA()])

        with pytest.raises(ValueError, match="retrieved_chunks cannot be empty"):
            composite.evaluate(query="test", retrieved_chunks=[])


class TestCompositeEvaluatorFactory:
    """Tests for factory integration."""

    def test_factory_creates_composite(self) -> None:
        from src.libs.evaluator.evaluator_factory import EvaluatorFactory

        settings = MagicMock()
        settings.evaluation.enabled = True
        settings.evaluation.provider = "composite"
        settings.evaluation.metrics = ["hit_rate", "mrr"]
        settings.evaluation.backends = ["custom"]

        evaluator = EvaluatorFactory.create(settings)
        assert isinstance(evaluator, CompositeEvaluator)

    def test_config_driven_with_custom_backend(self) -> None:
        settings = MagicMock()
        settings.evaluation.enabled = True
        settings.evaluation.provider = "composite"
        settings.evaluation.metrics = ["hit_rate", "mrr"]
        settings.evaluation.backends = ["custom"]

        composite = CompositeEvaluator(settings=settings)
        assert len(composite.evaluators) >= 1

        metrics = composite.evaluate(
            query="test",
            retrieved_chunks=[{"id": "c1"}],
            ground_truth=["c1"],
        )
        assert "hit_rate" in metrics
