"""Integration tests for CoreReranker with real Azure LLM.

This module tests the complete reranking flow with actual Azure OpenAI calls:
1. LLM Reranker integration with CoreReranker
2. Real reranking quality validation
3. Fallback behavior with invalid configuration

⚠️ WARNING: These tests make real API calls and incur costs!
"""

import pytest
from typing import List

from src.core.query_engine.reranker import CoreReranker, RerankConfig, RerankResult
from src.core.settings import load_settings
from src.core.types import RetrievalResult
from src.libs.reranker.llm_reranker import LLMReranker
from src.libs.reranker.reranker_factory import RerankerFactory


# =============================================================================
# Test Data
# =============================================================================

def create_test_results() -> List[RetrievalResult]:
    """Create test retrieval results for reranking.
    
    These results are ordered by initial retrieval score, but the LLM reranker
    should reorder them based on semantic relevance to the query.
    """
    return [
        RetrievalResult(
            chunk_id="chunk_python",
            score=0.95,  # High initial score but less relevant
            text="Python is a versatile programming language known for its simplicity. "
                 "It supports multiple programming paradigms including procedural, "
                 "object-oriented, and functional programming.",
            metadata={"source_path": "docs/languages.pdf", "page": 5},
        ),
        RetrievalResult(
            chunk_id="chunk_azure_config",
            score=0.85,  # Lower initial score but most relevant
            text="To configure Azure OpenAI, you need to set the following parameters: "
                 "azure_endpoint, api_key, deployment_name, and api_version. "
                 "The azure_endpoint should be your Azure resource URL, and the "
                 "deployment_name matches your model deployment in Azure Portal.",
            metadata={"source_path": "docs/azure-setup.pdf", "page": 12},
        ),
        RetrievalResult(
            chunk_id="chunk_ml_basics",
            score=0.80,  # Lower score, somewhat relevant
            text="Machine learning models can be deployed on various cloud platforms "
                 "including Azure, AWS, and GCP. Azure provides Azure ML for training "
                 "and Azure OpenAI Service for accessing GPT models.",
            metadata={"source_path": "docs/ml-guide.pdf", "page": 3},
        ),
        RetrievalResult(
            chunk_id="chunk_database",
            score=0.75,  # Lowest score, not relevant
            text="Database indexing improves query performance by creating data structures "
                 "that allow faster lookups. Common index types include B-tree, hash, "
                 "and full-text indexes.",
            metadata={"source_path": "docs/database.pdf", "page": 8},
        ),
    ]


# =============================================================================
# Integration Tests with Real Azure LLM
# =============================================================================

class TestCoreRerankerAzureLLM:
    """Integration tests with real Azure OpenAI LLM calls."""
    
    @pytest.fixture
    def settings(self):
        """Load real settings from config file."""
        return load_settings("config/settings.yaml")
    
    @pytest.fixture
    def test_results(self):
        """Create test retrieval results."""
        return create_test_results()
    
    def test_llm_reranker_creates_successfully(self, settings):
        """Test that LLM Reranker can be created from settings."""
        # Verify settings have rerank enabled with llm provider
        assert settings.rerank.enabled is True, "Rerank should be enabled in settings"
        assert settings.rerank.provider == "llm", "Provider should be 'llm'"
        
        # Create reranker via factory
        reranker = RerankerFactory.create(settings)
        
        assert isinstance(reranker, LLMReranker)
        print(f"✅ LLM Reranker created successfully")
    
    def test_core_reranker_with_llm_backend(self, settings):
        """Test CoreReranker initialization with LLM backend."""
        core_reranker = CoreReranker(settings)
        
        assert core_reranker.is_enabled is True
        assert core_reranker.reranker_type == "llm"
        print(f"✅ CoreReranker initialized with LLM backend")
    
    def test_real_llm_reranking(self, settings, test_results):
        """Test actual LLM reranking with Azure OpenAI.
        
        This test:
        1. Sends test results to the LLM for reranking
        2. Verifies that the most relevant chunk is ranked higher
        3. Prints the full ranking for manual review
        """
        print("\n" + "=" * 60)
        print("REAL LLM RERANKING TEST")
        print("=" * 60)
        
        core_reranker = CoreReranker(settings)
        query = "How do I configure Azure OpenAI settings?"
        
        print(f"\n📝 Query: {query}")
        print(f"\n📊 Input Results (by initial score):")
        for i, r in enumerate(test_results):
            print(f"  {i+1}. [{r.score:.2f}] {r.chunk_id}: {r.text[:60]}...")
        
        # Perform reranking
        result = core_reranker.rerank(query, test_results, top_k=4)
        
        # Verify result structure
        assert isinstance(result, RerankResult)
        assert result.used_fallback is False, f"Should not use fallback: {result.fallback_reason}"
        assert result.reranker_type == "llm"
        assert len(result.results) > 0
        
        print(f"\n🎯 Reranked Results:")
        for i, r in enumerate(result.results):
            orig_score = r.metadata.get("original_score", "N/A")
            rerank_score = r.metadata.get("rerank_score", r.score)
            print(f"  {i+1}. [rerank={rerank_score:.2f}, orig={orig_score}] {r.chunk_id}")
            print(f"      {r.text[:80]}...")
        
        # Validate: Azure config chunk should be ranked high (top 2)
        # This is the most relevant chunk for the query
        top_2_ids = [r.chunk_id for r in result.results[:2]]
        assert "chunk_azure_config" in top_2_ids, (
            f"'chunk_azure_config' should be in top 2 results. "
            f"Got: {top_2_ids}"
        )
        
        # Validate: Database chunk should be ranked low (bottom 2)
        bottom_2_ids = [r.chunk_id for r in result.results[-2:]]
        assert "chunk_database" in bottom_2_ids, (
            f"'chunk_database' should be in bottom 2 results. "
            f"Got: {bottom_2_ids}"
        )
        
        print(f"\n✅ LLM reranking completed successfully!")
        print(f"   - Most relevant chunk (Azure config) ranked in top 2")
        print(f"   - Least relevant chunk (Database) ranked in bottom 2")
        print("=" * 60)
    
    def test_reranking_preserves_metadata(self, settings, test_results):
        """Test that reranking preserves original metadata."""
        core_reranker = CoreReranker(settings)
        query = "How do I configure Azure?"
        
        result = core_reranker.rerank(query, test_results, top_k=4)
        
        assert result.used_fallback is False
        
        # Check that metadata is preserved
        for r in result.results:
            assert "source_path" in r.metadata
            assert "page" in r.metadata
            assert "original_score" in r.metadata
            assert "rerank_score" in r.metadata
            assert r.metadata["reranked"] is True
        
        print("✅ Metadata preserved correctly after reranking")
    
    def test_reranking_with_top_k_limit(self, settings, test_results):
        """Test that top_k limits the number of results."""
        core_reranker = CoreReranker(settings)
        query = "Azure OpenAI configuration"
        
        result = core_reranker.rerank(query, test_results, top_k=2)
        
        assert len(result.results) == 2
        print(f"✅ Top-k limit (2) applied correctly, got {len(result.results)} results")


class TestCoreRerankerFallbackIntegration:
    """Integration tests for fallback behavior."""
    
    @pytest.fixture
    def settings(self):
        """Load real settings from config file."""
        return load_settings("config/settings.yaml")
    
    @pytest.fixture
    def test_results(self):
        """Create test retrieval results."""
        return create_test_results()
    
    def test_fallback_on_invalid_model(self, settings, test_results):
        """Test graceful fallback when LLM call fails.
        
        We create an LLM reranker with an invalid model name to trigger failure.
        """
        print("\n" + "=" * 60)
        print("FALLBACK TEST WITH INVALID MODEL")
        print("=" * 60)
        
        # Create a mock settings with invalid model to trigger LLM error
        from unittest.mock import MagicMock
        
        mock_settings = MagicMock()
        mock_settings.rerank = MagicMock()
        mock_settings.rerank.enabled = True
        mock_settings.rerank.provider = "llm"
        mock_settings.rerank.top_k = 5
        
        # Copy LLM settings but with invalid model
        mock_settings.llm = MagicMock()
        mock_settings.llm.provider = settings.llm.provider
        mock_settings.llm.model = "invalid-model-that-does-not-exist"
        mock_settings.llm.deployment_name = "invalid-deployment"
        mock_settings.llm.azure_endpoint = settings.llm.azure_endpoint
        mock_settings.llm.api_version = settings.llm.api_version
        mock_settings.llm.api_key = settings.llm.api_key
        mock_settings.llm.temperature = 0.0
        mock_settings.llm.max_tokens = 1000
        
        # Create core reranker - should create LLM reranker
        core_reranker = CoreReranker(mock_settings)
        
        query = "Azure configuration"
        
        print(f"📝 Query: {query}")
        print(f"🔧 Using invalid model to trigger fallback...")
        
        # Rerank should fallback gracefully
        result = core_reranker.rerank(query, test_results, top_k=4)
        
        assert result.used_fallback is True, "Should use fallback for invalid model"
        assert result.fallback_reason is not None
        assert len(result.results) == 4
        
        # Verify original order is preserved in fallback
        assert result.results[0].chunk_id == "chunk_python"  # Original first
        
        # Verify fallback markers
        for r in result.results:
            assert r.metadata.get("reranked") is False
            assert r.metadata.get("rerank_fallback") is True
        
        print(f"✅ Fallback triggered successfully!")
        print(f"   Reason: {result.fallback_reason[:100]}...")
        print(f"   Original order preserved")
        print("=" * 60)


class TestEndToEndReranking:
    """End-to-end test demonstrating full reranking flow."""
    
    @pytest.fixture
    def settings(self):
        """Load real settings from config file."""
        return load_settings("config/settings.yaml")
    
    def test_end_to_end_reranking_flow(self, settings):
        """Complete end-to-end test of the reranking flow.
        
        This test simulates a real retrieval + reranking scenario:
        1. Start with retrieval results (simulated)
        2. Apply LLM reranking
        3. Validate improved ranking quality
        """
        print("\n" + "=" * 60)
        print("END-TO-END RERANKING FLOW")
        print("=" * 60)
        
        # Simulated retrieval results (would come from HybridSearch in production)
        retrieval_results = [
            RetrievalResult(
                chunk_id="result_1",
                score=0.92,
                text="Vector databases like Chroma and Qdrant store high-dimensional "
                     "embeddings for similarity search. They enable semantic retrieval "
                     "by comparing query embeddings with stored document embeddings.",
                metadata={"source_path": "docs/vectordb.pdf", "page": 1},
            ),
            RetrievalResult(
                chunk_id="result_2",
                score=0.88,
                text="Embedding models convert text into dense vectors. Popular choices "
                     "include OpenAI's text-embedding-ada-002 and sentence-transformers. "
                     "The vector dimension typically ranges from 384 to 1536.",
                metadata={"source_path": "docs/embeddings.pdf", "page": 5},
            ),
            RetrievalResult(
                chunk_id="result_3",
                score=0.85,
                text="Chunking strategies affect retrieval quality. Recursive character "
                     "splitting with overlap (e.g., 1000 chars, 200 overlap) maintains "
                     "context across chunk boundaries. Semantic chunking is an alternative.",
                metadata={"source_path": "docs/chunking.pdf", "page": 3},
            ),
        ]
        
        query = "What embedding dimensions does text-embedding-ada-002 use?"
        
        print(f"\n📝 Query: {query}")
        print(f"\n📊 Initial Retrieval Results:")
        for i, r in enumerate(retrieval_results):
            print(f"  {i+1}. [{r.score:.2f}] {r.chunk_id}: {r.text[:50]}...")
        
        # Create reranker and perform reranking
        core_reranker = CoreReranker(settings)
        result = core_reranker.rerank(query, retrieval_results, top_k=3)
        
        print(f"\n🎯 After LLM Reranking:")
        for i, r in enumerate(result.results):
            rerank_score = r.metadata.get("rerank_score", r.score)
            print(f"  {i+1}. [rerank={rerank_score:.1f}] {r.chunk_id}: {r.text[:50]}...")
        
        # The embedding chunk (result_2) should be ranked #1 as it directly
        # answers the question about text-embedding-ada-002 dimensions
        assert result.results[0].chunk_id == "result_2", (
            f"Embedding chunk should be ranked first. "
            f"Got: {result.results[0].chunk_id}"
        )
        
        print(f"\n✅ End-to-end reranking successful!")
        print(f"   - Most relevant chunk (embeddings) correctly ranked first")
        print(f"   - Reranker type: {result.reranker_type}")
        print(f"   - Fallback used: {result.used_fallback}")
        print("=" * 60)


# =============================================================================
# Run tests directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
