"""Clause Extractor - 从招标文件中提取商务文件条款要求.

Uses LLM to parse tender documents and extract structured clause requirements.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List

from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)

CLAUSE_EXTRACTION_PROMPT = """你是一个专业的招标文件分析助手。请从以下招标文件内容中提取商务文件要求条款。

招标文件内容：
{content}

请识别所有商务文件相关的要求，包括但不限于：
- 企业资质证书（营业执照、资质证书等）
- 财务报表（审计报告、财务报表等）
- 法人/授权代表证明（身份证、授权书等）
- 声明函/承诺书
- 业绩证明材料
- 其他商务文件要求

请以 JSON 格式输出，每个条款包含：
- id: 序号（从1开始）
- title: 条款标题（简洁明了，如"企业营业执照"）
- description: 具体要求描述
- category: 分类（certificate/financial/declaration/license/performance/other）
- required: 是否必须（true/false）
- source_page: 来源页码（如有，格式如"第X页"）

输出格式（仅输出JSON数组，不要其他内容）：
```json
[
  {{"id": 1, "title": "企业营业执照", "description": "提供有效期内的营业执照副本复印件，加盖公章", "category": "certificate", "required": true, "source_page": "第5页"}}
]
```"""


def _parse_json_from_response(response: str) -> List[Dict[str, Any]]:
    """Extract JSON array from LLM response."""
    json_match = re.search(r'\[[\s\S]*\]', response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from LLM response")
        return []


async def extract_clauses(
    content: str,
    llm: Any,
    max_content_length: int = 12000,
) -> List[Dict[str, Any]]:
    """从招标文件内容中提取商务文件条款.
    
    Args:
        content: 招标文件文本内容
        llm: LLM 实例（需要有 agenerate 方法）
        max_content_length: 最大内容长度（避免超出 token 限制）
    
    Returns:
        条款列表，每个条款包含 id, title, description, category, required, source_page
    """
    truncated_content = content[:max_content_length]
    if len(content) > max_content_length:
        truncated_content += "\n...(内容已截断)"
    
    prompt = CLAUSE_EXTRACTION_PROMPT.format(content=truncated_content)
    
    try:
        messages = [Message(role="user", content=prompt)]
        response = llm.chat(messages)
        clauses = _parse_json_from_response(response.content)
        
        for i, clause in enumerate(clauses):
            if "id" not in clause:
                clause["id"] = i + 1
            if "required" not in clause:
                clause["required"] = True
            if "category" not in clause:
                clause["category"] = "other"
        
        return clauses
    except Exception as e:
        logger.exception(f"Clause extraction failed: {e}")
        return []


async def extract_clauses_stream(
    content: str,
    llm: Any,
    max_content_length: int = 12000,
) -> AsyncGenerator[str, None]:
    """流式提取条款（用于 SSE）.
    
    Yields:
        SSE 格式的数据块
    """
    truncated_content = content[:max_content_length]
    if len(content) > max_content_length:
        truncated_content += "\n...(内容已截断)"
    
    prompt = CLAUSE_EXTRACTION_PROMPT.format(content=truncated_content)
    
    collected = ""
    try:
        messages = [Message(role="user", content=prompt)]
        for chunk in llm.chat_stream(messages):
            collected += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
        
        clauses = _parse_json_from_response(collected)
        for i, clause in enumerate(clauses):
            if "id" not in clause:
                clause["id"] = i + 1
            if "required" not in clause:
                clause["required"] = True
            if "category" not in clause:
                clause["category"] = "other"
        
        yield f"data: {json.dumps({'type': 'done', 'clauses': clauses}, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.exception(f"Clause extraction stream failed: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
