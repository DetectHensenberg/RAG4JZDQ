"""
Loader Module.

This package contains document loader components:
- Base loader class
- PDF loader (with Vision LLM support for scanned pages)
- PPTX loader (with Vision LLM support for slide understanding)
- Loader factory (auto-selects loader by file extension)
- File integrity checker
"""

from src.libs.loader.base_loader import BaseLoader
from src.libs.loader.pdf_loader import PdfLoader
from src.libs.loader.pptx_loader import PptxLoader
from src.libs.loader.loader_factory import LoaderFactory
from src.libs.loader.file_integrity import FileIntegrityChecker, SQLiteIntegrityChecker

__all__ = [
    "BaseLoader",
    "PdfLoader",
    "PptxLoader",
    "LoaderFactory",
    "FileIntegrityChecker",
    "SQLiteIntegrityChecker",
]
