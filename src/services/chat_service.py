"""Chat service — core RAG question-answering business logic.

Extracts the retrieval → context building → LLM streaming → image processing
→ answer sanitization pipeline from the router layer into a reusable,
independently testable service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.core.query_engine.answer_cache import get_answer_cache
from src.core.response.multimodal_assembler import MultimodalAssembler
from src.ingestion.storage.image_storage import ImageStorage
from src.libs.llm.base_llm import BaseLLM, Message
from src.repositories.history_repo import HistoryRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — image gallery filtering thresholds
# Adjust these to control which images appear in the answer gallery.
# ---------------------------------------------------------------------------

# Minimum relevance score (0.0–1.0) for an image to be included in gallery.
# Lower = more images shown; raise to 0.15–0.20 if too many irrelevant images.
IMAGE_RELEVANCE_THRESHOLD = 0.10

# Maximum number of images shown in the gallery panel.
MAX_GALLERY_IMAGES = 6

# Minimum file size (bytes) for candidate images. Filters out tiny icons/logos.
# 10 KB is a reasonable floor; raise to 50_000 for higher quality only.
MIN_IMAGE_SIZE = 10_000


SYSTEM_PROMPT = """你是一位专业的系统方案架构师。基于提供的参考资料，撰写专业、结构清晰的回答。

要求：
1. 优先使用参考资料中的信息，结构清晰，使用 Markdown 格式
2. **在回答末尾标注实际来源文件名**，格式示例：
   > 参考来源：`浅谈国产GPU芯片全景图.md`、`数字化转型方案.pptx`
   必须使用每段参考资料括号里"来源: xxx"的**真实文件名**，禁止自行编造或概括描述

## 图片引用规则（重要）
参考资料中可能包含 [IMAGE: xxx] 格式的图片引用和对应的 (Description: ...) 描述。
- **仅当参考资料中明确出现 [IMAGE: xxx] 时，才能在回答中原样引用该 ID**
- **绝对禁止自己编造或猜测图片 ID，只能引用参考资料中实际存在的 ID**
- 引用格式：直接输出 [IMAGE: xxx]（保持原始 ID 不变），系统会自动渲染为图片
- 在图片引用后面附上简要说明文字
- 如果参考资料中没有图片引用，则不要输出任何 [IMAGE: ...] 标签

## 图表生成规则
当参考资料中**没有相关图片**时，可以用 PlantUML 生成简单图表辅助说明：
- 适用场景：流程图（3-8步）、时序图（2-4个角色）、简单架构图
- 禁止超过 10 个节点的复杂图
- 语法格式：
  ```plantuml
  @startuml
  left to right direction
  步骤1 --> 步骤2 --> 步骤3
  @enduml
  ```
"""


class ChatService:
    """Orchestrates the RAG question-answering pipeline.

    Responsible for: retrieval, context assembly, LLM streaming,
    image gallery extraction, answer sanitization, and history persistence.

    Attributes:
        llm: The language model client.
        hybrid_search: The hybrid search engine instance.
        history_repo: Repository for persisting QA history.
    """

    def __init__(
        self,
        llm: BaseLLM,
        hybrid_search: Any,
        history_repo: Optional[HistoryRepository] = None,
    ) -> None:
        """Initialize ChatService.

        Args:
            llm: Language model client for answer generation.
            hybrid_search: Hybrid search engine for document retrieval.
            history_repo: Optional history repository (created if None).
        """
        self.llm = llm
        self.hybrid_search = hybrid_search
        self.history_repo = history_repo or HistoryRepository()

    async def stream_answer(
        self,
        question: str,
        collection: str = "default",
        top_k: int = 5,
        max_tokens: int = 4096,
        uploaded_text: str = "",
    ) -> AsyncGenerator[str, None]:
        """Generate SSE event stream for a knowledge-based question.

        This is the main entry point, yielding SSE-formatted strings
        that the router simply wraps in a StreamingResponse.

        Args:
            question: The user's question text.
            collection: Knowledge base collection name.
            top_k: Number of top retrieval results.
            max_tokens: Maximum LLM output tokens.
            uploaded_text: Optional user-uploaded document text.

        Yields:
            SSE-formatted event strings (data: {...}\\n\\n).
        """
        references: List[Dict[str, Any]] = []
        t0 = time.perf_counter()

        # Step 0: Check L3 answer cache
        answer_cache = get_answer_cache()
        cached = answer_cache.get(question)
        if cached is not None:
            logger.info(f"[perf] L3 cache HIT: {question[:50]}...")
            yield self._sse({"type": "references", "data": cached.sources})
            yield self._sse({"type": "token", "content": cached.answer})
            yield self._sse({"type": "done", "answer": cached.answer, "cache_hit": True})
            return

        # Step 1: Retrieve
        results = []
        try:
            results = self.hybrid_search.search(query=question, top_k=top_k)
            t_retrieve = time.perf_counter() - t0
            logger.info(f"[perf] retrieval: {t_retrieve:.2f}s")

            references = [
                {
                    "source": r.metadata.get("source_path", "未知"),
                    "score": round(r.score, 4),
                    "text": r.text[:200],
                }
                for r in results
            ]
            yield self._sse({"type": "references", "data": references})
        except Exception as e:
            logger.exception("Retrieval failed")
            yield self._sse({"type": "error", "message": f"检索失败: {e}"})
            return

        # Start background image extraction
        image_task = asyncio.create_task(
            self._extract_gallery_images(results, question, collection)
        )
        images_sent = False

        # Step 2: Build context and stream LLM
        context = self._build_context(results)
        messages = [Message(role="system", content=SYSTEM_PROMPT)]

        if context:
            messages.append(
                Message(role="user", content=f"参考资料:\n{context}\n\n问题: {question}")
            )
        elif uploaded_text:
            messages.append(
                Message(role="user", content=f"文档内容:\n{uploaded_text}\n\n问题: {question}")
            )
        else:
            messages.append(Message(role="user", content=question))

        full_answer = ""
        try:
            t1 = time.perf_counter()
            async for chunk in self.llm.achat_stream(messages, max_tokens=max_tokens):
                full_answer += chunk
                yield self._sse({"type": "token", "content": chunk})

                # Push images early if ready
                if not images_sent and image_task.done():
                    gallery = image_task.result()
                    yield self._sse({"type": "images", "data": gallery})
                    images_sent = True

            logger.info(f"[perf] LLM stream: {time.perf_counter() - t1:.2f}s")
        except Exception as e:
            logger.exception("LLM generation failed")
            yield self._sse({"type": "error", "message": f"生成失败: {e}"})
            return

        # Ensure images are sent
        if not images_sent:
            gallery = await image_task
            yield self._sse({"type": "images", "data": gallery})

        # Step 3: Sanitize answer
        full_answer = await self._sanitize_answer(full_answer)

        # Done
        yield self._sse({"type": "done", "answer": full_answer})

        # Async post-processing: cache + history
        try:
            answer_cache.put(
                query=question,
                answer=full_answer,
                sources=references,
                metadata={"collection": collection},
            )
        except Exception:
            pass

        await self.history_repo.save(question, full_answer, references)
        logger.info(f"[perf] total: {time.perf_counter() - t0:.2f}s")

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _sse(data: dict) -> str:
        """Format a dict as an SSE data line.

        Args:
            data: Payload dictionary to serialize.

        Returns:
            SSE-formatted string.
        """
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _build_context(results: list, max_chars: int = 8000) -> str:
        """Build context string from retrieval results.

        Args:
            results: List of retrieval result objects.
            max_chars: Maximum total characters for context.

        Returns:
            Formatted context string with source attributions.
        """
        parts = []
        total = 0
        for i, r in enumerate(results):
            source = r.metadata.get("source_path", "未知来源")
            source_name = Path(source).name if source != "未知来源" else source
            text = r.text
            remaining = max_chars - total
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining] + "…"

            img_captions = r.metadata.get("image_captions", [])
            caption_text = ""
            if img_captions:
                if isinstance(img_captions, dict):
                    captions = [f"  - {img_id}: {cap}" for img_id, cap in img_captions.items()]
                elif isinstance(img_captions, list):
                    captions = [f"  - {c}" for c in img_captions if c]
                else:
                    captions = []
                if captions:
                    caption_text = f"\n\n本段包含图片:\n" + "\n".join(captions)

            parts.append(f"【参考资料 {i + 1}】(来源: {source_name})\n{text}{caption_text}")
            total += len(text) + len(caption_text)
            if total >= max_chars:
                break
        return "\n\n---\n\n".join(parts)

    async def _extract_gallery_images(
        self,
        results: list,
        question: str,
        collection: str,
    ) -> list[dict]:
        """Extract and score relevant images from retrieval results.

        Args:
            results: List of retrieval result objects.
            question: The user's question (for relevance scoring).
            collection: Knowledge base collection name.

        Returns:
            List of scored image metadata dicts, sorted by relevance.
        """
        try:
            t2 = time.perf_counter()
            image_storage = ImageStorage()
            assembler = MultimodalAssembler(image_storage)
            scored: list[dict] = []
            total_results = len(results)

            for r_rank, r_obj in enumerate(results):
                for img_ref in assembler.extract_image_refs(r_obj):
                    path = await assembler.aresolve_image_path(img_ref, collection)
                    if not path:
                        continue
                    try:
                        if Path(path).stat().st_size < MIN_IMAGE_SIZE:
                            continue
                    except OSError:
                        continue
                    if await image_storage.adetect_background(img_ref.image_id, path):
                        continue

                    rel = self._calculate_image_relevance(
                        question,
                        img_ref.caption,
                        r_obj.score,
                        rank=r_rank,
                        total_results=total_results,
                    )
                    if rel >= IMAGE_RELEVANCE_THRESHOLD:
                        scored.append(
                            {
                                "image_id": img_ref.image_id,
                                "path": path,
                                "caption": img_ref.caption,
                                "source": r_obj.metadata.get("source_path", ""),
                                "relevance": round(rel, 3),
                                "chunk_score": round(r_obj.score, 3),
                            }
                        )

            final = sorted(scored, key=lambda x: x["relevance"], reverse=True)[
                :MAX_GALLERY_IMAGES
            ]
            logger.info(
                f"[perf] gallery: {time.perf_counter() - t2:.2f}s ({len(final)} imgs)"
            )
            return final
        except Exception as e:
            logger.warning(f"Gallery extraction failed: {e}")
            return []

    @staticmethod
    def _calculate_image_relevance(
        question: str,
        caption: Optional[str],
        chunk_score: float,
        rank: int = 0,
        total_results: int = 1,
    ) -> float:
        """Calculate relevance score for a candidate image.

        Args:
            question: User's question text.
            caption: Image caption (may be None).
            chunk_score: Raw retrieval score of the parent chunk.
            rank: 0-based rank of the chunk in results.
            total_results: Total number of retrieval results.

        Returns:
            Relevance score between 0.0 and 1.0.
        """
        if total_results > 1:
            rank_score = 0.8 - (rank / (total_results - 1)) * 0.5
        else:
            rank_score = 0.8

        if not caption:
            return rank_score * 0.7

        q_tokens = set(re.findall(r"\w+", question.lower()))
        c_tokens = set(re.findall(r"\w+", caption.lower()))

        if not q_tokens or not c_tokens:
            return rank_score * 0.8

        intersection = q_tokens & c_tokens
        union = q_tokens | c_tokens
        jaccard = len(intersection) / len(union) if union else 0

        phrase_boost = 0.0
        q_lower = question.lower()
        c_lower = caption.lower()
        for i in range(len(q_lower) - 3):
            phrase = q_lower[i : i + 4].strip()
            if len(phrase) >= 3 and phrase in c_lower:
                phrase_boost = 0.15
                break

        caption_sim = min(1.0, jaccard + phrase_boost)
        return rank_score * 0.6 + caption_sim * 0.4

    @staticmethod
    async def _sanitize_answer(text: str) -> str:
        """Strip hallucinated and background image references from answer.

        Args:
            text: Raw LLM answer text.

        Returns:
            Sanitized answer text with invalid image refs removed.
        """
        img_storage = ImageStorage()
        matches = list(re.finditer(r"\[IMAGE:\s*([^\]]+)\]", text))
        if not matches:
            return text

        valid_ids: dict[str, bool] = {}
        for m in matches:
            img_id = m.group(1).strip()
            if img_id not in valid_ids:
                img_path = await img_storage.aget_image_path(img_id)
                if not img_path:
                    valid_ids[img_id] = False
                elif await img_storage.adetect_background(img_id, img_path):
                    valid_ids[img_id] = False
                else:
                    valid_ids[img_id] = True

        return re.sub(
            r"\[IMAGE:\s*([^\]]+)\]",
            lambda m: m.group(0) if valid_ids.get(m.group(1).strip()) else "",
            text,
        )
