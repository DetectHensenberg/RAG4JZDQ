"""LLM-based product parameter extractor.

Reads prompt template from bid-param-extractor skill, sends chunk text
to LLM, and parses structured parameter JSON from the response.
Each extracted param includes page number and section for traceability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.settings import REPO_ROOT

logger = logging.getLogger(__name__)

_SKILL_DIR = REPO_ROOT / ".github" / "skills" / "bid-param-extractor"
_PROMPT_PATH = _SKILL_DIR / "references" / "extraction_prompt.md"

_FALLBACK_PROMPT = """你是一位专业的产品技术参数提取专家。请从以下产品技术文档片段中提取所有技术参数。

文档来源信息：
- 页码：{page_number}
- 章节：{section_hint}

严格要求：
1. 输出严格的 JSON 格式，不要输出其他内容
2. 参数名称使用中文
3. 保留原始数值和单位，不做任何转换或推算
4. 如果文本中包含表格，识别行列对应关系提取参数
5. 每个参数必须标注来源页码(page)和所在章节(section)

输出格式：
{{
  "products": [
    {{
      "product_name": "产品通用名称",
      "model": "具体型号",
      "vendor": "厂家名称",
      "category": "产品大类",
      "params": [
        {{"name": "参数名", "value": "参数值", "unit": "单位", "page": 页码数字, "section": "章节"}}
      ]
    }}
  ]
}}

文档片段：
{chunk_text}"""


@dataclass
class ChunkMeta:
    """Metadata for a single document chunk."""

    text: str = ""
    page: int = 0
    section: str = ""
    source: str = ""


def _load_prompt_template() -> str:
    """Load extraction prompt from skill references, with fallback."""
    if _PROMPT_PATH.exists():
        try:
            content = _PROMPT_PATH.read_text(encoding="utf-8")
            lines = content.split("```")
            if len(lines) >= 3:
                prompt_block = lines[1]
                prompt_lines = prompt_block.strip().split("\n")
                if prompt_lines and not prompt_lines[0].strip().startswith("{"):
                    prompt_lines = prompt_lines[1:]
                return "\n".join(prompt_lines)
        except Exception as e:
            logger.warning(f"Failed to load skill prompt: {e}")
    logger.warning("Skill prompt not found, using fallback")
    return _FALLBACK_PROMPT


def extract_params_from_text(
    llm: Any,
    text: str,
    *,
    page: int = 0,
    section: str = "",
    max_retries: int = 1,
) -> List[Dict[str, Any]]:
    """Extract product parameters from a text chunk using LLM.

    Args:
        llm: A BaseLLM instance (from LLMFactory).
        text: The document text chunk to extract parameters from.
        page: PDF page number for this chunk.
        section: Section/chapter hint for this chunk.
        max_retries: Number of retries on JSON parse failure.

    Returns:
        List of product dicts with extracted parameters (including page/section).
    """
    from src.libs.llm.base_llm import Message

    if not text or not text.strip():
        return []

    template = _load_prompt_template()
    prompt = (
        template
        .replace("{chunk_text}", text)
        .replace("{page_number}", str(page) if page else "未知")
        .replace("{section_hint}", section or "未知")
    )

    messages = [
        Message(role="system", content="你是产品技术参数提取专家。只输出JSON，不要输出任何其他内容。"),
        Message(role="user", content=prompt),
    ]

    raw = ""
    for attempt in range(max_retries + 1):
        try:
            response = llm.chat(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            parsed = json.loads(raw)
            products = parsed.get("products", [])

            # Ensure every param has page/section
            for product in products:
                for p in product.get("params", []):
                    if "page" not in p or not p["page"]:
                        p["page"] = page
                    if "section" not in p or not p["section"]:
                        p["section"] = section

            logger.info(
                f"Extracted {len(products)} product(s) from chunk "
                f"(page={page}, {len(text)} chars), attempt {attempt + 1}"
            )
            return products

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"JSON parse failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                messages.append(Message(role="assistant", content=raw))
                messages.append(
                    Message(
                        role="user",
                        content="输出格式错误，请严格输出JSON格式，不要包含任何其他文字。",
                    )
                )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return []

    return []


def extract_params_from_chunks(
    llm: Any,
    chunks: List[ChunkMeta],
) -> List[Dict[str, Any]]:
    """Extract and merge parameters from multiple document chunks.

    Args:
        llm: A BaseLLM instance.
        chunks: List of ChunkMeta with text, page, and section info.

    Returns:
        Merged list of product parameter dicts.
    """
    import sys
    scripts_dir = str(_SKILL_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from merge_params import merge_product_params

    all_extractions: List[Dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        if not chunk.text.strip():
            continue
        products = extract_params_from_text(
            llm, chunk.text, page=chunk.page, section=chunk.section,
        )
        if products:
            all_extractions.append({"products": products})
        logger.debug(f"Chunk {i + 1}/{len(chunks)}: extracted {len(products)} products")

    if not all_extractions:
        return []

    merged = merge_product_params(all_extractions)
    logger.info(f"Merged {len(all_extractions)} extractions → {len(merged)} products")
    return merged
