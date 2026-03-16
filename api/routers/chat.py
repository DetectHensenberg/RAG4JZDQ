"""Chat/QA API router — SSE streaming for knowledge-based Q&A."""

from __future__ import annotations

import json
import logging
import re
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


def _is_background_image(img_path: str, min_edge: float = 8.0, min_dim: int = 150) -> bool:
    """Return True if the image looks like a PPT background / decoration.

    Uses gradient-based edge strength: real content (tables, diagrams, text)
    has edge > 8, while gradients and solid backgrounds have edge < 5.
    """
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        if w < min_dim or h < min_dim:
            return True  # too small (icon)

        # Down-sample large images for speed
        if w > 800 or h > 800:
            img.thumbnail((800, 800))

        arr = np.array(img, dtype=np.float32)
        gray = arr.mean(axis=2)
        gx = np.diff(gray, axis=1)
        gy = np.diff(gray, axis=0)
        edge_strength = (np.abs(gx).mean() + np.abs(gy).mean()) / 2.0
        return edge_strength < min_edge
    except Exception:
        return False  # if analysis fails, keep the image
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)
router = APIRouter()

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
- **当参考资料中有 [IMAGE: xxx] 图片引用时，必须在回答的相关位置原样引用**
- 引用格式：直接输出 [IMAGE: xxx]（保持原始 ID 不变），系统会自动渲染为图片
- 在图片引用后面附上简要说明文字
- 示例：如参考资料中有 [IMAGE: abc123_s1_2]，则在回答中写：

  [IMAGE: abc123_s1_2]
  *图：XX架构示意图*

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


def _strip_background_images(text: str, collection: str = "default") -> str:
    """Remove [IMAGE: id]\\n(Description: ...) blocks for background images."""
    image_storage = ImageStorage()
    assembler = MultimodalAssembler(image_storage)

    def _check_replace(m: re.Match) -> str:
        img_id = m.group(1).strip()
        img_path = None
        try:
            from src.core.response.multimodal_assembler import ImageReference
            ref = ImageReference(image_id=img_id)
            img_path = assembler.resolve_image_path(ref, collection)
        except Exception:
            pass
        if img_path and _is_background_image(img_path):
            return ""  # strip this image reference
        return m.group(0)  # keep it

    # Match [IMAGE: id]\n(Description: ...)\n
    return re.sub(
        r"\[IMAGE:\s*([^\]]+)\]\s*\n\(Description:[^\)]*\)\s*\n?",
        _check_replace,
        text,
    )


def _build_context(results: list, max_chars: int = 8000) -> str:
    """Build context string from retrieval results, including image captions."""
    parts = []
    total = 0
    for i, r in enumerate(results):
        source = r.metadata.get("source_path", "未知来源")
        source_name = Path(source).name if source != "未知来源" else source
        text = _strip_background_images(r.text)
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
                
                MIN_IMAGE_SIZE = 10_000  # Skip images < 10KB (icons, color blocks)
                MAX_GALLERY_IMAGES = 6
                
                scored_images = []
                total_results = len(results)
                for rank, r in enumerate(results):
                    chunk_score = r.score
                    img_refs = assembler.extract_image_refs(r)
                    for ref in img_refs:
                        img_path = assembler.resolve_image_path(ref, req.collection)
                        if img_path:
                            # Skip tiny images
                            try:
                                file_size = Path(img_path).stat().st_size
                                if file_size < MIN_IMAGE_SIZE:
                                    continue
                            except OSError:
                                continue
                            # Skip PPT backgrounds / gradients (low edge content)
                            if _is_background_image(img_path):
                                continue
                            
                            # Calculate relevance score
                            relevance = _calculate_image_relevance(
                                question, ref.caption, chunk_score,
                                rank=rank, total_results=total_results,
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
                
                # Sort by relevance (highest first), cap at MAX_GALLERY_IMAGES
                images = sorted(scored_images, key=lambda x: x["relevance"], reverse=True)[:MAX_GALLERY_IMAGES]
                
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
