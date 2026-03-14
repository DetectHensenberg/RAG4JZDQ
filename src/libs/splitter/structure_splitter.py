"""Structure-aware three-layer text splitter.

Implements a three-layer chunking strategy:
  Layer 1 — Structure-aware rule splitting:
      Split at Markdown headings, preserve code blocks and tables as atomic units.
  Layer 2 — Semantic coherence merging:
      Merge short / incomplete chunks with neighbours.
  Layer 3 — Length balancing:
      Re-split oversized chunks; merge undersized remnants.

Design Principles:
- Pluggable: Implements BaseSplitter interface.
- Config-Driven: Reads chunk_size and chunk_overlap from settings.
- Observable: Accepts optional TraceContext.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from src.libs.splitter.base_splitter import BaseSplitter

# Regex patterns for structure detection
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)

# Characters that suggest a chunk ends mid-sentence
_INCOMPLETE_ENDINGS = (":", "：", ",", "，", ";", "；", "、")


class StructureSplitter(BaseSplitter):
    """Three-layer structure-aware text splitter.

    Attributes:
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap characters appended to the start of next chunk.
        min_chunk_ratio: Chunks shorter than chunk_size * ratio are merged.
        max_chunk_ratio: Chunks longer than chunk_size * ratio are re-split.
    """

    def __init__(
        self,
        settings: Any,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        min_chunk_ratio: float = 0.3,
        max_chunk_ratio: float = 1.5,
        **kwargs: Any,
    ) -> None:
        self.settings = settings

        try:
            ingestion_config = settings.ingestion
            self.chunk_size = chunk_size if chunk_size is not None else ingestion_config.chunk_size
            self.chunk_overlap = chunk_overlap if chunk_overlap is not None else ingestion_config.chunk_overlap
        except AttributeError as e:
            raise ValueError(
                "Missing ingestion configuration in settings. "
                "Expected settings.ingestion.chunk_size and settings.ingestion.chunk_overlap"
            ) from e

        if not isinstance(self.chunk_size, int) or self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be a positive integer, got: {self.chunk_size}")
        if not isinstance(self.chunk_overlap, int) or self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be a non-negative integer, got: {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than chunk_size ({self.chunk_size})"
            )

        self.min_chunk_len = int(self.chunk_size * min_chunk_ratio)
        self.max_chunk_len = int(self.chunk_size * max_chunk_ratio)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split_text(
        self,
        text: str,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Split text using three-layer strategy.

        Args:
            text: Input Markdown text.
            trace: Optional TraceContext.

        Returns:
            List of chunk strings in document order.
        """
        self.validate_text(text)

        # Layer 1: structure-aware splitting
        raw_chunks = self._split_by_structure(text)

        # Layer 2: merge short / incoherent chunks
        merged_chunks = self._merge_incoherent(raw_chunks)

        # Layer 3: length balancing + overlap
        balanced_chunks = self._balance_lengths(merged_chunks)

        # Apply overlap
        final_chunks = self._apply_overlap(balanced_chunks)

        # Safety: filter empty
        final_chunks = [c for c in final_chunks if c.strip()]
        if not final_chunks:
            final_chunks = [text]

        self.validate_chunks(final_chunks)
        return final_chunks

    # ------------------------------------------------------------------
    # Layer 1: Structure-aware splitting
    # ------------------------------------------------------------------

    def _split_by_structure(self, text: str) -> List[str]:
        """Split text at structural boundaries.

        Rules:
        - Split at Markdown headings (# / ## / ###).
        - Keep code fenced blocks (``` ... ```) intact.
        - Keep table blocks (consecutive | rows) intact.
        - Split at double newlines as paragraph boundary otherwise.
        """
        segments: List[str] = []
        current: List[str] = []

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # ── Code fence: consume until closing fence ──
            if line.strip().startswith("```"):
                # Flush current paragraph before code block
                if current:
                    segments.append("\n".join(current))
                    current = []
                code_lines = [line]
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    code_lines.append(lines[i])  # closing ```
                    i += 1
                segments.append("\n".join(code_lines))
                continue

            # ── Table block: consume consecutive | rows ──
            if _TABLE_ROW_RE.match(line):
                if current:
                    segments.append("\n".join(current))
                    current = []
                table_lines = [line]
                i += 1
                while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                    table_lines.append(lines[i])
                    i += 1
                segments.append("\n".join(table_lines))
                continue

            # ── Heading: start new segment ──
            if _HEADING_RE.match(line):
                if current:
                    segments.append("\n".join(current))
                    current = []
                current.append(line)
                i += 1
                continue

            # ── Blank line: paragraph boundary ──
            if not line.strip():
                if current:
                    segments.append("\n".join(current))
                    current = []
                i += 1
                continue

            # ── Normal line ──
            current.append(line)
            i += 1

        if current:
            segments.append("\n".join(current))

        return [s for s in segments if s.strip()]

    # ------------------------------------------------------------------
    # Layer 2: Semantic coherence merging
    # ------------------------------------------------------------------

    def _merge_incoherent(self, chunks: List[str]) -> List[str]:
        """Merge chunks that are too short or end with incomplete markers."""
        if len(chunks) <= 1:
            return chunks

        merged: List[str] = []
        buffer = chunks[0]

        for i in range(1, len(chunks)):
            next_chunk = chunks[i]

            should_merge = False

            # Rule A: buffer is too short
            if len(buffer) < self.min_chunk_len:
                should_merge = True

            # Rule B: buffer ends with incomplete sentence markers
            stripped = buffer.rstrip()
            if stripped and stripped[-1] in _INCOMPLETE_ENDINGS:
                should_merge = True

            # Rule C: next chunk starts with lowercase (mid-sentence continuation)
            next_stripped = next_chunk.lstrip()
            if next_stripped and next_stripped[0].islower():
                should_merge = True

            if should_merge and (len(buffer) + len(next_chunk) + 1) <= self.max_chunk_len:
                buffer = buffer + "\n\n" + next_chunk
            else:
                merged.append(buffer)
                buffer = next_chunk

        merged.append(buffer)
        return merged

    # ------------------------------------------------------------------
    # Layer 3: Length balancing
    # ------------------------------------------------------------------

    def _balance_lengths(self, chunks: List[str]) -> List[str]:
        """Re-split oversized chunks and merge undersized remnants."""
        balanced: List[str] = []

        for chunk in chunks:
            if len(chunk) <= self.max_chunk_len:
                balanced.append(chunk)
            else:
                # Re-split oversized chunk by paragraphs, then by sentences
                sub_chunks = self._resplit_oversized(chunk)
                balanced.extend(sub_chunks)

        # Second pass: merge any remaining undersized chunks
        if len(balanced) <= 1:
            return balanced

        final: List[str] = []
        buf = balanced[0]
        for i in range(1, len(balanced)):
            if len(buf) < self.min_chunk_len and (len(buf) + len(balanced[i]) + 1) <= self.max_chunk_len:
                buf = buf + "\n\n" + balanced[i]
            else:
                final.append(buf)
                buf = balanced[i]
        final.append(buf)
        return final

    def _resplit_oversized(self, text: str) -> List[str]:
        """Split an oversized chunk into smaller pieces.

        Strategy: split by double-newline first, then by sentence boundaries.
        """
        paragraphs = re.split(r"\n\n+", text)
        result: List[str] = []
        current = ""

        for para in paragraphs:
            if not para.strip():
                continue
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = (current + "\n\n" + para) if current else para
            else:
                if current:
                    result.append(current)
                # If single paragraph is still too big, split by sentences
                if len(para) > self.chunk_size:
                    sentences = re.split(r"(?<=[.!?。！？])\s+", para)
                    sent_buf = ""
                    for sent in sentences:
                        if len(sent_buf) + len(sent) + 1 <= self.chunk_size:
                            sent_buf = (sent_buf + " " + sent) if sent_buf else sent
                        else:
                            if sent_buf:
                                result.append(sent_buf)
                            # Last resort: hard split
                            if len(sent) > self.chunk_size:
                                for j in range(0, len(sent), self.chunk_size):
                                    result.append(sent[j:j + self.chunk_size])
                            else:
                                sent_buf = sent
                                continue
                            sent_buf = ""
                    if sent_buf:
                        result.append(sent_buf)
                    current = ""
                else:
                    current = para

        if current:
            result.append(current)

        return result if result else [text]

    # ------------------------------------------------------------------
    # Overlap
    # ------------------------------------------------------------------

    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        """Prepend overlap from previous chunk to current chunk."""
        if self.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            overlap_text = prev[-self.chunk_overlap:]
            # Try to start overlap at a word boundary
            space_idx = overlap_text.find(" ")
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]
            result.append(overlap_text + "\n" + chunks[i])

        return result
