"""Ingestion Pipeline orchestrator for the Modular RAG MCP Server.

This module implements the main pipeline that orchestrates the complete
document ingestion flow:
    1. File Integrity Check (SHA256 skip check)
    2. Document Loading (PDF → Document)
    3. Chunking (Document → Chunks)
    4. Transform (Refine + Enrich + Caption)
    5. Encoding (Dense + Sparse vectors)
    6. Storage (VectorStore + BM25 Index + ImageStorage)

Design Principles:
- Config-Driven: All components configured via settings.yaml
- Observable: Logs progress and stage completion
- Graceful Degradation: LLM failures don't block pipeline
- Idempotent: SHA256-based skip for unchanged files
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any, Coroutine

from src.core.settings import Settings, load_settings, resolve_path
from src.core.types import Document, Chunk
from src.core.trace.trace_context import TraceContext
from src.observability.logger import get_logger

# Libs layer imports
from src.libs.loader.file_integrity import SQLiteIntegrityChecker
from src.libs.loader.loader_factory import LoaderFactory
from src.libs.embedding.embedding_factory import EmbeddingFactory
from src.libs.vector_store.vector_store_factory import VectorStoreFactory

# Ingestion layer imports
from src.ingestion.chunking.document_chunker import DocumentChunker
from src.ingestion.chunking.hierarchical_chunker import HierarchicalChunker
from src.ingestion.transform.chunk_refiner import ChunkRefiner
from src.ingestion.transform.metadata_enricher import MetadataEnricher
from src.ingestion.transform.image_captioner import ImageCaptioner
from src.ingestion.transform.context_enricher import ContextEnricher
from src.ingestion.transform.graph_extractor import GraphExtractor
from src.ingestion.embedding.dense_encoder import DenseEncoder
from src.ingestion.embedding.sparse_encoder import SparseEncoder
from src.ingestion.embedding.batch_processor import BatchProcessor
from src.ingestion.storage.bm25_indexer import BM25Indexer
from src.ingestion.storage.vector_upserter import VectorUpserter
from src.ingestion.storage.image_storage import ImageStorage
from src.ingestion.storage.parent_store import ParentStore
from src.ingestion.storage.graph_store import GraphStore

logger = get_logger(__name__)


class PipelineResult:
    """Result of pipeline execution with detailed statistics.
    
    Attributes:
        success: Whether pipeline completed successfully
        file_path: Path to the processed file
        doc_id: Document ID (SHA256 hash)
        chunk_count: Number of chunks generated
        image_count: Number of images processed
        vector_ids: List of vector IDs stored
        error: Error message if pipeline failed
        stages: Dict of stage names to their individual results
    """
    
    def __init__(
        self,
        success: bool,
        file_path: str,
        doc_id: Optional[str] = None,
        chunk_count: int = 0,
        image_count: int = 0,
        vector_ids: Optional[List[str]] = None,
        error: Optional[str] = None,
        stages: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.file_path = file_path
        self.doc_id = doc_id
        self.chunk_count = chunk_count
        self.image_count = image_count
        self.vector_ids = vector_ids or []
        self.error = error
        self.stages = stages or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "file_path": self.file_path,
            "doc_id": self.doc_id,
            "chunk_count": self.chunk_count,
            "image_count": self.image_count,
            "vector_ids_count": len(self.vector_ids),
            "error": self.error,
            "stages": self.stages
        }


class IngestionPipeline:
    """Main pipeline orchestrator for document ingestion.
    
    This class coordinates all stages of the ingestion process:
    - File integrity checking for incremental processing
    - Document loading (PDF with image extraction)
    - Text chunking with configurable splitter
    - Chunk refinement (rule-based + LLM)
    - Metadata enrichment (rule-based + LLM)
    - Image captioning (Vision LLM)
    - Dense embedding (Azure text-embedding-ada-002)
    - Sparse encoding (BM25 term statistics)
    - Vector storage (ChromaDB)
    - BM25 index building
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings("config/settings.yaml")
        >>> pipeline = IngestionPipeline(settings)
        >>> result = pipeline.run("documents/report.pdf", collection="contracts")
        >>> print(f"Processed {result.chunk_count} chunks")
    """
    
    def __init__(
        self,
        settings: Settings,
        collection: str = "default",
        force: bool = False,
        skip_llm_transform: bool = False,
    ):
        """Initialize pipeline with all components.
        
        Args:
            settings: Application settings from settings.yaml
            collection: Collection name for organizing documents
            force: If True, re-process even if file was previously processed
            skip_llm_transform: If True, skip LLM-based ChunkRefiner,
                MetadataEnricher and ImageCaptioner. Useful for bulk
                re-ingestion where only image extraction changed.
        """
        self.settings = settings
        self.collection = collection
        self.force = force
        self.skip_llm_transform = skip_llm_transform
        
        # Initialize all components
        logger.info("Initializing Ingestion Pipeline components...")
        
        # Stage 1: File Integrity
        self.integrity_checker = SQLiteIntegrityChecker(db_path=str(resolve_path("data/db/ingestion_history.db")))
        logger.info("  ✓ FileIntegrityChecker initialized")
        
        # Stage 2: Loader (created dynamically per file via LoaderFactory)
        self._image_storage_dir = str(resolve_path(f"data/images/{collection}"))
        logger.info("  ✓ LoaderFactory ready")
        
        # Stage 3: Chunker
        self.chunker = DocumentChunker(settings)
        logger.info("  ✓ DocumentChunker initialized")
        
        # Stage 4: Transforms
        self.chunk_refiner = ChunkRefiner(settings)
        logger.info(f"  ✓ ChunkRefiner initialized (use_llm={self.chunk_refiner.use_llm})")
        
        self.metadata_enricher = MetadataEnricher(settings)
        logger.info(f"  ✓ MetadataEnricher initialized (use_llm={self.metadata_enricher.use_llm})")
        
        self.image_captioner = ImageCaptioner(settings)
        has_vision = self.image_captioner.llm is not None
        logger.info(f"  ✓ ImageCaptioner initialized (vision_enabled={has_vision})")
        
        self.context_enricher = ContextEnricher(settings)
        logger.info(f"  ✓ ContextEnricher initialized (enabled={self.context_enricher.enabled})")
        
        # Stage 5: Encoders
        embedding = EmbeddingFactory.create(settings)
        batch_size = settings.ingestion.batch_size if settings.ingestion else 100
        # Embedding API batch size should be small to respect provider limits
        # (e.g. DashScope text-embedding-v3 limits tokens/texts per request)
        embedding_batch_size = min(batch_size, 6)
        self.dense_encoder = DenseEncoder(embedding, batch_size=embedding_batch_size)
        logger.info(f"  ✓ DenseEncoder initialized (provider={settings.embedding.provider})")
        
        self.sparse_encoder = SparseEncoder()
        logger.info("  ✓ SparseEncoder initialized")
        
        self.batch_processor = BatchProcessor(
            dense_encoder=self.dense_encoder,
            sparse_encoder=self.sparse_encoder,
            batch_size=embedding_batch_size
        )
        logger.info(f"  ✓ BatchProcessor initialized (batch_size={embedding_batch_size})")
        
        # Stage 6: Storage
        self.vector_upserter = VectorUpserter(settings, collection_name=collection)
        logger.info(f"  ✓ VectorUpserter initialized (provider={settings.vector_store.provider}, collection={collection})")
        
        self.bm25_indexer = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
        logger.info("  ✓ BM25Indexer initialized")
        
        self.image_storage = ImageStorage(
            db_path=str(resolve_path("data/db/image_index.db")),
            images_root=str(resolve_path("data/images")),
        )
        logger.info(f"  ✓ ImageStorage initialized")

        # Optional Stage: Parent Retrieval
        self.parent_store: Optional[ParentStore] = None
        self.hierarchical_chunker: Optional[HierarchicalChunker] = None
        ingestion_settings = settings.ingestion
        if ingestion_settings and ingestion_settings.parent_retrieval and ingestion_settings.parent_retrieval.enabled:
            self.hierarchical_chunker = HierarchicalChunker(settings)
            self.parent_store = ParentStore(
                db_path=str(resolve_path(f"data/db/parent_store/{collection}.db"))
            )
            logger.info("  ✓ HierarchicalChunker + ParentStore initialized (Parent Retrieval enabled)")

        # Optional Stage: GraphRAG
        self.graph_store: Optional[GraphStore] = None
        self.graph_extractor: Optional[GraphExtractor] = None
        if ingestion_settings and ingestion_settings.graph_rag and ingestion_settings.graph_rag.enabled:
            self.graph_store = GraphStore(
                db_path=str(resolve_path(f"data/db/graph_store/{collection}.db"))
            )
            self.graph_extractor = GraphExtractor(settings, self.graph_store)
            logger.info("  ✓ GraphStore + GraphExtractor initialized (GraphRAG enabled)")
        
        logger.info("Pipeline initialization complete!")
    
    def _trace_stage(
        self,
        trace: Optional[TraceContext],
        stage_name: str,
        data: Dict[str, Any],
        elapsed_ms: float = 0.0,
    ) -> None:
        """Record a pipeline stage in the trace context (if enabled)."""
        if trace is not None:
            trace.record_stage(stage_name, data, elapsed_ms=elapsed_ms)
    
    @staticmethod
    def _chunk_details(chunks: List[Chunk]) -> List[Dict[str, Any]]:
        """Build a serializable chunk summary for trace recording."""
        return [
            {
                "chunk_id": c.id,
                "text": c.text,
                "char_len": len(c.text),
                "chunk_index": c.metadata.get("chunk_index", i),
            }
            for i, c in enumerate(chunks)
        ]
    
    @staticmethod
    def _transform_details(
        chunks: List[Chunk],
        pre_refine_texts: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Build transform stage chunk details for trace."""
        return [
            {
                "chunk_id": c.id,
                "text_before": pre_refine_texts.get(c.id, ""),
                "text_after": c.text,
                "char_len": len(c.text),
                "refined_by": c.metadata.get("refined_by", ""),
                "enriched_by": c.metadata.get("enriched_by", ""),
                "title": c.metadata.get("title", ""),
                "tags": c.metadata.get("tags", []),
                "summary": c.metadata.get("summary", ""),
            }
            for c in chunks
        ]
    
    @staticmethod
    def _encoding_details(
        chunks: List[Chunk],
        dense_vectors: List,
        sparse_stats: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build encoding stage per-chunk details for trace."""
        details = []
        for idx, c in enumerate(chunks):
            detail: Dict[str, Any] = {
                "chunk_id": c.id,
                "char_len": len(c.text),
            }
            if idx < len(dense_vectors):
                detail["dense_dim"] = len(dense_vectors[idx])
            if idx < len(sparse_stats):
                ss = sparse_stats[idx]
                detail["doc_length"] = ss.get("doc_length", 0)
                detail["unique_terms"] = ss.get("unique_terms", 0)
                tf = ss.get("term_frequencies", {})
                top_terms = sorted(tf.items(), key=lambda x: x[1], reverse=True)[:10]
                detail["top_terms"] = [{"term": t, "freq": f} for t, f in top_terms]
            details.append(detail)
        return details
    
    async def run(
        self,
        file_path: str,
        trace: Optional[TraceContext] = None,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
        on_progress_async: Optional[Callable[[str, float], Coroutine[Any, Any, None]]] = None,
        original_filename: Optional[str] = None,
        extra_metadata: Optional[Dict[str, str]] = None,
    ) -> PipelineResult:
        """Execute the full ingestion pipeline on a file (Async).
        
        Args:
            file_path: Path to the file to process.
            trace: Optional trace context.
            on_progress: Legacy synchronous progress callback.
            on_progress_async: Async progress callback providing (stage_name, percent).
            original_filename: Original name of the file.
            extra_metadata: Extra metadata to inject.
        """
        file_path = Path(file_path)
        display_name = original_filename or file_path.name
        stages: Dict[str, Any] = {}
        _total_stages = 6

        async def _notify(stage_name: str, step: int, percent: float = 0.0) -> None:
            if on_progress is not None:
                on_progress(stage_name, step, _total_stages)
            if on_progress_async is not None:
                # Provide a more granular percent if step is fixed
                # percent = (step - 1) / _total_stages + (local_progress / _total_stages)
                await on_progress_async(stage_name, percent)
        
        logger.info(f"=" * 60)
        logger.info(f"Starting Ingestion Pipeline for: {display_name}")
        logger.info(f"Collection: {self.collection}")
        logger.info(f"=" * 60)
        
        try:
            # ─────────────────────────────────────────────────────────────
            # Stage 1: File Integrity Check
            # ─────────────────────────────────────────────────────────────
            logger.info("\n📋 Stage 1: File Integrity Check")
            await _notify("integrity", 1)
            
            file_hash = self.integrity_checker.compute_sha256(str(file_path))
            logger.info(f"  File hash: {file_hash[:16]}...")
            
            if not self.force and self.integrity_checker.should_skip(file_hash):
                logger.info(f"  ⏭️  File already processed, skipping (use force=True to reprocess)")
                return PipelineResult(
                    success=True,
                    file_path=display_name,
                    doc_id=file_hash,
                    stages={"integrity": {"skipped": True, "reason": "already_processed"}}
                )
            
            stages["integrity"] = {"file_hash": file_hash, "skipped": False}
            logger.info("  ✓ File needs processing")
            
            # When force=True, delete old chunks for this source_path so
            # content-hash-based IDs don't create orphan duplicates.
            if self.force:
                src_path = original_filename or str(file_path)
                deleted = self.vector_upserter.delete_by_source_path(src_path)
                if deleted:
                    logger.info(f"  🗑️  Deleted {deleted} old chunks for re-ingestion")
            
            # ─────────────────────────────────────────────────────────────
            # Stage 2: Document Loading
            # ─────────────────────────────────────────────────────────────
            logger.info("\n📄 Stage 2: Document Loading")
            await _notify("load", 2)
            
            _t0 = time.monotonic()
            pdf_parser = "markitdown"
            if self.settings.ingestion:
                pdf_parser = getattr(self.settings.ingestion, "pdf_parser", "markitdown")
            loader = LoaderFactory.create(
                file_path,
                extract_images=True,
                image_storage_dir=self._image_storage_dir,
                pdf_parser=pdf_parser,
            )
            document = loader.load(str(file_path))
            # Override source_path with original filename if provided
            if original_filename and "source_path" in document.metadata:
                document.metadata["source_path"] = original_filename
                document.metadata["original_filename"] = original_filename
            _elapsed = (time.monotonic() - _t0) * 1000.0
            
            text_preview = document.text[:200].replace('\n', ' ') + "..." if len(document.text) > 200 else document.text
            image_count = len(document.metadata.get("images", []))
            
            logger.info(f"  Document ID: {document.id}")
            logger.info(f"  Text length: {len(document.text)} chars")
            logger.info(f"  Images extracted: {image_count}")
            logger.info(f"  Preview: {text_preview[:100]}...")
            
            stages["loading"] = {
                "doc_id": document.id,
                "text_length": len(document.text),
                "image_count": image_count
            }
            self._trace_stage(trace, "load", {
                "method": "markitdown",
                "doc_id": document.id,
                "text_length": len(document.text),
                "image_count": image_count,
                "text_preview": document.text,
            }, elapsed_ms=_elapsed)
            
            # ─────────────────────────────────────────────────────────────
            # Stage 3: Chunking
            # ─────────────────────────────────────────────────────────────
            logger.info("\n✂️  Stage 3: Document Chunking")
            await _notify("split", 3)
            
            _t0 = time.monotonic()
            chunks = self.chunker.split_document(document)
            _elapsed = (time.monotonic() - _t0) * 1000.0
            
            logger.info(f"  Chunks generated: {len(chunks)}")
            if chunks:
                logger.info(f"  First chunk ID: {chunks[0].id}")
                logger.info(f"  First chunk preview: {chunks[0].text[:100]}...")
            
            # Inject extra metadata into every chunk (e.g. product_vendor, product_model)
            if extra_metadata:
                for c in chunks:
                    c.metadata.update(extra_metadata)
                logger.info(f"  Extra metadata injected: {list(extra_metadata.keys())}")

            stages["chunking"] = {
                "chunk_count": len(chunks),
                "avg_chunk_size": sum(len(c.text) for c in chunks) // len(chunks) if chunks else 0
            }
            self._trace_stage(trace, "split", {
                "method": "recursive",
                "chunk_count": len(chunks),
                "avg_chunk_size": sum(len(c.text) for c in chunks) // len(chunks) if chunks else 0,
                "chunks": self._chunk_details(chunks),
            }, elapsed_ms=_elapsed)
            
            # ─────────────────────────────────────────────────────────────
            # Stage 4: Transform Pipeline
            # ─────────────────────────────────────────────────────────────
            logger.info("\n🔄 Stage 4: Transform Pipeline")
            await _notify("transform", 4)
            
            # 4a: Context Enrichment (zero-cost, always run first)
            _t0_transform = time.monotonic()
            chunks = self.context_enricher.transform(chunks, trace)
            context_enriched = sum(1 for c in chunks if c.metadata.get("embedding_text"))
            logger.info(f"  4a. Context Enrichment: {context_enriched}/{len(chunks)} chunks enriched")
            await _notify("transform:context", 4, 15.0)

            # 4b: Parallel LLM Transforms
            _pre_refine_texts = {c.id: c.text for c in chunks}
            refined_by_llm = refined_by_rule = 0
            enriched_by_llm = enriched_by_rule = 0
            captioned = 0

            if self.skip_llm_transform:
                logger.info("  ⏩ Skipping LLM transforms (skip_llm_transform=True)")
                chunks = self.chunk_refiner.transform(chunks, trace)
                refined_by_rule = sum(1 for c in chunks if c.metadata.get("refined_by") == "rule")
                logger.info(f"      Rule refined: {refined_by_rule}")
                await _notify("transform:rule", 4, 30.0)
            else:
                logger.info("  4b. Parallel LLM Transforms (Refine + Enrich + Caption)...")
                
                # We wrap the synchronous transform calls in asyncio.to_thread to run them in parallel
                # Since these are mostly IO/API bound (LLM calls), this is safe and effective.
                async def _run_refine():
                    nonlocal chunks
                    return await asyncio.to_thread(self.chunk_refiner.transform, chunks, trace)
                
                async def _run_enrich():
                    nonlocal chunks
                    return await asyncio.to_thread(self.metadata_enricher.transform, chunks, trace)
                
                async def _run_caption():
                    nonlocal chunks
                    return await asyncio.to_thread(self.image_captioner.transform, chunks, trace)

                # Execute Refine first as it might change the text, then Enrich and Caption in parallel
                # because metadata enrichment often depends on the final text.
                chunks = await _run_refine()
                await _notify("transform:refine", 4, 25.0)
                
                # Enrich and Caption can run in parallel
                await asyncio.gather(_run_enrich(), _run_caption())
                await _notify("transform:enrich_caption", 4, 45.0)
                
                refined_by_llm = sum(1 for c in chunks if c.metadata.get("refined_by") == "llm")
                refined_by_rule = sum(1 for c in chunks if c.metadata.get("refined_by") == "rule")
                enriched_by_llm = sum(1 for c in chunks if c.metadata.get("enriched_by") == "llm")
                enriched_by_rule = sum(1 for c in chunks if c.metadata.get("enriched_by") == "rule")
                captioned = sum(1 for c in chunks if c.metadata.get("image_captions"))
                
                logger.info(f"      LLM refined: {refined_by_llm}, Rule refined: {refined_by_rule}")
                logger.info(f"      LLM enriched: {enriched_by_llm}, Rule enriched: {enriched_by_rule}")
                logger.info(f"      Chunks with captions: {captioned}")
            
            stages["transform"] = {
                "context_enricher": {"enriched": context_enriched},
                "chunk_refiner": {"llm": refined_by_llm, "rule": refined_by_rule},
                "metadata_enricher": {"llm": enriched_by_llm, "rule": enriched_by_rule},
                "image_captioner": {"captioned_chunks": captioned}
            }
            _elapsed_transform = (time.monotonic() - _t0_transform) * 1000.0
            self._trace_stage(trace, "transform", {
                "method": "refine+enrich+caption",
                "refined_by_llm": refined_by_llm,
                "refined_by_rule": refined_by_rule,
                "enriched_by_llm": enriched_by_llm,
                "enriched_by_rule": enriched_by_rule,
                "captioned_chunks": captioned,
                "chunks": self._transform_details(chunks, _pre_refine_texts),
            }, elapsed_ms=_elapsed_transform)
            
            # ─────────────────────────────────────────────────────────────
            # Stage 5: Encoding
            # ─────────────────────────────────────────────────────────────
            logger.info("\n🔢 Stage 5: Encoding")
            await _notify("embed", 5)
            
            # Process through BatchProcessor
            _t0 = time.monotonic()
            batch_result = self.batch_processor.process(chunks, trace)
            _elapsed = (time.monotonic() - _t0) * 1000.0
            
            dense_vectors = batch_result.dense_vectors
            sparse_stats = batch_result.sparse_stats
            
            logger.info(f"  Dense vectors: {len(dense_vectors)} (dim={len(dense_vectors[0]) if dense_vectors else 0})")
            logger.info(f"  Sparse stats: {len(sparse_stats)} documents")
            
            stages["encoding"] = {
                "dense_vector_count": len(dense_vectors),
                "dense_dimension": len(dense_vectors[0]) if dense_vectors else 0,
                "sparse_doc_count": len(sparse_stats)
            }
            self._trace_stage(trace, "embed", {
                "method": "batch_processor",
                "dense_vector_count": len(dense_vectors),
                "dense_dimension": len(dense_vectors[0]) if dense_vectors else 0,
                "sparse_doc_count": len(sparse_stats),
                "chunks": self._encoding_details(chunks, dense_vectors, sparse_stats),
            }, elapsed_ms=_elapsed)
            
            # ─────────────────────────────────────────────────────────────
            # Stage 6: Storage
            # ─────────────────────────────────────────────────────────────
            logger.info("\n💾 Stage 6: Storage")
            await _notify("upsert", 6)
            
            # 6a: Vector Upsert
            if len(dense_vectors) == 0:
                raise RuntimeError(
                    f"Encoding failed: got 0 vectors for {len(chunks)} chunks. "
                    f"Check embedding API logs above for details."
                )
            if len(dense_vectors) != len(chunks):
                lost = len(chunks) - len(dense_vectors)
                logger.warning(
                    f"Partial encoding: {len(dense_vectors)}/{len(chunks)} chunks succeeded "
                    f"({lost} chunks lost due to embedding errors). Proceeding with successful chunks."
                )
                # Trim chunks and sparse_stats to match the vectors we have
                chunks = chunks[:len(dense_vectors)]
                sparse_stats = sparse_stats[:len(dense_vectors)]
            logger.info("  6a. Vector Storage (ChromaDB)...")
            _t0_storage = time.monotonic()
            vector_ids = self.vector_upserter.upsert(chunks, dense_vectors, trace)
            logger.info(f"      Stored {len(vector_ids)} vectors")

            # Align BM25 chunk_ids with Chroma vector IDs so the SparseRetriever
            # can look up BM25 hits in the vector store after retrieval.
            for stat, vid in zip(sparse_stats, vector_ids):
                stat["chunk_id"] = vid

            # 6b: BM25 Index (with rollback on failure)
            logger.info("  6b. BM25 Index...")
            try:
                self.bm25_indexer.add_documents(
                    sparse_stats,
                    collection=self.collection,
                    doc_id=document.id,
                    trace=trace,
                )
            except Exception as bm25_err:
                # Rollback: delete vectors from ChromaDB to maintain consistency
                logger.error(f"BM25 index failed: {bm25_err}. Rolling back ChromaDB upsert...")
                try:
                    self.vector_upserter.vector_store.delete(vector_ids)
                    logger.info(f"      Rollback: deleted {len(vector_ids)} vectors from ChromaDB")
                except Exception as rollback_err:
                    logger.error(f"      Rollback failed: {rollback_err}")
                raise RuntimeError(
                    f"BM25 index failed (ChromaDB rolled back): {bm25_err}"
                ) from bm25_err
            logger.info(f"      Index built for {len(sparse_stats)} documents")
            
            # 6c: Register images in image storage index
            # Note: Images are already saved by PdfLoader, we just need to index them
            logger.info("  6c. Image Storage Index (Background detection)...")
            images = document.metadata.get("images", [])
            for img in images:
                img_path = Path(img["path"])
                if img_path.exists():
                    # Optimization 2: Persistent Background Detection during ingestion
                    # This ensures background status is known before any queries
                    is_bg = await self.image_storage.adetect_background(
                        image_id=img["id"],
                        image_path=str(img_path.resolve())
                    )
                    self.image_storage.register_image(
                        image_id=img["id"],
                        file_path=img_path,
                        collection=self.collection,
                        doc_hash=file_hash,
                        page_num=img.get("page", 0),
                        is_background=int(is_bg)
                    )
            logger.info(f"      Indexed {len(images)} images")

            # 6d: Parent Chunk Storage (if Parent Retrieval enabled)
            if self.hierarchical_chunker and self.parent_store:
                logger.info("  6d. Parent Chunk Storage (hierarchical)...")
                try:
                    child_chunks, parent_chunks = self.hierarchical_chunker.split_hierarchical(document)
                    self.parent_store.add_parents(parent_chunks)
                    logger.info(f"      Stored {len(parent_chunks)} parent chunks, {len(child_chunks)} child chunks indexed")
                except Exception as pr_err:
                    logger.warning(f"      Parent Retrieval storage failed (non-fatal): {pr_err}")

            # 6e: GraphRAG Entity Extraction (if enabled)
            if self.graph_extractor and self.graph_store:
                logger.info("  6e. GraphRAG Entity Extraction...")
                try:
                    e_count, r_count = self.graph_extractor.extract_and_store(
                        chunks, doc_id=document.id, trace=trace
                    )
                    logger.info(f"      Extracted {e_count} entities, {r_count} relationships")
                except Exception as gr_err:
                    logger.warning(f"      GraphRAG extraction failed (non-fatal): {gr_err}")
            
            stages["storage"] = {
                "vector_count": len(vector_ids),
                "bm25_docs": len(sparse_stats),
                "images_indexed": len(images)
            }
            _elapsed_storage = (time.monotonic() - _t0_storage) * 1000.0
            self._trace_stage(trace, "upsert", {
                "method": "chroma+bm25+image",
                "dense_store": {
                    "backend": "ChromaDB",
                    "collection": self.collection,
                    "count": len(vector_ids),
                    "path": "data/db/chroma/",
                },
                "sparse_store": {
                    "backend": "BM25",
                    "collection": self.collection,
                    "count": len(sparse_stats),
                    "path": f"data/db/bm25/{self.collection}/",
                },
                "image_store": {
                    "backend": "ImageStorage (JSON index)",
                    "count": len(images),
                    "images": [
                        {"image_id": img["id"], "file_path": str(img["path"]),
                         "page": img.get("page", 0), "doc_hash": file_hash}
                        for img in images
                    ],
                },
                "chunk_mapping": [
                    {"chunk_id": c.id,
                     "vector_id": vector_ids[i] if i < len(vector_ids) else "—",
                     "collection": self.collection, "store": "ChromaDB"}
                    for i, c in enumerate(chunks)
                ],
            }, elapsed_ms=_elapsed_storage)
            
            # ─────────────────────────────────────────────────────────────
            # Mark Success
            # ─────────────────────────────────────────────────────────────
            self.integrity_checker.mark_success(file_hash, display_name, self.collection)
            
            # Force ChromaDB to persist HNSW index to disk after each file
            # This prevents index corruption during long batch runs
            try:
                self.vector_upserter.vector_store._wal_checkpoint()
                logger.info("  💾 ChromaDB WAL checkpoint completed")
            except Exception as flush_err:
                logger.warning(f"  ⚠️  ChromaDB flush warning: {flush_err}")
            
            # Verify HNSW health and create backup after successful ingestion
            try:
                vs = self.vector_upserter.vector_store
                if hasattr(vs, 'backup_manager'):
                    vs.backup_manager.verify_and_backup(
                        vs.collection, label="ingest"
                    )
            except Exception as bak_err:
                logger.warning(f"  ⚠️  HNSW backup warning: {bak_err}")
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ Pipeline completed successfully!")
            logger.info(f"   Chunks: {len(chunks)}")
            logger.info(f"   Vectors: {len(vector_ids)}")
            logger.info(f"   Images: {len(images)}")
            logger.info("=" * 60)
            
            return PipelineResult(
                success=True,
                file_path=display_name,
                doc_id=file_hash,
                chunk_count=len(chunks),
                image_count=len(images),
                vector_ids=vector_ids,
                stages=stages
            )
            
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
            self.integrity_checker.mark_failed(file_hash, display_name, str(e))
            
            return PipelineResult(
                success=False,
                file_path=display_name,
                doc_id=file_hash if 'file_hash' in locals() else None,
                error=str(e),
                stages=stages
            )
    
    def close(self) -> None:
        """Clean up resources."""
        self.image_storage.close()


async def run_pipeline(
    file_path: str,
    settings_path: Optional[str] = None,
    collection: str = "default",
    force: bool = False,
    on_progress_async: Optional[Callable[[str, float], Coroutine[Any, Any, None]]] = None,
) -> PipelineResult:
    """Convenience function to run the pipeline (Async).
    
    Args:
        file_path: Path to file to process
        settings_path: Path to settings.yaml
        collection: Collection name
        force: Force reprocessing
        on_progress_async: Async progress callback
    
    Returns:
        PipelineResult with execution details
    """
    settings = load_settings(settings_path)
    pipeline = IngestionPipeline(settings, collection=collection, force=force)
    
    try:
        return await pipeline.run(file_path, on_progress_async=on_progress_async)
    finally:
        pipeline.close()
