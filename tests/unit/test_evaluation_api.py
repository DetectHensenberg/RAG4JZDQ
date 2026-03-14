"""Unit tests for the rewritten Evaluation API (RAGAS integration).

Tests cover:
- Request model validation (EvalCase, EvalRunRequest)
- Helper functions (_build_context_text, _create_ragas_evaluator)
- Endpoint logic with mocked search/llm/evaluator
- Error handling (ImportError, evaluation failure, LLM failure)
- Aggregation logic
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------

class TestEvalCaseModel:
    """Tests for EvalCase Pydantic model."""

    def test_minimal_case(self) -> None:
        from api.routers.evaluation import EvalCase

        case = EvalCase(question="What is RAG?")
        assert case.question == "What is RAG?"
        assert case.ground_truth is None

    def test_case_with_ground_truth(self) -> None:
        from api.routers.evaluation import EvalCase

        case = EvalCase(question="Q?", ground_truth="A.")
        assert case.ground_truth == "A."

    def test_case_requires_question(self) -> None:
        from api.routers.evaluation import EvalCase
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EvalCase()  # type: ignore[call-arg]


class TestEvalRunRequestModel:
    """Tests for EvalRunRequest Pydantic model."""

    def test_defaults(self) -> None:
        from api.routers.evaluation import EvalRunRequest, EvalCase

        req = EvalRunRequest(cases=[EvalCase(question="Q?")])
        assert req.collection == "default"
        assert req.top_k == 5
        assert req.max_tokens == 2048

    def test_custom_values(self) -> None:
        from api.routers.evaluation import EvalRunRequest, EvalCase

        req = EvalRunRequest(
            cases=[EvalCase(question="Q?")],
            collection="my_col",
            top_k=10,
            max_tokens=512,
        )
        assert req.collection == "my_col"
        assert req.top_k == 10
        assert req.max_tokens == 512

    def test_multiple_cases(self) -> None:
        from api.routers.evaluation import EvalRunRequest, EvalCase

        req = EvalRunRequest(
            cases=[
                EvalCase(question="Q1"),
                EvalCase(question="Q2", ground_truth="A2"),
            ]
        )
        assert len(req.cases) == 2
        assert req.cases[1].ground_truth == "A2"

    def test_requires_cases(self) -> None:
        from api.routers.evaluation import EvalRunRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EvalRunRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestBuildContextText:
    """Tests for _build_context_text helper."""

    def test_builds_numbered_text(self) -> None:
        from api.routers.evaluation import _build_context_text

        r1 = MagicMock()
        r1.text = "First chunk content"
        r2 = MagicMock()
        r2.text = "Second chunk content"

        result = _build_context_text([r1, r2])
        assert "[1] First chunk content" in result
        assert "[2] Second chunk content" in result

    def test_truncates_long_text(self) -> None:
        from api.routers.evaluation import _build_context_text

        r = MagicMock()
        r.text = "x" * 1000
        result = _build_context_text([r])
        # Should truncate to 500 chars
        assert len(result.split("] ")[1]) == 500

    def test_empty_list(self) -> None:
        from api.routers.evaluation import _build_context_text

        result = _build_context_text([])
        assert result == ""


class TestCreateRagasEvaluator:
    """Tests for _create_ragas_evaluator helper."""

    @pytest.mark.skipif(
        not _ragas_available(),
        reason="ragas not installed",
    ) if False else lambda f: f  # noqa: handled below

    def test_creates_ragas_evaluator(self) -> None:
        pytest.importorskip("ragas", reason="ragas not installed")
        from api.routers.evaluation import _create_ragas_evaluator
        from src.core.settings import load_settings

        settings = load_settings()
        evaluator = _create_ragas_evaluator(settings)

        assert type(evaluator).__name__ == "RagasEvaluator"

    def test_forces_ragas_provider(self) -> None:
        """Even if settings say custom, _create_ragas_evaluator forces ragas."""
        pytest.importorskip("ragas", reason="ragas not installed")
        from api.routers.evaluation import _create_ragas_evaluator
        from src.core.settings import load_settings

        settings = load_settings()
        # settings.yaml has provider: "custom" by default
        evaluator = _create_ragas_evaluator(settings)
        assert type(evaluator).__name__ == "RagasEvaluator"

    def test_evaluator_has_correct_metrics(self) -> None:
        pytest.importorskip("ragas", reason="ragas not installed")
        from api.routers.evaluation import _create_ragas_evaluator
        from src.core.settings import load_settings

        settings = load_settings()
        evaluator = _create_ragas_evaluator(settings)

        expected = {"faithfulness", "answer_relevancy", "context_precision"}
        assert set(evaluator._metric_names) == expected


# ---------------------------------------------------------------------------
# Endpoint tests (with mocked dependencies)
# ---------------------------------------------------------------------------

def _make_mock_hit(text: str = "chunk text", score: float = 0.9, source: str = "doc.pdf") -> MagicMock:
    """Create a mock search hit."""
    hit = MagicMock()
    hit.text = text
    hit.score = score
    hit.metadata = {"source_path": source}
    return hit


def _make_mock_evaluator(metrics: Dict[str, float] | None = None) -> MagicMock:
    """Create a mock evaluator that returns given metrics."""
    evaluator = MagicMock()
    evaluator.evaluate.return_value = metrics or {
        "faithfulness": 0.9,
        "answer_relevancy": 0.85,
        "context_precision": 0.8,
    }
    return evaluator


def _make_mock_llm(answer: str = "Generated answer.") -> MagicMock:
    """Create a mock LLM that streams the given answer."""
    llm = MagicMock()
    llm.chat_stream.return_value = iter([answer])
    return llm


class TestEvalEndpoint:
    """Tests for POST /api/eval/run endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        from api.main import app
        return TestClient(app)

    def test_endpoint_exists(self, client: TestClient) -> None:
        """Endpoint should not 404."""
        # Use an invalid body so FastAPI returns 422 (validation error)
        # rather than running the full pipeline. 422 proves the route exists.
        response = client.post(
            "/api/eval/run",
            json={},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code != 404
        assert response.status_code == 422

    def test_validation_rejects_empty_body(self, client: TestClient) -> None:
        response = client.post(
            "/api/eval/run",
            json={},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 422

    def test_validation_rejects_missing_question(self, client: TestClient) -> None:
        response = client.post(
            "/api/eval/run",
            json={"cases": [{}]},
            headers={"X-API-Key": "dev"},
        )
        assert response.status_code == 422

    def test_successful_single_case(self, client: TestClient) -> None:
        """Full pipeline: retrieve → generate → evaluate."""
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm("Test answer")
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "What is RAG?"}]},
                headers={"X-API-Key": "dev"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["data"]["summary"]["total_cases"] == 1
        assert "avg_scores" in data["data"]["summary"]
        assert len(data["data"]["results"]) == 1

        result = data["data"]["results"][0]
        assert result["question"] == "What is RAG?"
        assert result["answer"] == "Test answer"
        assert "faithfulness" in result["scores"]
        assert result["latency_ms"] > 0

    def test_successful_multiple_cases(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm("Answer")
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={
                    "cases": [
                        {"question": "Q1"},
                        {"question": "Q2", "ground_truth": "A2"},
                    ]
                },
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        assert data["ok"] is True
        assert data["data"]["summary"]["total_cases"] == 2
        assert len(data["data"]["results"]) == 2

    def test_aggregation_averages_scores(self, client: TestClient) -> None:
        """Average scores should be computed across all cases."""
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm("Answer")

        # Evaluator returns different scores for each call
        evaluator = MagicMock()
        evaluator.evaluate.side_effect = [
            {"faithfulness": 0.8, "answer_relevancy": 0.6},
            {"faithfulness": 1.0, "answer_relevancy": 0.8},
        ]

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q1"}, {"question": "Q2"}]},
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        avg = data["data"]["summary"]["avg_scores"]
        assert avg["faithfulness"] == 0.9  # (0.8 + 1.0) / 2
        assert avg["answer_relevancy"] == 0.7  # (0.6 + 0.8) / 2

    def test_evaluator_name_in_summary(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm()
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        assert "evaluator" in data["data"]["summary"]

    def test_ground_truth_passed_to_evaluator(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm()
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q", "ground_truth": "GT answer"}]},
                headers={"X-API-Key": "dev"},
            )

        # Verify evaluator was called with ground_truth
        call_kwargs = mock_evaluator.evaluate.call_args[1]
        assert call_kwargs["ground_truth"] == {"reference_answer": "GT answer"}

    def test_no_ground_truth_passes_none(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm()
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        call_kwargs = mock_evaluator.evaluate.call_args[1]
        assert call_kwargs["ground_truth"] is None

    def test_contexts_in_response(self, client: TestClient) -> None:
        hit = _make_mock_hit(text="chunk text", score=0.85, source="doc.pdf")
        mock_search = MagicMock()
        mock_search.search.return_value = [hit]
        mock_llm = _make_mock_llm()
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        ctx = response.json()["data"]["results"][0]["contexts"]
        assert len(ctx) == 1
        assert ctx[0]["source"] == "doc.pdf"
        assert ctx[0]["text"] == "chunk text"
        assert ctx[0]["score"] == 0.85

    def test_custom_top_k_and_collection(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_llm = _make_mock_llm()
        mock_evaluator = _make_mock_evaluator(metrics={})

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search) as get_search, \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={
                    "cases": [{"question": "Q"}],
                    "collection": "my_col",
                    "top_k": 3,
                },
                headers={"X-API-Key": "dev"},
            )

        get_search.assert_called_once_with("my_col")
        mock_search.search.assert_called_once()
        assert mock_search.search.call_args[1]["top_k"] == 3


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestEvalEndpointErrors:
    """Tests for error handling in the evaluation endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        from api.main import app
        return TestClient(app)

    def test_ragas_import_error(self, client: TestClient) -> None:
        """Should return clear error if RAGAS import fails."""
        with patch("src.core.settings.load_settings"), \
             patch("api.routers.evaluation.get_hybrid_search", return_value=MagicMock()), \
             patch("api.routers.evaluation.get_llm", return_value=MagicMock()), \
             patch(
                 "api.routers.evaluation._create_ragas_evaluator",
                 side_effect=ImportError("No module named 'ragas'"),
             ):
            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        assert data["ok"] is False
        assert "RAGAS" in data["message"] or "ragas" in data["message"]

    def test_evaluation_failure_per_case(self, client: TestClient) -> None:
        """If evaluator.evaluate raises, that case gets empty metrics."""
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm()
        evaluator = MagicMock()
        evaluator.evaluate.side_effect = RuntimeError("LLM timeout")

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        # Should still succeed overall but with empty scores for that case
        assert data["ok"] is True
        assert data["data"]["results"][0]["scores"] == {}

    def test_general_exception(self, client: TestClient) -> None:
        """Unexpected exceptions should return ok=False."""
        with patch(
            "src.core.settings.load_settings",
            side_effect=Exception("Config broken"),
        ):
            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        data = response.json()
        assert data["ok"] is False
        assert "message" in data

    def test_llm_generates_answer_from_context(self, client: TestClient) -> None:
        """LLM should receive context in system prompt."""
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit(text="RAG is great")]
        mock_llm = _make_mock_llm("Answer about RAG")
        mock_evaluator = _make_mock_evaluator()

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=mock_evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "What is RAG?"}]},
                headers={"X-API-Key": "dev"},
            )

        # Verify LLM was called
        mock_llm.chat_stream.assert_called_once()
        messages = mock_llm.chat_stream.call_args[0][0]
        # System message should contain context
        assert "RAG is great" in messages[0].content
        # User message should be the question
        assert messages[1].content == "What is RAG?"

    def test_scores_rounded_to_3_decimals(self, client: TestClient) -> None:
        mock_search = MagicMock()
        mock_search.search.return_value = [_make_mock_hit()]
        mock_llm = _make_mock_llm()
        evaluator = MagicMock()
        evaluator.evaluate.return_value = {"faithfulness": 0.123456789}

        with patch("api.routers.evaluation.get_hybrid_search", return_value=mock_search), \
             patch("api.routers.evaluation.get_llm", return_value=mock_llm), \
             patch("api.routers.evaluation._create_ragas_evaluator", return_value=evaluator), \
             patch("src.core.settings.load_settings"):

            response = client.post(
                "/api/eval/run",
                json={"cases": [{"question": "Q"}]},
                headers={"X-API-Key": "dev"},
            )

        scores = response.json()["data"]["results"][0]["scores"]
        assert scores["faithfulness"] == 0.123


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ragas_available() -> bool:
    try:
        import ragas  # noqa: F401
        return True
    except ImportError:
        return False
