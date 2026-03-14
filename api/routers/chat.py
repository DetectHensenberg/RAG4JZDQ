"""Chat/QA API router — SSE streaming for knowledge-based Q&A."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.db import get_connection
from api.deps import get_hybrid_search, get_llm, get_settings
from api.models import ChatRequest
from src.core.settings import resolve_path
from src.core.response.multimodal_assembler import MultimodalAssembler
from src.ingestion.storage.image_storage import ImageStorage
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)
router = APIRouter()

# Image relevance threshold (0.0 - 1.0)
# Images with score below this threshold will not be returned
IMAGE_RELEVANCE_THRESHOLD = 0.25


def _calculate_image_relevance(
    question: str,
    caption: str | None,
    chunk_score: float,
) -> float:
    """Calculate image relevance score based on caption semantic matching.
    
    Scoring formula:
    - Base score: chunk retrieval score (0.0 - 1.0)
    - Caption boost: semantic similarity between caption and question
    - Final score = chunk_score * 0.6 + caption_similarity * 0.4
    
    Args:
        question: User's question
        caption: Image caption text (may be None)
        chunk_score: Retrieval score of the chunk containing this image
        
    Returns:
        Relevance score between 0.0 and 1.0
    """
    if not caption:
        # No caption: rely only on chunk score with penalty
        return chunk_score * 0.5
    
    # Simple keyword overlap scoring (fast, no additional API calls)
    question_lower = question.lower()
    caption_lower = caption.lower()
    
    # Tokenize (simple split on whitespace and punctuation)
    import re
    q_tokens = set(re.findall(r'\w+', question_lower))
    c_tokens = set(re.findall(r'\w+', caption_lower))
    
    if not q_tokens or not c_tokens:
        return chunk_score * 0.6
    
    # Jaccard similarity with bonus for exact phrase matches
    intersection = q_tokens & c_tokens
    union = q_tokens | c_tokens
    jaccard = len(intersection) / len(union) if union else 0
    
    # Boost for multi-word phrase matches
    phrase_boost = 0.0
    for i in range(len(question_lower) - 3):
        phrase = question_lower[i:i+4].strip()
        if len(phrase) >= 3 and phrase in caption_lower:
            phrase_boost = 0.2
            break
    
    caption_similarity = min(1.0, jaccard + phrase_boost)
    
    # Weighted combination
    final_score = chunk_score * 0.6 + caption_similarity * 0.4
    
    return final_score

_HISTORY_DB = resolve_path("data/qa_history.db")

SYSTEM_PROMPT = """你是一位专业的系统方案架构师。基于提供的参考资料，撰写专业、结构清晰的回答。

要求：
1. 优先使用参考资料中的信息
2. 结构清晰，使用 Markdown 格式
3. 在回答末尾标注参考了哪些来源文档
4. **优先引用数据库中已有的图片**（参考资料中标注"本段包含图片"的）
5. 仅在以下情况才生成图表：
   - 需要展示简单的线性流程（3-5步）
   - 需要展示简单的时序关系（2-3个角色）
6. **禁止生成复杂图表**：
   - 禁止总分结构（一个节点分出多个子节点）
   - 禁止超过5个节点的图
   - 禁止嵌套结构
7. 如需生成图表，使用 PlantUML 语法：
   ```plantuml
   @startuml
   left to right direction
   步骤1 --> 步骤2 --> 步骤3
   @enduml
   ```

记住：能用文字描述清楚的，就不要生成图表。图表只用于最简单的线性流程。
"""


def _build_context(results: list, max_chars: int = 8000) -> str:
    """Build context string from retrieval results, including image captions."""
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


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint for knowledge-based Q&A."""

    def event_stream():
        question = req.question
        references: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        context = ""

        # Step 1: Retrieve
        try:
            search = get_hybrid_search(req.collection)
            results = search.search(query=question, top_k=req.top_k)
            references = [
                {"source": r.metadata.get("source_path", "未知"), "score": round(r.score, 4), "text": r.text[:200]}
                for r in results
            ]
            context = _build_context(results)
            
            # Extract images from retrieval results with relevance scoring
            try:
                image_storage = ImageStorage()
                assembler = MultimodalAssembler(image_storage)
                
                scored_images = []
                for r in results:
                    chunk_score = r.score
                    img_refs = assembler.extract_image_refs(r)
                    for ref in img_refs:
                        img_path = assembler.resolve_image_path(ref, req.collection)
                        if img_path:
                            # Calculate relevance score
                            relevance = _calculate_image_relevance(
                                question, ref.caption, chunk_score
                            )
                            
                            # Only include images above threshold
                            if relevance >= IMAGE_RELEVANCE_THRESHOLD:
                                scored_images.append({
                                    "image_id": ref.image_id,
                                    "path": img_path,
                                    "caption": ref.caption,
                                    "source": r.metadata.get("source_path", ""),
                                    "relevance": round(relevance, 3),
                                    "chunk_score": round(chunk_score, 3),
                                })
                
                # Sort by relevance (highest first)
                images = sorted(scored_images, key=lambda x: x["relevance"], reverse=True)
                
                if images:
                    logger.info(f"Found {len(images)} relevant images (threshold={IMAGE_RELEVANCE_THRESHOLD})")
            except Exception as e:
                logger.warning(f"Failed to extract images: {e}")
            
            yield f"data: {json.dumps({'type': 'references', 'data': references}, ensure_ascii=False)}\n\n"
            
            # Send images if any
            if images:
                yield f"data: {json.dumps({'type': 'images', 'data': images}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("Retrieval failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'检索失败: {e}'}, ensure_ascii=False)}\n\n"
            return

        # Step 2: Build messages
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        if context:
            messages.append(Message(role="user", content=f"参考资料:\n{context}\n\n问题: {question}"))
        elif req.uploaded_text:
            messages.append(Message(role="user", content=f"文档内容:\n{req.uploaded_text}\n\n问题: {question}"))
        else:
            messages.append(Message(role="user", content=question))

        # Step 3: Stream LLM
        full_answer = ""
        try:
            llm = get_llm()
            for chunk in llm.chat_stream(messages, max_tokens=req.max_tokens):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("LLM generation failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败: {e}'}, ensure_ascii=False)}\n\n"
            return

        # Step 4: Done
        yield f"data: {json.dumps({'type': 'done', 'answer': full_answer}, ensure_ascii=False)}\n\n"

        # Save to history
        _save_history(question, full_answer, references)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history")
async def get_history(limit: int = 50):
    """Return recent QA history."""
    try:
        _init_history_db()
        with get_connection(_HISTORY_DB) as conn:
            rows = conn.execute(
                "SELECT id, question, answer, references_json, created_at FROM qa_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
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
        _init_history_db()
        with get_connection(_HISTORY_DB) as conn:
            conn.execute("DELETE FROM qa_history")
            conn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}
