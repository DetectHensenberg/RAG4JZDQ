"""Outline Generator — 基于需求 + 模板/RAG 生成方案大纲.

两种模式：
1. 有模板时：以 template_outline 为骨架，LLM 将需求分配到对应章节
2. 无模板时：RAG 检索历史方案参考 + LLM 自动生成大纲
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.libs.llm.base_llm import BaseLLM, Message

logger = logging.getLogger(__name__)

# ── 有模板时的 Prompt ────────────────────────────────────────────

TEMPLATE_OUTLINE_PROMPT = """你是技术方案编写专家。现在有一个方案模板的目录结构和客户的需求清单。

请基于模板目录结构，将需求分配到对应的章节。
- 保持模板的目录结构不变
- 为每个章节标注它应涵盖的需求 ID
- 如果某些需求不属于任何现有章节，可新增章节
- 为每个章节补充用于知识库检索的关键词

模板目录结构：
{template_outline}

需求清单：
{requirements}

请以 JSON 数组格式输出，每项包含:
- id: 章节 ID（保持模板的 ID）
- title: 章节标题
- level: 层级（1/2/3）
- requirement_ids: 对应的需求 ID 列表
- keywords: 知识库检索关键词列表（3-5个）

仅输出 JSON 数组，不要包含其他内容。"""

# ── 无模板时的 Prompt ────────────────────────────────────────────

AUTO_OUTLINE_PROMPT = """你是技术方案编写专家。请根据以下需求清单，生成一份技术方案的目录大纲。

需求清单：
{requirements}

{reference_context}

请生成一份专业的技术方案目录大纲，典型的技术方案应包含：
1. 项目概述（背景、目标、范围）
2. 需求分析（功能/非功能需求梳理）
3. 系统总体设计（架构、技术选型）
4. 详细设计（根据具体需求展开）
5. 实施方案（部署、进度计划）
6. 质量保障（测试策略、运维方案）
7. 项目管理（组织架构、风险管控）

请以 JSON 数组格式输出，每项包含:
- id: 章节ID（如 SEC-001）
- title: 章节标题
- level: 层级（1代表一级标题，2代表二级标题，3代表三级标题）
- requirement_ids: 对应的需求 ID 列表
- keywords: 知识库检索关键词列表（3-5个）

仅输出 JSON 数组，不要包含其他内容。"""


def _parse_outline_json(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中解析大纲 JSON.

    Args:
        text: LLM 原始输出

    Returns:
        解析后的大纲列表
    """
    # 尝试提取代码块
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 找 [ ... ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("无法解析大纲 JSON")
    return []


async def generate_outline(
    requirements: List[Dict[str, Any]],
    llm: BaseLLM,
    template_outline: Optional[List[Dict[str, Any]]] = None,
    hybrid_search: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """生成方案大纲.

    Args:
        requirements: 结构化需求列表
        llm: LLM 实例
        template_outline: 可选的模板大纲（有模板时传入）
        hybrid_search: 可选的混合检索实例（无模板时用于检索历史方案）

    Returns:
        方案大纲列表 [{id, title, level, requirement_ids, keywords}]
    """
    req_text = json.dumps(requirements, ensure_ascii=False, indent=2)

    if template_outline:
        # 模式 1：有模板 → 基于模板骨架分配需求
        tpl_text = json.dumps(template_outline, ensure_ascii=False, indent=2)
        prompt = TEMPLATE_OUTLINE_PROMPT.format(
            template_outline=tpl_text,
            requirements=req_text,
        )
    else:
        # 模式 2：无模板 → RAG 检索参考 + LLM 生成
        reference_context = ""
        if hybrid_search:
            try:
                # 用需求关键词检索历史方案
                all_keywords = []
                for req in requirements[:5]:
                    all_keywords.extend(req.get("keywords", []))
                    all_keywords.append(req.get("title", ""))

                query = " ".join(all_keywords[:10])
                results = hybrid_search.search(query=query, top_k=5)
                if results:
                    ref_texts = []
                    for r in results[:3]:
                        if r.text:
                            ref_texts.append(r.text[:500])
                    if ref_texts:
                        reference_context = (
                            "以下是知识库中相关方案的参考内容：\n"
                            + "\n---\n".join(ref_texts)
                        )
            except Exception as e:
                logger.warning(f"RAG 检索参考方案失败: {e}")

        prompt = AUTO_OUTLINE_PROMPT.format(
            requirements=req_text,
            reference_context=reference_context,
        )

    messages = [Message(role="user", content=prompt)]

    try:
        response = llm.chat(messages)
        outline = _parse_outline_json(response.content)

        # 确保每项都有必要字段
        for i, item in enumerate(outline):
            if not item.get("id"):
                item["id"] = f"SEC-{i + 1:03d}"
            if not item.get("level"):
                item["level"] = 1
            if not item.get("requirement_ids"):
                item["requirement_ids"] = []
            if not item.get("keywords"):
                item["keywords"] = []

        logger.info(f"生成大纲 {len(outline)} 个章节")
        return outline
    except Exception as e:
        logger.exception(f"大纲生成失败: {e}")
        raise


def generate_default_outline(
    requirements: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """生成默认大纲（LLM 失败时的兜底方案）.

    Args:
        requirements: 结构化需求列表

    Returns:
        默认的方案大纲
    """
    default_sections = [
        {"id": "SEC-001", "title": "项目概述", "level": 1},
        {"id": "SEC-002", "title": "项目背景", "level": 2},
        {"id": "SEC-003", "title": "建设目标", "level": 2},
        {"id": "SEC-004", "title": "建设范围", "level": 2},
        {"id": "SEC-005", "title": "需求分析", "level": 1},
        {"id": "SEC-006", "title": "功能需求", "level": 2},
        {"id": "SEC-007", "title": "非功能需求", "level": 2},
        {"id": "SEC-008", "title": "系统总体设计", "level": 1},
        {"id": "SEC-009", "title": "系统架构", "level": 2},
        {"id": "SEC-010", "title": "技术选型", "level": 2},
        {"id": "SEC-011", "title": "详细设计", "level": 1},
        {"id": "SEC-012", "title": "实施方案", "level": 1},
        {"id": "SEC-013", "title": "部署方案", "level": 2},
        {"id": "SEC-014", "title": "进度计划", "level": 2},
        {"id": "SEC-015", "title": "质量保障", "level": 1},
        {"id": "SEC-016", "title": "项目管理", "level": 1},
    ]

    # 将需求分配到对应章节
    for req in requirements:
        cat = req.get("category", "")
        if cat == "functional":
            default_sections[5].setdefault("requirement_ids", []).append(
                req.get("id", "")
            )
        elif cat == "non_functional":
            default_sections[6].setdefault("requirement_ids", []).append(
                req.get("id", "")
            )

    for s in default_sections:
        s.setdefault("requirement_ids", [])
        s.setdefault("keywords", [])

    return default_sections
