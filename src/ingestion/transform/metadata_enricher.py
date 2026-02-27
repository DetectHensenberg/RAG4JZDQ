"""Metadata enrichment transform: rule-based + optional LLM enhancement."""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from src.core.settings import Settings, resolve_path
from src.core.types import Chunk
from src.core.trace.trace_context import TraceContext
from src.ingestion.transform.base_transform import BaseTransform
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.base_llm import BaseLLM, Message
from src.observability.logger import get_logger

logger = get_logger(__name__)

# Default max parallel workers for LLM calls
DEFAULT_MAX_WORKERS = 5


class MetadataEnricher(BaseTransform):
    """Enriches chunk metadata with title, summary, and tags.
    
    Processing Pipeline:
        1. Rule-based enrichment: Extract basic metadata from content
        2. (Optional) LLM enrichment: Generate semantic-rich metadata
        3. On LLM failure: Gracefully fallback to rule-based metadata
    
    Output Metadata:
        - title: Brief title/heading for the chunk
        - summary: Concise summary of the content
        - tags: List of relevant keywords/topics
        - enriched_by: "rule" or "llm"
    
    Configuration (via settings.yaml):
        - ingestion.metadata_enricher.use_llm: bool - Enable LLM enhancement
        - ingestion.metadata_enricher.prompt_path: str - Custom prompt file path
    
    Design Principles:
        - Graceful Degradation: LLM errors don't block ingestion
        - Atomic Processing: Each chunk processed independently
        - Observable: Records enriched_by in metadata
    """
    
    def __init__(
        self,
        settings: Settings,
        llm: Optional[BaseLLM] = None,
        prompt_path: Optional[str] = None
    ):
        """Initialize MetadataEnricher.
        
        Args:
            settings: Application settings
            llm: Optional LLM instance (for testing; auto-created if None)
            prompt_path: Optional custom prompt file path
        """
        self.settings = settings
        self._llm = llm
        self._prompt_template: Optional[str] = None
        self._prompt_path = prompt_path or str(resolve_path("config/prompts/metadata_enrichment.txt"))
        
        # Determine if LLM should be used
        enricher_config = {}
        if hasattr(settings, 'ingestion') and settings.ingestion is not None:
            ingestion_config = settings.ingestion
            # Check if ingestion has metadata_enricher attribute (dataclass) or dict
            if hasattr(ingestion_config, 'metadata_enricher') and ingestion_config.metadata_enricher:
                enricher_config = ingestion_config.metadata_enricher
            elif isinstance(ingestion_config, dict):
                enricher_config = ingestion_config.get('metadata_enricher', {})
        
        self.use_llm = enricher_config.get('use_llm', False) if enricher_config else False
        
    @property
    def llm(self) -> Optional[BaseLLM]:
        """Lazy-load LLM instance."""
        if self.use_llm and self._llm is None:
            try:
                self._llm = LLMFactory.create(self.settings)
                logger.info("LLM initialized for metadata enrichment")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM: {e}. Falling back to rule-based only.")
                self.use_llm = False
        return self._llm
    
    def transform(
        self,
        chunks: List[Chunk],
        trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        """Transform chunks by enriching their metadata.
        
        Args:
            chunks: List of chunks to enrich
            trace: Optional trace context
            
        Returns:
            List of enriched chunks (same length as input)
        """
        if not chunks:
            return []
        
        # Process chunks in parallel if LLM is enabled
        if self.use_llm and self.llm:
            return self._transform_parallel(chunks, trace)
        else:
            return self._transform_sequential(chunks, trace)
    
    def _enrich_single_chunk(
        self, 
        chunk: Chunk, 
        trace: Optional[TraceContext] = None
    ) -> Tuple[Chunk, str, Optional[str]]:
        """Enrich a single chunk. Thread-safe.
        
        Args:
            chunk: Chunk to enrich
            trace: Optional trace context
            
        Returns:
            Tuple of (enriched_chunk, enriched_by, error_message)
        """
        try:
            # Step 1: Rule-based enrichment
            rule_metadata = self._rule_based_enrich(chunk.text)
            
            # Step 2: LLM enhancement
            if self.use_llm and self.llm:
                llm_metadata = self._llm_enrich(chunk.text, trace)
                
                if llm_metadata:
                    enriched_metadata = llm_metadata
                    enriched_by = "llm"
                else:
                    enriched_metadata = rule_metadata
                    enriched_by = "rule"
                    enriched_metadata['enrich_fallback_reason'] = "llm_failed"
            else:
                enriched_metadata = rule_metadata
                enriched_by = "rule"
            
            final_metadata = {
                **(chunk.metadata or {}),
                **enriched_metadata,
                'enriched_by': enriched_by
            }
            
            enriched_chunk = Chunk(
                id=chunk.id,
                text=chunk.text,
                metadata=final_metadata,
                source_ref=chunk.source_ref
            )
            return (enriched_chunk, enriched_by, None)
            
        except Exception as e:
            logger.error(f"Failed to enrich chunk {chunk.id}: {e}")
            text_preview = ""
            if chunk.text:
                text_preview = chunk.text[:100] + '...' if len(chunk.text) > 100 else chunk.text
            minimal_metadata = {
                **(chunk.metadata or {}),
                'title': 'Untitled',
                'summary': text_preview,
                'tags': [],
                'enriched_by': 'error',
                'enrich_error': str(e)
            }
            enriched_chunk = Chunk(
                id=chunk.id,
                text=chunk.text or "",
                metadata=minimal_metadata,
                source_ref=chunk.source_ref
            )
            return (enriched_chunk, "error", str(e))
    
    def _transform_parallel(
        self, 
        chunks: List[Chunk], 
        trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        """Process chunks in parallel using ThreadPoolExecutor."""
        max_workers = min(DEFAULT_MAX_WORKERS, len(chunks))
        enriched_chunks = [None] * len(chunks)
        llm_enhanced_count = 0
        fallback_count = 0
        
        logger.debug(f"Processing {len(chunks)} chunks in parallel (max_workers={max_workers})")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self._enrich_single_chunk, chunk, trace): idx
                for idx, chunk in enumerate(chunks)
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    enriched_chunk, enriched_by, error = future.result()
                    enriched_chunks[idx] = enriched_chunk
                    
                    if enriched_by == "llm":
                        llm_enhanced_count += 1
                    elif enriched_by == "rule" and error is None:
                        fallback_count += 1
                except Exception as e:
                    logger.error(f"Unexpected error in parallel enrichment: {e}")
                    enriched_chunks[idx] = chunks[idx]
        
        success_count = sum(1 for c in enriched_chunks if c is not None)
        
        if trace:
            trace.record_stage("metadata_enricher", {
                "total_chunks": len(chunks),
                "success_count": success_count,
                "llm_enhanced_count": llm_enhanced_count,
                "fallback_count": fallback_count,
                "use_llm": self.use_llm,
                "parallel": True,
                "max_workers": max_workers
            })
        
        logger.info(
            f"Enriched {success_count}/{len(chunks)} chunks "
            f"(LLM: {llm_enhanced_count}, Fallback: {fallback_count})"
        )
        
        return enriched_chunks
    
    def _transform_sequential(
        self, 
        chunks: List[Chunk], 
        trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        """Process chunks sequentially (fallback when LLM disabled)."""
        enriched_chunks = []
        success_count = 0
        llm_enhanced_count = 0
        fallback_count = 0
        
        for chunk in chunks:
            try:
                # Step 1: Rule-based enrichment (always performed)
                rule_metadata = self._rule_based_enrich(chunk.text)
                
                # Step 2: Optional LLM enhancement
                if self.use_llm and self.llm:
                    llm_metadata = self._llm_enrich(chunk.text, trace)
                    
                    if llm_metadata:
                        # LLM success
                        enriched_metadata = llm_metadata
                        enriched_by = "llm"
                        llm_enhanced_count += 1
                    else:
                        # LLM failed, fallback to rule-based
                        enriched_metadata = rule_metadata
                        enriched_by = "rule"
                        fallback_count += 1
                        enriched_metadata['enrich_fallback_reason'] = "llm_failed"
                else:
                    # LLM disabled, use rule-based
                    enriched_metadata = rule_metadata
                    enriched_by = "rule"
                
                # Merge enriched metadata with existing metadata
                final_metadata = {
                    **(chunk.metadata or {}),
                    **enriched_metadata,
                    'enriched_by': enriched_by
                }
                
                # Create enriched chunk
                enriched_chunk = Chunk(
                    id=chunk.id,
                    text=chunk.text,
                    metadata=final_metadata,
                    source_ref=chunk.source_ref
                )
                enriched_chunks.append(enriched_chunk)
                success_count += 1
                
            except Exception as e:
                # Atomic failure: log and preserve original with minimal metadata
                logger.error(f"Failed to enrich chunk {chunk.id}: {e}")
                # Handle None text case
                text_preview = ""
                if chunk.text:
                    text_preview = chunk.text[:100] + '...' if len(chunk.text) > 100 else chunk.text
                minimal_metadata = {
                    **(chunk.metadata or {}),
                    'title': 'Untitled',
                    'summary': text_preview,
                    'tags': [],
                    'enriched_by': 'error',
                    'enrich_error': str(e)
                }
                enriched_chunk = Chunk(
                    id=chunk.id,
                    text=chunk.text or "",  # Ensure text is not None
                    metadata=minimal_metadata,
                    source_ref=chunk.source_ref
                )
                enriched_chunks.append(enriched_chunk)
        
        # Record trace
        if trace:
            trace.record_stage("metadata_enricher", {
                "total_chunks": len(chunks),
                "success_count": success_count,
                "llm_enhanced_count": llm_enhanced_count,
                "fallback_count": fallback_count,
                "use_llm": self.use_llm,
                "parallel": False
            })
        
        logger.info(
            f"Enriched {success_count}/{len(chunks)} chunks "
            f"(LLM: {llm_enhanced_count}, Fallback: {fallback_count})"
        )
        
        return enriched_chunks
    
    def _rule_based_enrich(self, text: str) -> Dict[str, Any]:
        """Extract metadata using rule-based heuristics.
        
        Args:
            text: Chunk text content
            
        Returns:
            Dictionary with title, summary, tags
            
        Raises:
            TypeError: If text is None
        """
        if text is None:
            raise TypeError("Chunk text cannot be None")
        
        # Extract title from first heading or first line
        title = self._extract_title(text)
        
        # Generate summary from first sentences
        summary = self._extract_summary(text)
        
        # Extract tags from common patterns
        tags = self._extract_tags(text)
        
        return {
            'title': title,
            'summary': summary,
            'tags': tags
        }
    
    def _extract_title(self, text: str) -> str:
        """Extract title from text using heuristics.
        
        Priority:
            1. Markdown heading (# Title)
            2. First line if short enough
            3. First sentence
            4. First N characters
        """
        if not text:
            return "Untitled"
        
        # Check for markdown heading
        heading_match = re.match(r'^#{1,6}\s+(.+)$', text, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()
        
        # Use first line if it's short and looks like a title
        first_line = text.split('\n')[0].strip()
        if first_line and len(first_line) <= 100 and not first_line.endswith(('.', ',', ';')):
            return first_line
        
        # Use first sentence (without trailing punctuation)
        sentences = re.split(r'[.!?]\s+', text)
        if sentences and sentences[0]:
            title = sentences[0].strip()
            # Remove trailing punctuation if present
            title = re.sub(r'[.!?]+$', '', title)
            if len(title) <= 150:
                return title
            return title[:147] + "..."
        
        # Fallback: first 100 chars
        return text[:100].strip() + ("..." if len(text) > 100 else "")
    
    def _extract_summary(self, text: str, max_sentences: int = 3) -> str:
        """Extract summary from text using first N sentences.
        
        Args:
            text: Source text
            max_sentences: Maximum number of sentences to include
            
        Returns:
            Summary text
        """
        if not text:
            return ""
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Take first N sentences
        summary_sentences = sentences[:max_sentences]
        summary = ' '.join(summary_sentences).strip()
        
        # Limit length
        if len(summary) > 500:
            summary = summary[:497] + "..."
        
        return summary
    
    def _extract_tags(self, text: str, max_tags: int = 10) -> List[str]:
        """Extract tags using keyword extraction heuristics.
        
        Args:
            text: Source text
            max_tags: Maximum number of tags to extract
            
        Returns:
            List of tag strings
        """
        if not text:
            return []
        
        tags = set()
        
        # Extract capitalized words (potential proper nouns)
        capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        tags.update(capitalized[:5])
        
        # Extract code identifiers (camelCase, snake_case)
        identifiers = re.findall(r'\b[a-z]+(?:[A-Z][a-z]*)+\b|\b[a-z]+_[a-z_]+\b', text)
        tags.update(identifiers[:5])
        
        # Extract markdown bold/italic terms (potential keywords)
        markdown_keywords = re.findall(r'\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_', text)
        for match in markdown_keywords[:5]:
            for group in match:
                if group:
                    tags.add(group.strip())
        
        # Convert to list and limit
        tag_list = sorted(list(tags))[:max_tags]
        
        return tag_list
    
    def _llm_enrich(
        self,
        text: str,
        trace: Optional[TraceContext] = None
    ) -> Optional[Dict[str, Any]]:
        """Enrich metadata using LLM.
        
        Args:
            text: Chunk text content
            trace: Optional trace context
            
        Returns:
            Dictionary with title, summary, tags, or None on failure
        """
        if not self.llm:
            return None
        
        try:
            # Load prompt template
            prompt = self._load_prompt()
            
            # Build prompt with text
            formatted_prompt = prompt.replace("{chunk_text}", text[:2000])  # Limit text length
            
            # Call LLM
            messages = [Message(role="user", content=formatted_prompt)]
            response = self.llm.chat(messages)
            
            if not response:
                logger.warning("LLM returned empty response for metadata enrichment")
                return None
            
            # Extract text from response (handle both string and ChatResponse object)
            response_text = response
            if hasattr(response, 'content'):
                response_text = response.content
            elif hasattr(response, 'text'):
                response_text = response.text
            elif not isinstance(response, str):
                response_text = str(response)
            
            # Parse LLM response
            metadata = self._parse_llm_response(response_text)
            
            if trace:
                trace.record_stage("llm_enrich", {
                    "success": True,
                    "response_length": len(response_text)
                })
            
            return metadata
            
        except Exception as e:
            logger.warning(f"LLM enrichment failed: {e}")
            if trace:
                trace.record_stage("llm_enrich", {
                    "success": False,
                    "error": str(e)
                })
            return None
    
    def _load_prompt(self) -> str:
        """Load prompt template from file.
        
        Returns:
            Prompt template string
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if self._prompt_template is not None:
            return self._prompt_template
        
        prompt_path = Path(self._prompt_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {self._prompt_path}")
        
        self._prompt_template = prompt_path.read_text(encoding='utf-8')
        logger.info(f"Loaded metadata enrichment prompt from {self._prompt_path}")
        
        return self._prompt_template
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured metadata.
        
        Expected format:
            Title: <title>
            Summary: <summary>
            Tags: <tag1>, <tag2>, <tag3>
        
        Args:
            response: LLM response text
            
        Returns:
            Dictionary with title, summary, tags
        """
        metadata = {
            'title': '',
            'summary': '',
            'tags': []
        }
        
        # Extract title
        title_match = re.search(r'Title:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if title_match:
            metadata['title'] = title_match.group(1).strip()
        
        # Extract summary
        summary_match = re.search(r'Summary:\s*(.+?)(?:\n(?:Tags:|$))', response, re.IGNORECASE | re.DOTALL)
        if summary_match:
            metadata['summary'] = summary_match.group(1).strip()
        
        # Extract tags
        tags_match = re.search(r'Tags:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if tags_match:
            tags_text = tags_match.group(1).strip()
            # Split by comma and clean
            tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
            metadata['tags'] = tags
        
        # Validation: ensure non-empty values
        if not metadata['title']:
            metadata['title'] = 'Untitled'
        if not metadata['summary']:
            metadata['summary'] = response[:500]  # Fallback to raw response
        
        return metadata
