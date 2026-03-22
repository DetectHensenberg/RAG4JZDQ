"""Chat/QA API router — SSE streaming for knowledge-based Q&A."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.db import get_connection, get_async_connection
from api.deps import get_hybrid_search, get_llm, get_settings
from api.models import ChatRequest
from src.core.settings import resolve_path
from src.core.query_engine.answer_cache import get_answer_cache
from src.core.response.multimodal_assembler import MultimodalAssembler
from src.ingestion.storage.image_storage import ImageStorage


# Constants
# Image relevance threshold (0.0 - 1.0)
# Images from retrieved chunks are inherently relevant; keep threshold low
IMAGE_RELEVANCE_THRESHOLD = 0.10


def _calculate_image_relevance(
    question: str,
    caption: str | None,
    chunk_score: float,
    rank: int = 0,
    total_results: int = 1,
) -> float:
    """Calculate image relevance score.
    
    Since chunks are already retrieved by hybrid search, their images
    are inherently relevant. Scoring is based on:
    - Rank-based base score (higher rank = more relevant)
    - Caption keyword overlap bonus (if caption available)
    
    Args:
        question: User's question
        caption: Image caption text (may be None)
        chunk_score: Raw retrieval score (may be very small)
        rank: 0-based rank of the chunk in results
        total_results: Total number of results retrieved
        
    Returns:
        Relevance score between 0.0 and 1.0
    """
    import re
    
    # Rank-based base: top result gets 0.8, last gets 0.3
    if total_results > 1:
        rank_score = 0.8 - (rank / (total_results - 1)) * 0.5
    else:
        rank_score = 0.8
    
    if not caption:
        return rank_score * 0.7
    
    # Caption keyword overlap bonus
    q_tokens = set(re.findall(r'\w+', question.lower()))
    c_tokens = set(re.findall(r'\w+', caption.lower()))
    
    if not q_tokens or not c_tokens:
        return rank_score * 0.8
    
    intersection = q_tokens & c_tokens
    union = q_tokens | c_tokens
    jaccard = len(intersection) / len(union) if union else 0
    
    # Phrase match bonus
    phrase_boost = 0.0
    q_lower = question.lower()
    c_lower = caption.lower()
    for i in range(len(q_lower) - 3):
        phrase = q_lower[i:i+4].strip()
        if len(phrase) >= 3 and phrase in c_lower:
            phrase_boost = 0.15
            break
    
    caption_sim = min(1.0, jaccard + phrase_boost)
    
    return rank_score * 0.6 + caption_sim * 0.4

_HISTORY_DB = resolve_path("data/qa_history.db")

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
- 示例：如参考资料中有 [IMAGE: f8d3e201_s3_1]，则在回答中写：

  [IMAGE: f8d3e201_s3_1]
  *图：XX架构示意图*
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


async def _strip_background_images(text: str, collection: str = "default") -> str:
    """Remove [IMAGE: id] references for background / decorative images."""
    image_storage = ImageStorage()
    
    # find all placeholders
    matches = list(re.finditer(r"\[IMAGE:\s*([^\]]+)\](?:\s*\n\(Description:[^\)]*\))?\s*\n?", text))
    if not matches:
        return text
        
    valid_ids = {}
    for m in matches:
        img_id = m.group(1).strip()
        if img_id not in valid_ids:
            img_path = await image_storage.aget_image_path(img_id)
            if not img_path:
                valid_ids[img_id] = True # Keep if not found, it might be hallucinated or external
            elif await image_storage.adetect_background(img_id, img_path):
                valid_ids[img_id] = False
            else:
                valid_ids[img_id] = True

    def _replacer(m: re.Match) -> str:
        img_id = m.group(1).strip()
        return m.group(0) if valid_ids.get(img_id) else ""

    return re.sub(
        r"\[IMAGE:\s*([^\]]+)\](?:\s*\n\(Description:[^\)]*\))?\s*\n?",
        _replacer,
        text,
    )


def _build_context(results: list, max_chars: int = 8000) -> str:
    """Build context string from retrieval results, including image captions."""
    parts = []
    total = 0
    for i, r in enumerate(results):
        source = r.metadata.get("source_path", "未知来源")
        source_name = Path(source).name if source != "未知来源" else source
        text = r.text  # Keep all [IMAGE: xxx] refs so LLM can reference them;
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + "…"
        
        # Include image captions in context
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
        
        
        parts.append(f"【参考资料 {i+1}】(来源: {source_name})\n{text}{caption_text}")
        total += len(text) + len(caption_text)
        if total >= max_chars:
            break
    return "\n\n---\n\n".join(parts)


def _init_history_db() -> None:
    _HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(_HISTORY_DB) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            references_json TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()


async def _ainit_history_db() -> None:
    _HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    async with get_async_connection(_HISTORY_DB) as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            references_json TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await conn.commit()


def _save_history(question: str, answer: str, refs: list) -> None:
    try:
        _init_history_db()
        with get_connection(_HISTORY_DB) as conn:
            conn.execute(
                "INSERT INTO qa_history (id, question, answer, references_json) VALUES (?,?,?,?)",
                (int(time.time() * 1000), question, answer, json.dumps(refs, ensure_ascii=False)),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save QA history: {e}")


async def _asave_history(question: str, answer: str, refs: list) -> None:
    try:
        await _ainit_history_db()
        async with get_async_connection(_HISTORY_DB) as conn:
            await conn.execute(
                "INSERT INTO qa_history (id, question, answer, references_json) VALUES (?,?,?,?)",
                (int(time.time() * 1000), question, answer, json.dumps(refs, ensure_ascii=False)),
            )
            await conn.commit()
    except Exception as e:
        logger.warning(f"Failed to save QA history: {e}")


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint for knowledge-based Q&A."""

    async def event_stream():
        question = req.question
        references: List[Dict[str, Any]] = []
        context = ""

        # Step 0: Check L3 answer cache (FAQ-type questions)
        answer_cache = get_answer_cache()
        cached_answer = answer_cache.get(question)
        
        if cached_answer is not None:
            logger.info(f"[perf] L3 answer cache HIT for: {question[:50]}...")
            yield f"data: {json.dumps({'type': 'references', 'data': cached_answer.sources}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'content': cached_answer.answer}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'answer': cached_answer.answer, 'cache_hit': True}, ensure_ascii=False)}\n\n"
            return

        # Step 1: Retrieve
        try:
            t0 = time.perf_counter()
            search = get_hybrid_search(req.collection)
            results = search.search(query=question, top_k=req.top_k)
            t_retrieve = time.perf_counter() - t0
            logger.info(f"[perf] retrieval: {t_retrieve:.2f}s")
            references = [
                {"source": r.metadata.get("source_path", "未知"), "score": round(r.score, 4), "text": r.text[:200]}
                for r in results
            ]
            context = _build_context(results)
            yield f"data: {json.dumps({'type': 'references', 'data': references}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("Retrieval failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'检索失败: {e}'}, ensure_ascii=False)}\n\n"
            return

        # --- Optimization: Parallel Image Processing ---
        import asyncio
        from src.core.response.multimodal_assembler import MultimodalAssembler

        async def _extract_images_background(results_list, question_text, coll):
            """Task to run image processing in background."""
            try:
                t2 = time.perf_counter()
                image_storage = ImageStorage()
                assembler = MultimodalAssembler(image_storage)
                MIN_IMAGE_SIZE = 10_000
                MAX_GALLERY_IMAGES = 6
                scored_images = []
                total_results = len(results_list)
                
                for r_rank, r_obj in enumerate(results_list):
                    for img_ref in assembler.extract_image_refs(r_obj):
                        path = await assembler.aresolve_image_path(img_ref, coll)
                        if not path: continue
                        try:
                            if Path(path).stat().st_size < MIN_IMAGE_SIZE: continue
                        except OSError: continue
                        
                        if await image_storage.adetect_background(img_ref.image_id, path):
                            continue
                            
                        rel = _calculate_image_relevance(
                            question_text, img_ref.caption, r_obj.score,
                            rank=r_rank, total_results=total_results,
                        )
                        if rel >= IMAGE_RELEVANCE_THRESHOLD:
                            scored_images.append({
                                "image_id": img_ref.image_id,
                                "path": path,
                                "caption": img_ref.caption,
                                "source": r_obj.metadata.get("source_path", ""),
                                "relevance": round(rel, 3),
                                "chunk_score": round(r_obj.score, 3),
                            })
                final_imgs = sorted(scored_images, key=lambda x: x["relevance"], reverse=True)[:MAX_GALLERY_IMAGES]
                logger.info(f"[perf] background gallery: {time.perf_counter()-t2:.2f}s ({len(final_imgs)} imgs)")
                return final_imgs
            except Exception as e_bg:
                logger.warning(f"Background image extraction failed: {e_bg}")
                return []

        # Start the background task immediately after retrieval
        image_task = asyncio.create_task(_extract_images_background(results, question, req.collection))
        images_sent = False

        # Step 2: Build messages + stream LLM
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        if context:
            messages.append(Message(role="user", content=f"参考资料:\n{context}\n\n问题: {question}"))
        elif req.uploaded_text:
            messages.append(Message(role="user", content=f"文档内容:\n{req.uploaded_text}\n\n问题: {question}"))
        else:
            messages.append(Message(role="user", content=question))

        full_answer = ""
        try:
            t1 = time.perf_counter()
            llm = get_llm()
            for chunk in llm.chat_stream(messages, max_tokens=req.max_tokens):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
                
                # Try to push images early if they are ready while streaming
                if not images_sent and image_task.done():
                    gallery_result = image_task.result()
                    yield f"data: {json.dumps({'type': 'images', 'data': gallery_result}, ensure_ascii=False)}\n\n"
                    images_sent = True

            logger.info(f"[perf] LLM stream: {time.perf_counter()-t1:.2f}s")
        except Exception as e:
            logger.exception("LLM generation failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败: {e}'}, ensure_ascii=False)}\n\n"
            return

        # Ensure images are sent even if LLM finishes before image_task
        if not images_sent:
            gallery_result = await image_task
            yield f"data: {json.dumps({'type': 'images', 'data': gallery_result}, ensure_ascii=False)}\n\n"
            images_sent = True

        # Step 3: Sanitize answer — strip hallucinated IDs + background images
        async def _strip_bad_images(text: str) -> str:
            _img_storage = ImageStorage()
            matches = list(re.finditer(r"\[IMAGE:\s*([^\]]+)\]", text))
            if not matches: return text
            valid_ids = {}
            for m in matches:
                img_id = m.group(1).strip()
                if img_id not in valid_ids:
                    img_path = await _img_storage.aget_image_path(img_id)
                    if not img_path:
                        valid_ids[img_id] = False
                    elif await _img_storage.adetect_background(img_id, img_path):
                        valid_ids[img_id] = False
                    else:
                        valid_ids[img_id] = True
            return re.sub(r"\[IMAGE:\s*([^\]]+)\]", lambda m: m.group(0) if valid_ids.get(m.group(1).strip()) else "", text)

        full_answer = await _strip_bad_images(full_answer)

        # Done event
        yield f"data: {json.dumps({'type': 'done', 'answer': full_answer}, ensure_ascii=False)}\n\n"

        # Caching & History
        try:
            answer_cache.put(query=question, answer=full_answer, sources=references, metadata={"collection": req.collection})
        except Exception: pass
        await _asave_history(question, full_answer, references)
        logger.info(f"[perf] total: {time.perf_counter()-t0:.2f}s")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history")
async def get_history(limit: int = 50):
    """Return recent QA history."""
    try:
        await _ainit_history_db()
        async with get_async_connection(_HISTORY_DB) as conn:
            async with conn.execute(
                "SELECT id, question, answer, references_json, created_at FROM qa_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return {
            "ok": True,
            "data": [
                {
                    "id": r[0], "question": r[1], "answer": r[2],
                    "references": json.loads(r[3]) if r[3] else [],
                    "created_at": r[4],
                }
                for r in reversed(rows)
            ],
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.delete("/history")
async def clear_history():
    """Clear all QA history."""
    try:
        await _ainit_history_db()
        async with get_async_connection(_HISTORY_DB) as conn:
            await conn.execute("DELETE FROM qa_history")
            await conn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}
