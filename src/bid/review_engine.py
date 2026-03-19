"""Bid review engine — disqualification item identification and checking.

Combines rule-based regex scanning with LLM refinement to identify
disqualification items (废标项) from tender documents, then checks
bid responses against those items via SSE streaming.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)


# ── Data models ──────────────────────────────────────────────────


@dataclass
class DisqualItem:
    """A single disqualification item extracted from a tender document."""

    id: str = ""
    category: str = ""        # 符合性/资格性/实质性/★号/其他
    requirement: str = ""     # 具体要求描述
    source_section: str = ""  # 来源章节
    source_page: int = 0      # 来源页码
    original_text: str = ""   # 原文摘录

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex[:8]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    """A single review check result row."""

    item_id: str = ""
    category: str = ""
    requirement: str = ""
    status: str = ""       # responded / incomplete / missing
    risk: str = ""         # high / medium / low
    detail: str = ""
    source_section: str = ""


# ── Rule-based scanning ──────────────────────────────────────────

# Patterns that indicate disqualification clauses
_STAR_PATTERN = re.compile(r'[★☆✦✧⭐]\s*(.{5,200})')
_DISQUAL_KEYWORDS = [
    "否则废标", "按废标处理", "不予受理", "无效投标", "按无效投标处理",
    "视为无效", "不合格", "予以否决", "取消投标资格",
]
_MANDATORY_KEYWORDS = ["必须", "应当", "不得", "严禁", "强制"]
_SECTION_KEYWORDS = {
    "符合性审查": "符合性",
    "资格性审查": "资格性",
    "资格审查": "资格性",
    "实质性要求": "实质性",
    "实质性审查": "实质性",
    "实质性响应": "实质性",
}


def _extract_context(text: str, pos: int, radius: int = 200) -> str:
    """Extract text around a match position."""
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    return text[start:end].strip()


# Heading pattern: matches lines like "第一章 xxx", "一、xxx", "1.2 xxx", "（一）xxx"
_HEADING_PATTERN = re.compile(
    r'(?:^|\n)\s*'
    r'(?:'
    r'第[一二三四五六七八九十\d]+[章节条款部分][\s\.、：:]*'
    r'|[一二三四五六七八九十]+[\s、．\.]\s*'
    r'|（[一二三四五六七八九十]+）\s*'
    r'|\d+[\.\s]\d*[\s\.]*'
    r')'
    r'(.{2,40}?)(?:\n|$)',
)

# Category inference keywords — map context keywords to categories
_CATEGORY_INFER = [
    (["符合性审查", "符合性要求", "投标文件格式", "密封", "装订", "签章"], "符合性"),
    (["资格性审查", "资格审查", "资格条件", "资质", "营业执照", "社保", "财务报表"], "资格性"),
    (["实质性要求", "实质性审查", "技术参数", "技术要求", "商务要求", "商务条款"], "实质性"),
    (["保证金", "投标保证金", "履约保证金"], "资格性"),
    (["质量", "验收", "交货", "交付", "质保", "售后"], "实质性"),
]


def _build_section_index(text: str) -> List[tuple[int, str]]:
    """Build an ordered index of (position, heading_text) from the document."""
    sections: List[tuple[int, str]] = []
    for m in _HEADING_PATTERN.finditer(text):
        heading = m.group(0).strip()
        if len(heading) > 60:
            heading = heading[:60]
        sections.append((m.start(), heading))
    return sections


def _find_section(pos: int, sections: List[tuple[int, str]]) -> str:
    """Find the nearest preceding section heading for a given position."""
    result = ""
    for sec_pos, sec_text in sections:
        if sec_pos <= pos:
            result = sec_text
        else:
            break
    return result


def _infer_category(context: str) -> str:
    """Infer disqualification category from surrounding text context."""
    for keywords, category in _CATEGORY_INFER:
        for kw in keywords:
            if kw in context:
                return category
    return "其他"


def rule_based_scan(
    text: str,
    page_boundaries: Optional[List[Tuple[int, int, int]]] = None,
) -> List[DisqualItem]:
    """First-pass rule-based scan for potential disqualification items.

    Args:
        text: Full tender document text.
        page_boundaries: Optional list of (page_num, start, end) from extraction.

    Returns a list of raw items with category guesses and original text.
    """
    items: List[DisqualItem] = []
    seen_texts: set[str] = set()
    sections = _build_section_index(text)
    pages = page_boundaries or []

    def _add(
        category: str, requirement: str, original: str,
        pos: int = 0, wider_context: str = "",
    ) -> None:
        key = requirement[:80]
        if key in seen_texts:
            return
        seen_texts.add(key)
        # Infer better category if current is "其他"
        if category == "其他" and wider_context:
            inferred = _infer_category(wider_context)
            if inferred != "其他":
                category = inferred
        # Find source section and page
        source_section = _find_section(pos, sections)
        source_page = _find_page_for_pos(pos, pages) if pages else 0
        items.append(DisqualItem(
            category=category,
            requirement=requirement.strip(),
            source_section=source_section,
            source_page=source_page,
            original_text=original.strip()[:500],
        ))

    # 1. Star items (★)
    for m in _STAR_PATTERN.finditer(text):
        ctx = _extract_context(text, m.start(), 300)
        _add("★号", m.group(1).strip(), ctx, pos=m.start())

    # 2. Disqualification keyword sentences
    for kw in _DISQUAL_KEYWORDS:
        for m in re.finditer(re.escape(kw), text):
            ctx = _extract_context(text, m.start(), 300)
            wider = _extract_context(text, m.start(), 800)
            sentence_start = text.rfind("。", max(0, m.start() - 200), m.start())
            sentence_end = text.find("。", m.start())
            if sentence_start < 0:
                sentence_start = max(0, m.start() - 150)
            if sentence_end < 0:
                sentence_end = min(len(text), m.start() + 150)
            sentence = text[sentence_start:sentence_end + 1].strip().lstrip("。")
            _add("其他", sentence, ctx, pos=m.start(), wider_context=wider)

    # 3. Section-specific items
    for section_kw, category in _SECTION_KEYWORDS.items():
        for m in re.finditer(re.escape(section_kw), text):
            ctx = _extract_context(text, m.start(), 400)
            _add(category, f"[{section_kw}] " + ctx[:200], ctx, pos=m.start())

    return items


# ── LLM refinement ───────────────────────────────────────────────

_IDENTIFY_PROMPT = """你是一位专业的招标文件审查专家。请分析以下招标文件文本，识别出所有废标项/否决项条款。

需要识别的类型：
1. **符合性审查项** - 投标文件格式、签章、密封等基本要求
2. **资格性审查项** - 投标人资质、资格条件等
3. **实质性要求** - 技术参数、商务条款等核心要求
4. **★号项** - 招标文件中标注★号的强制响应项
5. **其他强制项** - 其他明确要求必须响应的条款（如"否则废标"）

已通过规则引擎初步识别到以下条目（可能有误报或遗漏）：
{rule_items_json}

请基于以上初步结果和完整文本，输出最终的废标项清单。

严格要求：
1. 输出严格的 JSON 格式
2. 去除重复项和误报
3. 补充规则引擎遗漏的废标项
4. 每条必须有明确的要求描述
5. **source_section 必须填写**，从文本中找到该条款所属的章节标题（如"第三章 资格性审查"、"3.4 投标保证金"等）
6. **category 尽量精确分类**，优先使用"符合性"、"资格性"、"实质性"、"★号"，仅当确实无法归类时才用"其他"
7. 涉及保证金、资质证书、资格条件的归为"资格性"；涉及技术参数、质量、验收、交付的归为"实质性"；涉及文件格式、签章、密封的归为"符合性"

输出格式：
{{
  "items": [
    {{
      "category": "符合性/资格性/实质性/★号/其他",
      "requirement": "具体要求描述",
      "source_section": "来源章节标题（必填）",
      "original_text": "原文摘录"
    }}
  ]
}}

以下是招标文件文本（已截取关键部分）：
---
{text}
---

请输出废标项清单 JSON："""


async def identify_items_with_llm(
    text: str,
    rule_items: List[DisqualItem],
    llm: Any,
    max_text_chars: int = 20000,
) -> List[DisqualItem]:
    """Refine rule-based items using LLM analysis.

    Args:
        text: Full tender document text.
        rule_items: Items from rule_based_scan().
        llm: LLM instance with chat() or generate() method.
        max_text_chars: Max text length to send to LLM.

    Returns:
        Refined list of DisqualItem.
    """
    rule_json = json.dumps(
        [{"category": i.category, "requirement": i.requirement, "source_section": i.source_section} for i in rule_items],
        ensure_ascii=False, indent=2,
    )

    truncated = text[:max_text_chars] if len(text) > max_text_chars else text
    prompt = _IDENTIFY_PROMPT.format(rule_items_json=rule_json, text=truncated)

    try:
        messages = [Message(role="user", content=prompt)]
        if hasattr(llm, "chat"):
            resp = llm.chat(messages)
            response = resp.content if hasattr(resp, "content") else str(resp)
        elif hasattr(llm, "generate"):
            resp = llm.generate(prompt)
            response = resp.content if hasattr(resp, "content") else str(resp)
        else:
            logger.error("LLM has no chat() or generate() method")
            return rule_items
    except Exception as e:
        logger.exception(f"LLM identify call failed: {e}")
        return rule_items

    return _parse_identify_response(response) or rule_items


def _parse_identify_response(response: str) -> List[DisqualItem]:
    """Parse LLM JSON response into DisqualItem list."""
    if not response:
        return []

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                return []
        else:
            return []

    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        return []

    result: List[DisqualItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        req = str(item.get("requirement", "")).strip()
        if not req:
            continue
        result.append(DisqualItem(
            category=str(item.get("category", "其他")).strip(),
            requirement=req,
            source_section=str(item.get("source_section", "")).strip(),
            original_text=str(item.get("original_text", "")).strip()[:500],
        ))

    return result


# ── Review check (SSE streaming) ─────────────────────────────────

_CHECK_PROMPT = """你是一位专业的标书审查专家。请根据以下废标项清单，逐一核查投标文件中是否有对应响应。

## 废标项清单

{items_text}

## 投标文件内容

{bid_text}

## 审查要求

请对每一条废标项进行核查，输出 Markdown 格式的审查报告，包含：

1. **总体评估**：概述审查结果
2. **逐项核查表**：使用 Markdown 表格，列：
   | 序号 | 类型 | 废标项要求 | 响应状态 | 风险等级 | 详细说明 |
   
   - 响应状态：✅已响应 / ⚠️不完整 / ❌缺失
   - 风险等级：高 / 中 / 低
3. **高风险项汇总**：列出所有需要立即关注的问题
4. **改进建议**：针对不完整和缺失项给出修改建议

请确保审查全面、准确，不要遗漏任何废标项。"""


async def check_bid_response_stream(
    items: List[DisqualItem],
    bid_text: str,
    llm: Any,
    max_bid_chars: int = 20000,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream review check results as SSE events.

    Yields dicts with keys: type, content/answer/table_data/message.
    """
    items_text = "\n".join(
        f"{i+1}. [{item.category}] {item.requirement}"
        for i, item in enumerate(items)
    )
    truncated_bid = bid_text[:max_bid_chars] if len(bid_text) > max_bid_chars else bid_text
    prompt = _CHECK_PROMPT.format(items_text=items_text, bid_text=truncated_bid)

    full_response = ""

    try:
        messages = [Message(role="user", content=prompt)]
        if hasattr(llm, "stream_chat") and callable(llm.stream_chat):
            async for chunk in llm.stream_chat(messages):
                token = chunk if isinstance(chunk, str) else str(chunk)
                full_response += token
                yield {"type": "token", "content": token}
        elif hasattr(llm, "chat"):
            resp = llm.chat(messages)
            full_response = resp.content if hasattr(resp, "content") else str(resp)
            # Simulate streaming by sending in chunks
            chunk_size = 50
            for i in range(0, len(full_response), chunk_size):
                yield {"type": "token", "content": full_response[i:i + chunk_size]}
        else:
            yield {"type": "error", "message": "LLM 无可用的对话方法"}
            return
    except Exception as e:
        logger.exception(f"Review check LLM call failed: {e}")
        yield {"type": "error", "message": f"审查失败: {e}"}
        return

    # Parse table data from the markdown response
    table_data = parse_review_table(full_response)

    yield {
        "type": "done",
        "answer": full_response,
        "table_data": table_data,
    }


# ── Table parsing ────────────────────────────────────────────────

_STATUS_MAP = {
    "已响应": "responded",
    "✅已响应": "responded",
    "✅": "responded",
    "不完整": "incomplete",
    "⚠️不完整": "incomplete",
    "⚠️": "incomplete",
    "缺失": "missing",
    "❌缺失": "missing",
    "❌": "missing",
}

_RISK_MAP = {
    "高": "high",
    "中": "medium",
    "低": "low",
}


def parse_review_table(md_text: str) -> List[Dict[str, Any]]:
    """Parse the Markdown review table into structured data."""
    rows: List[Dict[str, Any]] = []
    in_table = False

    for line in md_text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                in_table = False
            continue

        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]  # remove empty from leading/trailing |

        if len(cells) < 4:
            continue

        # Skip header separator rows
        if all(set(c) <= {"-", ":", " "} for c in cells):
            in_table = True
            continue

        # Skip header row (contains "序号" or "类型")
        if any(h in cells[0] for h in ["序号", "#", "编号"]):
            in_table = True
            continue

        if not in_table and len(cells) >= 5:
            in_table = True
            continue

        # Parse data row
        try:
            idx = 0
            if cells[0].isdigit():
                idx = 1

            category = cells[idx] if idx < len(cells) else ""
            requirement = cells[idx + 1] if idx + 1 < len(cells) else ""
            status_raw = cells[idx + 2] if idx + 2 < len(cells) else ""
            risk_raw = cells[idx + 3] if idx + 3 < len(cells) else ""
            detail = cells[idx + 4] if idx + 4 < len(cells) else ""

            status = "responded"
            for k, v in _STATUS_MAP.items():
                if k in status_raw:
                    status = v
                    break

            risk = "low"
            for k, v in _RISK_MAP.items():
                if k in risk_raw:
                    risk = v
                    break

            rows.append({
                "category": category,
                "requirement": requirement,
                "status": status,
                "risk": risk,
                "detail": detail,
            })
        except (IndexError, ValueError):
            continue

    return rows


# ── PDF text extraction (reuse pattern) ──────────────────────────


def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF or DOCX file."""
    text, _ = extract_text_with_pages(file_path)
    return text


def extract_text_with_pages(file_path: str) -> Tuple[str, List[Tuple[int, int, int]]]:
    """Extract text and page boundaries from PDF or DOCX.

    Returns:
        (full_text, page_boundaries) where page_boundaries is a list of
        (page_number, start_offset, end_offset) tuples (1-indexed pages).
    """
    import os
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _extract_pdf_with_pages(file_path)
    elif ext == ".doc":
        return _extract_doc_with_pages(file_path)
    elif ext == ".docx":
        return _extract_docx_with_pages(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


def _find_page_for_pos(pos: int, page_boundaries: List[Tuple[int, int, int]]) -> int:
    """Find the 1-indexed page number for a character offset."""
    for page_num, start, end in page_boundaries:
        if start <= pos < end:
            return page_num
    return 0


def _extract_pdf_with_pages(file_path: str) -> Tuple[str, List[Tuple[int, int, int]]]:
    try:
        import fitz
        doc = fitz.open(file_path)
        parts: List[str] = []
        boundaries: List[Tuple[int, int, int]] = []
        offset = 0
        for i, page in enumerate(doc):
            page_text = page.get_text()
            start = offset
            parts.append(page_text)
            offset += len(page_text) + 2  # +2 for \n\n separator
            boundaries.append((i + 1, start, offset))
        doc.close()
        return "\n\n".join(parts), boundaries
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        # pdfminer doesn't give per-page easily; approximate
        return text, _approximate_pages(text)
    except ImportError:
        pass

    raise ImportError("需要 PyMuPDF 或 pdfminer.six 来解析 PDF")


def _extract_doc_with_pages(file_path: str) -> Tuple[str, List[Tuple[int, int, int]]]:
    """Read .doc file directly via win32com without conversion."""
    import os
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            abs_path = os.path.abspath(file_path)
            doc = word.Documents.Open(abs_path)
            text = doc.Content.Text
            # Get per-page text for boundaries
            pages_count = doc.ComputeStatistics(2)  # 2 = wdStatisticPages
            boundaries: List[Tuple[int, int, int]] = []
            if pages_count > 1:
                offset = 0
                for pg in range(1, pages_count + 1):
                    try:
                        rng = doc.GoTo(1, 1, pg)  # 1=wdGoToPage, 1=wdGoToAbsolute
                        pg_start = rng.Start
                        if pg < pages_count:
                            next_rng = doc.GoTo(1, 1, pg + 1)
                            pg_end = next_rng.Start
                        else:
                            pg_end = len(text)
                        boundaries.append((pg, pg_start, pg_end))
                    except Exception:
                        break
            doc.Close(False)
            word.Quit()
            if not boundaries:
                boundaries = _approximate_pages(text)
            return text, boundaries
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        raise ValueError(
            "不支持旧版 .doc 格式。请安装 pywin32 (pip install pywin32) "
            "或将文件另存为 .docx 格式后重新上传"
        )
    except Exception as e:
        raise ValueError(f"读取 .doc 文件失败: {e}")


def _extract_docx_with_pages(file_path: str) -> Tuple[str, List[Tuple[int, int, int]]]:
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text, _approximate_pages(text)
    except ImportError:
        raise ImportError("需要 python-docx 来解析 DOCX 文件")


def _approximate_pages(text: str, chars_per_page: int = 1800) -> List[Tuple[int, int, int]]:
    """Approximate page boundaries by character count."""
    boundaries: List[Tuple[int, int, int]] = []
    total = len(text)
    page = 1
    offset = 0
    while offset < total:
        end = min(offset + chars_per_page, total)
        boundaries.append((page, offset, end))
        page += 1
        offset = end
    return boundaries
