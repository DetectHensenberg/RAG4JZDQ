"""SuggestedQuestionGenerator - Generates follow-up questions using LLM."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, Message
from src.libs.llm.llm_factory import LLMFactory
from src.core.settings import Settings

logger = logging.getLogger(__name__)


class SuggestedQuestionGenerator:
    """Generates relevant follow-up questions based on query and answer.
    
    This component uses a Language Model to analyze the current interaction
    and suggest 3 concise questions the user might want to ask next.
    """
    
    DEFAULT_PROMPT = """你是一个专业的助手。请根据以下用户提问和你的回答，生成 3 个用户接下来最可能感兴趣的追问。

要求：
1. 追问必须与当前的提问和回答上下文高度相关。
2. 语言简练、专业且易于点击提问。
3. 必须输出为 JSON 数组格式，例如: ["追问1", "追问2", "追问3"]。
4. 严禁包含任何 JSON 以外的解释性文本。

用户提问：{query}
你的回答：{answer}
"""

    def __init__(self, settings: Settings, llm: Optional[BaseLLM] = None):
        """Initialize with settings and optional LLM instance.
        
        Args:
            settings: Application settings.
            llm: Optional pre-configured LLM instance. If None, created via factory.
        """
        self.settings = settings
        self._llm = llm

    @property
    def llm(self) -> BaseLLM:
        """Get or create LLM instance."""
        if self._llm is None:
            self._llm = LLMFactory.create(self.settings)
        return self._llm

    async def generate(self, query: str, answer: str) -> List[str]:
        """Generate 3 suggested questions based on query and answer.
        
        Args:
            query: The original user question.
            answer: The generated answer from the RAG system.
            
        Returns:
            List of 3 suggested question strings. Returns empty list on failure.
        """
        if not query or not answer:
            return []
            
        prompt = self.DEFAULT_PROMPT.format(query=query, answer=answer)
        
        try:
            messages = [
                Message(role="system", content="You are a helpful assistant that generates JSON arrays of follow-up questions."),
                Message(role="user", content=prompt)
            ]
            
            # Using low temperature for deterministic and formatted output
            response = await self.llm.chat(messages, temperature=0.1)
            content = response.content.strip()
            
            return self._parse_json_result(content)
            
        except Exception as e:
            logger.warning(f"Failed to generate suggested questions: {e}")
            return []

    def _parse_json_result(self, content: str) -> List[str]:
        """Parse JSON array from LLM response content.
        
        Handles potential Markdown code blocks and extra text.
        """
        # 1. Try direct JSON parse
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return [str(q) for q in data[:3]]
        except json.JSONDecodeError:
            pass
            
        # 2. Try extract from markdown code blocks
        match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if isinstance(data, list):
                    return [str(q) for q in data[:3]]
            except json.JSONDecodeError:
                pass
                
        # 3. Try find anything that looks like a JSON array [ ... ]
        array_match = re.search(r'\[\s*".*?"\s*(?:,\s*".*?"\s*)*\]', content, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group(0))
                if isinstance(data, list):
                    return [str(q) for q in data[:3]]
            except json.JSONDecodeError:
                pass
                
        logger.warning(f"Could not parse suggested questions from LLM response: {content[:100]}...")
        return []
