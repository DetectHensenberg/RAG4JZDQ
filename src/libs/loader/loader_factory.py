"""Factory for creating document loader instances.

This module implements the Factory Pattern to select the appropriate
document loader based on file extension, enabling seamless handling
of different document formats (PDF, PPTX, DOCX, etc.) through a
unified interface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from src.libs.loader.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class LoaderFactory:
    """Factory for creating document loaders based on file extension.

    Supports:
    - .pdf  → LayoutPdfLoader (layout) or PdfLoader (markitdown)
    - .pptx → PptxLoader (python-pptx + Vision LLM for slide understanding)
    - .ppt  → PptxLoader
    - .docx → PdfLoader  (MarkItDown handles DOCX natively)
    - .txt  → PdfLoader  (MarkItDown handles TXT natively)
    - .md   → PdfLoader  (MarkItDown handles Markdown natively)
    """

    @staticmethod
    def create(
        file_path: str | Path,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        vision_llm: Optional[Any] = None,
        pdf_parser: str = "markitdown",
    ) -> BaseLoader:
        """Create the appropriate loader for a given file.

        Args:
            file_path: Path to the file to load (used to determine extension).
            extract_images: Whether to extract images.
            image_storage_dir: Base directory for storing extracted images.
            vision_llm: Optional Vision LLM instance for enhanced extraction.
            pdf_parser: PDF parsing backend: "markitdown", "layout", or "docling".

        Returns:
            A BaseLoader instance appropriate for the file type.

        Raises:
            ValueError: If the file type is not supported.
        """
        # Validate file path: must exist and not contain traversal sequences
        resolved = Path(file_path).resolve()
        if ".." in str(file_path):
            raise ValueError(f"Path traversal detected in file path: {file_path}")
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        suffix = resolved.suffix.lower()

        if suffix == ".pdf" and pdf_parser == "docling":
            from src.libs.loader.docling_pdf_loader import DoclingPdfLoader

            logger.info("Using DoclingPdfLoader for PDF (deep learning layout analysis)")
            return DoclingPdfLoader(
                extract_images=extract_images,
                image_storage_dir=image_storage_dir,
                vision_llm=vision_llm,
            )

        if suffix == ".pdf" and pdf_parser == "layout":
            from src.libs.loader.layout_pdf_loader import LayoutPdfLoader

            logger.info("Using LayoutPdfLoader for PDF (layout analysis + OCR)")
            return LayoutPdfLoader(
                extract_images=extract_images,
                image_storage_dir=image_storage_dir,
                vision_llm=vision_llm,
            )

        if suffix in (".pdf", ".docx", ".txt", ".md"):
            from src.libs.loader.pdf_loader import PdfLoader

            return PdfLoader(
                extract_images=extract_images,
                image_storage_dir=image_storage_dir,
                vision_llm=vision_llm,
            )

        if suffix in (".pptx", ".ppt"):
            from src.libs.loader.pptx_loader import PptxLoader

            return PptxLoader(
                extract_images=extract_images,
                image_storage_dir=image_storage_dir,
                vision_llm=vision_llm,
            )

        supported = sorted({".pdf", ".pptx", ".ppt", ".docx", ".txt", ".md"})
        raise ValueError(
            f"Unsupported file type '{suffix}' for: {file_path}. "
            f"Supported: {', '.join(supported)}"
        )

    @staticmethod
    def supported_extensions() -> list[str]:
        """Return sorted list of all supported file extensions."""
        return sorted([".pdf", ".pptx", ".ppt", ".docx", ".txt", ".md"])
