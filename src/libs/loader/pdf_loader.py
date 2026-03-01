"""PDF Loader implementation using MarkItDown with Vision LLM fallback.

This module implements PDF parsing with image extraction support,
converting PDFs to standardized Markdown format with image placeholders.

For scanned or image-based PDF pages (low text density), the loader
can optionally use a Vision LLM to extract content by rendering pages
to images and sending them for multimodal understanding.

Features:
- Text extraction and Markdown conversion via MarkItDown
- Scanned/image-based page detection via text density analysis
- Vision LLM fallback for pages with insufficient text
- Image extraction and storage
- Image placeholder insertion with metadata tracking
- Graceful degradation if image extraction or Vision LLM fails
"""

from __future__ import annotations

import base64
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

# Minimum characters per page to consider it text-based.
# Pages below this threshold are treated as scanned/image-based.
MIN_TEXT_CHARS_PER_PAGE = 50

# DPI for rendering PDF pages to images for Vision LLM
RENDER_DPI = 200

# Default prompt for Vision LLM page understanding
DEFAULT_PAGE_PROMPT = (
    "You are a document OCR and understanding assistant. "
    "Extract ALL text content from this document page image. "
    "Preserve the original structure including headings, lists, tables, and paragraphs. "
    "Output the content in clean Markdown format. "
    "If there are diagrams or charts, describe them briefly. "
    "Do NOT add any commentary — only output the extracted content."
)


class PdfLoader(BaseLoader):
    """PDF Loader using MarkItDown for text extraction and Markdown conversion.
    
    This loader:
    1. Extracts text from PDF and converts to Markdown via MarkItDown
    2. Detects scanned/image-based pages via text density analysis
    3. Uses Vision LLM to extract content from scanned pages (if provided)
    4. Extracts images and saves to data/images/{doc_hash}/
    5. Inserts image placeholders in the format [IMAGE: {image_id}]
    6. Records image metadata in Document.metadata.images
    
    Configuration:
        extract_images: Enable/disable image extraction (default: True)
        image_storage_dir: Base directory for image storage (default: data/images)
        vision_llm: Optional Vision LLM instance for scanned page understanding
        page_prompt: Custom prompt for Vision LLM page extraction
    
    Graceful Degradation:
        - If Vision LLM is not provided, scanned pages use MarkItDown output as-is
        - If Vision LLM call fails, falls back to MarkItDown output for that page
        - If image extraction fails, continues with text-only parsing
    """
    
    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        vision_llm: Optional[Any] = None,
        page_prompt: Optional[str] = None,
    ):
        """Initialize PDF Loader.
        
        Args:
            extract_images: Whether to extract images from PDFs.
            image_storage_dir: Base directory for storing extracted images.
            vision_llm: Optional BaseVisionLLM instance for scanned page OCR.
            page_prompt: Custom prompt for Vision LLM page extraction.
        """
        if not MARKITDOWN_AVAILABLE:
            raise ImportError(
                "MarkItDown is required for PdfLoader. "
                "Install with: pip install markitdown"
            )
        
        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self.vision_llm = vision_llm
        self.page_prompt = page_prompt or DEFAULT_PAGE_PROMPT
        self._markitdown = MarkItDown()
    
    # File types supported by MarkItDown
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

    def load(self, file_path: str | Path) -> Document:
        """Load and parse a document file.
        
        For PDF files, the loader:
        1. First extracts text via MarkItDown (fast, works for text-based PDFs)
        2. Then checks each page's text density via PyMuPDF
        3. For scanned pages (text < MIN_TEXT_CHARS_PER_PAGE), renders to image
           and uses Vision LLM to extract content
        4. Merges results: text pages from MarkItDown + scanned pages from Vision LLM
        
        Args:
            file_path: Path to the document file (.pdf, .docx, .txt, .md).
            
        Returns:
            Document with Markdown text and metadata.
            
        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file type is not supported.
            RuntimeError: If parsing fails critically.
        """
        # Validate file
        path = self._validate_file(file_path)
        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{suffix}': {path}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
        
        # Compute document hash for unique ID and image directory
        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"
        
        # Parse document with MarkItDown (baseline extraction)
        try:
            result = self._markitdown.convert(str(path))
            text_content = result.text_content if hasattr(result, 'text_content') else str(result)
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")
            raise RuntimeError(f"Document parsing failed: {e}") from e
        
        # For PDFs: enhance with Vision LLM for scanned/image-based pages
        vision_pages_processed = 0
        if suffix == '.pdf' and PYMUPDF_AVAILABLE:
            try:
                text_content, vision_pages_processed = self._enhance_with_vision(
                    path, text_content, doc_hash
                )
            except Exception as e:
                logger.warning(
                    f"Vision enhancement failed for {path}, using MarkItDown output: {e}"
                )
        
        # Initialize metadata
        doc_type = suffix.lstrip('.')
        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": doc_type,
            "doc_hash": doc_hash,
        }
        
        if vision_pages_processed > 0:
            metadata["vision_pages_processed"] = vision_pages_processed
        
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
    
    def _enhance_with_vision(
        self,
        pdf_path: Path,
        markitdown_text: str,
        doc_hash: str,
    ) -> tuple[str, int]:
        """Detect scanned pages and use Vision LLM to extract their content.
        
        Strategy:
        1. Open PDF with PyMuPDF, iterate pages
        2. For each page, get raw text via PyMuPDF (fast, no conversion)
        3. If text length < MIN_TEXT_CHARS_PER_PAGE, page is likely scanned
        4. Render scanned page to image, send to Vision LLM
        5. Build final text by combining MarkItDown output for text pages
           with Vision LLM output for scanned pages
        
        Args:
            pdf_path: Path to PDF file.
            markitdown_text: Text extracted by MarkItDown (used for text-rich pages).
            doc_hash: Document hash for image directory naming.
            
        Returns:
            Tuple of (final_text, number_of_vision_pages_processed)
        """
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        if total_pages == 0:
            doc.close()
            return markitdown_text, 0
        
        # Analyze each page's text density
        page_texts = []
        scanned_pages = []
        for page_num in range(total_pages):
            page = doc[page_num]
            page_text = page.get_text("text").strip()
            page_texts.append(page_text)
            if len(page_text) < MIN_TEXT_CHARS_PER_PAGE:
                scanned_pages.append(page_num)
        
        # If no scanned pages detected, return MarkItDown output as-is
        if not scanned_pages:
            doc.close()
            logger.debug(f"All {total_pages} pages are text-based, using MarkItDown output")
            return markitdown_text, 0
        
        logger.info(
            f"Detected {len(scanned_pages)}/{total_pages} scanned pages in {pdf_path}: "
            f"pages {[p + 1 for p in scanned_pages]}"
        )
        
        # If no Vision LLM, log warning and return MarkItDown output
        if not self.vision_llm:
            doc.close()
            logger.warning(
                f"Found {len(scanned_pages)} scanned pages but no Vision LLM configured. "
                f"Set vision_llm.enabled=true in settings.yaml for OCR support."
            )
            return markitdown_text, 0
        
        # Process scanned pages with Vision LLM (parallel)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Pre-render pages to images before closing doc
        page_images: Dict[int, bytes] = {}
        for page_num in scanned_pages:
            page = doc[page_num]
            mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            page_images[page_num] = pix.tobytes("png")
        
        doc.close()
        
        def _ocr_page(page_num: int) -> tuple[int, str | None]:
            try:
                vision_text = self._process_rendered_page_with_vision(
                    page_images[page_num], page_num, doc_hash,
                )
                if vision_text:
                    logger.info(f"  Vision LLM extracted {len(vision_text)} chars from page {page_num + 1}")
                return page_num, vision_text
            except Exception as e:
                logger.warning(f"  Vision LLM failed for page {page_num + 1}: {e}")
                return page_num, None
        
        vision_results: Dict[int, str] = {}
        max_workers = min(5, len(scanned_pages))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_ocr_page, pn) for pn in scanned_pages]
            for future in as_completed(futures):
                pn, text = future.result()
                if text:
                    vision_results[pn] = text
        
        if not vision_results:
            return markitdown_text, 0
        
        # Build final text: for all-scanned PDFs, use vision output entirely;
        # for mixed PDFs, combine per-page text with vision results
        if len(scanned_pages) == total_pages:
            # All pages are scanned — build from vision results only
            parts = []
            for page_num in range(total_pages):
                if page_num in vision_results:
                    parts.append(f"<!-- Page {page_num + 1} (Vision) -->\n{vision_results[page_num]}")
                elif page_texts[page_num]:
                    parts.append(f"<!-- Page {page_num + 1} -->\n{page_texts[page_num]}")
            final_text = "\n\n".join(parts)
        else:
            # Mixed PDF — append vision results to MarkItDown text
            vision_appendix = []
            for page_num in sorted(vision_results.keys()):
                vision_appendix.append(
                    f"\n\n<!-- Page {page_num + 1} (Vision OCR) -->\n{vision_results[page_num]}"
                )
            final_text = markitdown_text + "".join(vision_appendix)
        
        return final_text, len(vision_results)
    
    def _process_page_with_vision(
        self,
        page: Any,
        page_num: int,
        doc_hash: str,
    ) -> Optional[str]:
        """Render a single PDF page to image and extract content via Vision LLM.
        
        Args:
            page: PyMuPDF page object.
            page_num: 0-based page number.
            doc_hash: Document hash for naming.
            
        Returns:
            Extracted text content or None if failed.
        """
        mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image_bytes = pix.tobytes("png")
        return self._process_rendered_page_with_vision(image_bytes, page_num, doc_hash)

    def _process_rendered_page_with_vision(
        self,
        image_bytes: bytes,
        page_num: int,
        doc_hash: str,
    ) -> Optional[str]:
        """Extract content from a pre-rendered page image via Vision LLM.
        
        Args:
            image_bytes: PNG image bytes of the rendered page.
            page_num: 0-based page number.
            doc_hash: Document hash for naming.
            
        Returns:
            Extracted text content or None if failed.
        """
        from src.libs.llm.base_vision_llm import ImageInput
        
        # Optionally save the rendered page image for debugging/caching
        image_dir = self.image_storage_dir / doc_hash
        image_dir.mkdir(parents=True, exist_ok=True)
        page_image_path = image_dir / f"page_{page_num + 1}.png"
        page_image_path.write_bytes(image_bytes)
        
        # Send to Vision LLM
        image_input = ImageInput(data=image_bytes, mime_type="image/png")
        response = self.vision_llm.chat_with_image(
            text=self.page_prompt,
            image=image_input,
        )
        return response.content if response and response.content else None
    
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
    
    def _extract_and_process_images(
        self,
        pdf_path: Path,
        text_content: str,
        doc_hash: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Extract images from PDF and insert placeholders.
        
        Uses PyMuPDF to extract images, save them to disk, and insert
        placeholders in the text content.
        
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
        
        images_metadata = []
        modified_text = text_content
        
        try:
            # Create image storage directory
            image_dir = self.image_storage_dir / doc_hash
            image_dir.mkdir(parents=True, exist_ok=True)
            
            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)
            
            # Track text offset for placeholder insertion
            text_offset = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                
                for img_index, img_info in enumerate(image_list):
                    try:
                        # Extract image
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Generate image ID and filename
                        image_id = self._generate_image_id(doc_hash, page_num + 1, img_index + 1)
                        image_filename = f"{image_id}.{image_ext}"
                        image_path = image_dir / image_filename
                        
                        # Save image
                        with open(image_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        
                        # Get image dimensions
                        try:
                            img = Image.open(io.BytesIO(image_bytes))
                            width, height = img.size
                        except Exception:
                            width, height = 0, 0
                        
                        # Create placeholder
                        placeholder = f"[IMAGE: {image_id}]"
                        
                        # Insert placeholder at end of current page's content
                        # (simplified - in production, you'd parse page boundaries)
                        insert_position = len(modified_text)
                        modified_text += f"\n{placeholder}\n"
                        
                        # Convert path to be relative to project root or absolute
                        try:
                            relative_path = image_path.relative_to(Path.cwd())
                        except ValueError:
                            # If not in cwd, use absolute path
                            relative_path = image_path.absolute()
                        
                        # Record metadata
                        image_metadata = {
                            "id": image_id,
                            "path": str(relative_path),
                            "page": page_num + 1,
                            "text_offset": insert_position + 1,  # +1 for newline
                            "text_length": len(placeholder),
                            "position": {
                                "width": width,
                                "height": height,
                                "page": page_num + 1,
                                "index": img_index
                            }
                        }
                        images_metadata.append(image_metadata)
                        
                        logger.debug(f"Extracted image {image_id} from page {page_num + 1}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
            if images_metadata:
                logger.info(f"Extracted {len(images_metadata)} images from {pdf_path}")
            else:
                logger.debug(f"No images found in {pdf_path}")
            
            return modified_text, images_metadata
            
        except Exception as e:
            logger.warning(f"Image extraction failed for {pdf_path}: {e}")
            # Graceful degradation: return original text without images
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
