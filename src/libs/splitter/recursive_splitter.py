"""Recursive Splitter implementation using LangChain.

This module provides a recursive character-based text splitting strategy
that respects document structure (headers, code blocks) and splits text
hierarchically to maintain semantic coherence.
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    RecursiveCharacterTextSplitter = None  # type: ignore[misc, assignment]

from src.libs.splitter.base_splitter import BaseSplitter


class RecursiveSplitter(BaseSplitter):
    """Recursive character-based text splitter.
    
    This splitter uses LangChain's RecursiveCharacterTextSplitter to split text
    by trying different separators in order (paragraphs, sentences, words) while
    respecting Markdown structure elements like headers and code blocks.
    
    Design Principles Applied:
    - Pluggable: Implements BaseSplitter interface for factory instantiation.
    - Config-Driven: Reads chunk_size and chunk_overlap from settings.
    - Fail-Fast: Raises ImportError if langchain-text-splitters is not installed.
    - Graceful Degradation: Validates inputs and provides clear error messages.
    
    Attributes:
        chunk_size: Maximum size of each chunk in characters.
        chunk_overlap: Number of overlapping characters between chunks.
        separators: List of separators to try in order (defaults to Markdown-aware).
        
    Raises:
        ImportError: If langchain-text-splitters package is not installed.
    """
    
    DEFAULT_SEPARATORS = [
        "\n\n",  # Double newline (paragraphs)
        "\n",    # Single newline
        ". ",    # Sentence endings
        "! ",
        "? ",
        "; ",
        ", ",
        " ",     # Spaces
        "",      # Characters
    ]
    
    def __init__(
        self,
        settings: Any,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        separators: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize RecursiveSplitter.
        
        Args:
            settings: Application settings containing ingestion configuration.
            chunk_size: Optional override for chunk size (defaults to settings.ingestion.chunk_size).
            chunk_overlap: Optional override for overlap (defaults to settings.ingestion.chunk_overlap).
            separators: Optional list of separator strings (defaults to Markdown-aware separators).
            **kwargs: Additional parameters passed to LangChain splitter.
        
        Raises:
            ImportError: If langchain-text-splitters is not installed.
            ValueError: If chunk_size or chunk_overlap are invalid.
        """
        if RecursiveCharacterTextSplitter is None:
            raise ImportError(
                "langchain-text-splitters is not installed. "
                "Install it with: pip install langchain-text-splitters"
            )
        
        self.settings = settings
        
        # Extract configuration from settings with overrides
        try:
            ingestion_config = settings.ingestion
            self.chunk_size = chunk_size if chunk_size is not None else ingestion_config.chunk_size
            self.chunk_overlap = chunk_overlap if chunk_overlap is not None else ingestion_config.chunk_overlap
        except AttributeError as e:
            raise ValueError(
                "Missing ingestion configuration in settings. "
                "Expected settings.ingestion.chunk_size and settings.ingestion.chunk_overlap"
            ) from e
        
        # Validate configuration
        if not isinstance(self.chunk_size, int) or self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be a positive integer, got: {self.chunk_size}")
        
        if not isinstance(self.chunk_overlap, int) or self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be a non-negative integer, got: {self.chunk_overlap}")
        
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )
        
        self.separators = separators if separators is not None else self.DEFAULT_SEPARATORS
        
        # Initialize LangChain splitter
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            length_function=len,
            is_separator_regex=False,
            **kwargs,
        )
    
    def split_text(
        self,
        text: str,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Split text into chunks recursively.
        
        This method splits text by trying different separators hierarchically,
        preserving document structure like Markdown headers and code blocks.
        
        Args:
            text: Input text to split. Must be a non-empty string.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Additional parameters (currently unused, reserved for future extensions).
        
        Returns:
            A list of text chunks. Each chunk respects the configured chunk_size
            and chunk_overlap. Order preserves the original text sequence.
        
        Raises:
            ValueError: If input text is invalid (empty, wrong type).
            RuntimeError: If splitting fails unexpectedly.
        
        Example:
            >>> splitter = RecursiveSplitter(settings)
            >>> chunks = splitter.split_text("# Header\\n\\nParagraph 1.\\n\\nParagraph 2.")
            >>> len(chunks)
            1  # If text fits in chunk_size
        """
        # Validate input
        self.validate_text(text)
        
        try:
            # Perform splitting
            chunks = self._splitter.split_text(text)
            
            # Handle edge case: LangChain may return empty list for very short text
            if not chunks:
                chunks = [text]
            
            # Validate output
            self.validate_chunks(chunks)
            
            return chunks
            
        except Exception as e:
            # Catch any LangChain errors and provide context
            raise RuntimeError(
                f"RecursiveSplitter failed to split text: {e}. "
                f"Text length: {len(text)}, chunk_size: {self.chunk_size}, "
                f"chunk_overlap: {self.chunk_overlap}"
            ) from e
