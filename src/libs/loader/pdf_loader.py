"""PDF Loader implementation using MarkItDown.

This module implements PDF parsing with image extraction support,
converting PDFs to standardized Markdown format with image placeholders.

Features:
- Text extraction and Markdown conversion via MarkItDown
- Image extraction and storage
- Image placeholder insertion with metadata tracking
- Graceful degradation if image extraction fails
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from PIL import Image
import io

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class PdfLoader(BaseLoader):
    """PDF Loader using MarkItDown for text extraction and Markdown conversion.
    
    This loader:
    1. Extracts text from PDF and converts to Markdown
    2. Extracts images and saves to data/images/{doc_hash}/
    3. Inserts image placeholders in the format [IMAGE: {image_id}]
    4. Records image metadata in Document.metadata.images
    
    Configuration:
        extract_images: Enable/disable image extraction (default: True)
        image_storage_dir: Base directory for image storage (default: data/images)
    
    Graceful Degradation:
        If image extraction fails, logs warning and continues with text-only parsing.
    """
    
    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        vision_llm: Any = None,
    ):
        """Initialize PDF Loader.
        
        Args:
            extract_images: Whether to extract images from PDFs.
            image_storage_dir: Base directory for storing extracted images.
        """
        if not MARKITDOWN_AVAILABLE:
            raise ImportError(
                "MarkItDown is required for PdfLoader. "
                "Install with: pip install markitdown"
            )
        
        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self._markitdown = MarkItDown()
    
    def load(self, file_path: str | Path) -> Document:
        """Load and parse a PDF file.
        
        Args:
            file_path: Path to the PDF file.
            
        Returns:
            Document with Markdown text and metadata.
            
        Raises:
            FileNotFoundError: If the PDF file doesn't exist.
            ValueError: If the file is not a valid PDF.
            RuntimeError: If parsing fails critically.
        """
        # Validate file
        path = self._validate_file(file_path)
        suffix = path.suffix.lower()
        supported = ('.pdf', '.md', '.docx', '.txt')
        if suffix not in supported:
            raise ValueError(f"Unsupported file type: {path} (supported: {supported})")
        
        # Compute document hash for unique ID and image directory
        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"
        
        # Parse PDF with MarkItDown
        try:
            result = self._markitdown.convert(str(path))
            text_content = result.text_content if hasattr(result, 'text_content') else str(result)
        except (IOError, OSError, ValueError, RuntimeError) as e:
            logger.error(f"Failed to parse PDF {path}: {e}")
            raise RuntimeError(f"PDF parsing failed: {e}") from e
        
        # Initialize metadata
        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": suffix.lstrip('.'),
            "doc_hash": doc_hash,
        }
        
        # Extract title from first heading if available
        title = self._extract_title(text_content)
        if title:
            metadata["title"] = title
        
        # Handle image extraction (PDF only, with graceful degradation)
        if self.extract_images and suffix == '.pdf':
            try:
                text_content, images_metadata = self._extract_and_process_images(
                    path, text_content, doc_hash
                )
                if images_metadata:
                    metadata["images"] = images_metadata
            except Exception as e:
                logger.warning(
                    f"Image extraction failed for {path}, continuing with text-only: {e}"
                )
        
        return Document(
            id=doc_id,
            text=text_content,
            metadata=metadata
        )
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content.
        
        Args:
            file_path: Path to file.
            
        Returns:
            Hex string of SHA256 hash.
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from first Markdown heading or first non-empty line.
        
        Args:
            text: Markdown text content.
            
        Returns:
            Title string if found, None otherwise.
        """
        lines = text.split('\n')
        
        # First try to find a markdown heading
        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        
        # Fallback: use first non-empty line as title
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 0:
                return line
        
        return None
    
    # Render DPI for full-page images (150 = good balance of quality vs size)
    RENDER_DPI = 150
    # Maximum pixel dimension (longest side). If a page would exceed this
    # at RENDER_DPI, the DPI is reduced proportionally for that page.
    MAX_RENDER_DIM = 2000
    # Minimum number of embedded images on a page to trigger rendering.
    # Pages with 0 images are pure text and don't need a render.
    MIN_IMAGES_FOR_RENDER = 1

    def _extract_and_process_images(
        self,
        pdf_path: Path,
        text_content: str,
        doc_hash: str,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Render PDF pages as full images instead of extracting fragments.

        Previous approach used ``page.get_images()`` which decomposes each page
        into its constituent image xrefs — a single architecture diagram could
        become dozens of tiny fragments (icons, gradients, background tiles).

        New approach: render each page that contains images as a single
        high-quality PNG via ``page.get_pixmap()``.  This produces one clean,
        complete image per page — exactly what the user sees.

        Args:
            pdf_path: Path to PDF file.
            text_content: Extracted text content.
            doc_hash: Document hash for image directory.

        Returns:
            Tuple of (modified_text, images_metadata_list)
        """
        if not self.extract_images:
            logger.debug(f"Image extraction disabled for {pdf_path}")
            return text_content, []

        if not PYMUPDF_AVAILABLE:
            logger.warning(f"PyMuPDF not available, skipping image extraction for {pdf_path}")
            return text_content, []

        images_metadata: List[Dict[str, Any]] = []
        modified_text = text_content

        try:
            image_dir = self.image_storage_dir / doc_hash
            image_dir.mkdir(parents=True, exist_ok=True)

            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            base_scale = self.RENDER_DPI / 72

            for page_num in range(total_pages):
                page = doc[page_num]

                # Only render pages that contain visual content
                if len(page.get_images(full=True)) < self.MIN_IMAGES_FOR_RENDER:
                    continue

                try:
                    # Dynamically reduce DPI if page would exceed MAX_RENDER_DIM
                    rect = page.rect
                    max_side = max(rect.width * base_scale, rect.height * base_scale)
                    if max_side > self.MAX_RENDER_DIM:
                        scale = self.MAX_RENDER_DIM / max(rect.width, rect.height) / (72 / 72)
                        mat = fitz.Matrix(scale, scale)
                    else:
                        mat = fitz.Matrix(base_scale, base_scale)

                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    slide_num = page_num + 1

                    image_id = self._generate_image_id(doc_hash, slide_num, 1)
                    image_filename = f"{image_id}.png"
                    image_path = image_dir / image_filename

                    pix.save(str(image_path))

                    width, height = pix.width, pix.height
                    placeholder = f"[IMAGE: {image_id}]"

                    # Append placeholder at end of text
                    insert_position = len(modified_text)
                    modified_text += f"\n{placeholder}\n"

                    try:
                        relative_path = image_path.relative_to(Path.cwd())
                    except ValueError:
                        relative_path = image_path.absolute()

                    images_metadata.append({
                        "id": image_id,
                        "path": str(relative_path),
                        "page": slide_num,
                        "text_offset": insert_position + 1,
                        "text_length": len(placeholder),
                        "position": {
                            "width": width,
                            "height": height,
                            "page": slide_num,
                            "index": 1,
                        },
                        "render_method": "page_pixmap",
                    })

                    logger.debug(f"Rendered page {slide_num} as {image_id} ({width}x{height})")

                except Exception as e:
                    logger.warning(f"Failed to render page {page_num + 1}: {e}")
                    continue

            doc.close()

            if images_metadata:
                logger.info(
                    f"Rendered {len(images_metadata)} page images from {pdf_path} "
                    f"(was {total_pages} pages, skipped text-only pages)"
                )
            else:
                logger.debug(f"No visual pages found in {pdf_path}")

            return modified_text, images_metadata

        except Exception as e:
            logger.warning(f"Image extraction failed for {pdf_path}: {e}")
            return text_content, []
    
    @staticmethod
    def _generate_image_id(doc_hash: str, page: int, sequence: int) -> str:
        """Generate unique image ID.
        
        Args:
            doc_hash: Document hash.
            page: Page number (0-based).
            sequence: Image sequence on page (0-based).
            
        Returns:
            Unique image ID string.
        """
        return f"{doc_hash[:8]}_{page}_{sequence}"
