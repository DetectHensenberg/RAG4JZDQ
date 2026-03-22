"""GraphExtractor - LLM-driven entity and relationship extraction for GraphRAG."""

import hashlib
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.settings import Settings
from src.core.types import Chunk
from src.core.trace.trace_context import TraceContext
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.base_llm import BaseLLM, Message
from src.ingestion.storage.graph_store import GraphStore
from src.observability.logger import get_logger

logger = get_logger(__name__)

EXTRACTION_PROMPT = """
You are a knowledge graph extraction assistant.
Given the following text chunk, extract entities and their relationships.

Output format (STRICTLY FOLLOW):
ENTITIES:
- EntityName | EntityType | Brief description (max 20 words)
- ...

RELATIONSHIPS:
- EntityA | relation_type | EntityB
- ...

Entity types: Person, Organization, Product, Concept, Location, Event, Technology, Other
Relation types: is_a, part_of, related_to, created_by, used_for, depends_on, leads_to

Only extract entities clearly mentioned in the text. Output a maximum of 8 entities and 10 relationships.
If there is nothing meaningful to extract, output empty sections.

TEXT:
{text}
"""

_ENTITY_PATTERN = re.compile(r"^-?\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$")
_REL_PATTERN = re.compile(r"^-?\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$")


class GraphExtractor:
    """Extracts entities and relationships from chunks via LLM.
    
    Usage:
        extractor = GraphExtractor(settings, graph_store)
        extractor.extract_and_store(chunks)
    """
    
    def __init__(
        self,
        settings: Settings,
        graph_store: GraphStore,
        llm: Optional[BaseLLM] = None,
        max_workers: int = 3,
    ) -> None:
        """Initialize extractor.
        
        Args:
            settings: Application settings.
            graph_store: Persistent graph storage backend.
            llm: Optional LLM override (for testing).
            max_workers: Max concurrent LLM extraction threads.
        """
        self.settings = settings
        self.graph_store = graph_store
        self.max_workers = max_workers
        self._llm = llm
    
    @property
    def llm(self) -> Optional[BaseLLM]:
        """Lazy-load LLM, using override extraction model if configured."""
        if self._llm is None:
            try:
                # Try to use graph_rag.extraction_model if configured
                graph_rag_config = None
                if self.settings.ingestion:
                    graph_rag_config = self.settings.ingestion.graph_rag
                
                if graph_rag_config and graph_rag_config.extraction_model:
                    # Temporarily override model for graph extraction
                    from dataclasses import replace
                    override_llm_settings = replace(
                        self.settings.llm, model=graph_rag_config.extraction_model
                    )
                    from dataclasses import replace as dc_replace
                    tmp_settings = dc_replace(self.settings, llm=override_llm_settings)
                    self._llm = LLMFactory.create(tmp_settings)
                else:
                    self._llm = LLMFactory.create(self.settings)
                logger.info("GraphExtractor: LLM initialized")
            except Exception as e:
                logger.warning(f"GraphExtractor: failed to init LLM: {e}")
        return self._llm

    def extract_and_store(
        self,
        chunks: List[Chunk],
        doc_id: str,
        trace: Optional[TraceContext] = None,
    ) -> Tuple[int, int]:
        """Extract entities and relationships from all chunks in parallel.
        
        Args:
            chunks: Source chunks to process.
            doc_id: Document ID for grouping in graph store.
            trace: Optional trace context.
            
        Returns:
            Tuple of (entity_count, relationship_count) added.
        """
        if not self.llm:
            logger.warning("GraphExtractor: LLM unavailable, skipping extraction")
            return 0, 0

        total_entities: List[Dict[str, Any]] = []
        total_rels: List[Dict[str, Any]] = []

        def _process_one(chunk: Chunk) -> Tuple[List, List]:
            return self._extract_single(chunk, doc_id)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(_process_one, c): c.id for c in chunks}
            for future in as_completed(futures):
                try:
                    entities, rels = future.result()
                    total_entities.extend(entities)
                    total_rels.extend(rels)
                except Exception as exc:
                    logger.warning(f"GraphExtractor: chunk extraction failed: {exc}")

        # Deduplicate by ID before storing
        seen_entity_ids = set()
        unique_entities = []
        for e in total_entities:
            if e["id"] not in seen_entity_ids:
                seen_entity_ids.add(e["id"])
                unique_entities.append(e)

        seen_rel_ids = set()
        unique_rels = []
        for r in total_rels:
            if r["id"] not in seen_rel_ids:
                seen_rel_ids.add(r["id"])
                unique_rels.append(r)

        e_count = self.graph_store.add_entities(unique_entities)
        r_count = self.graph_store.add_relationships(unique_rels)

        logger.info(f"GraphExtractor: stored {e_count} entities, {r_count} relationships for {doc_id}")
        return e_count, r_count

    def _extract_single(
        self, chunk: Chunk, doc_id: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run LLM extraction for a single chunk."""
        text = (chunk.text or "").strip()
        if len(text) < 50:
            return [], []

        prompt = EXTRACTION_PROMPT.replace("{text}", text[:3000])
        try:
            messages = [Message(role="user", content=prompt)]
            response = self.llm.chat(messages)
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.debug(f"GraphExtractor LLM call failed for chunk {chunk.id}: {exc}")
            return [], []

        entities, rels = self._parse_response(response_text, doc_id)
        return entities, rels

    def _parse_response(
        self, response: str, doc_id: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parse LLM response into entity/relationship dicts."""
        entities: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = []

        entity_section = re.search(r"ENTITIES:(.*?)(?:RELATIONSHIPS:|$)", response, re.DOTALL)
        rel_section = re.search(r"RELATIONSHIPS:(.*?)$", response, re.DOTALL)

        if entity_section:
            for line in entity_section.group(1).strip().splitlines():
                m = _ENTITY_PATTERN.match(line.strip())
                if m:
                    name, etype, desc = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                    eid = hashlib.md5(f"{doc_id}:{name}".encode()).hexdigest()[:12]
                    entities.append({
                        "id": eid, "name": name, "entity_type": etype,
                        "description": desc[:200], "doc_id": doc_id
                    })

        if rel_section:
            entity_name_to_id = {e["name"]: e["id"] for e in entities}
            for line in rel_section.group(1).strip().splitlines():
                m = _REL_PATTERN.match(line.strip())
                if m:
                    src_name, rel_type, tgt_name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                    src_id = entity_name_to_id.get(src_name)
                    tgt_id = entity_name_to_id.get(tgt_name)
                    if src_id and tgt_id:
                        rid = hashlib.md5(f"{src_id}:{rel_type}:{tgt_id}".encode()).hexdigest()[:12]
                        relationships.append({
                            "id": rid, "source_id": src_id, "target_id": tgt_id,
                            "relation_type": rel_type, "doc_id": doc_id
                        })

        return entities, relationships
