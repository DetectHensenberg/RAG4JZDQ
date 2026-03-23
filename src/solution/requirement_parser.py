"""Requirement Parser — 从需求文档中提取结构化需求条目.

支持 PDF/DOCX 文件上传和纯文本粘贴两种输入方式。
使用 LLM 将非结构化文本转化为分类需求列表。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List

from src.libs.llm.base_llm import BaseLLM, Message

logger = logging.getLogger(__name__)

REQUIREMENT_PARSE_PROMPT = """你是技术方案需求分析专家。请分析以下技术标/需求文档内容，提取所有技术需求条目。

为每个需求条目标注：
- id: 自动生成的唯一标识（如 REQ-001）
- category: 需求分类，可选值：
  - functional（功能性需求）
  - non_functional（性能/安全/可靠性等）
  - constraint（技术约束条件，如指定平台、协议等）
  - deliverable（交付物要求）
- title: 简短的需求标题（10-20字）
- description: 需求的详细描述
- keywords: 用于知识库检索的关键词列表（3-5个）

请以 JSON 数组格式输出，例如：
```json
[
  {{
    "id": "REQ-001",
    "category": "functional",
    "title": "用户身份认证",
    "description": "系统需要支持用户名密码登录和单点登录（SSO）",
    "keywords": ["身份认证", "SSO", "登录"]
  }}
]
```

仅输出 JSON 数组，不要包含其他内容。

以下是需求文档内容：

{text}"""


def _extract_text_from_file(file_path: str) -> str:
    """从文件中提取纯文本内容.

    Args:
        file_path: 文件路径（支持 PDF/DOCX）

    Returns:
        提取的文本内容

    Raises:
        ValueError: 不支持的文件格式
    """
    from pathlib import Path

    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        try:
            import fitz

            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            raise ValueError("需要安装 PyMuPDF: pip install pymupdf")
    elif suffix in (".docx", ".doc"):
        try:
            from docx import Document

            doc = Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except ImportError:
            raise ValueError("需要安装 python-docx: pip install python-docx")
    elif suffix in (".txt", ".md"):
        return Path(file_path).read_text(encoding="utf-8")
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 PDF/DOCX/TXT/MD")


def _parse_llm_json(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中解析 JSON 数组.

    Args:
        text: LLM 的原始输出文本

    Returns:
        解析后的字典列表
    """
    # 尝试提取 ```json ... ``` 代码块
    import re

    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    # 尝试直接解析
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "requirements" in result:
            return result["requirements"]
    except json.JSONDecodeError:
        pass

    # 尝试找到第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("无法从 LLM 输出中解析 JSON，返回空列表")
    return []


async def parse_requirements(
    llm: BaseLLM,
    file_path: str | None = None,
    text: str | None = None,
    max_chars: int = 30000,
) -> List[Dict[str, Any]]:
    """解析需求文档，返回结构化需求列表.

    Args:
        llm: LLM 实例
        file_path: 需求文件路径（与 text 二选一）
        text: 需求文本内容（与 file_path 二选一）
        max_chars: 文本截断长度限制

    Returns:
        结构化需求列表，每项包含 id/category/title/description/keywords

    Raises:
        ValueError: 无有效输入
    """
    if file_path:
        raw_text = _extract_text_from_file(file_path)
    elif text:
        raw_text = text
    else:
        raise ValueError("必须提供 file_path 或 text 参数")

    if not raw_text.strip():
        raise ValueError("文档内容为空，无法提取需求")

    # 截断避免超出上下文窗口
    if len(raw_text) > max_chars:
        raw_text = raw_text[:max_chars]
        logger.warning(f"需求文本过长，已截断至 {max_chars} 字符")

    prompt = REQUIREMENT_PARSE_PROMPT.format(text=raw_text)
    messages = [Message(role="user", content=prompt)]

    try:
        response = llm.chat(messages)
        requirements = _parse_llm_json(response.content)

        # 确保每项都有 id
        for i, req in enumerate(requirements):
            if not req.get("id"):
                req["id"] = f"REQ-{i + 1:03d}"
            if not req.get("keywords"):
                req["keywords"] = []

        logger.info(f"成功解析 {len(requirements)} 条需求")
        return requirements
    except Exception as e:
        logger.exception(f"需求解析失败: {e}")
        raise
