"""Unit tests for RagasEvaluator.

Tests verify:
- Initialization with valid/invalid metrics
- ImportError handling when ragas is not installed
- Input validation (missing answer, empty query, etc.)
- Metric extraction from settings
- Text extraction from various chunk formats

Note: Actual Ragas evaluation (LLM calls) is mocked to keep unit tests fast
and deterministic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any, Dict

import pytest


class TestRagasEvaluatorInit:
    """Tests for RagasEvaluator initialisation."""

    def test_init_default_metrics(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator()
        assert set(evaluator._metric_names) == {
            "answer_relevancy",
            "context_precision",
            "faithfulness",
        }

    def test_init_custom_metrics(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        assert evaluator._metric_names == ["faithfulness"]

    def test_init_unsupported_metric_raises(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        with pytest.raises(ValueError, match="Unsupported ragas metrics"):
            RagasEvaluator(metrics=["hit_rate"])

    def test_init_reads_metrics_from_settings(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        settings = MagicMock()
        settings.evaluation.metrics = ["faithfulness", "answer_relevancy", "hit_rate"]

        evaluator = RagasEvaluator(settings=settings)
        # hit_rate is not a ragas metric, should be filtered out
        assert "hit_rate" not in evaluator._metric_names
        assert "faithfulness" in evaluator._metric_names
        assert "answer_relevancy" in evaluator._metric_names

    def test_init_no_settings_defaults_to_all(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(settings=None, metrics=None)
        assert len(evaluator._metric_names) == 3


class TestRagasImportCheck:
    """Tests for ragas import validation."""

    def test_import_error_when_ragas_missing(self) -> None:
        from src.observability.evaluation.ragas_evaluator import _import_ragas

        with patch.dict("sys.modules", {"ragas": None}):
            with pytest.raises(ImportError, match="ragas"):
                _import_ragas()


class TestRagasEvaluatorValidation:
    """Tests for input validation in evaluate()."""

    def test_empty_query_raises(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        with pytest.raises(ValueError, match="Query cannot be empty"):
            evaluator.evaluate("  ", [{"text": "ctx"}], generated_answer="ans")

    def test_empty_chunks_raises(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        with pytest.raises(ValueError, match="retrieved_chunks cannot be empty"):
            evaluator.evaluate("query", [], generated_answer="ans")

    def test_missing_generated_answer_raises(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        with pytest.raises(ValueError, match="generated_answer"):
            evaluator.evaluate("query", [{"text": "ctx"}], generated_answer=None)

    def test_empty_generated_answer_raises(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        with pytest.raises(ValueError, match="generated_answer"):
            evaluator.evaluate("query", [{"text": "ctx"}], generated_answer="   ")


class TestRagasEvaluatorTextExtraction:
    """Tests for _extract_texts helper."""

    def test_extract_from_dicts(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        result = evaluator._extract_texts([
            {"text": "chunk1"},
            {"content": "chunk2"},
            {"page_content": "chunk3"},
        ])
        assert result == ["chunk1", "chunk2", "chunk3"]

    def test_extract_from_strings(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        result = evaluator._extract_texts(["chunk1", "chunk2"])
        assert result == ["chunk1", "chunk2"]

    def test_extract_from_objects(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])

        class Chunk:
            def __init__(self, text: str) -> None:
                self.text = text

        result = evaluator._extract_texts([Chunk("hello"), Chunk("world")])
        assert result == ["hello", "world"]


class TestRagasEvaluatorEvaluate:
    """Tests for evaluate() with mocked Ragas backend."""

    def _make_mock_ragas_result(self, scores: Dict[str, float]) -> MagicMock:
        """Create a mock ragas evaluation result."""
        import pandas as pd

        df = pd.DataFrame([scores])
        mock_result = MagicMock()
        mock_result.to_pandas.return_value = df
        return mock_result

    def test_evaluate_returns_metrics_dict(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness", "context_precision"])

        expected = {"faithfulness": 0.92, "context_precision": 0.85}
        evaluator._run_ragas = MagicMock(return_value=expected)  # type: ignore[method-assign]

        result = evaluator.evaluate(
            query="What is RAG?",
            retrieved_chunks=["RAG is retrieval augmented generation."],
            generated_answer="RAG stands for Retrieval Augmented Generation.",
        )

        assert result == expected

    def test_evaluate_with_mocked_run_ragas(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness", "answer_relevancy"])

        expected_scores = {"faithfulness": 0.95, "answer_relevancy": 0.88}
        evaluator._run_ragas = MagicMock(return_value=expected_scores)  # type: ignore[method-assign]

        result = evaluator.evaluate(
            query="What is RAG?",
            retrieved_chunks=[{"text": "RAG is Retrieval Augmented Generation"}],
            generated_answer="RAG stands for Retrieval Augmented Generation.",
        )

        assert result == expected_scores
        evaluator._run_ragas.assert_called_once()

    def test_evaluate_runtime_error_on_ragas_failure(self) -> None:
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        evaluator._run_ragas = MagicMock(  # type: ignore[method-assign]
            side_effect=Exception("LLM call failed"),
        )

        with pytest.raises(RuntimeError, match="Ragas evaluation failed"):
            evaluator.evaluate(
                query="test",
                retrieved_chunks=[{"text": "ctx"}],
                generated_answer="answer",
            )

    def test_ground_truth_is_ignored(self) -> None:
        """Ragas should work fine even when ground_truth is provided."""
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        evaluator = RagasEvaluator(metrics=["faithfulness"])
        evaluator._run_ragas = MagicMock(return_value={"faithfulness": 0.9})  # type: ignore[method-assign]

        result = evaluator.evaluate(
            query="test",
            retrieved_chunks=[{"text": "ctx"}],
            generated_answer="answer",
            ground_truth=["chunk_001"],  # should be ignored
        )

        assert "faithfulness" in result


class TestRagasEvaluatorFactory:
    """Tests for factory integration."""

    def test_factory_creates_ragas_evaluator(self) -> None:
        from src.libs.evaluator.evaluator_factory import EvaluatorFactory
        from src.observability.evaluation.ragas_evaluator import RagasEvaluator

        settings = MagicMock()
        settings.evaluation.enabled = True
        settings.evaluation.provider = "ragas"
        settings.evaluation.metrics = ["faithfulness"]

        evaluator = EvaluatorFactory.create(settings)
        assert isinstance(evaluator, RagasEvaluator)

    def test_factory_lists_ragas(self) -> None:
        from src.libs.evaluator.evaluator_factory import EvaluatorFactory

        providers = EvaluatorFactory.list_providers()
        assert "custom" in providers
        # ragas may be in _PROVIDERS after first create or in _LAZY_PROVIDERS
