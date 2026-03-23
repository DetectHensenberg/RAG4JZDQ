"""Template Parser — 从 Word 方案模板中提取大纲结构.

读取 Word 文档的标题层级（Heading 1/2/3），构建树形大纲结构。
用户上传已有方案模板时，生成的大纲将以模板目录为骨架。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Word 标题样式到层级的映射
_HEADING_LEVEL_MAP = {
    "Heading 1": 1,
    "Heading 2": 2,
    "Heading 3": 3,
    "Heading 4": 4,
    "标题 1": 1,
    "标题 2": 2,
    "标题 3": 3,
    "标题 4": 4,
}


def _detect_heading_level_from_text(text: str) -> int | None:
    """从文本格式推断标题层级（备用方案，当样式缺失时）.

    常见格式:
    - "一、xxx" / "第一章 xxx" → level 1
    - "（一）xxx" / "1.1 xxx" → level 2
    - "1.1.1 xxx" → level 3

    Args:
        text: 段落文本

    Returns:
        推断的层级（1-3），无法确定时返回 None
    """
    text = text.strip()
    if not text:
        return None

    # 第X章 / 第X部分
    if re.match(r"^第[一二三四五六七八九十\d]+[章部]", text):
        return 1
    # 一、二、三、...
    if re.match(r"^[一二三四五六七八九十]+、", text):
        return 1
    # （一）（二）...
    if re.match(r"^[（(][一二三四五六七八九十]+[）)]", text):
        return 2
    # 1. / 2. / 3.（顶层数字章节）
    if re.match(r"^\d+\.\s", text):
        return 1
    # 1.1.1（三级 — 放在 1.1 之前避免被吞）
    if re.match(r"^\d+\.\d+\.\d+", text):
        return 3
    # 1.1 / 2.3
    if re.match(r"^\d+\.\d+[\.\s]", text):
        return 2

    return None


def parse_template(file_path: str) -> List[Dict[str, Any]]:
    """从 Word 文件中提取标题层级结构作为大纲.

    遍历文档所有段落，按 Heading 样式或文本格式识别标题，
    构建扁平化的大纲列表。

    Args:
        file_path: Word 文件路径

    Returns:
        大纲列表 [{id, title, level}]，按文档顺序排列

    Raises:
        ValueError: 文件格式不支持或无法解析
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in (".docx", ".doc"):
        raise ValueError(f"模板解析仅支持 Word 文件，当前格式: {suffix}")

    try:
        from docx import Document
    except ImportError:
        raise ValueError("需要安装 python-docx: pip install python-docx")

    doc = Document(file_path)
    outline: List[Dict[str, Any]] = []
    counter = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        level: int | None = None

        # 优先使用 Word 内置样式
        style_name = para.style.name if para.style else ""
        if style_name in _HEADING_LEVEL_MAP:
            level = _HEADING_LEVEL_MAP[style_name]
        else:
            # 备用：从文本格式推断
            level = _detect_heading_level_from_text(text)

        if level is not None and level <= 3:
            counter += 1
            outline.append(
                {
                    "id": f"TPL-{counter:03d}",
                    "title": text,
                    "level": level,
                }
            )

    if not outline:
        logger.warning(f"模板 {file_path} 未提取到任何标题结构")

    logger.info(f"从模板提取到 {len(outline)} 个标题节点")
    return outline
