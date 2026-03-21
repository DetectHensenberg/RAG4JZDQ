"""LLM-based product parameter comparator.

Reads prompt and risk rules from bid-param-comparator skill, sends
two parameter sets to LLM, and streams a deviation report.
After streaming, parses the Markdown table into structured table_data
for the frontend to render as a sortable/filterable table.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

from src.core.settings import REPO_ROOT

logger = logging.getLogger(__name__)

_SKILL_DIR = REPO_ROOT / ".github" / "skills" / "bid-param-comparator"
_PROMPT_PATH = _SKILL_DIR / "references" / "comparison_prompt.md"
_RULES_PATH = _SKILL_DIR / "references" / "risk_rules.md"


def _load_comparison_prompt() -> str:
    """Load comparison prompt template from skill references."""
    if _PROMPT_PATH.exists():
        try:
            content = _PROMPT_PATH.read_text(encoding="utf-8")
            blocks = content.split("```")
            if len(blocks) >= 3:
                prompt_block = blocks[1].strip()
                # Skip optional language hint line (e.g. "markdown")
                lines = prompt_block.split("\n")
                if lines and lines[0].strip().isalpha() and len(lines[0].strip()) < 15:
                    lines = lines[1:]
                return "\n".join(lines).strip()
        except Exception as e:
            logger.warning(f"Failed to load comparison prompt: {e}")
    return _FALLBACK_PROMPT


def _load_risk_rules() -> str:
    """Load risk rules from skill references."""
    if _RULES_PATH.exists():
        try:
            return _RULES_PATH.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


_FALLBACK_PROMPT = """逐项比对以下两份产品技术参数。参数命名可能不同，按语义匹配。

【官方参数】
{official_params}

【送审参数】
{vendor_params}

比对规则：✅一致 ⚠️偏差 ❌缺失 ➕新增
风险：高=核心参数造假 中=有差异需关注 低=表述差异

输出Markdown：

## 比对结果

| 参数项 | 官方值 | 送审值 | 状态 | 风险 | 说明 |
|--------|--------|--------|------|------|------|

## 统计
一致X项/偏差X项(高X中X低X)/缺失X项/新增X项

## 结论
一句话总结是否存在造假嫌疑"""


def _params_to_compact(params: List[Dict[str, str]]) -> str:
    """Convert param list to compact format: one 'name: value' per line.

    This reduces token count by ~50% compared to full JSON with
    name/value/unit/page/section fields.
    """
    lines: List[str] = []
    for p in params:
        name = p.get("name", "")
        value = p.get("value", "")
        unit = p.get("unit", "")
        if not name:
            continue
        entry = f"- {name}: {value}"
        if unit and unit not in value:
            entry += f" ({unit})"
        lines.append(entry)
    return "\n".join(lines) if lines else "(无参数)"


def compare_params_stream(
    llm: Any,
    official_params: List[Dict[str, str]],
    vendor_params: List[Dict[str, str]],
    official_info: Optional[Dict[str, str]] = None,
    vendor_info: Optional[Dict[str, str]] = None,
) -> Generator[str, None, None]:
    """Stream a parameter comparison report.

    Args:
        llm: A BaseLLM instance.
        official_params: Official product params [{name, value, unit, page, section}].
        vendor_params: Vendor-submitted params [{name, value, unit, page, section}].
        official_info: Optional dict with vendor/model/product_name.
        vendor_info: Optional dict with vendor/model/product_name.

    Yields:
        Text chunks of the comparison report as they stream from LLM.
    """
    from src.libs.llm.base_llm import Message

    template = _load_comparison_prompt()
    risk_rules = _load_risk_rules()

    # Compact param format: "name: value" per line (saves ~50% tokens vs JSON)
    official_str = _params_to_compact(official_params)
    vendor_str = _params_to_compact(vendor_params)

    prompt = template.replace("{official_params}", official_str).replace(
        "{vendor_params}", vendor_str
    )

    context_parts: List[str] = []
    if official_info:
        context_parts.append(
            f"官方产品：{official_info.get('vendor', '')} {official_info.get('model', '')}"
        )
    if vendor_info:
        context_parts.append(
            f"送审产品：{vendor_info.get('vendor', '')} {vendor_info.get('model', '')}"
        )

    system_content = "你是产品技术审查专家。按规则逐项比对参数，输出Markdown表格。"
    if risk_rules:
        system_content += f"\n\n风险判定规则：\n{risk_rules}"

    user_content = prompt
    if context_parts:
        user_content = "\n".join(context_parts) + "\n\n" + user_content

    messages = [
        Message(role="system", content=system_content),
        Message(role="user", content=user_content),
    ]

    try:
        for chunk in llm.chat_stream(messages, max_tokens=2048):
            yield chunk
    except Exception as e:
        logger.error(f"LLM comparison stream failed: {e}")
        yield f"\n\n**比对失败**: {e}"


def parse_table_data(markdown: str) -> List[Dict[str, Any]]:
    """Parse the Markdown comparison table into structured table_data.

    Scans for the first Markdown table with a header row containing '参数项'
    and extracts each data row into a dict.

    Returns:
        List of dicts with keys: param, official, vendor, status, risk,
        page, section, note.
    """
    rows: List[Dict[str, Any]] = []
    lines = markdown.split("\n")

    # Find table header
    header_idx = -1
    headers: List[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "参数" in stripped:
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= 4:
                headers = cells
                header_idx = i
                break

    if header_idx < 0:
        return rows

    # Map header names to output keys
    key_map = {
        "序号": "index", "参数项": "param", "参数": "param",
        "官方值": "official", "官方": "official",
        "送审值": "vendor", "送审": "vendor",
        "状态": "status", "风险等级": "risk", "风险": "risk",
        "页码": "page", "章节": "section",
        "说明": "note", "备注": "note",
    }

    col_keys: List[str] = []
    for h in headers:
        matched = False
        for pattern, key in key_map.items():
            if pattern in h:
                col_keys.append(key)
                matched = True
                break
        if not matched:
            col_keys.append(h)

    # Parse data rows (skip separator line)
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if stripped and not stripped.startswith("-"):
                break
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue  # separator line

        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) < 4:
            continue

        row: Dict[str, Any] = {}
        for j, key in enumerate(col_keys):
            if j < len(cells):
                row[key] = cells[j]

        if "param" in row and row["param"]:
            # Normalize status
            status = row.get("status", "")
            if "一致" in status:
                row["status"] = "match"
            elif "偏差" in status:
                row["status"] = "deviation"
            elif "缺失" in status:
                row["status"] = "missing"
            elif "新增" in status:
                row["status"] = "added"

            # Normalize risk
            risk = row.get("risk", "")
            if "高" in risk:
                row["risk"] = "high"
            elif "中" in risk:
                row["risk"] = "medium"
            elif "低" in risk:
                row["risk"] = "low"
            else:
                row["risk"] = ""

            rows.append(row)

    logger.info(f"Parsed {len(rows)} rows from comparison table")
    return rows
