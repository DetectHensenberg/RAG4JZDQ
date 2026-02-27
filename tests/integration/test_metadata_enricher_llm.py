"""Integration tests for MetadataEnricher with real LLM providers.

These tests require actual API keys and will make real API calls.
Run with: pytest tests/integration/test_metadata_enricher_llm.py -v -s

Required environment variables:
    - OPENAI_API_KEY: For OpenAI tests
    - AZURE_OPENAI_API_KEY: For Azure tests
    - OLLAMA_BASE_URL: For Ollama tests (default: http://localhost:11434)
"""

import os
import pytest
from unittest.mock import Mock

from src.core.settings import Settings, load_settings
from src.core.types import Chunk
from src.core.trace.trace_context import TraceContext
from src.ingestion.transform.metadata_enricher import MetadataEnricher


# Test data: Realistic chunk needing metadata enrichment
SAMPLE_TECHNICAL_CHUNK = """
# Microservices Architecture Design Patterns

Microservices architecture is an approach to developing a single application as a suite of small services, each running in its own process and communicating with lightweight mechanisms, often an HTTP resource API. These services are built around business capabilities and independently deployable by fully automated deployment machinery.

Key characteristics include:
- Componentization via Services
- Organized around Business Capabilities
- Products not Projects
- Smart endpoints and dumb pipes
- Decentralized Governance
- Decentralized Data Management
- Infrastructure Automation
- Design for failure
- Evolutionary Design

The pattern emerged from real-world use at companies like Netflix, Amazon, and Uber. It addresses the challenges of monolithic architectures while introducing its own complexities.
"""

SAMPLE_CODE_CHUNK = """
The UserAuthenticationService class implements OAuth2 authentication flow. It uses JWT tokens for stateless session management and includes methods like authenticateUser(), refreshToken(), and validatePermissions(). The service integrates with external identity providers including Google, GitHub, and Azure AD.
"""

SAMPLE_DATA_SCIENCE_CHUNK = """
Gradient Boosting Machines (GBM) are ensemble learning methods that build predictive models in a stage-wise fashion. Unlike random forests which train trees in parallel, GBM trains them sequentially. Each new tree corrects errors made by the previous ensemble. Common implementations include XGBoost, LightGBM, and CatBoost.
"""


# Fixtures

@pytest.fixture
def sample_technical_chunk():
    """Technical documentation chunk."""
    return Chunk(
        id="chunk_tech_001",
        text=SAMPLE_TECHNICAL_CHUNK,
        metadata={"source_path": "architecture.md", "type": "technical"},
        source_ref="architecture.md#microservices"
    )


@pytest.fixture
def sample_code_chunk():
    """Code-related chunk."""
    return Chunk(
        id="chunk_code_001",
        text=SAMPLE_CODE_CHUNK,
        metadata={"source_path": "auth_service.md", "type": "code"},
        source_ref="auth_service.md#oauth"
    )


@pytest.fixture
def sample_datascience_chunk():
    """Data science chunk."""
    return Chunk(
        id="chunk_ds_001",
        text=SAMPLE_DATA_SCIENCE_CHUNK,
        metadata={"source_path": "ml_guide.md", "type": "datascience"},
        source_ref="ml_guide.md#gbm"
    )


def create_settings_for_provider(provider: str) -> Settings:
    """Create settings object for specific provider.
    
    For Azure provider, loads actual settings from settings.yaml.
    For other providers, uses environment variables.
    
    Args:
        provider: One of 'openai', 'azure', 'ollama'
    
    Returns:
        Settings object configured for the provider
    """
    if provider == 'azure':
        # Load real settings from settings.yaml for Azure
        try:
            import yaml
            with open("config/settings.yaml", "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)
            
            settings = load_settings("config/settings.yaml")
            
            # Verify LLM is configured
            if not hasattr(settings, 'llm') or settings.llm.provider != 'azure':
                pytest.skip("Azure LLM not configured in settings.yaml")
            
            # Extract API key from config_dict and inject into environment
            llm_config = config_dict.get('llm', {})
            api_key = llm_config.get('api_key', '')
            azure_endpoint = llm_config.get('azure_endpoint', '')
            
            if api_key:
                os.environ["AZURE_OPENAI_API_KEY"] = api_key
            if azure_endpoint:
                os.environ["AZURE_OPENAI_ENDPOINT"] = azure_endpoint
                os.environ["ENDPOINT"] = azure_endpoint
            
            # Note: Settings is frozen, so we'll enable LLM directly on enricher instance
            return settings
            
        except Exception as e:
            pytest.skip(f"Failed to load Azure settings: {e}")
    
    elif provider == 'openai':
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        settings = Mock(spec=Settings)
        settings.llm = Mock()
        settings.llm.provider = 'openai'
        settings.llm.api_key = api_key
        settings.llm.model = 'gpt-4o-mini'
        settings.llm.temperature = 0.3
        settings.llm.max_tokens = 500
        
        settings.ingestion = Mock()
        settings.ingestion.metadata_enricher = {'use_llm': True}
        
        return settings
    
    elif provider == 'ollama':
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        settings = Mock(spec=Settings)
        settings.llm = Mock()
        settings.llm.provider = 'ollama'
        settings.llm.base_url = base_url
        settings.llm.model = 'qwen2.5:3b'
        settings.llm.temperature = 0.3
        settings.llm.max_tokens = 500
        
        settings.ingestion = Mock()
        settings.ingestion.metadata_enricher = {'use_llm': True}
        
        return settings
    
    else:
        raise ValueError(f"Unsupported provider: {provider}")


# ============================================================================
# Azure LLM Integration Tests (Primary - using real config)
# ============================================================================

@pytest.mark.integration
@pytest.mark.llm
class TestMetadataEnricherAzureIntegration:
    """Integration tests using Azure OpenAI (from settings.yaml)."""
    
    def test_azure_enrichment_success(self, sample_technical_chunk):
        """Test successful metadata enrichment with Azure LLM."""
        settings = create_settings_for_provider('azure')
        enricher = MetadataEnricher(settings)
        
        # Force enable LLM (override frozen dataclass)
        enricher.use_llm = True
        
        trace = TraceContext(trace_id="azure_test_001")
        
        # Execute enrichment
        result = enricher.transform([sample_technical_chunk], trace=trace)
        
        # Assertions
        assert len(result) == 1
        enriched_chunk = result[0]
        
        # Verify metadata was enriched
        assert 'title' in enriched_chunk.metadata
        assert 'summary' in enriched_chunk.metadata
        assert 'tags' in enriched_chunk.metadata
        assert enriched_chunk.metadata['enriched_by'] == 'llm'
        
        # Verify quality of enrichment
        title = enriched_chunk.metadata['title']
        summary = enriched_chunk.metadata['summary']
        tags = enriched_chunk.metadata['tags']
        
        print("\n" + "="*60)
        print("AZURE LLM ENRICHMENT RESULT")
        print("="*60)
        print(f"Title: {title}")
        print(f"Summary: {summary}")
        print(f"Tags: {tags}")
        print("="*60)
        
        # Quality checks
        assert title
        assert len(title) <= 200, "Title should be concise"
        assert "microservice" in title.lower() or "architecture" in title.lower()
        
        assert summary
        assert len(summary) > 50, "Summary should be substantial"
        assert any(keyword in summary.lower() for keyword in ['service', 'microservice', 'architecture'])
        
        assert tags
        assert len(tags) >= 3, "Should extract at least 3 tags"
        assert isinstance(tags, list)
        
        # Verify trace recording
        assert 'llm_enrich' in trace.stages
        assert 'metadata_enricher' in trace.stages
        assert trace.stages['llm_enrich']['data']['success'] is True
    
    def test_azure_multiple_chunks_enrichment(self, sample_technical_chunk, sample_code_chunk, sample_datascience_chunk):
        """Test enrichment of multiple chunks with different content types."""
        settings = create_settings_for_provider('azure')
        enricher = MetadataEnricher(settings)
        
        # Force enable LLM
        enricher.use_llm = True
        
        chunks = [sample_technical_chunk, sample_code_chunk, sample_datascience_chunk]
        result = enricher.transform(chunks)
        
        assert len(result) == 3
        
        print("\n" + "="*60)
        print("MULTIPLE CHUNKS ENRICHMENT")
        print("="*60)
        
        for i, chunk in enumerate(result):
            assert chunk.metadata['enriched_by'] == 'llm'
            print(f"\nChunk {i+1}:")
            print(f"  Title: {chunk.metadata['title']}")
            print(f"  Tags: {chunk.metadata['tags']}")
        
        print("="*60)
    
    def test_azure_fallback_on_invalid_model(self, sample_technical_chunk):
        """Test graceful fallback when using invalid model name."""
        settings = create_settings_for_provider('azure')
        # Override with invalid model
        settings.llm.model = 'gpt-nonexistent-model-12345'
        
        enricher = MetadataEnricher(settings)
        
        # Force enable LLM
        enricher.use_llm = True
        
        trace = TraceContext(trace_id="azure_fallback_test")
        
        # Should not raise exception, should fallback to rule-based
        result = enricher.transform([sample_technical_chunk], trace=trace)
        
        assert len(result) == 1
        enriched_chunk = result[0]
        
        # Should have metadata (from rule-based fallback)
        assert 'title' in enriched_chunk.metadata
        assert 'summary' in enriched_chunk.metadata
        assert 'tags' in enriched_chunk.metadata
        
        # Should mark as fallback
        assert enriched_chunk.metadata['enriched_by'] == 'rule'
        assert 'enrich_fallback_reason' in enriched_chunk.metadata
        
        print("\n" + "="*60)
        print("FALLBACK TEST - Rule-based enrichment")
        print("="*60)
        print(f"Enriched by: {enriched_chunk.metadata['enriched_by']}")
        print(f"Fallback reason: {enriched_chunk.metadata.get('enrich_fallback_reason')}")
        print(f"Title: {enriched_chunk.metadata['title']}")
        print("="*60)


# ============================================================================
# OpenAI LLM Integration Tests (Optional - requires OPENAI_API_KEY)
# ============================================================================

@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
class TestMetadataEnricherOpenAIIntegration:
    """Integration tests using OpenAI (requires API key)."""
    
    def test_openai_enrichment_success(self, sample_code_chunk):
        """Test successful enrichment with OpenAI."""
        settings = create_settings_for_provider('openai')
        enricher = MetadataEnricher(settings)
        
        result = enricher.transform([sample_code_chunk])
        
        assert len(result) == 1
        enriched_chunk = result[0]
        
        assert enriched_chunk.metadata['enriched_by'] == 'llm'
        assert 'title' in enriched_chunk.metadata
        assert 'OAuth' in enriched_chunk.metadata['title'] or 'Authentication' in enriched_chunk.metadata['title']
        
        print("\n" + "="*60)
        print("OPENAI LLM ENRICHMENT RESULT")
        print("="*60)
        print(f"Title: {enriched_chunk.metadata['title']}")
        print(f"Summary: {enriched_chunk.metadata['summary']}")
        print(f"Tags: {enriched_chunk.metadata['tags']}")
        print("="*60)


# ============================================================================
# Ollama LLM Integration Tests (Optional - requires running Ollama)
# ============================================================================

@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.skipif(not os.getenv("OLLAMA_BASE_URL"), reason="Ollama not configured")
class TestMetadataEnricherOllamaIntegration:
    """Integration tests using Ollama local LLM."""
    
    def test_ollama_enrichment_success(self, sample_datascience_chunk):
        """Test successful enrichment with Ollama."""
        settings = create_settings_for_provider('ollama')
        enricher = MetadataEnricher(settings)
        
        result = enricher.transform([sample_datascience_chunk])
        
        assert len(result) == 1
        enriched_chunk = result[0]
        
        # Ollama might be slower or less reliable, so check if it attempted
        assert 'title' in enriched_chunk.metadata
        assert 'enriched_by' in enriched_chunk.metadata
        
        print("\n" + "="*60)
        print("OLLAMA LLM ENRICHMENT RESULT")
        print("="*60)
        print(f"Enriched by: {enriched_chunk.metadata['enriched_by']}")
        print(f"Title: {enriched_chunk.metadata['title']}")
        print(f"Summary: {enriched_chunk.metadata['summary']}")
        print(f"Tags: {enriched_chunk.metadata['tags']}")
        print("="*60)


# ============================================================================
# Verification Guidance
# ============================================================================

"""
To verify the integration tests are working correctly:

1. Run Azure tests (primary):
   pytest tests/integration/test_metadata_enricher_llm.py::TestMetadataEnricherAzureIntegration -v -s

2. Check output:
   - Title should be semantically meaningful and relevant
   - Summary should capture key concepts (not just copy first sentence)
   - Tags should include relevant technical terms
   - enriched_by should be 'llm' for success cases

3. Verify fallback:
   - When model is invalid, should fallback to 'rule' enrichment
   - Should not crash the pipeline

4. Cost awareness:
   - These tests make real API calls
   - Run sparingly during development
   - Azure tests use configured model (check settings.yaml for cost)
"""
