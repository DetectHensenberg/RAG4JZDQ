"""Query Traces page – browse query trace history with stage waterfall."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import streamlit as st

from src.observability.dashboard.services.trace_service import TraceService

logger = logging.getLogger(__name__)


def render() -> None:
    """Render the Query Traces page."""
    st.header("🔎 查询追踪")

    svc = TraceService()
    traces = svc.list_traces(trace_type="query")

    if not traces:
        st.info("暂无查询追踪记录。请先执行一次查询！")
        return

    keyword = st.text_input("按关键词搜索", value="", key="qt_keyword")
    if keyword.strip():
        kw = keyword.strip().lower()
        traces = [
            t for t in traces
            if kw in str(t.get("metadata", {})).lower()
            or kw in str(t.get("stages", [])).lower()
        ]

    st.subheader(f"📋 查询历史 ({len(traces)})")

    for idx, trace in enumerate(traces):
        trace_id = trace.get("trace_id", "unknown")
        started = trace.get("started_at", "—")
        total_ms = trace.get("elapsed_ms")
        total_label = f"{total_ms:.0f} ms" if total_ms is not None else "—"
        meta = trace.get("metadata", {})
        query_text = meta.get("query", "")
        source = meta.get("source", "unknown")

        query_preview = (
            query_text[:40] + "…" if len(query_text) > 40 else query_text
        ) if query_text else "—"
        expander_title = f"🔍 \"{query_preview}\"  ·  {total_label}  ·  {started[:19]}"

        with st.expander(expander_title, expanded=(idx == 0)):
            st.markdown("#### 💬 查询")
            col_q, col_meta = st.columns([3, 1])
            with col_q:
                st.markdown(f"> {query_text}")
            with col_meta:
                source_emoji = "🤖" if source == "mcp" else "📡"
                st.markdown(f"**来源:** {source_emoji} `{source}`")
                st.markdown(f"**Top-K:** `{meta.get('top_k', '—')}`")
                st.markdown(f"**集合:** `{meta.get('collection', '—')}`")

            st.divider()

            timings = svc.get_stage_timings(trace)
            stages_by_name = {t["stage_name"]: t for t in timings}

            dense_d = (stages_by_name.get("dense_retrieval", {}).get("data") or {})
            sparse_d = (stages_by_name.get("sparse_retrieval", {}).get("data") or {})
            fusion_d = (stages_by_name.get("fusion", {}).get("data") or {})
            rerank_d = (stages_by_name.get("rerank", {}).get("data") or {})

            dense_count = dense_d.get("result_count", 0)
            sparse_count = sparse_d.get("result_count", 0)
            fusion_count = fusion_d.get("result_count", 0)
            rerank_count = rerank_d.get("output_count", 0)

            rc1, rc2, rc3, rc4, rc5 = st.columns(5)
            with rc1:
                st.metric("稠密命中", dense_count)
            with rc2:
                st.metric("稀疏命中", sparse_count)
            with rc3:
                st.metric("融合结果", fusion_count or (dense_count + sparse_count))
            with rc4:
                st.metric("重排后", rerank_count if rerank_d else "—")
            with rc5:
                st.metric("总耗时", total_label)

            _render_diagnostics(stages_by_name, dense_d, sparse_d, fusion_d, rerank_d, dense_count, sparse_count)

            st.divider()

            main_stage_names = ("query_processing", "dense_retrieval", "sparse_retrieval", "fusion", "rerank")
            main_timings = [t for t in timings if t["stage_name"] in main_stage_names]
            if main_timings:
                st.markdown("#### ⏱️ 各阶段耗时")
                chart_data = {t["stage_name"]: t["elapsed_ms"] for t in main_timings}
                st.bar_chart(chart_data, horizontal=True)
                st.table([{"阶段": t["stage_name"], "耗时 (ms)": round(t["elapsed_ms"], 2)} for t in main_timings])

            st.divider()
            st.markdown("#### 🔍 阶段详情")

            tab_defs = []
            if "query_processing" in stages_by_name:
                tab_defs.append(("🔤 查询处理", "query_processing"))
            if "dense_retrieval" in stages_by_name:
                tab_defs.append(("🟦 稠密检索", "dense_retrieval"))
            if "sparse_retrieval" in stages_by_name:
                tab_defs.append(("🟨 稀疏检索", "sparse_retrieval"))
            if "fusion" in stages_by_name:
                tab_defs.append(("🟩 融合 (RRF)", "fusion"))
            if "rerank" in stages_by_name:
                tab_defs.append(("🟪 重排", "rerank"))

            if tab_defs:
                tabs = st.tabs([label for label, _ in tab_defs])
                for tab, (label, key) in zip(tabs, tab_defs):
                    with tab:
                        stage = stages_by_name[key]
                        data = stage.get("data", {})
                        elapsed = stage.get("elapsed_ms")
                        if elapsed is not None:
                            st.caption(f"⏱️ {elapsed:.1f} ms")
                        if key == "query_processing":
                            _render_query_processing_stage(data)
                        elif key == "dense_retrieval":
                            _render_retrieval_stage(data, "稠密", trace_idx=idx)
                        elif key == "sparse_retrieval":
                            _render_retrieval_stage(data, "稀疏", trace_idx=idx)
                        elif key == "fusion":
                            _render_fusion_stage(data, trace_idx=idx)
                        elif key == "rerank":
                            _render_rerank_stage(data, trace_idx=idx)
            else:
                st.info("无阶段详情。")

            _render_evaluate_button(trace, idx)


def _render_diagnostics(
    stages_by_name: Dict[str, Any],
    dense_d: Dict[str, Any],
    sparse_d: Dict[str, Any],
    fusion_d: Dict[str, Any],
    rerank_d: Dict[str, Any],
    dense_count: int,
    sparse_count: int,
) -> None:
    """Render diagnostic hints about missing or errored pipeline stages."""
    hints: list = []

    dense_err = dense_d.get("error", "")
    if dense_err:
        hints.append(("error", f"**稠密检索失败:** {dense_err}"))
    elif dense_count == 0 and "dense_retrieval" in stages_by_name:
        hints.append(("warning", "稠密检索返回了 **0 条结果**。请检查集合中是否已有索引数据。"))

    sparse_err = sparse_d.get("error", "")
    if sparse_err:
        hints.append(("error", f"**稀疏检索失败:** {sparse_err}"))
    elif sparse_count == 0 and "sparse_retrieval" in stages_by_name:
        hints.append(("warning", "稀疏 (BM25) 检索返回了 **0 条结果**。BM25 索引可能为空或尚未为此集合构建。"))

    if "fusion" not in stages_by_name:
        if dense_count > 0 and sparse_count > 0:
            hints.append(("info", "即使两个检索器都返回了结果，融合阶段也未被记录。"))
        elif dense_count == 0 or sparse_count == 0:
            only_source = "稠密" if dense_count > 0 else ("稀疏" if sparse_count > 0 else "均无")
            hints.append(("info", f"**融合 (RRF) 已跳过:** 仅 {only_source} 检索返回了结果。融合需要稠密和稀疏检索同时返回结果才能合并。"))

    if "rerank" not in stages_by_name:
        if dense_count > 0 or sparse_count > 0:
            hints.append(("info", "**重排已跳过:** 重排器未启用或未配置。在 settings.yaml 中启用 reranker 以应用基于 LLM 的重排。"))

    if dense_count == 0 and sparse_count == 0:
        hints.append(("warning", "**未找到任何结果。** 集合可能为空，或查询内容与已索引的内容不匹配。请先尝试摄取数据。"))

    for level, msg in hints:
        if level == "error":
            st.error(msg)
        elif level == "warning":
            st.warning(msg)
        else:
            st.info(msg)


def _render_evaluate_button(trace: Dict[str, Any], idx: int) -> None:
    """Render a Ragas evaluate button for a single query trace."""
    meta = trace.get("metadata", {})
    query = meta.get("query", "")
    if not query:
        return

    st.divider()
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        clicked = st.button(
            "📏 Ragas 评估",
            key=f"eval_trace_{idx}",
            help="重新运行此查询并使用 Ragas (LLM 评判) 打分",
        )
    with col_info:
        st.caption("使用 Ragas 评估忠实度、答案相关性和上下文精度。将调用 LLM — 可能需要几秒钟。")

    result_key = f"eval_result_{idx}"
    if result_key in st.session_state and not clicked:
        _display_eval_metrics(st.session_state[result_key])

    if clicked:
        with st.spinner("正在运行 Ragas 评估…"):
            result = _evaluate_single_trace(query, meta)
        st.session_state[result_key] = result
        _display_eval_metrics(result)


def _evaluate_single_trace(query: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run retrieval and evaluate a single query with Ragas."""
    try:
        from dataclasses import replace as dc_replace
        from src.core.settings import load_settings, EvaluationSettings
        from src.libs.evaluator.evaluator_factory import EvaluatorFactory

        settings = load_settings()
        ragas_eval = EvaluationSettings(
            enabled=True,
            provider="ragas",
            metrics=["faithfulness", "answer_relevancy", "context_precision"],
        )
        settings = dc_replace(settings, evaluation=ragas_eval)
        evaluator = EvaluatorFactory.create(settings)

        collection = meta.get("collection", "default")
        top_k = meta.get("top_k", 10)
        chunks = _retrieve_chunks(settings, query, top_k, collection)

        if not chunks:
            return {"error": "未检索到分块 — 是否已索引数据？"}

        _MAX_ANSWER_CHARS = 1500
        texts = []
        for c in chunks:
            if hasattr(c, "text"):
                texts.append(c.text)
            elif isinstance(c, dict):
                texts.append(c.get("text", str(c)))
            else:
                texts.append(str(c))
        answer = " ".join(texts[:3])
        if len(answer) > _MAX_ANSWER_CHARS:
            answer = answer[:_MAX_ANSWER_CHARS]

        metrics = evaluator.evaluate(
            query=query,
            retrieved_chunks=chunks,
            generated_answer=answer,
        )
        return {"metrics": metrics}
    except ImportError as exc:
        return {"error": f"Ragas 未安装: {exc}"}
    except Exception as exc:
        logger.exception("Ragas evaluation failed")
        return {"error": str(exc)}


def _retrieve_chunks(settings: Any, query: str, top_k: int, collection: str) -> list:
    """Re-run HybridSearch to retrieve chunks for evaluation."""
    try:
        from src.core.query_engine.hybrid_search import create_hybrid_search
        from src.core.query_engine.query_processor import QueryProcessor
        from src.core.query_engine.dense_retriever import create_dense_retriever
        from src.core.query_engine.sparse_retriever import create_sparse_retriever
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory

        vector_store = VectorStoreFactory.create(settings, collection_name=collection)
        embedding_client = EmbeddingFactory.create(settings)
        dense_retriever = create_dense_retriever(
            settings=settings, embedding_client=embedding_client, vector_store=vector_store,
        )
        from src.core.settings import resolve_path
        bm25_indexer = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
        sparse_retriever = create_sparse_retriever(
            settings=settings, bm25_indexer=bm25_indexer, vector_store=vector_store,
        )
        sparse_retriever.default_collection = collection
        query_processor = QueryProcessor()
        hybrid_search = create_hybrid_search(
            settings=settings,
            query_processor=query_processor,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
        )
        results = hybrid_search.search(query=query, top_k=top_k)
        return results if isinstance(results, list) else results.results
    except Exception as exc:
        logger.warning("Retrieval for evaluation failed: %s", exc)
        return []


def _display_eval_metrics(result: Dict[str, Any]) -> None:
    """Display evaluation result (metrics or error)."""
    if "error" in result:
        st.error(f"❌ 评估失败: {result['error']}")
        return

    metrics = result.get("metrics", {})
    if not metrics:
        st.warning("未返回指标。")
        return

    st.markdown("**📏 Ragas 评分**")
    cols = st.columns(min(len(metrics), 4))
    for i, (name, value) in enumerate(sorted(metrics.items())):
        with cols[i % len(cols)]:
            st.metric(label=name.replace("_", " ").title(), value=f"{value:.4f}")


def _extract_pipeline_chunks(
    timings: List[Dict[str, Any]], meta: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Extract chunk lists from each pipeline stage."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    for stage in timings:
        name = stage.get("stage_name", "")
        data = stage.get("data") or {}
        chunks = data.get("chunks")
        if chunks and isinstance(chunks, list):
            result[name] = chunks
    final = meta.get("final_results") or meta.get("results")
    if final and isinstance(final, list):
        result["final"] = final
    return result


# ═══════════════════════════════════════════════════════════════
# Per-stage renderers
# ═══════════════════════════════════════════════════════════════

def _render_query_processing_stage(data: Dict[str, Any]) -> None:
    """Render Query Processing stage: original query → keywords."""
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**原始查询**")
        st.info(data.get("original_query", "—"))
    with c2:
        st.markdown("**方法**")
        st.code(data.get("method", "—"))

    keywords = data.get("keywords", [])
    if keywords:
        st.markdown("**提取的关键词**")
        st.markdown(" · ".join(f"`{kw}`" for kw in keywords))
    else:
        st.warning("未提取到关键词。")


def _render_retrieval_stage(data: Dict[str, Any], label: str, *, trace_idx: int = 0) -> None:
    """Render Dense or Sparse retrieval stage."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("方法", data.get("method", "—"))
    with c2:
        extra = data.get("provider", data.get("keyword_count", "—"))
        extra_label = "提供商" if "provider" in data else "关键词数"
        st.metric(extra_label, extra)
    with c3:
        st.metric("结果数", data.get("result_count", 0))

    st.markdown(f"**请求 Top-K:** `{data.get('top_k', '—')}`")

    chunks = data.get("chunks", [])
    if chunks:
        _render_chunk_list(chunks, prefix=f"{label.lower().replace(' ', '_')}_chunk_{trace_idx}")
    else:
        st.info(f"未返回{label}检索结果。")


def _render_fusion_stage(data: Dict[str, Any], *, trace_idx: int = 0) -> None:
    """Render Fusion (RRF) stage."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("方法", data.get("method", "rrf"))
    with c2:
        st.metric("输入列表数", data.get("input_lists", "—"))
    with c3:
        st.metric("融合结果数", data.get("result_count", 0))

    st.markdown(f"**Top-K:** `{data.get('top_k', '—')}`")

    chunks = data.get("chunks", [])
    if chunks:
        _render_chunk_list(chunks, prefix=f"fusion_chunk_{trace_idx}")
    else:
        st.info("无融合结果。")


def _render_rerank_stage(data: Dict[str, Any], *, trace_idx: int = 0) -> None:
    """Render Rerank stage."""
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("方法", data.get("method", "—"))
    with c2:
        st.metric("提供商", data.get("provider", "—"))
    with c3:
        st.metric("输入数", data.get("input_count", "—"))
    with c4:
        st.metric("输出数", data.get("output_count", "—"))

    chunks = data.get("chunks", [])
    if chunks:
        _render_chunk_list(chunks, prefix=f"rerank_chunk_{trace_idx}")
    else:
        st.info("无重排结果。")


def _render_chunk_list(chunks: List[Dict[str, Any]], prefix: str = "chunk") -> None:
    """Render a list of chunk dicts as a compact, readable table with expandable text."""
    for ci, chunk in enumerate(chunks):
        score = chunk.get("score", 0)
        text = chunk.get("text", "")
        chunk_id = chunk.get("chunk_id", "")
        source = chunk.get("source", "")
        title = chunk.get("title", "")

        if score >= 0.8:
            score_bar = "🟢"
        elif score >= 0.5:
            score_bar = "🟡"
        else:
            score_bar = "🔴"

        header = f"{score_bar} **#{ci + 1}** — 分数: `{score:.4f}`"
        if title:
            header += f" — {title}"

        with st.expander(header, expanded=False):
            cols = st.columns([2, 3])
            with cols[0]:
                st.caption(f"分块 ID: `{chunk_id}`")
            with cols[1]:
                if source:
                    st.caption(f"来源: `{source}`")
            if text:
                st.text_area(
                    f"{prefix}_{ci}",
                    value=text,
                    height=max(80, min(len(text) // 2, 400)),
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.caption("_无文本内容_")


def _find_stage(timings, name):
    """Find a stage dict by name, or None."""
    for t in timings:
        if t["stage_name"] == name:
            return t
    return None
