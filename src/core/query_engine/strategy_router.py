import logging
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.libs.llm.base_llm import Message

if TYPE_CHECKING:
    from src.core.settings import Settings
    from src.libs.llm.base_llm import BaseLLM

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutingDecision:
    """Decision on which retrieval augmentation strategies to use.
    
    Attributes:
        use_parent_retrieval: Whether to expand context using parent chunks.
        use_graph_rag: Whether to append graph relationship context.
        reasoning: Optional string explaining the decision.
    """
    use_parent_retrieval: bool
    use_graph_rag: bool
    reasoning: Optional[str] = None


class StrategyRouter:
    """Intelligent router for retrieval augmentation strategies.
    
    Uses LLM-based intent recognition or rule-based patterns to decide 
    whether to apply Parent Document Retrieval and GraphRAG for a given query.
    """

    def __init__(
        self,
        settings: "Settings",
        llm: Optional["BaseLLM"] = None,
    ):
        """Initialize StrategyRouter.
        
        Args:
            settings: Application settings.
            llm: Optional LLM provider for intent recognition.
        """
        self.settings = settings
        self.llm = llm
        
        # Extract modes from settings
        # Default to 'never' if not found (legacy compatibility)
        retrieval_cfg = getattr(settings, "retrieval", None)
        self.parent_mode = getattr(retrieval_cfg, "parent_retrieval_mode", "never")
        self.graph_mode = getattr(retrieval_cfg, "graph_rag_mode", "never")
        
        logger.info(
            f"StrategyRouter initialized: parent_mode={self.parent_mode}, "
            f"graph_mode={self.graph_mode}, llm={llm is not None}"
        )

    def route(self, query: str, trace: Optional[Any] = None) -> RoutingDecision:
        """Route query to appropriate retrieval strategies.
        
        Args:
            query: User's raw query string.
            trace: Optional trace context.
            
        Returns:
            RoutingDecision containing flags for parent retrieval and GraphRAG.
        """
        # 1. Handle explicit 'always' / 'never' modes first (zero cost)
        use_parent = False
        if self.parent_mode == "always":
            use_parent = True
        elif self.parent_mode == "never":
            use_parent = False
        
        use_graph = False
        if self.graph_mode == "always":
            use_graph = True
        elif self.graph_mode == "never":
            use_graph = False

        # 2. If both are deterministic, return immediately
        if self.parent_mode != "auto" and self.graph_mode != "auto":
            return RoutingDecision(
                use_parent_retrieval=use_parent,
                use_graph_rag=use_graph,
                reasoning="Deterministic modes from settings"
            )

        # 3. Strategy recognition (Auto mode)
        # Try LLM first if available, otherwise fallback to patterns
        decision = None
        if self.llm is not None:
            logger.info("[Thinking] Routing: Analyzing query intent with LLM...")
            decision = self._route_with_ll(query, trace=trace)
            
        if decision is None:
            logger.info("[Thinking] Routing: Using pattern matching for strategy selection...")
            decision = self._route_with_patterns(query)

        # 4. Final override based on settings
        final_parent = use_parent if self.parent_mode != "auto" else decision.use_parent_retrieval
        final_graph = use_graph if self.graph_mode != "auto" else decision.use_graph_rag

        return RoutingDecision(
            use_parent_retrieval=final_parent,
            use_graph_rag=final_graph,
            reasoning=decision.reasoning
        )

    def _route_with_ll(self, query: str, trace: Optional[Any] = None) -> Optional[RoutingDecision]:
        """Use LLM to identify query intent and select strategies."""
        if self.llm is None:
            return None

        system_prompt = (
            "You are a RAG Strategy Router. Your task is to analyze user queries and decide "
            "which retrieval augmentation strategies are needed.\n\n"
            "Strategies:\n"
            "1. Parent Retrieval: Use when the query asks for background, context, summaries, "
            "explanations of broad concepts, or 'why/how' questions that need more than a short snippet.\n"
            "2. GraphRAG: Use when the query asks about relationships, connections between entities, "
            "comparisons, or complex networks of information.\n\n"
            "Output your decision in JSON format EXACTLY as shown:\n"
            '{"parent": true/false, "graph": true/false, "reason": "brief explanation"}'
        )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"Query: {query}"),
        ]

        try:
            # Low temperature for consistency
            response = self.llm.chat(messages, trace=trace, temperature=0.1)
            # Find JSON in response
            match = re.search(r"\{.*\}", response.content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return RoutingDecision(
                    use_parent_retrieval=bool(data.get("parent", False)),
                    use_graph_rag=bool(data.get("graph", False)),
                    reasoning=data.get("reason", "LLM decided")
                )
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}")
            
        return None

    def _route_with_patterns(self, query: str) -> RoutingDecision:
        """Rule-based fallback for intent recognition."""
        # Parent Retrieval Patterns: summary, context, broad questions
        parent_patterns = [
            r"什么是|介绍|总结|概括|背景|原理",
            r"what is|explain|summary|background|how does|context",
        ]
        
        # GraphRAG Patterns: relationships, connections, comparisons
        graph_patterns = [
            r"关系|联系|区别|对比|影响|作用",
            r"relationship|connection|vs|compare|impact|between",
        ]

        use_parent = any(re.search(p, query, re.IGNORECASE) for p in parent_patterns)
        use_graph = any(re.search(p, query, re.IGNORECASE) for p in graph_patterns)

        return RoutingDecision(
            use_parent_retrieval=use_parent,
            use_graph_rag=use_graph,
            reasoning="Pattern matching fallback"
        )
