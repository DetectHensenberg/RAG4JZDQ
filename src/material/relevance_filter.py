"""资料助手 — LLM 相关性筛选器。

使用项目已有的 LLM 基础设施判断搜索结果与用户意图的相关性，
过滤不相关的内容，提高下载质量。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.material.base_adapter import SearchResult

logger = logging.getLogger(__name__)

# ── 系统提示词 ────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
你是一个资料相关性评估专家。
用户正在搜索特定主题的资料，你需要判断搜索结果是否与用户需求相关。

请对每个搜索结果返回 JSON 数组，每个元素包含:
- "index": 结果编号 (从0开始)
- "relevant": 布尔值，是否相关
- "reason": 简短理由 (20字以内)

只返回 JSON 数组，不要添加其他内容。"""


class RelevanceFilter:
    """基于 LLM 的搜索结果相关性筛选器。

    利用项目的 LLM 基础设施判断搜索结果与用户搜索意图的匹配度。
    """

    def __init__(self, llm: Any) -> None:
        """初始化筛选器。

        Args:
            llm: LLM 实例 (来自 src/libs/llm/)。
        """
        self.llm = llm

    async def filter(
        self,
        items: list[SearchResult],
        keywords: list[str],
        batch_size: int = 10,
    ) -> list[SearchResult]:
        """筛选出与关键词相关的搜索结果。

        Args:
            items: 搜索结果列表。
            keywords: 用户的搜索关键词。
            batch_size: 每批发送给 LLM 的结果数量。

        Returns:
            筛选后的相关结果列表。
        """
        if not items:
            return []

        relevant_items: list[SearchResult] = []

        # 分批处理以避免超出 LLM 上下文窗口
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            batch_relevant = await self._filter_batch(batch, keywords)
            relevant_items.extend(batch_relevant)

        logger.info(
            f"Relevance filter: {len(relevant_items)}/{len(items)} items passed "
            f"(keywords: {keywords})"
        )
        return relevant_items

    async def _filter_batch(
        self,
        batch: list[SearchResult],
        keywords: list[str],
    ) -> list[SearchResult]:
        """筛选单个批次。

        Args:
            batch: 一批搜索结果。
            keywords: 搜索关键词。

        Returns:
            相关的结果列表。
        """
        # 构建搜索结果描述
        items_text = "\n".join(
            f"[{i}] 标题: {item.title}\n"
            f"    作者: {item.authors}\n"
            f"    摘要: {item.abstract[:200] if item.abstract else '无'}\n"
            f"    来源: {item.source}"
            for i, item in enumerate(batch)
        )

        user_prompt = (
            f"用户搜索关键词: {', '.join(keywords)}\n\n"
            f"以下是搜索结果:\n{items_text}\n\n"
            f"请判断每个结果是否与用户搜索意图相关。"
        )

        try:
            response = await self.llm.agenerate(
                prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
            )

            # 解析 LLM 响应
            judgments = self._parse_response(response)

            relevant: list[SearchResult] = []
            for j in judgments:
                idx = j.get("index", -1)
                if 0 <= idx < len(batch) and j.get("relevant", False):
                    relevant.append(batch[idx])

            return relevant

        except Exception as e:
            logger.warning(
                f"LLM relevance filter failed: {e}. "
                f"Falling back to pass-through."
            )
            # 失败时不过滤，全部通过
            return list(batch)

    @staticmethod
    def _parse_response(response: str) -> list[dict[str, Any]]:
        """解析 LLM 返回的 JSON 数组。

        Args:
            response: LLM 原始响应文本。

        Returns:
            解析后的判断结果列表。
        """
        text = response.strip()

        # 提取 JSON 部分 (可能被 markdown 代码块包裹)
        if "```" in text:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}")

        return []
