"""Dynamic retrieval strategy routing for Parent Retrieval and GraphRAG."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from src.libs.llm.base_llm import BaseLLM, Message

logger = logging.getLogger(__name__)

_PARENT_PATTERNS = [
    r"全文",
    r"完整",
    r"详细",
    r"上下文",
    r"章节",
    r"总结",
    r"概括",
    r"\bfull\b",
    r"\bcomplete\b",
    r"\bdetailed\b",
    r"\bcontext\b",
    r"\bchapter\b",
    r"\bsummar(?:y|ize)\b",
]
_GRAPH_PATTERNS = [
    r"关系",
    r"关联",
    r"比较",
    r"对比",
    r"区别",
    r"差异",
    r"因果",
    r"影响",
    r"\brelationship\b",
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bdifference\b",
    r"\bimpact\b",
    r"\bcause\b",
]

_CLASSIFIER_PROMPT = """你是一个查询分类器。分析用户查询，判断是否需要启用检索增强策略。

- parent_retrieval: 查询需要长段落、完整章节或上下文连续性时开启
- graph_rag: 查询涉及实体关系、比较、因果链或概念关联时开启

用户查询: {query}

仅输出 JSON:
{{"parent": true, "graph": false, "reason": "一句话理由"}}"""


@dataclass(frozen=True)
class RoutingDecision:
    """Routing decision for retrieval enhancements."""

    use_parent_retrieval: bool = False
    use_graph_rag: bool = False
    reasoning: str = ""
    method: str = "config"
    elapsed_ms: float = 0.0


class StrategyRouter:
    """Route retrieval enhancements using config, LLM, and pattern fallback."""

    def __init__(self, settings: Any, llm: Optional[BaseLLM] = None) -> None:
        retrieval = getattr(settings, "retrieval", None)
        self.parent_mode = getattr(retrieval, "parent_retrieval_mode", "never")
        self.graph_mode = getattr(retrieval, "graph_rag_mode", "never")
        self.llm = llm

    def route(self, query: str, trace: Optional[Any] = None) -> RoutingDecision:
        """Return a routing decision for the given query."""
        started = time.monotonic()
        decision: RoutingDecision

        if self.parent_mode != "auto" and self.graph_mode != "auto":
            decision = RoutingDecision(
                use_parent_retrieval=self.parent_mode == "always",
                use_graph_rag=self.graph_mode == "always",
                reasoning="static_config",
                method="config",
            )
        else:
            decision = self._route_with_fallbacks(query)
            decision = RoutingDecision(
                use_parent_retrieval=self._apply_mode_override(
                    self.parent_mode,
                    decision.use_parent_retrieval,
                ),
                use_graph_rag=self._apply_mode_override(
                    self.graph_mode,
                    decision.use_graph_rag,
                ),
                reasoning=decision.reasoning,
                method=decision.method,
            )

        elapsed_ms = (time.monotonic() - started) * 1000.0
        final_decision = RoutingDecision(
            use_parent_retrieval=decision.use_parent_retrieval,
            use_graph_rag=decision.use_graph_rag,
            reasoning=decision.reasoning,
            method=decision.method,
            elapsed_ms=elapsed_ms,
        )

        if trace is not None:
            trace.record_stage(
                "strategy_routing",
                {
                    "method": final_decision.method,
                    "parent_mode": self.parent_mode,
                    "graph_mode": self.graph_mode,
                    "use_parent_retrieval": final_decision.use_parent_retrieval,
                    "use_graph_rag": final_decision.use_graph_rag,
                    "reasoning": final_decision.reasoning,
                },
                elapsed_ms=elapsed_ms,
            )

        return final_decision

    def _route_with_fallbacks(self, query: str) -> RoutingDecision:
        """Run the LLM classifier, then pattern fallback, then default-off."""
        llm_decision = self._route_with_llm(query)
        if llm_decision is not None:
            return llm_decision

        pattern_decision = self._route_with_patterns(query)
        if pattern_decision is not None:
            return pattern_decision

        return RoutingDecision(
            reasoning="default_off_after_fallbacks",
            method="config",
        )

    def _route_with_llm(self, query: str) -> Optional[RoutingDecision]:
        """Classify query intent with the configured LLM."""
        if self.llm is None:
            return None

        try:
            response = self.llm.chat(
                [
                    Message(role="user", content=_CLASSIFIER_PROMPT.format(query=query)),
                ],
                temperature=0.0,
                max_tokens=100,
            )
            parsed = self._parse_llm_response(response.content)
            return RoutingDecision(
                use_parent_retrieval=parsed["parent"],
                use_graph_rag=parsed["graph"],
                reasoning=parsed["reason"],
                method="llm",
            )
        except Exception as exc:
            logger.warning("StrategyRouter LLM classification failed: %s", exc)
            return None

    def _route_with_patterns(self, query: str) -> Optional[RoutingDecision]:
        """Fallback to pattern-based routing when the LLM is unavailable."""
        try:
            parent_match = self._matches_any_pattern(query, _PARENT_PATTERNS)
            graph_match = self._matches_any_pattern(query, _GRAPH_PATTERNS)
            reasons = []
            if parent_match:
                reasons.append("parent_keywords")
            if graph_match:
                reasons.append("graph_keywords")
            return RoutingDecision(
                use_parent_retrieval=parent_match,
                use_graph_rag=graph_match,
                reasoning=",".join(reasons) if reasons else "no_pattern_match",
                method="pattern",
            )
        except Exception as exc:
            logger.warning("StrategyRouter pattern fallback failed: %s", exc)
            return None

    def _apply_mode_override(self, mode: str, auto_value: bool) -> bool:
        """Let static modes override auto decisions."""
        if mode == "always":
            return True
        if mode == "never":
            return False
        return auto_value

    def _matches_any_pattern(self, query: str, patterns: list[str]) -> bool:
        """Return True when any configured pattern matches."""
        return any(re.search(pattern, query, flags=re.IGNORECASE) for pattern in patterns)

    def _parse_llm_response(self, raw_text: str) -> dict[str, Any]:
        """Parse structured JSON from the classifier response."""
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("Classifier response does not contain JSON object")

        parsed = json.loads(text[start:end + 1])
        parent = self._coerce_bool(parsed.get("parent"))
        graph = self._coerce_bool(parsed.get("graph"))
        reason = str(parsed.get("reason", "")).strip() or "llm_classification"

        return {
            "parent": parent,
            "graph": graph,
            "reason": reason,
        }

    def _coerce_bool(self, value: Any) -> bool:
        """Coerce permissive boolean-like values from LLM JSON."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        raise ValueError(f"Expected boolean value, got {value!r}")
