"""Integration tests for DenseEncoder with real Azure Embedding.

This test suite validates that DenseEncoder correctly integrates with
the Azure Embedding provider using real API calls. These tests verify:
- Real embedding API connectivity
- Correct vector dimensions
- Batch processing with real provider
- Error handling in production-like scenarios

⚠️ WARNING: These tests make REAL API calls and incur costs.
Run only when validating Azure Embedding configuration.
"""

import pytest
from src.ingestion.embedding.dense_encoder import DenseEncoder
from src.core.types import Chunk
from src.core.settings import load_settings
from src.libs.embedding.embedding_factory import EmbeddingFactory


@pytest.fixture(scope="module")
def settings():
    """Load settings from config file."""
    return load_settings("config/settings.yaml")


@pytest.fixture(scope="module")
def azure_embedding(settings):
    """Create Azure Embedding instance from settings.
    
    This fixture verifies that:
    1. Settings contain valid Azure Embedding configuration
    2. EmbeddingFactory can create Azure provider from settings.yaml
    3. The provider is ready for use
    
    All configuration (endpoint, api_key, model) comes from settings.yaml.
    No hardcoded values or environment variable overrides.
    """
    # Validate Azure configuration is present
    assert settings.embedding.provider == "azure", \
        "Integration test requires Azure embedding provider in settings"
    
    assert settings.embedding.azure_endpoint, \
        "Azure endpoint must be configured in settings.yaml"
    
    assert settings.embedding.api_key, \
        "Azure API key must be configured in settings.yaml"
    
    # Create embedding provider via factory (reads all config from settings)
    embedding = EmbeddingFactory.create(settings)
    
    return embedding


@pytest.fixture
def encoder(azure_embedding):
    """Create DenseEncoder with Azure Embedding provider."""
    return DenseEncoder(azure_embedding, batch_size=10)


# ============================================================================
# Real API Call Tests
# ============================================================================

def test_encode_single_chunk_with_azure(encoder):
    """Test encoding a single chunk with real Azure Embedding API.
    
    This test verifies:
    - API connectivity
    - Correct response format
    - Expected vector dimensions (1536 for text-embedding-ada-002)
    """
    chunks = [
        Chunk(
            id="test_1",
            text="This is a test chunk for Azure Embedding integration.",
            metadata={'source_path': 'integration_test'}
        )
    ]
    
    vectors = encoder.encode(chunks)
    
    # Verify output structure
    assert len(vectors) == 1, "Should return exactly 1 vector"
    assert len(vectors[0]) == 1536, \
        "text-embedding-ada-002 should return 1536-dimensional vectors"
    
    # Verify all values are floats
    assert all(isinstance(v, float) for v in vectors[0]), \
        "All vector components should be floats"
    
    # Verify non-zero vector (sanity check)
    assert any(v != 0.0 for v in vectors[0]), \
        "Vector should contain non-zero values"


def test_encode_multiple_chunks_with_azure(encoder):
    """Test encoding multiple chunks in single batch.
    
    This test verifies:
    - Batch processing works with real API
    - All chunks are processed
    - Vectors are semantically distinct
    """
    chunks = [
        Chunk(id="1", text="Artificial intelligence is transforming technology.", metadata={'source_path': 'integration_test'}),
        Chunk(id="2", text="Machine learning enables computers to learn from data.", metadata={'source_path': 'integration_test'}),
        Chunk(id="3", text="Python is a popular programming language.", metadata={'source_path': 'integration_test'}),
    ]
    
    vectors = encoder.encode(chunks)
    
    # Verify correct number of vectors
    assert len(vectors) == 3, "Should return 3 vectors for 3 chunks"
    
    # Verify all vectors have correct dimension
    assert all(len(v) == 1536 for v in vectors), \
        "All vectors should have 1536 dimensions"
    
    # Verify vectors are distinct (semantic difference)
    # Chunks 1 and 2 are related (AI/ML), chunk 3 is different (Python)
    # We don't assert exact similarity values, just that vectors differ
    assert vectors[0] != vectors[1] != vectors[2], \
        "Vectors should be distinct for different texts"


def test_encode_with_batching(azure_embedding):
    """Test encoding with multiple batches using real API.
    
    This test verifies:
    - Multi-batch processing works correctly
    - Batch boundaries don't cause issues
    - All chunks are processed across batches
    """
    encoder = DenseEncoder(azure_embedding, batch_size=2)
    
    chunks = [
        Chunk(id=f"chunk_{i}", text=f"Test chunk number {i} with unique content.", metadata={'source_path': 'integration_test'})
        for i in range(5)
    ]
    
    vectors = encoder.encode(chunks)
    
    # Should process in 3 batches: [0:2], [2:4], [4:5]
    assert len(vectors) == 5, "All 5 chunks should be processed"
    assert all(len(v) == 1536 for v in vectors), "All vectors should have correct dimension"
    
    # Verify batch processing didn't corrupt ordering
    # (We can't verify exact order without knowing vector content,
    #  but we can verify count and dimensions)
    assert encoder.get_batch_count(5) == 3, "Should calculate 3 batches"


def test_encode_realistic_text_lengths(encoder):
    """Test encoding chunks of varying realistic lengths.
    
    This test verifies:
    - Short chunks (titles/headers)
    - Medium chunks (paragraphs)
    - Long chunks (full sections)
    """
    chunks = [
        Chunk(
            id="short",
            text="Introduction",
            metadata={'source_path': 'integration_test'}
        ),
        Chunk(
            id="medium",
            text=(
                "This is a medium-length chunk representing a typical paragraph. "
                "It contains multiple sentences with varying content and structure. "
                "The embedding should capture the semantic meaning effectively."
            ),
            metadata={'source_path': 'integration_test'}
        ),
        Chunk(
            id="long",
            text=(
                "This is a longer chunk that might represent a full section of a document. "
                "It contains multiple paragraphs with different topics and concepts. "
                "The first paragraph introduces the main theme and sets the context. "
                "The second paragraph provides detailed explanations and examples. "
                "The third paragraph summarizes key points and conclusions. "
                "This tests the embedding model's ability to capture meaning from longer texts."
            ),
            metadata={'source_path': 'integration_test'}
        ),
    ]
    
    vectors = encoder.encode(chunks)
    
    assert len(vectors) == 3, "Should process all 3 chunks"
    assert all(len(v) == 1536 for v in vectors), "All vectors should have correct dimension"


def test_encode_special_characters(encoder):
    """Test encoding text with special characters and formatting.
    
    This test verifies:
    - Unicode handling
    - Special characters
    - Code snippets
    - Mathematical symbols
    """
    chunks = [
        Chunk(
            id="unicode",
            text="多语言文本支持：中文、日本語、한국어、العربية",
            metadata={'source_path': 'integration_test'}
        ),
        Chunk(
            id="code",
            text='def hello_world():\n    print("Hello, World!")\n    return True',
            metadata={'source_path': 'integration_test'}
        ),
        Chunk(
            id="math",
            text="Mathematical formula: E = mc² and α + β = γ",
            metadata={'source_path': 'integration_test'}
        ),
    ]
    
    vectors = encoder.encode(chunks)
    
    assert len(vectors) == 3, "Should handle special characters correctly"
    assert all(len(v) == 1536 for v in vectors), "Vector dimensions should be consistent"


# ============================================================================
# Configuration Validation Tests
# ============================================================================

def test_azure_configuration_is_valid(settings):
    """Verify that Azure Embedding configuration in settings.yaml is correct.
    
    This test validates:
    - Provider is set to 'azure'
    - Model name is specified
    - Dimensions match model (1536 for ada-002)
    - Credentials can be provided via env vars
    """
    assert settings.embedding.provider == "azure", \
        "Provider should be 'azure' for integration tests"
    
    assert settings.embedding.model == "text-embedding-ada-002", \
        "Model should be text-embedding-ada-002 for this test suite"
    
    assert settings.embedding.dimensions == 1536, \
        "Dimensions should be 1536 for text-embedding-ada-002"


def test_factory_creates_azure_embedding(settings):
    """Verify that EmbeddingFactory correctly creates Azure provider."""
    embedding = EmbeddingFactory.create(settings)
    
    # Verify it's the correct type (AzureEmbedding)
    assert embedding.__class__.__name__ == "AzureEmbedding", \
        "Factory should create AzureEmbedding instance"


# ============================================================================
# Error Handling Tests (Graceful Degradation)
# ============================================================================

def test_encode_handles_empty_text_gracefully(encoder):
    """Test that empty/invalid chunks are caught before API call.
    
    This prevents wasting API quota on invalid requests.
    """
    chunks = [
        Chunk(id="empty", text="", metadata={'source_path': 'integration_test'})
    ]
    
    with pytest.raises(ValueError, match="has empty or whitespace-only text"):
        encoder.encode(chunks)


def test_encode_validates_before_api_call(encoder):
    """Test that validation happens before making expensive API calls."""
    chunks = [
        Chunk(id="valid", text="Valid chunk", metadata={'source_path': 'integration_test'}),
        Chunk(id="invalid", text="   \n  ", metadata={'source_path': 'integration_test'}),  # Whitespace only
    ]
    
    # Should fail validation before any API call is made
    with pytest.raises(ValueError, match="whitespace-only"):
        encoder.encode(chunks)


# ============================================================================
# Performance and Quality Observations
# ============================================================================

def test_encode_performance_observation(encoder):
    """Observe encoding performance with real API.
    
    This test doesn't assert performance, but logs timing information
    for manual observation and optimization opportunities.
    """
    import time
    
    chunks = [
        Chunk(id=f"perf_{i}", text=f"Performance test chunk {i}", metadata={'source_path': 'integration_test'})
        for i in range(10)
    ]
    
    start_time = time.time()
    vectors = encoder.encode(chunks)
    elapsed = time.time() - start_time
    
    assert len(vectors) == 10
    
    # Log for observation (not assertion)
    print(f"\n⏱️  Encoded 10 chunks in {elapsed:.2f}s ({elapsed/10:.2f}s per chunk)")


def test_semantic_similarity_observation(encoder):
    """Observe semantic similarity of related vs unrelated chunks.
    
    This test computes cosine similarity to validate that the embeddings
    capture semantic relationships correctly.
    """
    import math
    
    chunks = [
        Chunk(id="1", text="Dogs are loyal pets and great companions.", metadata={'source_path': 'integration_test'}),
        Chunk(id="2", text="Cats are independent animals that enjoy solitude.", metadata={'source_path': 'integration_test'}),
        Chunk(id="3", text="Canines make excellent guard animals for homes.", metadata={'source_path': 'integration_test'}),
    ]
    
    vectors = encoder.encode(chunks)
    
    # Helper function to compute cosine similarity
    def cosine_similarity(v1, v2):
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        return dot_product / (magnitude1 * magnitude2)
    
    # Compute similarities
    sim_dogs_cats = cosine_similarity(vectors[0], vectors[1])  # Different: dogs vs cats
    sim_dogs_canines = cosine_similarity(vectors[0], vectors[2])  # Similar: dogs vs canines
    
    # Log observations
    print(f"\n📊 Semantic Similarity:")
    print(f"   Dogs vs Cats: {sim_dogs_cats:.4f}")
    print(f"   Dogs vs Canines: {sim_dogs_canines:.4f}")
    
    # Expectation: Dogs should be more similar to Canines than to Cats
    # (This is a weak assertion - real thresholds depend on the model)
    assert sim_dogs_canines > sim_dogs_cats, \
        "Semantically related chunks should have higher similarity"
