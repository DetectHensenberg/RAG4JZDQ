"""Unit tests for ResponseBuilder and CitationGenerator.

This module tests the response building components used by MCP tools
to generate formatted output with citations.
"""

import pytest
from typing import Dict, Any, List

from src.core.response.citation_generator import Citation, CitationGenerator
from src.core.response.response_builder import ResponseBuilder, MCPToolResponse
from src.core.types import RetrievalResult


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_retrieval_results() -> List[RetrievalResult]:
    """Create sample retrieval results for testing."""
    return [
        RetrievalResult(
            chunk_id="doc1_chunk_001",
            score=0.95,
            text="Azure OpenAI 是微软提供的人工智能服务，提供 GPT-4 和 DALL-E 等模型的访问能力。它与 Azure 云服务深度集成，支持企业级安全和合规性需求。",
            metadata={
                "source_path": "docs/azure-guide.pdf",
                "page": 5,
                "chunk_index": 0,
                "title": "Azure OpenAI 简介",
                "doc_type": "pdf",
            },
        ),
        RetrievalResult(
            chunk_id="doc1_chunk_002",
            score=0.87,
            text="配置 Azure OpenAI 需要以下步骤：1. 创建 Azure 订阅；2. 在 Azure Portal 创建 OpenAI 资源；3. 获取 API 密钥和端点地址。",
            metadata={
                "source_path": "docs/azure-guide.pdf",
                "page": 10,
                "chunk_index": 5,
                "title": "配置步骤",
            },
        ),
        RetrievalResult(
            chunk_id="doc2_chunk_003",
            score=0.72,
            text="GPT-4 模型支持多轮对话、代码生成、文本分析等多种任务。在 Azure 平台上，您可以通过 REST API 或 SDK 进行调用。",
            metadata={
                "source_path": "docs/gpt4-usage.md",
                "chunk_index": 2,
                "title": "GPT-4 使用指南",
            },
        ),
    ]


@pytest.fixture
def empty_retrieval_results() -> List[RetrievalResult]:
    """Empty results list."""
    return []


@pytest.fixture
def citation_generator() -> CitationGenerator:
    """Create CitationGenerator instance."""
    return CitationGenerator()


@pytest.fixture
def response_builder() -> ResponseBuilder:
    """Create ResponseBuilder instance."""
    return ResponseBuilder()


# =============================================================================
# CitationGenerator Tests
# =============================================================================

class TestCitationGenerator:
    """Tests for CitationGenerator class."""
    
    def test_generate_citations_basic(
        self,
        citation_generator: CitationGenerator,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test basic citation generation."""
        citations = citation_generator.generate(sample_retrieval_results)
        
        assert len(citations) == 3
        
        # Check first citation
        assert citations[0].index == 1
        assert citations[0].chunk_id == "doc1_chunk_001"
        assert citations[0].source == "docs/azure-guide.pdf"
        assert citations[0].score == 0.95
        assert citations[0].page == 5
        
        # Check indexing is 1-based
        assert citations[1].index == 2
        assert citations[2].index == 3
    
    def test_generate_citations_empty_results(
        self,
        citation_generator: CitationGenerator,
        empty_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test citation generation with empty results."""
        citations = citation_generator.generate(empty_retrieval_results)
        assert citations == []
    
    def test_citation_to_dict(
        self,
        citation_generator: CitationGenerator,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test Citation.to_dict() serialization."""
        citations = citation_generator.generate(sample_retrieval_results)
        
        citation_dict = citations[0].to_dict()
        
        assert citation_dict["index"] == 1
        assert citation_dict["chunk_id"] == "doc1_chunk_001"
        assert citation_dict["source"] == "docs/azure-guide.pdf"
        assert citation_dict["score"] == 0.95
        assert citation_dict["page"] == 5
        assert "text_snippet" in citation_dict
    
    def test_text_snippet_truncation(self) -> None:
        """Test that long text is truncated in snippets."""
        generator = CitationGenerator(snippet_max_length=50)
        
        result = RetrievalResult(
            chunk_id="test_001",
            score=0.9,
            text="这是一段非常长的文本，用于测试文本截断功能是否正常工作。" * 10,
            metadata={"source_path": "test.pdf"},
        )
        
        citations = generator.generate([result])
        
        # Snippet should be truncated
        assert len(citations[0].text_snippet) <= 60  # 50 + "..."
        assert citations[0].text_snippet.endswith("...")
    
    def test_metadata_extraction(
        self,
        citation_generator: CitationGenerator,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test that metadata fields are correctly extracted."""
        citations = citation_generator.generate(sample_retrieval_results)
        
        # First citation should have title in metadata
        assert "title" in citations[0].metadata
        assert citations[0].metadata["title"] == "Azure OpenAI 简介"
        
        # Check chunk_index is included
        assert "chunk_index" in citations[0].metadata
        assert citations[0].metadata["chunk_index"] == 0
    
    def test_page_number_extraction(self) -> None:
        """Test page number extraction from different metadata formats."""
        generator = CitationGenerator()
        
        # Test with 'page' key
        result1 = RetrievalResult(
            chunk_id="test_001",
            score=0.9,
            text="Test content",
            metadata={"source_path": "test.pdf", "page": 5},
        )
        
        # Test with 'page_num' key
        result2 = RetrievalResult(
            chunk_id="test_002",
            score=0.8,
            text="Test content",
            metadata={"source_path": "test.pdf", "page_num": 10},
        )
        
        # Test without page info
        result3 = RetrievalResult(
            chunk_id="test_003",
            score=0.7,
            text="Test content",
            metadata={"source_path": "test.md"},
        )
        
        citations = generator.generate([result1, result2, result3])
        
        assert citations[0].page == 5
        assert citations[1].page == 10
        assert citations[2].page is None
    
    def test_format_citation_marker(
        self,
        citation_generator: CitationGenerator,
    ) -> None:
        """Test citation marker formatting."""
        assert citation_generator.format_citation_marker(1) == "[1]"
        assert citation_generator.format_citation_marker(10) == "[10]"
        assert citation_generator.format_citation_marker(99) == "[99]"


# =============================================================================
# ResponseBuilder Tests
# =============================================================================

class TestResponseBuilder:
    """Tests for ResponseBuilder class."""
    
    def test_build_basic_response(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test basic response building."""
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure OpenAI 配置",
            collection="docs",
        )
        
        assert isinstance(response, MCPToolResponse)
        assert response.is_empty is False
        assert len(response.citations) == 3
        assert response.metadata["query"] == "Azure OpenAI 配置"
        assert response.metadata["collection"] == "docs"
        assert response.metadata["result_count"] == 3
    
    def test_build_empty_response(
        self,
        response_builder: ResponseBuilder,
        empty_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test response building with empty results."""
        response = response_builder.build(
            results=empty_retrieval_results,
            query="不存在的查询",
            collection="docs",
        )
        
        assert response.is_empty is True
        assert len(response.citations) == 0
        assert "未找到相关结果" in response.content
        assert "建议" in response.content
    
    def test_content_contains_citation_markers(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test that content contains citation markers."""
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure 配置",
        )
        
        # Should contain citation markers
        assert "[1]" in response.content
        assert "[2]" in response.content
        assert "[3]" in response.content
    
    def test_content_contains_source_info(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test that content contains source information."""
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure",
        )
        
        # Should contain source paths
        assert "azure-guide.pdf" in response.content
        assert "gpt4-usage.md" in response.content
    
    def test_content_contains_scores(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test that content contains relevance scores."""
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure",
        )
        
        # Should contain score indicators
        assert "相关度" in response.content or "95%" in response.content
    
    def test_response_to_dict(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test MCPToolResponse.to_dict() serialization."""
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure",
        )
        
        response_dict = response.to_dict()
        
        assert "content" in response_dict
        assert "structuredContent" in response_dict
        assert "citations" in response_dict["structuredContent"]
        assert len(response_dict["structuredContent"]["citations"]) == 3
    
    def test_response_to_mcp_content(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test MCPToolResponse.to_mcp_content() for MCP protocol."""
        from mcp import types
        
        response = response_builder.build(
            results=sample_retrieval_results,
            query="Azure",
        )
        
        content_blocks = response.to_mcp_content()
        
        assert len(content_blocks) >= 1
        # Now returns TextContent objects instead of dicts
        assert isinstance(content_blocks[0], types.TextContent)
        assert content_blocks[0].type == "text"
        assert "检索结果" in content_blocks[0].text
    
    def test_max_results_in_content(self) -> None:
        """Test that max_results_in_content is respected."""
        builder = ResponseBuilder(max_results_in_content=2)
        
        results = [
            RetrievalResult(
                chunk_id=f"chunk_{i}",
                score=0.9 - i * 0.1,
                text=f"Content {i}",
                metadata={"source_path": f"doc{i}.pdf"},
            )
            for i in range(5)
        ]
        
        response = builder.build(results=results, query="test")
        
        # Content should mention that more results exist
        assert "还有" in response.content or "未显示" in response.content
        
        # But all citations should still be included
        assert len(response.citations) == 5
    
    def test_collection_in_metadata(
        self,
        response_builder: ResponseBuilder,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test that collection is included in metadata when provided."""
        # With collection
        response1 = response_builder.build(
            results=sample_retrieval_results,
            query="test",
            collection="my_collection",
        )
        assert response1.metadata["collection"] == "my_collection"
        
        # Without collection
        response2 = response_builder.build(
            results=sample_retrieval_results,
            query="test",
        )
        assert "collection" not in response2.metadata
    
    def test_empty_response_with_collection(
        self,
        response_builder: ResponseBuilder,
    ) -> None:
        """Test empty response mentions collection name."""
        response = response_builder.build(
            results=[],
            query="test",
            collection="my_docs",
        )
        
        assert "my_docs" in response.content


# =============================================================================
# Citation Dataclass Tests
# =============================================================================

class TestCitationDataclass:
    """Tests for Citation dataclass."""
    
    def test_citation_creation(self) -> None:
        """Test Citation object creation."""
        citation = Citation(
            index=1,
            chunk_id="test_001",
            source="test.pdf",
            score=0.95,
            text_snippet="Test content...",
            page=5,
            metadata={"title": "Test"},
        )
        
        assert citation.index == 1
        assert citation.chunk_id == "test_001"
        assert citation.source == "test.pdf"
        assert citation.score == 0.95
        assert citation.page == 5
    
    def test_citation_to_dict_without_page(self) -> None:
        """Test Citation.to_dict() when page is None."""
        citation = Citation(
            index=1,
            chunk_id="test_001",
            source="test.md",
            score=0.8,
            text_snippet="Test",
        )
        
        citation_dict = citation.to_dict()
        
        assert "page" not in citation_dict
    
    def test_citation_score_rounding(self) -> None:
        """Test that scores are rounded in to_dict()."""
        citation = Citation(
            index=1,
            chunk_id="test_001",
            source="test.pdf",
            score=0.123456789,
            text_snippet="Test",
        )
        
        citation_dict = citation.to_dict()
        
        # Score should be rounded to 4 decimal places
        assert citation_dict["score"] == 0.1235


# =============================================================================
# MCPToolResponse Dataclass Tests
# =============================================================================

class TestMCPToolResponseDataclass:
    """Tests for MCPToolResponse dataclass."""
    
    def test_response_creation(self) -> None:
        """Test MCPToolResponse object creation."""
        response = MCPToolResponse(
            content="Test content",
            citations=[],
            metadata={"query": "test"},
            is_empty=False,
        )
        
        assert response.content == "Test content"
        assert response.citations == []
        assert response.metadata["query"] == "test"
        assert response.is_empty is False
    
    def test_response_default_values(self) -> None:
        """Test MCPToolResponse default values."""
        response = MCPToolResponse(content="Test")
        
        assert response.citations == []
        assert response.metadata == {}
        assert response.is_empty is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestResponseBuilderIntegration:
    """Integration tests for ResponseBuilder with CitationGenerator."""
    
    def test_full_response_generation_flow(
        self,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test complete response generation flow."""
        builder = ResponseBuilder()
        
        response = builder.build(
            results=sample_retrieval_results,
            query="如何配置 Azure OpenAI？",
            collection="technical_docs",
        )
        
        # Verify response structure
        assert isinstance(response, MCPToolResponse)
        assert not response.is_empty
        
        # Verify content
        assert "检索结果" in response.content
        assert "Azure" in response.content
        
        # Verify citations
        assert len(response.citations) == 3
        assert all(isinstance(c, Citation) for c in response.citations)
        
        # Verify metadata
        assert response.metadata["query"] == "如何配置 Azure OpenAI？"
        assert response.metadata["collection"] == "technical_docs"
        assert response.metadata["result_count"] == 3
        
        # Verify serialization
        response_dict = response.to_dict()
        assert "content" in response_dict
        assert "structuredContent" in response_dict
    
    def test_custom_citation_generator(
        self,
        sample_retrieval_results: List[RetrievalResult],
    ) -> None:
        """Test ResponseBuilder with custom CitationGenerator."""
        custom_generator = CitationGenerator(
            snippet_max_length=50,
            include_metadata_fields=["title"],
        )
        
        builder = ResponseBuilder(citation_generator=custom_generator)
        response = builder.build(
            results=sample_retrieval_results,
            query="test",
        )
        
        # Snippets should be shorter
        for citation in response.citations:
            assert len(citation.text_snippet) <= 60  # 50 + "..."
        
        # Only 'title' should be in metadata
        for citation in response.citations:
            if citation.metadata:
                assert "chunk_index" not in citation.metadata
