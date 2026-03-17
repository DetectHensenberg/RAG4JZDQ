"""Query Rewriter with LLM-based rewriting and HyDE expansion.

This module provides query enhancement capabilities:
1. LLM Query Rewriting: Transforms user queries into retrieval-friendly formats
2. HyDE (Hypothetical Document Embedding): Generates hypothetical documents for better semantic matching

Design Principles:
- Optional: Both features can be disabled via configuration
- Graceful degradation: Falls back to original query on LLM errors
- Configurable: Prompts and behavior controlled via settings
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.core.settings import Settings
    from src.libs.llm.base import BaseLLM

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    """Result of query rewriting."""
    
    original_query: str
    rewritten_queries: List[str]
    hyde_document: Optional[str] = None
    rewrite_used: bool = False
    hyde_used: bool = False


class QueryRewriter:
    """LLM-based query rewriting and HyDE expansion.
    
    Enhances user queries for better retrieval performance by:
    1. Rewriting queries into multiple retrieval-friendly variants
    2. Generating hypothetical documents that might answer the query
    
    Example:
        >>> rewriter = QueryRewriter(settings, llm)
        >>> result = rewriter.rewrite("九洲搞什么的")
        >>> print(result.rewritten_queries)
        ['九洲公司的主营业务是什么', '九洲集团的业务范围', '九洲的核心产品和服务']
    """
    
    REWRITE_PROMPT = """请将以下用户问题改写为2-3个更适合知识库检索的规范表述。
要求：
1. 保持原意，但使用更正式、更具体的表达
2. 每行输出一个改写结果
3. 不要添加编号或其他格式

用户问题：{query}

改写结果："""

    HYDE_PROMPT = """请根据以下问题，写一段可能回答该问题的文档片段（50-100字）。
要求：
1. 假设你是知识库中的一篇文档
2. 直接给出内容，不要说"根据问题"等开头
3. 使用专业、正式的语言

问题：{query}

文档片段："""

    def __init__(
        self,
        settings: Settings,
        llm: Optional[BaseLLM] = None,
    ):
        """Initialize QueryRewriter.
        
        Args:
            settings: Application settings
            llm: LLM client for rewriting. If None, will be created from settings.
        """
        self._settings = settings
        self._llm = llm
        
        # Get configuration
        retrieval = getattr(settings, "retrieval", None)
        self._rewrite_enabled = getattr(retrieval, "query_rewrite", False) if retrieval else False
        self._hyde_enabled = getattr(retrieval, "hyde_enabled", False) if retrieval else False
        
        logger.info(
            f"QueryRewriter initialized: rewrite={self._rewrite_enabled}, hyde={self._hyde_enabled}"
        )
    
    def _get_llm(self) -> Optional[BaseLLM]:
        """Get or create LLM client."""
        if self._llm is not None:
            return self._llm
        
        try:
            from src.libs.llm.llm_factory import LLMFactory
            self._llm = LLMFactory.create(self._settings)
            return self._llm
        except Exception as e:
            logger.warning(f"Failed to create LLM for query rewriting: {e}")
            return None
    
    def rewrite(self, query: str) -> RewriteResult:
        """Rewrite query and optionally generate HyDE document.
        
        Args:
            query: Original user query
            
        Returns:
            RewriteResult with rewritten queries and optional HyDE document
        """
        result = RewriteResult(
            original_query=query,
            rewritten_queries=[query],  # Always include original
        )
        
        if not query or not query.strip():
            return result
        
        # LLM Query Rewriting
        if self._rewrite_enabled:
            rewritten = self._do_rewrite(query)
            if rewritten:
                result.rewritten_queries = [query] + rewritten  # Original + rewritten
                result.rewrite_used = True
        
        # HyDE Expansion
        if self._hyde_enabled:
            hyde_doc = self._do_hyde(query)
            if hyde_doc:
                result.hyde_document = hyde_doc
                result.hyde_used = True
        
        return result
    
    def _do_rewrite(self, query: str) -> List[str]:
        """Perform LLM-based query rewriting.
        
        Args:
            query: Original query
            
        Returns:
            List of rewritten queries (empty on failure)
        """
        llm = self._get_llm()
        if llm is None:
            return []
        
        try:
            prompt = self.REWRITE_PROMPT.format(query=query)
            response = llm.generate(prompt)
            
            # Parse response: each line is a rewritten query
            rewritten = []
            for line in response.strip().split("\n"):
                line = line.strip()
                # Skip empty lines and lines that look like numbering
                if line and not line[0].isdigit():
                    rewritten.append(line)
                elif line and line[0].isdigit():
                    # Remove numbering like "1. " or "1) "
                    cleaned = line.lstrip("0123456789.）) ").strip()
                    if cleaned:
                        rewritten.append(cleaned)
            
            logger.debug(f"Query rewrite: '{query}' -> {rewritten}")
            return rewritten[:3]  # Limit to 3 rewrites
            
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            return []
    
    def _do_hyde(self, query: str) -> Optional[str]:
        """Generate hypothetical document for HyDE.
        
        Args:
            query: Original query
            
        Returns:
            Hypothetical document text, or None on failure
        """
        llm = self._get_llm()
        if llm is None:
            return None
        
        try:
            prompt = self.HYDE_PROMPT.format(query=query)
            response = llm.generate(prompt)
            
            hyde_doc = response.strip()
            if hyde_doc:
                logger.debug(f"HyDE generated: '{query}' -> '{hyde_doc[:50]}...'")
                return hyde_doc
            return None
            
        except Exception as e:
            logger.warning(f"HyDE generation failed: {e}")
            return None
    
    @property
    def rewrite_enabled(self) -> bool:
        """Whether query rewriting is enabled."""
        return self._rewrite_enabled
    
    @property
    def hyde_enabled(self) -> bool:
        """Whether HyDE is enabled."""
        return self._hyde_enabled
