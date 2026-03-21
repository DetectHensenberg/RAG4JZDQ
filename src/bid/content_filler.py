"""Content Filler - 根据大纲填充商务文件内容.

Uses knowledge base retrieval and LLM to fill document sections.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.bid.document_db import (
    BidMaterial,
    BidTemplate,
    get_material,
    list_materials,
    list_templates,
    search_materials,
)
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)

CONTENT_GENERATION_PROMPT = """你是一个专业的投标文件编写助手。请根据以下信息，为投标文件的"{section_title}"章节生成内容。

章节要求：
{clause_description}

可用参考材料：
{reference_materials}

可用模板：
{template_content}

请生成专业、规范的投标文件内容。如果有模板，请按模板格式填写；如果有参考材料，请合理引用。
内容应当：
1. 语言正式、专业
2. 符合招标文件要求
3. 结构清晰

直接输出内容，不要添加额外说明。"""


async def fill_section(
    section: Dict[str, Any],
    clauses: List[Dict[str, Any]],
    llm: Any,
    project_name: str = "",
    project_code: str = "",
) -> str:
    """填充单个章节内容.
    
    Args:
        section: 大纲章节
        clauses: 条款列表
        llm: LLM 实例
        project_name: 项目名称（用于模板变量替换）
        project_code: 项目编号（用于模板变量替换）
    
    Returns:
        填充后的章节内容
    """
    section_title = section.get("title", "")
    clause_ids = section.get("clause_ids", [])
    material_category = section.get("material_category")
    
    related_clauses = [c for c in clauses if c.get("id") in clause_ids]
    clause_description = "\n".join([
        f"- {c.get('title', '')}: {c.get('description', '')}"
        for c in related_clauses
    ]) or "无具体要求"
    
    reference_materials = ""
    if material_category:
        result = list_materials(category=material_category, page_size=5)
        materials = result.get("records", [])
        if materials:
            reference_materials = "\n".join([
                f"【{m['name']}】\n{m.get('content', '')[:500]}"
                for m in materials
            ])
    
    if not reference_materials:
        hits = search_materials(section_title, top_k=3)
        if hits:
            for hit in hits:
                mat = get_material(hit.get("material_id", 0))
                if mat:
                    reference_materials += f"【{mat.name}】\n{mat.content[:500]}\n\n"
    
    if not reference_materials:
        reference_materials = "无可用参考材料"
    
    template_content = ""
    template_result = list_templates(template_type=material_category, page_size=1)
    templates = template_result.get("records", [])
    if templates:
        template_content = templates[0].get("content", "")
        template_content = template_content.replace("{{项目名称}}", project_name)
        template_content = template_content.replace("{{项目编号}}", project_code)
        template_content = template_content.replace("{{公司名称}}", "本公司")
    
    if not template_content:
        template_content = "无可用模板"
    
    prompt = CONTENT_GENERATION_PROMPT.format(
        section_title=section_title,
        clause_description=clause_description,
        reference_materials=reference_materials,
        template_content=template_content,
    )
    
    try:
        messages = [Message(role="user", content=prompt)]
        response = llm.chat(messages)
        return response.content.strip()
    except Exception as e:
        logger.exception(f"Content generation failed for section {section_title}: {e}")
        return f"[内容生成失败: {e}]"


async def fill_outline_stream(
    outline: List[Dict[str, Any]],
    clauses: List[Dict[str, Any]],
    llm: Any,
    project_name: str = "",
    project_code: str = "",
) -> AsyncGenerator[str, None]:
    """流式填充整个大纲（用于 SSE）.
    
    Yields:
        SSE 格式的数据块
    """
    total = len(outline)
    content_map: Dict[str, str] = {}
    
    for i, section in enumerate(outline):
        section_id = section.get("id", str(i))
        section_title = section.get("title", "")
        
        yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'section_id': section_id, 'section_title': section_title}, ensure_ascii=False)}\n\n"
        
        try:
            content = await fill_section(
                section, clauses, llm, project_name, project_code
            )
            content_map[section_id] = content
            
            yield f"data: {json.dumps({'type': 'section', 'section_id': section_id, 'content': content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"Failed to fill section {section_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'section_id': section_id, 'message': str(e)}, ensure_ascii=False)}\n\n"
    
    yield f"data: {json.dumps({'type': 'done', 'content': content_map}, ensure_ascii=False)}\n\n"


def get_material_for_section(section: Dict[str, Any]) -> Optional[BidMaterial]:
    """获取章节对应的材料（用于附件）.
    
    Args:
        section: 大纲章节
    
    Returns:
        匹配的材料，如果没有则返回 None
    """
    material_category = section.get("material_category")
    section_title = section.get("title", "")
    
    if material_category:
        result = list_materials(category=material_category, page_size=1)
        materials = result.get("records", [])
        if materials:
            return get_material(materials[0]["id"])
    
    hits = search_materials(section_title, top_k=1)
    if hits and hits[0].get("score", 0) > 0.6:
        return get_material(hits[0].get("material_id", 0))
    
    return None
