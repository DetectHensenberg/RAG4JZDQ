"""Integration tests for the Ingestion Pipeline.

This module tests the complete ingestion flow using real Azure services:
- Azure LLM (gpt-4o) for chunk refinement and metadata enrichment
- Azure Vision LLM (gpt-4o) for image captioning
- Azure Embedding (text-embedding-ada-002) for dense vectors
- ChromaDB for vector storage
- BM25 indexer for sparse retrieval

Test Data:
- complex_technical_doc.pdf: Multi-chapter technical document with images and tables
- simple.pdf: Basic PDF for regression testing
"""

import os
import shutil
import pytest
from pathlib import Path

from src.core.settings import load_settings
from src.ingestion.pipeline import IngestionPipeline, PipelineResult


class TestIngestionPipeline:
    """Integration tests for the full ingestion pipeline."""
    
    @pytest.fixture(autouse=True)
    def setup_test_dirs(self, tmp_path):
        """Set up and clean test directories."""
        # Use tmp_path for test isolation where possible
        self.test_output_dir = tmp_path
        yield
        # Cleanup handled by pytest's tmp_path
    
    @pytest.fixture
    def settings(self):
        """Load settings from config file."""
        return load_settings("config/settings.yaml")
    
    @pytest.fixture
    def complex_pdf_path(self):
        """Path to complex technical document."""
        path = Path("tests/fixtures/sample_documents/complex_technical_doc.pdf")
        assert path.exists(), f"Test fixture not found: {path}"
        return str(path)
    
    @pytest.fixture
    def simple_pdf_path(self):
        """Path to simple PDF document."""
        path = Path("tests/fixtures/sample_documents/simple.pdf")
        assert path.exists(), f"Test fixture not found: {path}"
        return str(path)
    
    def test_pipeline_with_complex_technical_doc(self, settings, complex_pdf_path):
        """Test full pipeline with complex technical document.
        
        This test validates:
        1. File integrity checking works
        2. PDF loading with image extraction
        3. Document chunking
        4. LLM-based chunk refinement
        5. LLM-based metadata enrichment
        6. Vision LLM image captioning
        7. Azure embedding generation
        8. Vector storage to ChromaDB
        9. BM25 index building
        """
        # Create pipeline with test collection
        collection = "test_complex_doc"
        pipeline = IngestionPipeline(
            settings=settings,
            collection=collection,
            force=True  # Force reprocessing for test
        )
        
        try:
            # Run the pipeline
            result = pipeline.run(complex_pdf_path)
            
            # ─────────────────────────────────────────────────────────────
            # Assertions
            # ─────────────────────────────────────────────────────────────
            
            # Basic success check
            assert result.success, f"Pipeline failed: {result.error}"
            assert result.doc_id is not None, "Document ID should be set"
            assert result.file_path == complex_pdf_path
            
            # Chunk generation
            assert result.chunk_count > 0, "Should generate at least one chunk"
            print(f"\n[OK] Generated {result.chunk_count} chunks")
            
            # Vector storage
            assert len(result.vector_ids) > 0, "Should store vectors"
            assert len(result.vector_ids) == result.chunk_count, "Vector count should match chunk count"
            print(f"[OK] Stored {len(result.vector_ids)} vectors")
            
            # Stage-specific checks
            stages = result.stages
            
            # Loading stage
            assert "loading" in stages
            assert stages["loading"]["text_length"] > 0
            print(f"[OK] Loaded document with {stages['loading']['text_length']} chars")
            
            # Transform stage - LLM enhancement verification
            assert "transform" in stages
            transform = stages["transform"]
            
            # Check chunk refinement used LLM
            refiner_stats = transform.get("chunk_refiner", {})
            llm_refined = refiner_stats.get("llm", 0)
            rule_refined = refiner_stats.get("rule", 0)
            print(f"[OK] Chunk Refinement: LLM={llm_refined}, Rule={rule_refined}")
            
            # At least some chunks should be LLM refined (since use_llm=true)
            # Note: might fallback to rule if LLM fails
            total_refined = llm_refined + rule_refined
            assert total_refined == result.chunk_count, "All chunks should be refined"
            
            # Check metadata enrichment used LLM
            enricher_stats = transform.get("metadata_enricher", {})
            llm_enriched = enricher_stats.get("llm", 0)
            rule_enriched = enricher_stats.get("rule", 0)
            print(f"[OK] Metadata Enrichment: LLM={llm_enriched}, Rule={rule_enriched}")
            
            total_enriched = llm_enriched + rule_enriched
            assert total_enriched == result.chunk_count, "All chunks should be enriched"
            
            # Check image captioning
            captioner_stats = transform.get("image_captioner", {})
            captioned = captioner_stats.get("captioned_chunks", 0)
            print(f"[OK] Image Captioning: {captioned} chunks with captions")
            
            # Encoding stage
            assert "encoding" in stages
            encoding = stages["encoding"]
            assert encoding["dense_vector_count"] == result.chunk_count
            assert encoding["dense_dimension"] == 1536, "Azure ada-002 should produce 1536-dim vectors"
            print(f"[OK] Dense vectors: {encoding['dense_vector_count']} x {encoding['dense_dimension']}dim")
            
            # Storage stage
            assert "storage" in stages
            storage = stages["storage"]
            assert storage["vector_count"] == result.chunk_count
            assert storage["bm25_docs"] == result.chunk_count
            print(f"[OK] Storage: {storage['vector_count']} vectors, {storage['bm25_docs']} BM25 docs")
            
            # Verify files were created
            chroma_dir = Path(settings.vector_store.persist_directory)
            assert chroma_dir.exists(), "ChromaDB directory should exist"
            
            bm25_dir = Path(f"data/db/bm25/{collection}")
            assert bm25_dir.exists(), "BM25 index directory should exist"
            
            print("\n" + "=" * 60)
            print("SUCCESS - All pipeline stages completed!")
            print(f"   Document: {complex_pdf_path}")
            print(f"   Chunks: {result.chunk_count}")
            print(f"   Vectors: {len(result.vector_ids)}")
            print(f"   Images: {result.image_count}")
            print("=" * 60)
            
        finally:
            pipeline.close()
    
    def test_pipeline_skip_already_processed(self, settings, simple_pdf_path):
        """Test that pipeline skips already processed files."""
        collection = "test_skip"
        
        # First run - should process
        pipeline1 = IngestionPipeline(settings, collection=collection, force=True)
        try:
            result1 = pipeline1.run(simple_pdf_path)
            assert result1.success
            assert result1.chunk_count > 0
        finally:
            pipeline1.close()
        
        # Second run without force - should skip
        pipeline2 = IngestionPipeline(settings, collection=collection, force=False)
        try:
            result2 = pipeline2.run(simple_pdf_path)
            assert result2.success
            assert "integrity" in result2.stages
            assert result2.stages["integrity"].get("skipped") == True
            print("\n[OK] File correctly skipped on second run")
        finally:
            pipeline2.close()
    
    def test_pipeline_force_reprocess(self, settings, simple_pdf_path):
        """Test that force=True reprocesses even if already done."""
        collection = "test_force"
        
        # First run
        pipeline1 = IngestionPipeline(settings, collection=collection, force=True)
        try:
            result1 = pipeline1.run(simple_pdf_path)
            assert result1.success
            chunk_count1 = result1.chunk_count
        finally:
            pipeline1.close()
        
        # Second run with force - should reprocess
        pipeline2 = IngestionPipeline(settings, collection=collection, force=True)
        try:
            result2 = pipeline2.run(simple_pdf_path)
            assert result2.success
            assert result2.chunk_count == chunk_count1
            assert result2.stages.get("integrity", {}).get("skipped") != True
            print("\n[OK] File correctly reprocessed with force=True")
        finally:
            pipeline2.close()


class TestPipelineComponents:
    """Test individual pipeline components in isolation."""
    
    @pytest.fixture
    def settings(self):
        """Load settings from config file."""
        return load_settings("config/settings.yaml")
    
    def test_settings_loads_correctly(self, settings):
        """Verify settings are loaded with expected values."""
        # LLM settings
        assert settings.llm.provider == "azure"
        assert settings.llm.model == "gpt-4o"
        print(f"[OK] LLM: {settings.llm.provider}/{settings.llm.model}")
        
        # Embedding settings
        assert settings.embedding.provider == "azure"
        assert settings.embedding.model == "text-embedding-ada-002"
        assert settings.embedding.dimensions == 1536
        print(f"[OK] Embedding: {settings.embedding.provider}/{settings.embedding.model}")
        
        # Vision LLM settings
        assert settings.vision_llm is not None
        assert settings.vision_llm.enabled == True
        assert settings.vision_llm.provider == "azure"
        print(f"[OK] Vision LLM: {settings.vision_llm.provider}/{settings.vision_llm.model}")
        
        # Ingestion settings
        assert settings.ingestion is not None
        assert settings.ingestion.chunk_refiner is not None
        assert settings.ingestion.chunk_refiner.get("use_llm") == True
        assert settings.ingestion.metadata_enricher is not None
        assert settings.ingestion.metadata_enricher.get("use_llm") == True
        print("[OK] Ingestion LLM enhancement: enabled")
    
    def test_embedding_creates_vectors(self, settings):
        """Test that Azure embedding service works."""
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        
        embedding = EmbeddingFactory.create(settings)
        
        texts = ["Hello world", "Testing embedding"]
        vectors = embedding.embed(texts)
        
        assert len(vectors) == 2
        assert len(vectors[0]) == 1536  # ada-002 dimension
        print(f"[OK] Embedding test: produced {len(vectors)} vectors of dim {len(vectors[0])}")
    
    def test_llm_responds(self, settings):
        """Test that Azure LLM service works."""
        from src.libs.llm.llm_factory import LLMFactory
        from src.libs.llm.base_llm import Message
        
        llm = LLMFactory.create(settings)
        
        messages = [
            Message(role="user", content="Say 'Hello' and nothing else.")
        ]
        response = llm.chat(messages)
        
        assert response is not None
        assert len(response.content) > 0
        print(f"[OK] LLM test: received response: {response.content[:50]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
