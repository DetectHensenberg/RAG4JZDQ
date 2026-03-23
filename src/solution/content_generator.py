"""Content Generator — 逐章节 RAG + LLM 融合生成方案内容.

复用 src/bid/content_filler.py 的 SSE 流式填充模式。
对每个章节：检索知识库素材 → LLM 融合生成 → SSE 推送。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, Message
from src.solution.solution_db import SolutionSession

logger = logging.getLogger(__name__)

SECTION_GENERATION_PROMPT = """你是资深技术方案编写专家。
请根据以下信息编写技术方案的「{section_title}」章节。

【项目名称】
{project_name}

【客户需求】
{requirement_text}

【参考素材】（来自知识库检索）
{reference_materials}

【上文摘要】
{previous_context}

【编写要求】
1. 内容必须针对客户需求进行定制化回应
2. 可参考素材中的已有方案但不能照搬
3. 使用专业但易懂的技术语言
4. 适当使用小标题组织内容
5. 字数控制在 600-1200 字
6. 使用 Markdown 格式

直接输出章节内容，不要重复章节标题，不要添加额外说明。"""


def _build_query(
    section: Dict[str, Any],
    requirements: List[Dict[str, Any]],
) -> str:
    """构建用于知识库检索的查询文本.

    Args:
        section: 大纲章节
        requirements: 完整需求列表

    Returns:
        组合查询文本
    """
    parts = [section.get("title", "")]

    # 添加章节关键词
    keywords = section.get("keywords", [])
    if keywords:
        parts.extend(keywords[:3])

    # 添加关联需求的标题
    req_ids = section.get("requirement_ids", [])
    for req in requirements:
        if req.get("id") in req_ids:
            parts.append(req.get("title", ""))

    return " ".join(parts)


def _format_requirements(
    section: Dict[str, Any],
    requirements: List[Dict[str, Any]],
) -> str:
    """格式化章节关联的需求文本.

    Args:
        section: 大纲章节
        requirements: 完整需求列表

    Returns:
        格式化的需求描述
    """
    req_ids = section.get("requirement_ids", [])
    related = [r for r in requirements if r.get("id") in req_ids]

    if not related:
        return "无具体需求关联"

    lines = []
    for r in related:
        lines.append(f"- [{r.get('category', '')}] {r.get('title', '')}: "
                      f"{r.get('description', '')}")
    return "\n".join(lines)


async def generate_section_content(
    section: Dict[str, Any],
    requirements: List[Dict[str, Any]],
    llm: BaseLLM,
    project_name: str = "",
    hybrid_search: Optional[Any] = None,
    collection: str = "default",
    previous_context: str = "",
) -> str:
    """生成单个章节的内容.

    Args:
        section: 大纲章节
        requirements: 完整需求列表
        llm: LLM 实例
        project_name: 项目名称
        hybrid_search: 混合检索实例
        collection: 知识库集合名
        previous_context: 前文摘要（保持连贯性）

    Returns:
        生成的章节 Markdown 内容
    """
    section_title = section.get("title", "")
    requirement_text = _format_requirements(section, requirements)

    # RAG 检索知识库素材
    reference_materials = "无可用参考素材"
    if hybrid_search:
        try:
            query = _build_query(section, requirements)
            results = hybrid_search.search(query=query, top_k=5)
            if results:
                ref_parts = []
                for r in results:
                    if r.text:
                        source = ""
                        if r.metadata:
                            source = r.metadata.get("source_path", "")
                        ref_parts.append(
                            f"[来源: {source}]\n{r.text[:600]}"
                        )
                if ref_parts:
                    reference_materials = "\n\n---\n\n".join(ref_parts[:3])
        except Exception as e:
            logger.warning(f"知识库检索失败 ({section_title}): {e}")

    prompt = SECTION_GENERATION_PROMPT.format(
        section_title=section_title,
        project_name=project_name or "（未指定）",
        requirement_text=requirement_text,
        reference_materials=reference_materials,
        previous_context=previous_context or "（无）",
    )

    try:
        messages = [Message(role="user", content=prompt)]
        response = llm.chat(messages)
        return response.content.strip()
    except Exception as e:
        logger.exception(f"章节内容生成失败 ({section_title}): {e}")
        return f"[章节内容生成失败: {e}]"


async def generate_content_stream(
    session: SolutionSession,
    llm: BaseLLM,
    hybrid_search: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """流式生成所有章节内容（SSE 格式）.

    对每个章节：
    1. 推送 progress 事件
    2. RAG 检索 + LLM 生成
    3. 推送 section 事件（含内容）
    4. 全部完成后推送 done 事件

    Args:
        session: 方案会话
        llm: LLM 实例
        hybrid_search: 混合检索实例

    Yields:
        SSE 格式的数据块
    """
    outline = session.outline
    requirements = session.requirements
    total = len(outline)
    content_map: Dict[str, str] = {}
    previous_context = ""

    for i, section in enumerate(outline):
        section_id = section.get("id", str(i))
        section_title = section.get("title", "")
        level = section.get("level", 1)

        # 跳过非叶子节点（仅生成最具体层级的内容）
        # 但一级标题如果没有子标题，也需要生成
        has_children = False
        if i + 1 < total:
            next_level = outline[i + 1].get("level", 1)
            if next_level > level:
                has_children = True

        yield _sse(
            {
                "type": "progress",
                "current": i + 1,
                "total": total,
                "section_id": section_id,
                "section_title": section_title,
            }
        )

        if has_children and level < 3:
            # 容器章节，不生成内容
            content_map[section_id] = ""
            continue

        try:
            content = await generate_section_content(
                section=section,
                requirements=requirements,
                llm=llm,
                project_name=session.project_name,
                hybrid_search=hybrid_search,
                collection=session.collection,
                previous_context=previous_context,
            )
            content_map[section_id] = content

            # 更新前文摘要（取最近内容的前200字作为上下文）
            if content and not content.startswith("["):
                previous_context = f"上一章节「{section_title}」要点:\n{content[:200]}"

            yield _sse(
                {
                    "type": "section",
                    "section_id": section_id,
                    "section_title": section_title,
                    "content": content,
                }
            )
        except Exception as e:
            logger.exception(f"章节生成失败 {section_id}: {e}")
            yield _sse(
                {
                    "type": "error",
                    "section_id": section_id,
                    "message": str(e),
                }
            )

    yield _sse({"type": "done", "content": content_map})


def _sse(data: Dict[str, Any]) -> str:
    """格式化 SSE 数据行.

    Args:
        data: 要发送的数据字典

    Returns:
        SSE 格式字符串
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
