"""Evaluation API router — RAGAS evaluation via existing RagasEvaluator + EvalRunner.

Uses the project's built-in evaluation infrastructure:
- src/observability/evaluation/ragas_evaluator.py  (RagasEvaluator)
- src/observability/evaluation/eval_runner.py      (EvalRunner)
- src/libs/evaluator/evaluator_factory.py          (EvaluatorFactory)

Metrics (from ragas library):
- Faithfulness: Is the answer grounded in the retrieved context?
- Answer Relevancy: Is the answer relevant to the question?
- Context Precision: Are retrieved chunks relevant and well-ordered?
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace as dc_replace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import get_hybrid_search, get_llm
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class EvalCase(BaseModel):
    """Single evaluation test case."""
    question: str
    ground_truth: Optional[str] = None


class EvalRunRequest(BaseModel):
    """Evaluation run request."""
    cases: List[EvalCase]
    collection: str = "default"
    top_k: int = 5
    max_tokens: int = 2048


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "参考资料:\n{context}\n\n请基于以上资料回答问题，如资料不足请说明。"


def _build_context_text(results: list) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r.text[:500]}")
    return "\n\n".join(parts)


def _create_ragas_evaluator(settings: Any) -> Any:
    """Create a RagasEvaluator from settings, forcing ragas provider on."""
    from src.core.settings import EvaluationSettings
    from src.libs.evaluator.evaluator_factory import EvaluatorFactory

    ragas_eval = EvaluationSettings(
        enabled=True,
        provider="ragas",
        metrics=["faithfulness", "answer_relevancy", "context_precision"],
    )
    patched = dc_replace(settings, evaluation=ragas_eval)
    return EvaluatorFactory.create(patched)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
def run_evaluation(req: EvalRunRequest):
    """Run RAGAS evaluation on a set of test cases.

    For each case: retrieve → generate answer → evaluate with RagasEvaluator.
    """
    try:
        from src.core.settings import load_settings

        settings = load_settings()
        print("[Eval] settings loaded", flush=True)
        search = get_hybrid_search(req.collection)
        print("[Eval] search ready", flush=True)
        llm = get_llm()
        print("[Eval] llm ready", flush=True)

        # Create evaluator (real ragas)
        evaluator = _create_ragas_evaluator(settings)
        evaluator_name = type(evaluator).__name__
        print(f"[Eval] evaluator={evaluator_name}, cases={len(req.cases)}", flush=True)

        case_results: List[Dict[str, Any]] = []
        all_metrics: Dict[str, List[float]] = {}

        for idx, case in enumerate(req.cases):
            t0 = time.time()

            # Step 1: Retrieve
            print(f"[Eval {idx+1}/{len(req.cases)}] Step 1: Retrieving...", flush=True)
            hits = search.search(query=case.question, top_k=req.top_k)
            print(f"[Eval {idx+1}/{len(req.cases)}] Step 1 done: {len(hits)} hits", flush=True)
            contexts = [
                {
                    "source": r.metadata.get("source_path", "未知"),
                    "text": r.text[:500],
                    "score": round(r.score, 4),
                }
                for r in hits
            ]

            # Step 2: Generate answer via LLM
            print(f"[Eval {idx+1}/{len(req.cases)}] Step 2: LLM generating...", flush=True)
            context_text = _build_context_text(hits)
            gen_messages = [
                Message(role="system", content=SYSTEM_PROMPT.format(context=context_text)),
                Message(role="user", content=case.question),
            ]
            answer = ""
            for chunk in llm.chat_stream(gen_messages, max_tokens=req.max_tokens):
                answer += chunk
            print(f"[Eval {idx+1}/{len(req.cases)}] Step 2 done: {len(answer)} chars", flush=True)

            # Step 3: Evaluate with RagasEvaluator
            # Truncate answer + chunks to keep RAGAS LLM output within token limits
            # (faithfulness extracts statements from answer, then verifies each against each chunk)
            eval_answer = answer[:500]
            eval_contexts = [r.text[:200] for r in hits[:3]]
            print(f"[Eval {idx+1}/{len(req.cases)}] Step 3: RAGAS evaluating (answer={len(eval_answer)}c, {len(eval_contexts)} chunks)...", flush=True)
            metrics: Dict[str, float] = {}
            try:
                metrics = evaluator.evaluate(
                    query=case.question,
                    retrieved_chunks=eval_contexts,
                    generated_answer=eval_answer,
                    ground_truth=(
                        {"reference_answer": case.ground_truth}
                        if case.ground_truth else None
                    ),
                )
            except Exception as eval_err:
                logger.warning(
                    "RAGAS evaluation failed for case %d: %s", idx, eval_err
                )

            latency_ms = round((time.time() - t0) * 1000, 1)

            # Accumulate for averaging
            for k, v in metrics.items():
                all_metrics.setdefault(k, []).append(v)

            case_results.append({
                "question": case.question,
                "ground_truth": case.ground_truth,
                "answer": answer,
                "contexts": contexts,
                "scores": {k: round(v, 3) for k, v in metrics.items()},
                "latency_ms": latency_ms,
            })

            logger.info(
                "Eval [%d/%d] %s — %s (%.0fms)",
                idx + 1, len(req.cases),
                case.question[:40],
                {k: round(v, 2) for k, v in metrics.items()},
                latency_ms,
            )

        # Aggregate
        avg_scores = {
            k: round(sum(v) / len(v), 3) for k, v in all_metrics.items() if v
        }

        summary = {
            "total_cases": len(req.cases),
            "evaluator": evaluator_name,
            "avg_scores": avg_scores,
        }

        return {"ok": True, "data": {"summary": summary, "results": case_results}}

    except ImportError as e:
        logger.exception("RAGAS not available")
        return {"ok": False, "message": f"RAGAS 依赖未安装: {e}"}
    except Exception as e:
        logger.exception("Evaluation failed")
        return {"ok": False, "message": str(e)}
