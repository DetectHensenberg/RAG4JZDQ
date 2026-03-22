from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.query_engine.strategy_router import StrategyRouter
from src.core.trace.trace_context import TraceContext
from src.libs.llm.base_llm import ChatResponse


class FakeLLM:
    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = []

    def chat(self, messages, trace=None, **kwargs):
        self.calls.append({"messages": messages, "trace": trace, "kwargs": kwargs})
        if self.error is not None:
            raise self.error
        return ChatResponse(content=self.content, model="fake-router")


def _settings(parent_mode: str = "never", graph_mode: str = "never"):
    return SimpleNamespace(
        retrieval=SimpleNamespace(
            parent_retrieval_mode=parent_mode,
            graph_rag_mode=graph_mode,
        )
    )


def test_static_modes_skip_llm_calls() -> None:
    llm = FakeLLM(content='{"parent": false, "graph": true, "reason": "unused"}')
    router = StrategyRouter(_settings("always", "never"), llm=llm)

    decision = router.route("请给我完整章节")

    assert decision.use_parent_retrieval is True
    assert decision.use_graph_rag is False
    assert decision.method == "config"
    assert llm.calls == []


def test_auto_mode_uses_llm_json_response() -> None:
    llm = FakeLLM(content='{"parent": true, "graph": false, "reason": "需要完整上下文"}')
    trace = TraceContext()
    router = StrategyRouter(_settings("auto", "never"), llm=llm)

    decision = router.route("请详细说明完整上下文", trace=trace)

    assert decision.use_parent_retrieval is True
    assert decision.use_graph_rag is False
    assert decision.method == "llm"
    assert decision.reasoning == "需要完整上下文"
    assert llm.calls[0]["kwargs"]["temperature"] == 0.0
    assert llm.calls[0]["kwargs"]["max_tokens"] == 100
    assert trace.get_stage_data("strategy_routing")["method"] == "llm"


def test_invalid_llm_response_falls_back_to_patterns() -> None:
    llm = FakeLLM(content="not-json")
    router = StrategyRouter(_settings("auto", "auto"), llm=llm)

    decision = router.route("请比较 A 和 B 的关系与影响")

    assert decision.use_parent_retrieval is False
    assert decision.use_graph_rag is True
    assert decision.method == "pattern"
    assert "graph" in decision.reasoning


def test_static_modes_override_auto_decisions() -> None:
    llm = FakeLLM(content='{"parent": false, "graph": true, "reason": "llm"}')
    router = StrategyRouter(_settings("always", "auto"), llm=llm)

    decision = router.route("比较两家公司差异")

    assert decision.use_parent_retrieval is True
    assert decision.use_graph_rag is True
    assert decision.method == "llm"


def test_missing_llm_defaults_to_pattern_or_off() -> None:
    router = StrategyRouter(_settings("auto", "auto"), llm=None)

    graph_decision = router.route("请比较它们的关系")
    off_decision = router.route("你好")

    assert graph_decision.method == "pattern"
    assert graph_decision.use_graph_rag is True
    assert off_decision.method == "pattern"
    assert off_decision.use_parent_retrieval is False
    assert off_decision.use_graph_rag is False


def test_markdown_json_response_is_supported() -> None:
    llm = FakeLLM(
        content='```json\n{"parent": "true", "graph": "false", "reason": "wrapped"}\n```'
    )
    router = StrategyRouter(_settings("auto", "auto"), llm=llm)

    decision = router.route("给我完整总结")

    assert decision.use_parent_retrieval is True
    assert decision.use_graph_rag is False
    assert decision.method == "llm"
