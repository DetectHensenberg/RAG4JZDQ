"""Abstract base class for document loaders.

This module defines the pluggable interface for document loaders,
enabling seamless loading of different document formats (PDF, Markdown, etc.)
with unified output structure.

Design Principles:
- Single Responsibility: Loaders only handle format unification + structure extraction
- Type Safety: Return standardized Document type from core.types
- No Splitting: Loaders don't chunk documents, only parse and normalize
- Graceful Degradation: Failures in optional features (e.g., image extraction) shouldn't block text parsing
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.core.types import Document


class BaseLoader(ABC):
    """Abstract base class for document loaders.
    
    All loaders must implement the load() method to parse a file
    and return a standardized Document object with:
    - text: Normalized content (preferably Markdown format)
    - metadata: At minimum must contain 'source_path'
    
    Loaders should handle:
    - Format-specific parsing logic
    - Metadata extraction (title, page count, etc.)
    - Structure normalization (to Markdown when possible)
    - Optional: Image extraction and placeholder insertion
    """
    
    @abstractmethod
    def load(self, file_path: str | Path) -> Document:
        """Load and parse a document file.
        
        Args:
            file_path: Path to the document file to load.
            
        Returns:
            Document object with parsed content and metadata.
            metadata MUST contain at least 'source_path'.
            
        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is invalid or unsupported.
            RuntimeError: If parsing fails critically.
            
        Example:
            >>> loader = PdfLoader()
            >>> doc = loader.load("data/documents/report.pdf")
            >>> assert "source_path" in doc.metadata
            >>> assert doc.text  # Non-empty text
        """
        pass
    
    @staticmethod
    def _validate_file(file_path: str | Path) -> Path:
        """Validate that file exists and is readable.
        
        Args:
            file_path: Path to validate.
            
        Returns:
            Resolved Path object.
            
        Raises:
            FileNotFoundError: If file doesn't exist.
            PermissionError: If file is not readable.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")
        return path
