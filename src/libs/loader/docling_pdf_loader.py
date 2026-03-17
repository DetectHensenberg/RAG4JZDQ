"""Docling-based PDF loader using IBM's deep learning layout analysis.

This loader uses docling (https://github.com/DS4SD/docling) for advanced
PDF parsing with deep learning-based layout understanding. It provides
superior handling of complex layouts, tables, and figures compared to
rule-based approaches.

Requirements:
    pip install docling>=2.0.0

Note: docling requires significant computational resources and may benefit
from GPU acceleration. For simpler documents, consider using LayoutPdfLoader.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.libs.loader.base_loader import BaseLoader

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DoclingPdfLoader(BaseLoader):
    """PDF loader using IBM docling for deep learning layout analysis.
    
    Features:
    - Deep learning-based layout understanding
    - Superior table extraction
    - Better handling of complex multi-column layouts
    - Figure and caption detection
    
    Example:
        >>> loader = DoclingPdfLoader()
        >>> result = loader.load("complex_report.pdf")
        >>> print(result["text"][:100])
    """
    
    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        vision_llm: Optional[Any] = None,
    ):
        """Initialize DoclingPdfLoader.
        
        Args:
            extract_images: Whether to extract images from PDF.
            image_storage_dir: Directory to store extracted images.
            vision_llm: Optional Vision LLM for image captioning.
        """
        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self.vision_llm = vision_llm
        self._converter = None
    
    def _get_converter(self):
        """Lazy-load docling converter."""
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
                self._converter = DocumentConverter()
                logger.info("Docling DocumentConverter initialized")
            except ImportError as e:
                raise ImportError(
                    "docling is not installed. Install with: pip install docling>=2.0.0"
                ) from e
        return self._converter
    
    def load(self, file_path: str | Path) -> Dict[str, Any]:
        """Load and parse a PDF file using docling.
        
        Args:
            file_path: Path to the PDF file.
            
        Returns:
            Dictionary containing:
            - text: Extracted markdown text
            - metadata: Document metadata
            - images: List of extracted image info (if extract_images=True)
        """
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Loading PDF with docling: {file_path}")
        
        converter = self._get_converter()
        
        # Convert PDF to docling document
        result = converter.convert(str(file_path))
        
        # Export to markdown
        markdown_text = result.document.export_to_markdown()
        
        # Extract metadata
        metadata = {
            "source_path": str(file_path),
            "file_name": file_path.stem,
            "file_ext": file_path.suffix.lstrip("."),
            "parser": "docling",
            "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
        }
        
        # Extract images if requested
        images = []
        if self.extract_images:
            images = self._extract_images(result, file_path)
        
        logger.info(
            f"Docling parsed {file_path.name}: "
            f"{len(markdown_text)} chars, {len(images)} images"
        )
        
        return {
            "text": markdown_text,
            "metadata": metadata,
            "images": images,
        }
    
    def _extract_images(
        self, 
        result: Any, 
        source_path: Path
    ) -> List[Dict[str, Any]]:
        """Extract images from docling result.
        
        Args:
            result: Docling conversion result.
            source_path: Original PDF path.
            
        Returns:
            List of image metadata dictionaries.
        """
        images = []
        
        try:
            # Ensure image storage directory exists
            doc_image_dir = self.image_storage_dir / source_path.stem
            doc_image_dir.mkdir(parents=True, exist_ok=True)
            
            # Docling stores images in result.document.pictures
            if hasattr(result.document, 'pictures'):
                for idx, picture in enumerate(result.document.pictures):
                    if hasattr(picture, 'image') and picture.image is not None:
                        # Save image
                        image_path = doc_image_dir / f"img_{idx:03d}.png"
                        picture.image.save(str(image_path))
                        
                        images.append({
                            "id": f"{source_path.stem}_img_{idx:03d}",
                            "path": str(image_path),
                            "page": getattr(picture, 'page_no', None),
                            "caption": getattr(picture, 'caption', None),
                        })
                        
            logger.debug(f"Extracted {len(images)} images from {source_path.name}")
            
        except Exception as e:
            logger.warning(f"Failed to extract images from {source_path}: {e}")
        
        return images
