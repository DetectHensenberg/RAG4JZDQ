"""LLM-based achievement extraction from contract PDFs.

Reads a PDF, extracts text, sends it to LLM with a structured prompt,
and parses out achievement record fields (project name, amount, dates, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """你是一位专业的合同信息提取专家。请从以下合同/项目文档文本中提取业绩信息。

严格要求：
1. 输出严格的 JSON 格式，不要输出其他内容
2. 如果某个字段在文本中找不到，对应值留空字符串或 null
3. 金额单位统一为"万元"，如果原文是"元"请换算
4. 日期格式统一为 YYYY-MM-DD
5. 标签(tags)根据项目内容自动归类，如"智慧城市"、"安防"、"信息化"等

输出格式：
{{
  "achievements": [
    {{
      "project_name": "项目名称",
      "project_content": "项目内容描述",
      "amount": 500.0,
      "sign_date": "2023-01-15",
      "acceptance_date": "2023-12-30",
      "client_contact": "张三",
      "client_phone": "13800138000",
      "tags": ["智慧城市", "集成"]
    }}
  ]
}}

如果文档中包含多个项目/合同信息，全部提取并放入 achievements 数组。

以下是文档文本：
---
{text}
---

请提取业绩信息（仅输出 JSON）："""


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using available libraries."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text

        return extract_text(file_path)
    except ImportError:
        pass

    raise ImportError(
        "需要 PyMuPDF (fitz) 或 pdfminer.six 来解析 PDF。"
        "请安装: pip install PyMuPDF 或 pip install pdfminer.six"
    )


def extract_achievements_from_pdf(
    file_path: str,
    llm: Any,
    max_chars: int = 15000,
) -> List[Dict[str, Any]]:
    """Extract achievement records from a contract PDF via LLM.

    Args:
        file_path: Path to the PDF file.
        llm: An LLM instance with a ``chat`` or ``generate`` method.
        max_chars: Maximum text length to send to LLM (truncated if exceeded).

    Returns:
        List of dicts, each representing an extracted achievement.
    """
    text = _extract_text_from_pdf(file_path)
    if not text.strip():
        logger.warning(f"PDF text extraction returned empty for {file_path}")
        return []

    if len(text) > max_chars:
        logger.info(f"PDF text truncated from {len(text)} to {max_chars} chars")
        text = text[:max_chars]

    prompt = _EXTRACTION_PROMPT.format(text=text)

    try:
        if hasattr(llm, "chat"):
            from src.libs.llm.base_llm import Message
            response = llm.chat([Message(role="user", content=prompt)])
        elif hasattr(llm, "generate"):
            response = llm.generate(prompt)
        else:
            logger.error("LLM instance has no chat() or generate() method")
            return []
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return []

    return _parse_response(response)


def _parse_response(response: str) -> List[Dict[str, Any]]:
    """Parse LLM JSON response into achievement dicts."""
    if not response:
        return []

    # Try to find JSON in the response
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON")
                return []
        else:
            return []

    achievements = data.get("achievements", [])
    if not isinstance(achievements, list):
        return []

    # Normalize fields
    result: List[Dict[str, Any]] = []
    for item in achievements:
        if not isinstance(item, dict):
            continue
        project_name = str(item.get("project_name", "")).strip()
        if not project_name:
            continue

        amount = item.get("amount")
        if amount is not None:
            try:
                amount = float(amount)
            except (ValueError, TypeError):
                amount = None

        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        result.append({
            "project_name": project_name,
            "project_content": str(item.get("project_content", "")).strip(),
            "amount": amount,
            "sign_date": str(item.get("sign_date", "")).strip(),
            "acceptance_date": str(item.get("acceptance_date", "")).strip(),
            "client_contact": str(item.get("client_contact", "")).strip(),
            "client_phone": str(item.get("client_phone", "")).strip(),
            "tags": tags if isinstance(tags, list) else [],
        })

    return result
