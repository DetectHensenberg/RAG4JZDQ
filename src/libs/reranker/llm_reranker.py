"""LLM-based Reranker implementation.

This module implements reranking using Large Language Models to evaluate
the relevance of candidate passages to a given query. It reads prompts from
config/prompts/rerank.txt and structures LLM outputs for downstream processing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.settings import resolve_path
from src.libs.llm.base_llm import BaseLLM, Message
from src.libs.llm.llm_factory import LLMFactory
from src.libs.reranker.base_reranker import BaseReranker


class LLMRerankError(RuntimeError):
    """Raised when LLM reranking fails."""


class LLMReranker(BaseReranker):
    """LLM-based reranker using structured prompts.
    
    This implementation leverages an LLM to score and rerank candidate passages
    based on their relevance to a query. It reads the reranking prompt from
    a configurable file and expects structured JSON output from the LLM.
    
    Design Principles Applied:
    - Pluggable: Can be swapped with other reranker implementations via factory.
    - Config-Driven: Prompt file path and LLM settings come from configuration.
    - Observable: Supports TraceContext for monitoring (Stage F integration).
    - Fallback-Aware: Returns signal on failure for upstream fallback logic.
    - Structured Output: Validates LLM output against expected schema.
    """
    
    def __init__(
        self,
        settings: Any,
        prompt_path: Optional[str] = None,
        llm: Optional[BaseLLM] = None,
        **kwargs: Any
    ) -> None:
        """Initialize the LLM Reranker.
        
        Args:
            settings: Application settings containing LLM and rerank configuration.
            prompt_path: Optional path to rerank prompt file. If None, uses default
                'config/prompts/rerank.txt'. Used for testing to inject custom prompts.
            llm: Optional LLM instance. If None, creates via LLMFactory from settings.
                Used for testing to inject mock LLMs.
            **kwargs: Additional provider-specific parameters.
        """
        self.settings = settings
        self.prompt_path = prompt_path or str(resolve_path("config/prompts/rerank.txt"))
        self.llm = llm or LLMFactory.create(settings)
        self.kwargs = kwargs
        
        # Load prompt template
        try:
            self.prompt_template = self._load_prompt_template(self.prompt_path)
        except Exception as e:
            raise LLMRerankError(f"Failed to load rerank prompt from {self.prompt_path}: {e}") from e
    
    def _load_prompt_template(self, path: str) -> str:
        """Load the rerank prompt template from file.
        
        Args:
            path: Path to the prompt template file.
        
        Returns:
            The prompt template as a string.
        
        Raises:
            FileNotFoundError: If prompt file doesn't exist.
            IOError: If file can't be read.
        """
        prompt_file = Path(path)
        if not prompt_file.exists():
            raise FileNotFoundError(f"Rerank prompt file not found: {path}")
        
        return prompt_file.read_text(encoding="utf-8")
    
    def _build_rerank_prompt(self, query: str, candidates: List[Dict[str, Any]]) -> str:
        """Build the reranking prompt with query and candidates.
        
        Args:
            query: The user query string.
            candidates: List of candidate records to rerank.
        
        Returns:
            Formatted prompt string ready for LLM.
        """
        # Format candidates for the prompt
        candidates_text = []
        for i, candidate in enumerate(candidates):
            passage_id = candidate.get("id", f"passage_{i}")
            text = candidate.get("text", candidate.get("content", ""))
            candidates_text.append(f"Passage ID: {passage_id}\nText: {text}\n")
        
        candidates_str = "\n".join(candidates_text)
        
        # Construct full prompt
        full_prompt = f"{self.prompt_template}\n\nQuery: {query}\n\nPassages:\n{candidates_str}\n\nOutput your response as a JSON array of objects, one per passage."
        
        return full_prompt
    
    def _parse_llm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse and validate LLM response.
        
        Args:
            response_text: Raw text response from LLM.
        
        Returns:
            List of parsed ranking records with passage_id and score.
        
        Raises:
            LLMRerankError: If response doesn't match expected schema.
        """
        # Try to extract JSON from response (LLM might wrap in markdown)
        text = response_text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Parse JSON
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMRerankError(
                f"LLM response is not valid JSON: {e}\nResponse: {response_text[:200]}"
            ) from e
        
        # Validate structure
        if not isinstance(parsed, list):
            raise LLMRerankError(
                f"Expected JSON array, got {type(parsed).__name__}\nResponse: {response_text[:200]}"
            )
        
        # Validate each item
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise LLMRerankError(
                    f"Item {i} is not a dict (type: {type(item).__name__})"
                )
            if "passage_id" not in item:
                raise LLMRerankError(f"Item {i} missing required field 'passage_id'")
            if "score" not in item:
                raise LLMRerankError(f"Item {i} missing required field 'score'")
            
            # Validate score is numeric
            score = item["score"]
            if not isinstance(score, (int, float)):
                raise LLMRerankError(
                    f"Item {i} score must be numeric, got {type(score).__name__}: {score}"
                )
        
        return parsed
    
    def _map_results_to_candidates(
        self,
        parsed_results: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Map LLM ranking results back to original candidate objects.
        
        Args:
            parsed_results: Parsed LLM output with passage_id and score.
            candidates: Original candidate list.
        
        Returns:
            Reranked list of candidate objects, sorted by score descending.
        """
        # Create mapping from id to candidate
        id_to_candidate = {}
        for i, candidate in enumerate(candidates):
            candidate_id = candidate.get("id", f"passage_{i}")
            id_to_candidate[candidate_id] = candidate
        
        # Build reranked list
        reranked = []
        for result in parsed_results:
            passage_id = result["passage_id"]
            score = result["score"]
            
            if passage_id in id_to_candidate:
                candidate = id_to_candidate[passage_id].copy()
                # Update score with LLM rerank score
                candidate["rerank_score"] = float(score)
                reranked.append(candidate)
        
        # Sort by rerank score descending
        reranked.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        
        return reranked
    
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Rerank candidates using LLM-based relevance scoring.
        
        Args:
            query: The user query string.
            candidates: List of candidate records to rerank.
            trace: Optional TraceContext for observability.
            **kwargs: Additional parameters (timeout, temperature, etc.).
        
        Returns:
            Reranked list of candidates sorted by LLM-assigned relevance score.
            On success, each candidate will have 'rerank_score' in metadata.
        
        Raises:
            ValueError: If query or candidates are invalid.
            LLMRerankError: If LLM call fails or response is malformed.
        """
        # Validate inputs
        self.validate_query(query)
        self.validate_candidates(candidates)
        
        # If only one candidate, no need to rerank
        if len(candidates) == 1:
            return candidates
        
        # Build prompt
        try:
            prompt = self._build_rerank_prompt(query, candidates)
        except Exception as e:
            raise LLMRerankError(f"Failed to build rerank prompt: {e}") from e
        
        # Call LLM
        try:
            messages = [Message(role="user", content=prompt)]
            response = self.llm.chat(messages, trace=trace, **kwargs)
            response_text = response.content
        except Exception as e:
            # Return fallback signal - let upstream decide how to handle
            raise LLMRerankError(f"LLM call failed during reranking: {e}") from e
        
        # Parse response
        try:
            parsed_results = self._parse_llm_response(response_text)
        except LLMRerankError:
            raise
        except Exception as e:
            raise LLMRerankError(f"Failed to parse LLM rerank response: {e}") from e
        
        # Map back to candidates and sort
        try:
            reranked = self._map_results_to_candidates(parsed_results, candidates)
        except Exception as e:
            raise LLMRerankError(f"Failed to map LLM results to candidates: {e}") from e
        
        return reranked
