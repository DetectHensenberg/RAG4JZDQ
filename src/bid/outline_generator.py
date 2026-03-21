"""Outline Generator - 根据条款生成商务文件大纲.

Uses LLM to generate structured document outline based on extracted clauses.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from src.bid.document_db import search_materials
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)

OUTLINE_GENERATION_PROMPT = """你是一个专业的投标文件编写助手。请根据以下商务文件条款要求，生成投标文件商务部分的结构化大纲。

条款要求：
{clauses}

请生成一个层次清晰的大纲，包含：
1. 一级标题（如"第一章 公司简介"）
2. 二级标题（如"1.1 企业概况"）
3. 每个章节应对应一个或多个条款要求

输出 JSON 格式：
```json
[
  {{"id": "1", "title": "公司简介", "level": 1, "clause_ids": [1], "material_category": "introduction"}},
  {{"id": "1.1", "title": "企业概况", "level": 2, "clause_ids": [1], "material_category": null}},
  {{"id": "2", "title": "企业资质", "level": 1, "clause_ids": [2, 3], "material_category": "certificate"}},
  {{"id": "2.1", "title": "营业执照", "level": 2, "clause_ids": [2], "material_category": "license"}},
  {{"id": "2.2", "title": "资质证书", "level": 2, "clause_ids": [3], "material_category": "certificate"}}
]
```

字段说明：
- id: 章节编号
- title: 章节标题
- level: 层级（1=一级标题，2=二级标题）
- clause_ids: 对应的条款ID列表
- material_category: 对应的材料分类（certificate/financial/declaration/license/performance/introduction/null）

仅输出 JSON 数组，不要其他内容。"""


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


async def generate_outline(
    clauses: List[Dict[str, Any]],
    llm: Any,
) -> List[Dict[str, Any]]:
    """根据条款生成商务文件大纲.
    
    Args:
        clauses: 条款列表
        llm: LLM 实例
    
    Returns:
        大纲列表，每项包含 id, title, level, clause_ids, material_category
    """
    clauses_text = json.dumps(clauses, ensure_ascii=False, indent=2)
    prompt = OUTLINE_GENERATION_PROMPT.format(clauses=clauses_text)
    
    try:
        messages = [Message(role="user", content=prompt)]
        response = llm.chat(messages)
        outline = _parse_json_from_response(response.content)
        
        for item in outline:
            if "level" not in item:
                item["level"] = 1
            if "clause_ids" not in item:
                item["clause_ids"] = []
            if "material_category" not in item:
                item["material_category"] = None
        
        return outline
    except Exception as e:
        logger.exception(f"Outline generation failed: {e}")
        return []


def enrich_outline_with_matches(outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """为大纲添加知识库匹配状态.
    
    检查每个章节是否有对应的材料可用。
    
    Args:
        outline: 大纲列表
    
    Returns:
        添加了 has_material 字段的大纲列表
    """
    for item in outline:
        category = item.get("material_category")
        if category:
            hits = search_materials(item.get("title", ""), top_k=1)
            item["has_material"] = len(hits) > 0 and hits[0].get("score", 0) > 0.5
        else:
            item["has_material"] = False
    
    return outline


def generate_default_outline(clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据条款生成默认大纲（不使用 LLM）.
    
    用于 LLM 不可用时的降级方案。
    """
    outline: List[Dict[str, Any]] = []
    
    category_map = {
        "certificate": "企业资质",
        "financial": "财务状况",
        "declaration": "声明与承诺",
        "license": "证照材料",
        "performance": "业绩证明",
        "other": "其他材料",
    }
    
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for clause in clauses:
        cat = clause.get("category", "other")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(clause)
    
    chapter_num = 1
    for cat, cat_clauses in grouped.items():
        cat_title = category_map.get(cat, "其他材料")
        outline.append({
            "id": str(chapter_num),
            "title": cat_title,
            "level": 1,
            "clause_ids": [c["id"] for c in cat_clauses],
            "material_category": cat,
            "has_material": False,
        })
        
        for i, clause in enumerate(cat_clauses, 1):
            outline.append({
                "id": f"{chapter_num}.{i}",
                "title": clause.get("title", f"条款{clause['id']}"),
                "level": 2,
                "clause_ids": [clause["id"]],
                "material_category": cat,
                "has_material": False,
            })
        
        chapter_num += 1
    
    return outline
