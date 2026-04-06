"""Bid document writing service — core business logic.

Extracts the heavy orchestration logic (file parsing, LLM clause extraction,
outline generation, content filling, and DOCX export) out of the router layer,
making it independently testable and reusable.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.bid.clause_extractor import extract_clauses
from src.bid.content_filler import fill_outline_stream
from src.bid.docx_exporter import export_to_docx
from src.bid.document_db import (
    DocumentSession,
    get_material,
    get_session,
    list_materials,
    update_session,
)
from src.bid.outline_generator import (
    enrich_outline_with_matches,
    generate_default_outline,
    generate_outline,
)
from src.bid.watermark import add_watermark, generate_watermark_text
from src.core.settings import Settings, load_settings, resolve_path
from src.libs.llm import LLMFactory
from src.libs.llm.base_llm import BaseLLM

logger = logging.getLogger(__name__)


class BidDocumentService:
    """Orchestrates the bid document writing workflow.

    Lifecycle:
        1. parse_tender_file   → extract text from PDF/DOCX/TXT
        2. extract_clauses     → LLM-based clause extraction
        3. generate_outline    → LLM-based outline generation (fallback to rule-based)
        4. fill_content_stream → SSE streaming content generation
        5. export_to_docx      → final document assembly

    Args:
        settings: Application settings (LLM config etc.).
        llm: Pre-built LLM instance. If None, created from settings.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm: Optional[BaseLLM] = None,
    ) -> None:
        """Initialize service with settings and optional pre-built LLM.

        Args:
            settings: Application settings. Loaded automatically if None.
            llm: LLM instance. Created from settings if None.
        """
        self._settings = settings or load_settings()
        self._llm = llm or LLMFactory.create(self._settings)

    # ------------------------------------------------------------------
    # Step 1: Parse tender file
    # ------------------------------------------------------------------

    def parse_tender_file(self, file_path: Path) -> str:
        """Extract text content from a tender file.

        Args:
            file_path: Path to the tender document (PDF/DOCX/TXT).

        Returns:
            Extracted text content.

        Raises:
            ValueError: If format is unsupported or content is empty.
            ImportError: If required parser library is missing.
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            try:
                import fitz

                doc = fitz.open(str(file_path))
                content = "".join(page.get_text() for page in doc)
                doc.close()
            except ImportError:
                raise ImportError("需要安装 PyMuPDF: pip install pymupdf")
        elif suffix in (".docx", ".doc"):
            try:
                from docx import Document

                doc = Document(str(file_path))
                content = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                raise ImportError("需要安装 python-docx: pip install python-docx")
        elif suffix == ".txt":
            content = file_path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

        if not content.strip():
            raise ValueError("文件内容为空")

        return content

    # ------------------------------------------------------------------
    # Step 2: Extract clauses
    # ------------------------------------------------------------------

    async def extract_clauses_from_content(
        self,
        content: str,
    ) -> List[Dict[str, Any]]:
        """Extract structured clauses from tender text via LLM.

        Args:
            content: Raw text content from the tender file.

        Returns:
            List of clause dicts with id, title, description, etc.
        """
        return await extract_clauses(content, self._llm)

    # ------------------------------------------------------------------
    # Step 3: Generate outline
    # ------------------------------------------------------------------

    async def generate_outline_from_clauses(
        self,
        clauses: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Generate a document outline from extracted clauses.

        Falls back to rule-based default outline if LLM generation fails.

        Args:
            clauses: Previously extracted clause list.

        Returns:
            Enriched outline with material category matches.
        """
        try:
            outline = await generate_outline(clauses, self._llm)
        except Exception as e:
            logger.warning(f"LLM outline generation failed, using default: {e}")
            outline = generate_default_outline(clauses)

        return enrich_outline_with_matches(outline)

    # ------------------------------------------------------------------
    # Step 4: Fill content (SSE stream)
    # ------------------------------------------------------------------

    async def fill_content_stream(
        self,
        session: DocumentSession,
    ) -> AsyncGenerator[str, None]:
        """Stream content generation for each outline section.

        Yields SSE-formatted chunks and updates the session on completion.

        Args:
            session: The active document session with outline and clauses.

        Yields:
            SSE data lines (``data: {...}\\n\\n``).
        """
        content_map: Dict[str, str] = {}

        try:
            async for chunk in fill_outline_stream(
                session.outline,
                session.clauses,
                self._llm,
                session.project_name,
                session.project_code,
            ):
                yield chunk

                # Capture section completions for persistence
                try:
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if data.get("type") == "section":
                        content_map[data["section_id"]] = data["content"]
                except Exception:
                    pass

            session.content = content_map
            update_session(session)
        except Exception as e:
            logger.exception("Content fill failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    # ------------------------------------------------------------------
    # Step 5: Export to DOCX
    # ------------------------------------------------------------------

    def export_session_to_docx(
        self,
        session: DocumentSession,
        output_path: Path,
    ) -> Path:
        """Export a completed session to a DOCX file.

        Args:
            session: Session with outline and content.
            output_path: Destination path for the DOCX file.

        Returns:
            The output path of the generated file.

        Raises:
            ValueError: If outline is missing.
        """
        if not session.outline:
            raise ValueError("请先生成大纲")

        # Collect image attachments from materials
        attachments: Dict[str, str] = {}
        for item in session.outline:
            section_id = item.get("id", "")
            category = item.get("material_category")
            if category:
                result = list_materials(category=category, page_size=1)
                materials = result.get("records", [])
                if materials and materials[0].get("file_path"):
                    file_path = materials[0]["file_path"]
                    suffix = Path(file_path).suffix.lower()
                    if suffix in (".jpg", ".jpeg", ".png", ".bmp", ".gif"):
                        attachments[section_id] = file_path

        export_to_docx(
            outline=session.outline,
            content=session.content,
            attachments=attachments,
            output_path=str(output_path),
            project_name=session.project_name,
            project_code=session.project_code,
        )

        session.status = "completed"
        update_session(session)

        return output_path

    # ------------------------------------------------------------------
    # Watermark utility
    # ------------------------------------------------------------------

    @staticmethod
    def add_watermarks(
        material_ids: List[int],
        project_code: str,
    ) -> List[Dict[str, Any]]:
        """Add watermark to specified material files.

        Args:
            material_ids: List of material IDs to watermark.
            project_code: Project code for watermark text.

        Returns:
            List of result dicts per material (id, ok, message, output_path).
        """
        watermark_text = generate_watermark_text(project_code)
        results: List[Dict[str, Any]] = []

        for material_id in material_ids:
            material = get_material(material_id)
            if not material or not material.file_path:
                results.append({"id": material_id, "ok": False, "message": "材料或文件不存在"})
                continue

            file_path = Path(material.file_path)
            if not file_path.exists():
                results.append({"id": material_id, "ok": False, "message": "文件不存在"})
                continue

            try:
                output_path = add_watermark(str(file_path), watermark_text)
                results.append({
                    "id": material_id,
                    "ok": True,
                    "output_path": output_path,
                    "message": "水印添加成功",
                })
            except Exception as e:
                results.append({"id": material_id, "ok": False, "message": str(e)})

        return results
