"""Evaluation Panel page – run evaluations and view metrics.

Layout:
1. Configuration section: select evaluator backend, golden test set, top_k
2. Run button with progress indicator
3. Results section: aggregate metrics, per-query detail table
4. Optional: historical evaluation results comparison
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

logger = logging.getLogger(__name__)

# Default golden test set location
DEFAULT_GOLDEN_SET = Path("tests/fixtures/golden_test_set.json")
# Evaluation results history file
EVAL_HISTORY_PATH = Path("logs/eval_history.jsonl")


def render() -> None:
    """Render the Evaluation Panel page."""
    st.header("📏 Evaluation Panel")
    st.markdown(
        "Run evaluation against a **golden test set** to measure retrieval "
        "and generation quality. Results include per-query details and "
        "aggregate metrics."
    )

    # ── Configuration Section ──────────────────────────────────────
    st.subheader("⚙️ Configuration")

    col1, col2, col3 = st.columns(3)

    with col1:
        backend = st.selectbox(
            "Evaluator Backend",
            options=["custom", "ragas", "composite"],
            index=0,
            key="eval_backend",
            help="Select which evaluator backend to use.",
        )

    # Show info/warning based on selected backend
    if backend in ("custom", "composite"):
        st.info(
            "ℹ️ **Custom Evaluator** 尚未完成数据集准备，当前仅为预留接口。"
            "Custom Evaluator 需要在 Golden Test Set 中填写 `expected_chunk_ids` "
            "作为 ground truth 才能计算 hit_rate / MRR 指标。"
            "目前建议使用 **ragas** 后端进行评估。",
            icon="🚧",
        )

    with col2:
        top_k = st.number_input(
            "Top-K",
            min_value=1,
            max_value=50,
            value=10,
            key="eval_top_k",
            help="Number of chunks to retrieve per query.",
        )

    with col3:
        collection = st.text_input(
            "Collection (optional)",
            value="",
            key="eval_collection",
            help="Limit retrieval to a specific collection.",
        )

    # Golden test set file selection
    golden_path_str = st.text_input(
        "Golden Test Set Path",
        value=str(DEFAULT_GOLDEN_SET),
        key="eval_golden_path",
        help="Path to the golden_test_set.json file.",
    )
    golden_path = Path(golden_path_str)

    # Validate golden set exists
    if not golden_path.exists():
        st.warning(
            f"⚠️ **Golden test set not found:** `{golden_path}`. "
            "Create a JSON file with test queries and expected results. "
            "See `tests/fixtures/golden_test_set.json` for the format."
        )

    # ── Answer Input Section (for Ragas) ───────────────────────────
    user_answers: Dict[int, str] = {}
    if backend == "ragas" and golden_path.exists():
        st.divider()
        st.subheader("✏️ Provide Answers (回答输入)")
        st.caption(
            "**RAGAS 需要 Query + Context + Answer 三要素来评估。**"
            "日志中仅包含 Query 和检索到的上下文（Context），"
            "请为每个测试用例填写实际的系统回答（Answer），"
            "以便获得有意义的 faithfulness 和 answer_relevancy 评分。"
        )
        try:
            _test_cases = _load_golden_queries(golden_path)
            for tc_idx, tc in enumerate(_test_cases):
                ans_key = f"eval_answer_tc_{tc_idx}"
                default_val = tc.get("reference_answer", "")
                q_preview = tc["query"][:60] + ("…" if len(tc["query"]) > 60 else "")
                user_ans = st.text_area(
                    f"Q{tc_idx + 1}: {q_preview}",
                    value=st.session_state.get(ans_key, default_val),
                    height=80,
                    key=ans_key,
                    placeholder="请输入该问题对应的系统回答…",
                    help=(
                        f"Query: {tc['query']}\n\n"
                        "填写 LLM 生成的回答或期望的回答文本。"
                        "Ragas 会基于此评估 faithfulness（忠实度）和 answer_relevancy（相关性）。"
                    ),
                )
                if user_ans.strip():
                    user_answers[tc_idx] = user_ans.strip()

            # Show fill status
            filled = len(user_answers)
            total = len(_test_cases)
            if filled < total:
                st.warning(f"⚠️ 已填写 {filled}/{total} 个回答。未填写的用例将使用检索片段拼接作为回答（评估结果可能不准确）。")
            else:
                st.success(f"✅ 所有 {total} 个回答已填写。")
        except Exception as exc:
            st.warning(f"无法加载测试用例预览: {exc}")

    # ── Run Evaluation ─────────────────────────────────────────────
    st.divider()

    run_clicked = st.button(
        "▶️  Run Evaluation",
        type="primary",
        key="eval_run_btn",
        disabled=not golden_path.exists(),
    )

    if run_clicked:
        _run_evaluation(
            backend=backend,
            golden_path=golden_path,
            top_k=int(top_k),
            collection=collection.strip() or None,
            user_answers=user_answers if user_answers else None,
        )

    # ── Historical Results ─────────────────────────────────────────
    st.divider()
    _render_history()


def _run_evaluation(
    backend: str,
    golden_path: Path,
    top_k: int,
    collection: Optional[str],
    user_answers: Optional[Dict[int, str]] = None,
) -> None:
    """Execute an evaluation run and display results.

    Attempts to load the evaluator, run the golden test set, and
    display aggregate + per-query metrics.  Falls back to a graceful
    error message on failure.
    """
    with st.spinner("Loading evaluator and running evaluation…"):
        try:
            report_dict = _execute_evaluation(
                backend=backend,
                golden_path=golden_path,
                top_k=top_k,
                collection=collection,
                user_answers=user_answers,
            )
        except Exception as exc:
            st.error(f"❌ Evaluation failed: {exc}")
            logger.exception("Evaluation failed")
            return

    # ── Display results ────────────────────────────────────────────
    st.success("✅ Evaluation complete!")

    _render_aggregate_metrics(report_dict)
    _render_query_details(report_dict)

    # Save to history
    _save_to_history(report_dict)


def _execute_evaluation(
    backend: str,
    golden_path: Path,
    top_k: int,
    collection: Optional[str],
    user_answers: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """Run the evaluation pipeline and return the report dict.

    This function imports heavy dependencies lazily to keep the
    dashboard responsive when the page is not used.
    """
    from dataclasses import replace as dc_replace

    from src.core.settings import load_settings
    from src.libs.evaluator.evaluator_factory import EvaluatorFactory
    from src.observability.evaluation.eval_runner import EvalRunner, load_test_set

    settings = load_settings()

    # Override evaluator provider from UI selection — build a new full
    # Settings object so that RagasEvaluator can still access .llm / .embedding.
    eval_settings = settings.evaluation
    overridden_eval = type(eval_settings)(
        enabled=True,
        provider=backend,
        metrics=eval_settings.metrics if hasattr(eval_settings, "metrics") else [],
    )
    # Replace only the evaluation sub-config in the full settings
    settings_with_override = dc_replace(settings, evaluation=overridden_eval)

    evaluator = EvaluatorFactory.create(settings_with_override)

    # Try to create HybridSearch (optional – works without if not configured)
    target_collection = collection or "default"
    hybrid_search = _try_create_hybrid_search(settings, target_collection)

    # Create reranker if enabled
    reranker = None
    try:
        from src.core.query_engine.reranker import create_core_reranker
        reranker = create_core_reranker(settings=settings)
        if not reranker.is_enabled:
            reranker = None
    except Exception as exc:
        logger.warning("Could not create reranker: %s", exc)

    # Build answer_override map: index → user-provided answer text
    # EvalRunner will use these instead of auto-generating from chunks.
    runner = EvalRunner(
        settings=settings,
        hybrid_search=hybrid_search,
        evaluator=evaluator,
        answer_overrides=user_answers,
        reranker=reranker,
    )

    report = runner.run(
        test_set_path=golden_path,
        top_k=top_k,
        collection=collection,
    )

    return report.to_dict()


def _try_create_hybrid_search(settings: Any, collection: str = "default") -> Any:
    """Attempt to create a HybridSearch instance.

    Returns None if required dependencies are not available
    (e.g., no indexed data).
    """
    try:
        from src.core.query_engine.query_processor import QueryProcessor
        from src.core.query_engine.hybrid_search import create_hybrid_search
        from src.core.query_engine.dense_retriever import create_dense_retriever
        from src.core.query_engine.sparse_retriever import create_sparse_retriever
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory

        vector_store = VectorStoreFactory.create(
            settings, collection_name=collection,
        )
        embedding_client = EmbeddingFactory.create(settings)
        dense_retriever = create_dense_retriever(
            settings=settings,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )
        bm25_indexer = BM25Indexer(index_dir=f"data/db/bm25/{collection}")
        sparse_retriever = create_sparse_retriever(
            settings=settings,
            bm25_indexer=bm25_indexer,
            vector_store=vector_store,
        )
        sparse_retriever.default_collection = collection

        query_processor = QueryProcessor()
        return create_hybrid_search(
            settings=settings,
            query_processor=query_processor,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
        )
    except Exception as exc:
        logger.warning("Could not create HybridSearch: %s", exc)
        return None


def _render_aggregate_metrics(report: Dict[str, Any]) -> None:
    """Display aggregate metrics as metric cards."""
    st.subheader("📊 Aggregate Metrics")

    agg = report.get("aggregate_metrics", {})

    if not agg:
        st.info("No aggregate metrics available.")
        return

    cols = st.columns(min(len(agg), 4))
    for idx, (name, value) in enumerate(sorted(agg.items())):
        with cols[idx % len(cols)]:
            st.metric(
                label=name.replace("_", " ").title(),
                value=f"{value:.4f}",
            )

    st.caption(
        f"Evaluator: **{report.get('evaluator_name', '—')}** · "
        f"Queries: **{report.get('query_count', 0)}** · "
        f"Total time: **{report.get('total_elapsed_ms', 0):.0f} ms**"
    )


def _render_query_details(report: Dict[str, Any]) -> None:
    """Display per-query evaluation results in an expandable table."""
    st.subheader("🔍 Per-Query Details")

    query_results = report.get("query_results", [])
    if not query_results:
        st.info("No per-query results available.")
        return

    for idx, qr in enumerate(query_results):
        query = qr.get("query", "—")
        elapsed = qr.get("elapsed_ms", 0)
        metrics = qr.get("metrics", {})

        # Build metric summary for the expander label
        metric_summary = " · ".join(
            f"{k}: {v:.3f}" for k, v in sorted(metrics.items())
        )
        if not metric_summary:
            metric_summary = "no metrics"

        with st.expander(
            f"**Q{idx + 1}**: {query[:80]} — {elapsed:.0f} ms — {metric_summary}",
            expanded=False,
        ):
            # Metrics
            if metrics:
                mcols = st.columns(min(len(metrics), 4))
                for midx, (mname, mval) in enumerate(sorted(metrics.items())):
                    with mcols[midx % len(mcols)]:
                        st.metric(mname, f"{mval:.4f}")

            # Retrieved chunks
            chunks = qr.get("retrieved_chunk_ids", [])
            if chunks:
                st.markdown(f"**Retrieved Chunks** ({len(chunks)}):")
                st.code(", ".join(chunks[:20]), language=None)

            # Generated answer
            answer = qr.get("generated_answer")
            if answer:
                st.markdown("**Generated Answer:**")
                st.text(answer[:500])


def _render_history() -> None:
    """Display historical evaluation results for comparison."""
    st.subheader("📈 Evaluation History")

    history = _load_history()
    if not history:
        st.info(
            "**No evaluation history yet.** "
            "Configure the evaluator above and click \"Run Evaluation\" to start. "
            "Results will be saved here for comparison across runs."
        )
        return

    # Show recent runs as a table
    rows = []
    for entry in history[-10:]:  # last 10 runs
        rows.append(
            {
                "Timestamp": entry.get("timestamp", "—"),
                "Evaluator": entry.get("evaluator_name", "—"),
                "Queries": entry.get("query_count", 0),
                "Time (ms)": round(entry.get("total_elapsed_ms", 0)),
                **{
                    k: round(v, 4)
                    for k, v in entry.get("aggregate_metrics", {}).items()
                },
            }
        )

    st.dataframe(rows, use_container_width=True)


def _save_to_history(report: Dict[str, Any]) -> None:
    """Append an evaluation report to the history file."""
    try:
        EVAL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            **report,
        }
        with EVAL_HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to save evaluation history: %s", exc)


def _load_history() -> List[Dict[str, Any]]:
    """Load evaluation history from JSONL file."""
    if not EVAL_HISTORY_PATH.exists():
        return []

    entries: List[Dict[str, Any]] = []
    try:
        with EVAL_HISTORY_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        logger.warning("Failed to load evaluation history: %s", exc)

    return entries


def _load_golden_queries(golden_path: Path) -> List[Dict[str, Any]]:
    """Load test cases from golden test set for display in the UI.

    Returns list of dicts with at least 'query' and optionally
    'reference_answer' keys.
    """
    with golden_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("test_cases", [])
