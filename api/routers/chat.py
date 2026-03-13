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

from api.deps import get_hybrid_search, get_llm, get_settings
from api.models import ChatRequest
from src.core.settings import resolve_path
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)
router = APIRouter()

_HISTORY_DB = resolve_path("data/qa_history.db")

SYSTEM_PROMPT = """你是一位专业的系统方案架构师。基于提供的参考资料，撰写专业、结构清晰的回答。
要求：
1. 优先使用参考资料中的信息
2. 结构清晰，使用 Markdown 格式
3. 在回答末尾标注参考了哪些来源文档
4. 当方案涉及架构、流程时，使用 Mermaid 语法生成图表
"""


def _build_context(results: list, max_chars: int = 8000) -> str:
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
        parts.append(f"【参考资料 {i+1}】(来源: {source_name})\n{text}")
        total += len(text)
        if total >= max_chars:
            break
    return "\n\n---\n\n".join(parts)


def _init_history_db() -> None:
    _HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_HISTORY_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS qa_history (
        id INTEGER PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        references_json TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()


def _save_history(question: str, answer: str, refs: list) -> None:
    try:
        _init_history_db()
        conn = sqlite3.connect(str(_HISTORY_DB))
        conn.execute(
            "INSERT INTO qa_history (id, question, answer, references_json) VALUES (?,?,?,?)",
            (int(time.time() * 1000), question, answer, json.dumps(refs, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to save QA history: {e}")


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint for knowledge-based Q&A."""

    def event_stream():
        question = req.question
        references: List[Dict[str, Any]] = []
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
            yield f"data: {json.dumps({'type': 'references', 'data': references}, ensure_ascii=False)}\n\n"
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
        conn = sqlite3.connect(str(_HISTORY_DB))
        rows = conn.execute(
            "SELECT id, question, answer, references_json, created_at FROM qa_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
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
        conn = sqlite3.connect(str(_HISTORY_DB))
        conn.execute("DELETE FROM qa_history")
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}
