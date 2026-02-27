"""Unit tests for CustomEvaluator and EvaluatorFactory."""

from unittest.mock import MagicMock

import pytest

from src.libs.evaluator.base_evaluator import NoneEvaluator
from src.libs.evaluator.custom_evaluator import CustomEvaluator
from src.libs.evaluator.evaluator_factory import EvaluatorFactory


class TestCustomEvaluator:
    """Tests for CustomEvaluator metrics computation."""

    def test_hit_rate_and_mrr_success(self) -> None:
        evaluator = CustomEvaluator(metrics=["hit_rate", "mrr"])
        retrieved = [
            {"id": "c1"},
            {"id": "c2"},
            {"id": "c3"},
        ]
        ground_truth = ["c2", "c9"]

        metrics = evaluator.evaluate("query", retrieved, ground_truth=ground_truth)

        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 0.5

    def test_hit_rate_and_mrr_no_hit(self) -> None:
        evaluator = CustomEvaluator(metrics=["hit_rate", "mrr"])
        retrieved = [{"id": "a"}, {"id": "b"}]
        ground_truth = ["x", "y"]

        metrics = evaluator.evaluate("query", retrieved, ground_truth=ground_truth)

        assert metrics["hit_rate"] == 0.0
        assert metrics["mrr"] == 0.0

    def test_validate_query_and_retrieved(self) -> None:
        evaluator = CustomEvaluator(metrics=["hit_rate"])

        with pytest.raises(ValueError, match="Query cannot be empty"):
            evaluator.evaluate("  ", [{"id": "x"}], ground_truth=["x"])

        with pytest.raises(ValueError, match="retrieved_chunks cannot be empty"):
            evaluator.evaluate("query", [], ground_truth=["x"])

    def test_unsupported_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported custom metrics"):
            CustomEvaluator(metrics=["faithfulness"])  # not supported in custom evaluator


class TestEvaluatorFactory:
    """Tests for EvaluatorFactory."""

    def setup_method(self) -> None:
        EvaluatorFactory._PROVIDERS = {"custom": CustomEvaluator}

    def test_create_custom_evaluator(self) -> None:
        settings = MagicMock()
        settings.evaluation.enabled = True
        settings.evaluation.provider = "custom"
        settings.evaluation.metrics = ["hit_rate", "mrr"]

        evaluator = EvaluatorFactory.create(settings)

        assert isinstance(evaluator, CustomEvaluator)

    def test_create_disabled_returns_none_evaluator(self) -> None:
        settings = MagicMock()
        settings.evaluation.enabled = False
        settings.evaluation.provider = "custom"
        settings.evaluation.metrics = ["hit_rate"]

        evaluator = EvaluatorFactory.create(settings)

        assert isinstance(evaluator, NoneEvaluator)

    def test_create_unknown_provider_raises(self) -> None:
        settings = MagicMock()
        settings.evaluation.enabled = True
        settings.evaluation.provider = "unknown"
        settings.evaluation.metrics = ["hit_rate"]

        with pytest.raises(ValueError, match="Unsupported Evaluator provider"):
            EvaluatorFactory.create(settings)

    def test_register_provider_success(self) -> None:
        class FakeEvaluator(CustomEvaluator):
            pass

        EvaluatorFactory.register_provider("fake", FakeEvaluator)

        assert "fake" in EvaluatorFactory._PROVIDERS
        assert EvaluatorFactory._PROVIDERS["fake"] is FakeEvaluator

    def test_list_providers_sorted(self) -> None:
        class AlphaEvaluator(CustomEvaluator):
            pass

        class BetaEvaluator(CustomEvaluator):
            pass

        EvaluatorFactory.register_provider("beta", BetaEvaluator)
        EvaluatorFactory.register_provider("alpha", AlphaEvaluator)

        assert EvaluatorFactory.list_providers() == ["alpha", "beta", "custom"]


# ── Boundary / Contract tests (I4) ──────────────────────────────────

class TestCustomEvaluatorBoundary:
    """Boundary tests for CustomEvaluator."""

    def test_hit_rate_first_position(self) -> None:
        """Hit at position 1 should give MRR = 1.0."""
        evaluator = CustomEvaluator(metrics=["hit_rate", "mrr"])
        retrieved = [{"id": "target"}, {"id": "other"}]
        metrics = evaluator.evaluate("q", retrieved, ground_truth=["target"])
        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 1.0

    def test_hit_rate_last_position(self) -> None:
        """Hit at last position should give MRR = 1/n."""
        evaluator = CustomEvaluator(metrics=["mrr"])
        retrieved = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "target"}]
        metrics = evaluator.evaluate("q", retrieved, ground_truth=["target"])
        assert metrics["mrr"] == pytest.approx(0.25)

    def test_single_retrieved_single_ground_truth_match(self) -> None:
        """Minimal case: 1 retrieved, 1 ground_truth, match."""
        evaluator = CustomEvaluator(metrics=["hit_rate", "mrr"])
        metrics = evaluator.evaluate("q", [{"id": "x"}], ground_truth=["x"])
        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 1.0

    def test_single_retrieved_single_ground_truth_no_match(self) -> None:
        """Minimal case: 1 retrieved, 1 ground_truth, no match."""
        evaluator = CustomEvaluator(metrics=["hit_rate", "mrr"])
        metrics = evaluator.evaluate("q", [{"id": "a"}], ground_truth=["b"])
        assert metrics["hit_rate"] == 0.0
        assert metrics["mrr"] == 0.0

    def test_multiple_ground_truth_best_mrr(self) -> None:
        """MRR should use the best (earliest) matching position."""
        evaluator = CustomEvaluator(metrics=["mrr"])
        retrieved = [{"id": "a"}, {"id": "gt1"}, {"id": "gt2"}]
        metrics = evaluator.evaluate("q", retrieved, ground_truth=["gt1", "gt2"])
        assert metrics["mrr"] == 0.5  # gt1 at position 2 → 1/2

    def test_none_evaluator_returns_empty_dict(self) -> None:
        """NoneEvaluator should return empty metrics dict."""
        evaluator = NoneEvaluator()
        metrics = evaluator.evaluate("q", [{"id": "x"}])
        assert metrics == {}

    def test_none_evaluator_validates_inputs(self) -> None:
        """NoneEvaluator should still validate query and chunks."""
        evaluator = NoneEvaluator()
        with pytest.raises(ValueError):
            evaluator.evaluate("", [{"id": "x"}])
        with pytest.raises(ValueError):
            evaluator.evaluate("q", [])