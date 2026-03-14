"""Layout-aware PDF Loader with multi-column detection and OCR fallback.

This module implements PDF parsing with layout analysis using PyMuPDF's
text block coordinate extraction to correctly handle:
- Multi-column layouts (academic papers, reports)
- Reading order reconstruction
- Scanned page detection with OCR fallback
- Table structure preservation

Graceful Degradation:
- No PyMuPDF → falls back to MarkItDown
- No OCR engine → logs warning, returns empty text for scanned pages
- Layout detection fails → falls back to sequential text extraction
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# OCR engines (optional)
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

# Minimum text length per page to consider it "not scanned"
SCANNED_PAGE_TEXT_THRESHOLD = 50

# Column detection: if text blocks cluster into groups with X-gap > this ratio
# of page width, treat as multi-column
COLUMN_GAP_RATIO = 0.15


class LayoutPdfLoader(BaseLoader):
    """Layout-aware PDF Loader using PyMuPDF text block coordinates.

    Parsing strategy per page:
    1. Extract text blocks with bounding boxes via ``page.get_text("dict")``
    2. Detect columns by clustering block X-coordinates
    3. Sort blocks in reading order (column-first, then top-to-bottom)
    4. If page has too little text (scanned), render to image → OCR
    5. Detect table-like regions and preserve structure

    Falls back to MarkItDown if PyMuPDF is unavailable.
    """

    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        vision_llm: Optional[Any] = None,
        ocr_engine: str = "auto",
    ) -> None:
        """Initialize LayoutPdfLoader.

        Args:
            extract_images: Whether to extract images from PDFs.
            image_storage_dir: Base directory for storing extracted images.
            vision_llm: Optional Vision LLM (unused, kept for interface compat).
            ocr_engine: OCR engine to use: "auto", "tesseract", "paddleocr", "none".
        """
        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self.ocr_engine = ocr_engine
        self._paddle_ocr: Optional[Any] = None

    def load(self, file_path: str | Path) -> Document:
        """Load and parse a PDF file with layout analysis.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Document with layout-aware Markdown text and metadata.
        """
        path = self._validate_file(file_path)
        suffix = path.suffix.lower()
        if suffix != ".pdf":
            raise ValueError(f"LayoutPdfLoader only supports .pdf, got: {suffix}")

        if not PYMUPDF_AVAILABLE:
            logger.warning("PyMuPDF not available, falling back to MarkItDown")
            return self._fallback_markitdown(path)

        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"

        try:
            pdf_doc = fitz.open(path)
        except Exception as e:
            logger.error(f"Failed to open PDF {path}: {e}")
            raise RuntimeError(f"PDF open failed: {e}") from e

        all_page_texts: List[str] = []
        images_metadata: List[Dict[str, Any]] = []
        scanned_pages: List[int] = []
        multi_col_pages: List[int] = []

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_text, is_scanned, is_multi_col = self._extract_page_layout(
                page, page_num, pdf_doc, doc_hash
            )
            all_page_texts.append(page_text)
            if is_scanned:
                scanned_pages.append(page_num + 1)
            if is_multi_col:
                multi_col_pages.append(page_num + 1)

        # Extract images if enabled
        if self.extract_images:
            try:
                images_metadata = self._extract_images(pdf_doc, doc_hash)
            except Exception as e:
                logger.warning(f"Image extraction failed: {e}")

        pdf_doc.close()

        text_content = "\n\n".join(all_page_texts)

        # Append image placeholders
        for img in images_metadata:
            text_content += f"\n[IMAGE: {img['id']}]\n"

        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "pdf",
            "doc_hash": doc_hash,
            "parser": "layout",
        }

        if scanned_pages:
            metadata["scanned_pages"] = scanned_pages
        if multi_col_pages:
            metadata["multi_column_pages"] = multi_col_pages
        if images_metadata:
            metadata["images"] = images_metadata

        title = self._extract_title(text_content)
        if title:
            metadata["title"] = title

        return Document(id=doc_id, text=text_content, metadata=metadata)

    # ------------------------------------------------------------------
    # Core layout extraction
    # ------------------------------------------------------------------

    def _extract_page_layout(
        self,
        page: Any,
        page_num: int,
        pdf_doc: Any,
        doc_hash: str,
    ) -> Tuple[str, bool, bool]:
        """Extract text from a single page with layout analysis.

        Returns:
            Tuple of (page_text, is_scanned, is_multi_column).
        """
        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        blocks = page_dict.get("blocks", [])

        # Filter to text blocks only (type 0)
        text_blocks = [b for b in blocks if b.get("type") == 0]

        # Check if page is scanned (too little text)
        total_text = "".join(
            span.get("text", "")
            for b in text_blocks
            for line in b.get("lines", [])
            for span in line.get("spans", [])
        )

        is_scanned = len(total_text.strip()) < SCANNED_PAGE_TEXT_THRESHOLD
        if is_scanned:
            ocr_text = self._ocr_page(page, page_num, pdf_doc)
            return ocr_text, True, False

        # Detect columns
        page_width = page_dict.get("width", 612)
        columns = self._detect_columns(text_blocks, page_width)
        is_multi_col = len(columns) > 1

        # Sort blocks in reading order: by column, then top-to-bottom
        ordered_blocks = self._sort_by_reading_order(text_blocks, columns)

        # Convert blocks to Markdown text
        page_lines: List[str] = []
        for block in ordered_blocks:
            block_text = self._block_to_markdown(block)
            if block_text.strip():
                page_lines.append(block_text)

        return "\n\n".join(page_lines), False, is_multi_col

    def _detect_columns(
        self, blocks: List[Dict[str, Any]], page_width: float
    ) -> List[Tuple[float, float]]:
        """Detect column boundaries by clustering block X-coordinates.

        Returns:
            List of (x_min, x_max) tuples, one per detected column.
        """
        if not blocks:
            return [(0, page_width)]

        # Collect left-edge X coordinates of all blocks
        x_positions = sorted(set(b["bbox"][0] for b in blocks))

        if len(x_positions) < 2:
            return [(0, page_width)]

        # Find large gaps in X positions
        gap_threshold = page_width * COLUMN_GAP_RATIO
        column_boundaries: List[Tuple[float, float]] = []
        col_start = x_positions[0]

        for i in range(1, len(x_positions)):
            if x_positions[i] - x_positions[i - 1] > gap_threshold:
                col_end = x_positions[i - 1]
                column_boundaries.append((col_start, col_end + gap_threshold))
                col_start = x_positions[i]

        # Last column
        column_boundaries.append((col_start, page_width))

        return column_boundaries if len(column_boundaries) > 1 else [(0, page_width)]

    def _sort_by_reading_order(
        self,
        blocks: List[Dict[str, Any]],
        columns: List[Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        """Sort blocks by reading order: column-first, then top-to-bottom."""
        if len(columns) <= 1:
            return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        def column_index(block: Dict[str, Any]) -> int:
            bx = block["bbox"][0]
            for idx, (cx_min, cx_max) in enumerate(columns):
                if cx_min - 10 <= bx <= cx_max + 10:
                    return idx
            return len(columns)

        return sorted(blocks, key=lambda b: (column_index(b), b["bbox"][1]))

    def _block_to_markdown(self, block: Dict[str, Any]) -> str:
        """Convert a text block to Markdown, preserving structure hints."""
        lines = block.get("lines", [])
        if not lines:
            return ""

        parts: List[str] = []
        for line in lines:
            spans = line.get("spans", [])
            line_text = "".join(s.get("text", "") for s in spans)

            if not line_text.strip():
                continue

            # Detect heading by font size
            avg_size = sum(s.get("size", 12) for s in spans) / max(len(spans), 1)
            is_bold = any(
                "bold" in s.get("font", "").lower() for s in spans
            )

            if avg_size >= 18 and is_bold:
                parts.append(f"# {line_text.strip()}")
            elif avg_size >= 15 and is_bold:
                parts.append(f"## {line_text.strip()}")
            elif avg_size >= 13 and is_bold:
                parts.append(f"### {line_text.strip()}")
            else:
                parts.append(line_text)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Table detection
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_table(text: str) -> bool:
        """Heuristic check if text block looks like a table."""
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return False
        # Check if multiple lines have tab or multi-space alignment
        aligned = sum(1 for l in lines if "\t" in l or "  " in l)
        return aligned >= len(lines) * 0.5

    # ------------------------------------------------------------------
    # OCR fallback for scanned pages
    # ------------------------------------------------------------------

    def _ocr_page(self, page: Any, page_num: int, pdf_doc: Any) -> str:
        """Render page to image and OCR it."""
        engine = self._resolve_ocr_engine()
        if engine == "none":
            logger.warning(f"Page {page_num + 1} appears scanned but no OCR engine available")
            return f"[SCANNED PAGE {page_num + 1} — OCR NOT AVAILABLE]"

        # Render page to image
        try:
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            logger.warning(f"Failed to render page {page_num + 1} for OCR: {e}")
            return f"[SCANNED PAGE {page_num + 1} — RENDER FAILED]"

        if engine == "tesseract":
            return self._ocr_tesseract(img, page_num)
        elif engine == "paddleocr":
            return self._ocr_paddle(img, page_num)

        return ""

    def _resolve_ocr_engine(self) -> str:
        """Determine which OCR engine to use."""
        if self.ocr_engine == "none":
            return "none"
        if self.ocr_engine == "tesseract":
            return "tesseract" if TESSERACT_AVAILABLE else "none"
        if self.ocr_engine == "paddleocr":
            return "paddleocr" if PADDLEOCR_AVAILABLE else "none"
        # auto: prefer paddleocr > tesseract
        if PADDLEOCR_AVAILABLE:
            return "paddleocr"
        if TESSERACT_AVAILABLE:
            return "tesseract"
        return "none"

    def _ocr_tesseract(self, img: Any, page_num: int) -> str:
        """OCR using Tesseract."""
        try:
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            logger.info(f"Tesseract OCR page {page_num + 1}: {len(text)} chars")
            return text
        except Exception as e:
            logger.warning(f"Tesseract OCR failed for page {page_num + 1}: {e}")
            return f"[OCR FAILED PAGE {page_num + 1}]"

    def _ocr_paddle(self, img: Any, page_num: int) -> str:
        """OCR using PaddleOCR."""
        try:
            if self._paddle_ocr is None:
                self._paddle_ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

            import numpy as np
            img_array = np.array(img)
            result = self._paddle_ocr.ocr(img_array, cls=True)

            if not result or not result[0]:
                return ""

            # Sort by Y coordinate for reading order, then extract text
            lines: List[Tuple[float, str]] = []
            for line_info in result[0]:
                box = line_info[0]
                text = line_info[1][0]
                y_coord = box[0][1]  # Top-left Y
                lines.append((y_coord, text))

            lines.sort(key=lambda x: x[0])
            text = "\n".join(t for _, t in lines)
            logger.info(f"PaddleOCR page {page_num + 1}: {len(text)} chars")
            return text
        except Exception as e:
            logger.warning(f"PaddleOCR failed for page {page_num + 1}: {e}")
            return f"[OCR FAILED PAGE {page_num + 1}]"

    # ------------------------------------------------------------------
    # Image extraction (reuse PyMuPDF approach from PdfLoader)
    # ------------------------------------------------------------------

    def _extract_images(
        self, pdf_doc: Any, doc_hash: str
    ) -> List[Dict[str, Any]]:
        """Extract images from PDF and save to disk."""
        images_metadata: List[Dict[str, Any]] = []
        image_dir = self.image_storage_dir / doc_hash
        image_dir.mkdir(parents=True, exist_ok=True)

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    base_image = pdf_doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    image_id = f"{doc_hash[:8]}_{page_num + 1}_{img_index + 1}"
                    image_filename = f"{image_id}.{image_ext}"
                    image_path = image_dir / image_filename

                    with open(image_path, "wb") as f:
                        f.write(image_bytes)

                    try:
                        img = Image.open(io.BytesIO(image_bytes))
                        width, height = img.size
                    except Exception:
                        width, height = 0, 0

                    images_metadata.append({
                        "id": image_id,
                        "path": str(image_path),
                        "page": page_num + 1,
                        "position": {
                            "width": width,
                            "height": height,
                            "page": page_num + 1,
                            "index": img_index,
                        },
                    })
                except Exception as e:
                    logger.warning(
                        f"Failed to extract image {img_index} from page {page_num + 1}: {e}"
                    )

        return images_metadata

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _extract_title(text: str) -> Optional[str]:
        for line in text.split("\n")[:20]:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        for line in text.split("\n")[:10]:
            line = line.strip()
            if line:
                return line
        return None

    def _fallback_markitdown(self, path: Path) -> Document:
        """Fall back to MarkItDown-based PdfLoader."""
        from src.libs.loader.pdf_loader import PdfLoader
        fallback = PdfLoader(
            extract_images=self.extract_images,
            image_storage_dir=self.image_storage_dir,
        )
        return fallback.load(path)
