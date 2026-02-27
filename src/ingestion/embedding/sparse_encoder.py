"""Sparse Encoder for generating BM25 term statistics from text chunks.

This module implements the Sparse Encoder component of the Ingestion Pipeline,
responsible for extracting term statistics needed for BM25 indexing.

Design Principles:
- Stateless Processing: No internal state between encode() calls
- Observable: Accepts TraceContext for future observability integration
- Deterministic: Same inputs produce same term statistics
- Clear Contracts: Well-defined output structure for downstream BM25Indexer
"""

from typing import List, Dict, Optional, Any
from collections import Counter
import re

import jieba

from src.core.types import Chunk


class SparseEncoder:
    """Encodes text chunks into BM25 term statistics.
    
    This encoder prepares term-level statistics needed for BM25 indexing.
    The actual index construction is handled by BM25Indexer (C12).
    
    Output Structure:
        For each chunk, produces:
        {
            "chunk_id": str,
            "term_frequencies": Dict[str, int],  # term -> count in this chunk
            "doc_length": int,                    # number of terms in chunk
            "unique_terms": int                   # vocabulary size in chunk
        }
    
    Design:
    - Tokenization: Simple whitespace + lowercasing (can be enhanced later)
    - Stop Words: None by default (can add in future iterations)
    - Deterministic: Same chunk text always produces same statistics
    
    Example:
        >>> from src.core.types import Chunk
        >>> encoder = SparseEncoder()
        >>> 
        >>> chunks = [Chunk(id="1", text="Hello world hello", metadata={})]
        >>> stats = encoder.encode(chunks)
        >>> stats[0]["term_frequencies"]["hello"]  # 2
        >>> stats[0]["doc_length"]  # 3
    """
    
    def __init__(
        self,
        min_term_length: int = 2,
        lowercase: bool = True,
    ):
        """Initialize SparseEncoder.
        
        Args:
            min_term_length: Minimum character length for a term (default: 2)
            lowercase: Whether to convert terms to lowercase (default: True)
        
        Raises:
            ValueError: If min_term_length < 1
        """
        if min_term_length < 1:
            raise ValueError(f"min_term_length must be >= 1, got {min_term_length}")
        
        self.min_term_length = min_term_length
        self.lowercase = lowercase
    
    def encode(
        self,
        chunks: List[Chunk],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Encode chunks into BM25 term statistics.
        
        For each chunk, extracts:
        - Term frequencies (term -> count)
        - Document length (total terms)
        - Unique terms count
        
        Args:
            chunks: List of Chunk objects to encode
            trace: Optional TraceContext for observability (reserved for Stage F)
        
        Returns:
            List of statistics dictionaries (one per chunk, in same order).
            Each dict contains: chunk_id, term_frequencies, doc_length, unique_terms
        
        Raises:
            ValueError: If chunks list is empty
            ValueError: If any chunk has empty text
        
        Example:
            >>> chunks = [
            ...     Chunk(id="1", text="machine learning", metadata={}),
            ...     Chunk(id="2", text="deep learning networks", metadata={})
            ... ]
            >>> stats = encoder.encode(chunks)
            >>> len(stats) == len(chunks)  # True
            >>> stats[0]["term_frequencies"]["machine"]  # 1
            >>> stats[1]["doc_length"]  # 3
        """
        if not chunks:
            raise ValueError("Cannot encode empty chunks list")
        
        results = []
        
        for i, chunk in enumerate(chunks):
            # Validate chunk text
            if not chunk.text or not chunk.text.strip():
                raise ValueError(
                    f"Chunk at index {i} (id={chunk.id}) has empty or whitespace-only text"
                )
            
            # Tokenize and count terms
            terms = self._tokenize(chunk.text)
            term_frequencies = Counter(terms)
            
            # Build statistics dict
            stat_dict = {
                "chunk_id": chunk.id,
                "term_frequencies": dict(term_frequencies),  # Convert Counter to dict
                "doc_length": len(terms),
                "unique_terms": len(term_frequencies),
            }
            
            results.append(stat_dict)
        
        return results
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms.
        
        Uses jieba for Chinese text segmentation and regex for English.
        This ensures consistent tokenization with the query-side
        (QueryProcessor), which is required for BM25 matching.
        
        Args:
            text: Input text to tokenize
        
        Returns:
            List of valid terms
        """
        tokens: List[str] = []

        # Use jieba to segment the text (handles both Chinese and English)
        raw_tokens = jieba.lcut(text)

        # Clean tokens: keep only alphanumeric and Chinese characters
        for token in raw_tokens:
            token = token.strip()
            if not token:
                continue
            # Skip pure punctuation / whitespace
            if re.fullmatch(r'[\s\W]+', token, re.UNICODE):
                continue
            tokens.append(token)
        
        # Apply lowercase if configured
        if self.lowercase:
            tokens = [t.lower() for t in tokens]
        
        # Filter by minimum length
        terms = [t for t in tokens if len(t) >= self.min_term_length]
        
        return terms
    
    def get_corpus_stats(
        self,
        encoded_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate corpus-level statistics from encoded chunks.
        
        Utility method for BM25Indexer to compute:
        - Average document length
        - Document frequency (how many docs contain each term)
        - Total number of documents
        
        Args:
            encoded_chunks: List of statistics dicts from encode()
        
        Returns:
            Dictionary with corpus-level statistics:
            {
                "num_docs": int,
                "avg_doc_length": float,
                "document_frequency": Dict[str, int]  # term -> # docs containing it
            }
        """
        if not encoded_chunks:
            return {
                "num_docs": 0,
                "avg_doc_length": 0.0,
                "document_frequency": {}
            }
        
        num_docs = len(encoded_chunks)
        total_length = sum(chunk["doc_length"] for chunk in encoded_chunks)
        avg_doc_length = total_length / num_docs if num_docs > 0 else 0.0
        
        # Calculate document frequency (DF) for each term
        doc_freq: Dict[str, int] = {}
        for chunk_stats in encoded_chunks:
            # Each unique term in this chunk contributes 1 to DF
            for term in chunk_stats["term_frequencies"].keys():
                doc_freq[term] = doc_freq.get(term, 0) + 1
        
        return {
            "num_docs": num_docs,
            "avg_doc_length": avg_doc_length,
            "document_frequency": doc_freq,
        }
