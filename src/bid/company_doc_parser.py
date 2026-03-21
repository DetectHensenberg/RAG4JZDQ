"""Parse a company qualification response PDF (资格性响应文件) into structured sections.

Uses PyMuPDF to extract text and LLM to identify document sections from the TOC,
then extracts each section's content and page range.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from src.bid.document_db import CompanyDocument, upsert_company_doc
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    """A section identified from the PDF TOC/structure."""

    doc_key: str = ""
    doc_name: str = ""
    category: str = "other"
    page_start: int = 0
    page_end: int = 0
    content: str = ""


def extract_pdf_text(pdf_path: str) -> tuple[str, int]:
    """Extract full text from a PDF file. Returns (text, page_count)."""
    doc = fitz.open(pdf_path)
    pages_text: list[str] = []
    for i in range(doc.page_count):
        text = doc[i].get_text()
        if text.strip():
            pages_text.append(f"[第{i + 1}页]\n{text.strip()}")
    doc.close()
    return "\n\n".join(pages_text), doc.page_count


def extract_page_text(pdf_path: str, page_start: int, page_end: int) -> str:
    """Extract text from specific page range (1-indexed, inclusive)."""
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    for i in range(max(0, page_start - 1), min(page_end, doc.page_count)):
        text = doc[i].get_text().strip()
        if text:
            parts.append(text)
    doc.close()
    return "\n\n".join(parts)


def extract_toc_text(pdf_path: str, max_pages: int = 5, max_chars: int = 8000) -> str:
    """Extract text from the first few pages to find TOC.
    
    Args:
        pdf_path: Path to the PDF file.
        max_pages: Maximum number of pages to scan.
        max_chars: Maximum characters to return (to avoid LLM timeout).
    """
    doc = fitz.open(pdf_path)
    parts: list[str] = []
    total_chars = 0
    for i in range(min(max_pages, doc.page_count)):
        text = doc[i].get_text().strip()
        if text:
            page_text = f"[第{i + 1}页]\n{text}"
            if total_chars + len(page_text) > max_chars:
                # Truncate to fit within limit
                remaining = max_chars - total_chars
                if remaining > 100:
                    parts.append(page_text[:remaining] + "...")
                break
            parts.append(page_text)
            total_chars += len(page_text)
    total = doc.page_count
    doc.close()
    return f"PDF共{total}页\n\n" + "\n\n".join(parts)


_IDENTIFY_SECTIONS_PROMPT = """你是一个文档分析专家。以下是一份投标"资格性响应文件"PDF的前几页内容（包含目录）。

请分析文档结构，识别出所有独立的文件/章节，并以JSON数组返回。

每个元素包含：
- "doc_key": 唯一标识符（英文snake_case，如 "business_license", "tax_payment_cert"）
- "doc_name": 中文名称（如 "营业执照"）
- "category": 分类，只能是以下之一：certificate（资质证书）, financial（财务类）, declaration（声明承诺类）, license（证照类）, other（其他）
- "page_start": 起始页码（PDF实际页码，从1开始）
- "page_end": 结束页码（PDF实际页码）

注意：
1. 目录中的页码可能是文档内部编号，不是PDF实际页码。请根据目录前面的空白页/封面页数量来推算实际PDF页码的偏移量。
2. 每个section的page_end应该是下一个section的page_start - 1
3. 合并明显属于同一文件的子章节（如1.2.1和1.2.2都是信用查询截图，可以合并为"商业信誉证明"）
4. 但保持独立的重要文件分开（如营业执照、审计报告、完税证明等应该独立）

只返回JSON数组，不要其他文字。

PDF内容：
{toc_text}"""


async def identify_sections(pdf_path: str, llm: Any) -> List[ParsedSection]:
    """Use LLM to identify document sections from the PDF TOC."""
    toc_text = extract_toc_text(pdf_path, max_pages=10)
    prompt = _IDENTIFY_SECTIONS_PROMPT.format(toc_text=toc_text)

    messages = [Message(role="user", content=prompt)]
    response = llm.chat(messages)
    raw = response.content.strip()

    json_match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not json_match:
        logger.error("LLM did not return valid JSON array for section identification")
        return []

    try:
        sections_data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return []

    sections: List[ParsedSection] = []
    for item in sections_data:
        sections.append(ParsedSection(
            doc_key=item.get("doc_key", ""),
            doc_name=item.get("doc_name", ""),
            category=item.get("category", "other"),
            page_start=int(item.get("page_start", 0)),
            page_end=int(item.get("page_end", 0)),
        ))

    return sections


async def parse_and_import(
    pdf_path: str,
    llm: Any,
    clear_existing: bool = True,
) -> List[Dict[str, Any]]:
    """Parse a qualification response PDF and import sections into the database.

    Returns a list of imported document dicts.
    """
    logger.info(f"Parsing company document PDF: {pdf_path}")

    sections = await identify_sections(pdf_path, llm)
    if not sections:
        logger.warning("No sections identified from PDF")
        return []

    logger.info(f"Identified {len(sections)} sections from PDF")

    if clear_existing:
        from src.bid.document_db import clear_company_docs
        deleted = clear_company_docs()
        if deleted:
            logger.info(f"Cleared {deleted} existing company documents")

    results: List[Dict[str, Any]] = []
    for section in sections:
        if not section.doc_key or section.page_start <= 0:
            continue

        content = extract_page_text(pdf_path, section.page_start, section.page_end)

        doc = CompanyDocument(
            doc_key=section.doc_key,
            doc_name=section.doc_name,
            category=section.category,
            content=content,
            page_start=section.page_start,
            page_end=section.page_end,
            source_file=pdf_path,
        )
        doc_id = upsert_company_doc(doc)
        logger.info(
            f"Imported: [{doc.doc_key}] {doc.doc_name} "
            f"(pages {doc.page_start}-{doc.page_end}, {len(content)} chars)"
        )
        results.append(doc.to_dict())

    return results
