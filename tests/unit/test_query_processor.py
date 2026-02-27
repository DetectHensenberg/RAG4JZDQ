"""Unit tests for QueryProcessor.

Tests cover:
- Basic keyword extraction
- Chinese and English stopword filtering
- Filter syntax parsing (collection:xxx, type:xxx)
- Edge cases (empty query, special characters)
- Configuration options
"""

import pytest
from src.core.query_engine.query_processor import (
    QueryProcessor,
    QueryProcessorConfig,
    create_query_processor,
    DEFAULT_STOPWORDS,
    CHINESE_STOPWORDS,
    ENGLISH_STOPWORDS,
)
from src.core.types import ProcessedQuery


class TestQueryProcessorBasic:
    """Test basic QueryProcessor functionality."""
    
    def test_simple_english_query(self):
        """Test simple English query keyword extraction."""
        processor = QueryProcessor()
        result = processor.process("Azure OpenAI configuration")
        
        assert result.original_query == "Azure OpenAI configuration"
        assert "Azure" in result.keywords
        assert "OpenAI" in result.keywords
        assert "configuration" in result.keywords
        assert isinstance(result.filters, dict)
    
    def test_simple_chinese_query(self):
        """Test simple Chinese query keyword extraction."""
        processor = QueryProcessor()
        result = processor.process("配置 Azure OpenAI")
        
        assert result.original_query == "配置 Azure OpenAI"
        assert "配置" in result.keywords
        assert "Azure" in result.keywords
        assert "OpenAI" in result.keywords
    
    def test_mixed_language_query(self):
        """Test mixed Chinese-English query."""
        processor = QueryProcessor()
        result = processor.process("如何配置 Azure OpenAI embedding 模型")
        
        # Note: Simple tokenizer treats continuous Chinese as single token
        # So "如何配置" is one token, not split into "如何" + "配置"
        assert "Azure" in result.keywords
        assert "OpenAI" in result.keywords
        assert "embedding" in result.keywords
        assert "模型" in result.keywords
        # Keywords should be non-empty (acceptance criteria)
        assert len(result.keywords) > 0


class TestStopwordFiltering:
    """Test stopword filtering."""
    
    def test_chinese_stopwords_filtered(self):
        """Test that Chinese stopwords are filtered."""
        processor = QueryProcessor()
        # Use space-separated Chinese words for proper tokenization
        result = processor.process("如何 在 配置 系统")
        
        # Individual stopwords should be filtered
        assert "如何" not in result.keywords
        assert "在" not in result.keywords
        # Content words should remain
        assert "配置" in result.keywords
        assert "系统" in result.keywords
    
    def test_english_stopwords_filtered(self):
        """Test that English stopwords are filtered."""
        processor = QueryProcessor()
        result = processor.process("how to configure the Azure API")
        
        # Stopwords should be filtered
        assert "how" not in result.keywords
        assert "to" not in result.keywords
        assert "the" not in result.keywords
        # Content words should remain
        assert "configure" in result.keywords
        assert "Azure" in result.keywords
        assert "API" in result.keywords
    
    def test_custom_stopwords(self):
        """Test custom stopwords configuration."""
        custom_stopwords = {"custom", "word"}
        config = QueryProcessorConfig(stopwords=custom_stopwords)
        processor = QueryProcessor(config)
        
        result = processor.process("custom word test")
        
        assert "custom" not in result.keywords
        assert "word" not in result.keywords
        assert "test" in result.keywords
    
    def test_add_stopwords(self):
        """Test adding stopwords dynamically."""
        processor = QueryProcessor()
        processor.add_stopwords({"newstop"})
        
        result = processor.process("newstop important")
        
        assert "newstop" not in result.keywords
        assert "important" in result.keywords
    
    def test_remove_stopwords(self):
        """Test removing stopwords dynamically."""
        processor = QueryProcessor()
        processor.remove_stopwords({"如何"})
        
        # Use space-separated input for proper tokenization
        result = processor.process("如何 配置")
        
        assert "如何" in result.keywords
        assert "配置" in result.keywords


class TestFilterParsing:
    """Test filter syntax parsing."""
    
    def test_collection_filter(self):
        """Test collection filter parsing."""
        processor = QueryProcessor()
        result = processor.process("collection:api-docs Azure configuration")
        
        assert result.filters.get("collection") == "api-docs"
        assert "Azure" in result.keywords
        assert "configuration" in result.keywords
        # Filter syntax should not appear in keywords
        assert "collection" not in result.keywords
        assert "api-docs" not in result.keywords
    
    def test_collection_short_syntax(self):
        """Test collection short syntax (col:)."""
        processor = QueryProcessor()
        result = processor.process("col:docs Azure")
        
        assert result.filters.get("collection") == "docs"
        assert "Azure" in result.keywords
    
    def test_type_filter(self):
        """Test doc_type filter parsing."""
        processor = QueryProcessor()
        result = processor.process("type:pdf search query")
        
        assert result.filters.get("doc_type") == "pdf"
        assert "search" in result.keywords
        assert "query" in result.keywords
    
    def test_source_filter(self):
        """Test source path filter parsing."""
        processor = QueryProcessor()
        result = processor.process("source:readme.md content")
        
        assert result.filters.get("source_path") == "readme.md"
        assert "content" in result.keywords
    
    def test_tag_filter(self):
        """Test tag filter parsing."""
        processor = QueryProcessor()
        result = processor.process("tag:important,urgent search")
        
        assert "tags" in result.filters
        assert "important" in result.filters["tags"]
        assert "urgent" in result.filters["tags"]
    
    def test_multiple_filters(self):
        """Test multiple filters in one query."""
        processor = QueryProcessor()
        result = processor.process("collection:docs type:pdf Azure configuration")
        
        assert result.filters.get("collection") == "docs"
        assert result.filters.get("doc_type") == "pdf"
        assert "Azure" in result.keywords
        assert "configuration" in result.keywords
    
    def test_generic_filter(self):
        """Test generic filter key:value syntax."""
        processor = QueryProcessor()
        result = processor.process("custom_field:custom_value search")
        
        assert result.filters.get("custom_field") == "custom_value"
        assert "search" in result.keywords
    
    def test_disable_filter_parsing(self):
        """Test disabling filter parsing."""
        config = QueryProcessorConfig(enable_filter_parsing=False)
        processor = QueryProcessor(config)
        
        result = processor.process("collection:docs Azure")
        
        assert len(result.filters) == 0
        # collection:docs should be treated as text
        assert "collection" in result.keywords or "docs" in result.keywords


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_query(self):
        """Test empty query handling."""
        processor = QueryProcessor()
        result = processor.process("")
        
        assert result.original_query == ""
        assert result.keywords == []
        assert result.filters == {}
    
    def test_none_query(self):
        """Test None query handling."""
        processor = QueryProcessor()
        result = processor.process(None)
        
        assert result.original_query == ""
        assert result.keywords == []
        assert result.filters == {}
    
    def test_whitespace_only_query(self):
        """Test whitespace-only query."""
        processor = QueryProcessor()
        result = processor.process("   \t\n  ")
        
        assert result.keywords == []
    
    def test_special_characters(self):
        """Test query with special characters."""
        processor = QueryProcessor()
        result = processor.process("Azure-OpenAI API_key configuration")
        
        # Hyphenated and underscored words should be handled
        assert any("Azure" in kw or "OpenAI" in kw for kw in result.keywords)
        assert any("API" in kw or "key" in kw for kw in result.keywords)
        assert "configuration" in result.keywords
    
    def test_numbers_in_query(self):
        """Test query with numbers."""
        processor = QueryProcessor()
        result = processor.process("GPT4 text-embedding-3-small")
        
        assert "GPT4" in result.keywords
        # Handle hyphenated model names
        assert any("embedding" in kw.lower() for kw in result.keywords)
    
    def test_duplicate_keywords(self):
        """Test duplicate keyword handling."""
        processor = QueryProcessor()
        result = processor.process("Azure Azure azure AZURE")
        
        # Should deduplicate (case-insensitive)
        azure_count = sum(1 for kw in result.keywords if kw.lower() == "azure")
        assert azure_count == 1
    
    def test_very_long_query(self):
        """Test very long query with max_keywords limit."""
        config = QueryProcessorConfig(max_keywords=5)
        processor = QueryProcessor(config)
        
        # Query with many keywords
        query = " ".join([f"keyword{i}" for i in range(20)])
        result = processor.process(query)
        
        assert len(result.keywords) <= 5
    
    def test_min_keyword_length(self):
        """Test minimum keyword length constraint."""
        config = QueryProcessorConfig(min_keyword_length=3)
        processor = QueryProcessor(config)
        
        result = processor.process("a ab abc abcd")
        
        assert "a" not in result.keywords
        assert "ab" not in result.keywords
        assert "abc" in result.keywords
        assert "abcd" in result.keywords


class TestProcessedQueryContract:
    """Test ProcessedQuery data contract."""
    
    def test_processed_query_structure(self):
        """Test ProcessedQuery has expected structure."""
        processor = QueryProcessor()
        result = processor.process("test query")
        
        assert isinstance(result, ProcessedQuery)
        assert hasattr(result, "original_query")
        assert hasattr(result, "keywords")
        assert hasattr(result, "filters")
        assert hasattr(result, "expanded_terms")
    
    def test_processed_query_serialization(self):
        """Test ProcessedQuery can be serialized to dict."""
        processor = QueryProcessor()
        result = processor.process("collection:docs Azure test")
        
        data = result.to_dict()
        
        assert isinstance(data, dict)
        assert data["original_query"] == "collection:docs Azure test"
        assert "Azure" in data["keywords"]
        assert "test" in data["keywords"]
        assert data["filters"]["collection"] == "docs"
    
    def test_processed_query_from_dict(self):
        """Test ProcessedQuery can be created from dict."""
        data = {
            "original_query": "test query",
            "keywords": ["test", "query"],
            "filters": {"collection": "docs"},
            "expanded_terms": []
        }
        
        result = ProcessedQuery.from_dict(data)
        
        assert result.original_query == "test query"
        assert result.keywords == ["test", "query"]
        assert result.filters == {"collection": "docs"}


class TestFactoryFunction:
    """Test create_query_processor factory function."""
    
    def test_default_factory(self):
        """Test factory with default settings."""
        processor = create_query_processor()
        result = processor.process("test Azure")
        
        assert isinstance(processor, QueryProcessor)
        assert "Azure" in result.keywords
    
    def test_factory_with_custom_stopwords(self):
        """Test factory with custom stopwords."""
        processor = create_query_processor(stopwords={"custom"})
        result = processor.process("custom test")
        
        assert "custom" not in result.keywords
        assert "test" in result.keywords
        # Default stopwords should not apply
        assert "how" not in processor.config.stopwords
    
    def test_factory_with_min_length(self):
        """Test factory with custom min_keyword_length."""
        processor = create_query_processor(min_keyword_length=4)
        result = processor.process("a ab abc abcd abcde")
        
        assert "a" not in result.keywords
        assert "abc" not in result.keywords
        assert "abcd" in result.keywords
    
    def test_factory_with_max_keywords(self):
        """Test factory with custom max_keywords."""
        processor = create_query_processor(max_keywords=2)
        result = processor.process("one two three four five")
        
        assert len(result.keywords) <= 2
    
    def test_factory_disable_filters(self):
        """Test factory with filter parsing disabled."""
        processor = create_query_processor(enable_filter_parsing=False)
        result = processor.process("collection:docs test")
        
        assert len(result.filters) == 0


class TestChineseTextProcessing:
    """Test Chinese text processing specifics."""
    
    def test_chinese_only_query(self):
        """Test pure Chinese query."""
        processor = QueryProcessor()
        result = processor.process("向量数据库配置指南")
        
        assert len(result.keywords) > 0
        # Should extract meaningful Chinese words/phrases
        assert any("向量" in kw or "数据库" in kw or "配置" in kw for kw in result.keywords)
    
    def test_chinese_with_punctuation(self):
        """Test Chinese query with punctuation."""
        processor = QueryProcessor()
        # Use space-separated for proper tokenization
        result = processor.process("配置 问题 ？ 帮助 ！")
        
        # Punctuation should not affect extraction, keywords extracted
        assert "配置" in result.keywords
        assert "问题" in result.keywords
        # Keywords should be non-empty
        assert len(result.keywords) > 0


class TestKeywordsNonEmpty:
    """Test that keywords are non-empty for valid queries (acceptance criteria)."""
    
    def test_keywords_non_empty_english(self):
        """Test keywords non-empty for English query."""
        processor = QueryProcessor()
        result = processor.process("configure Azure API")
        
        # Per acceptance criteria: keywords should be non-empty
        assert len(result.keywords) > 0
    
    def test_keywords_non_empty_chinese(self):
        """Test keywords non-empty for Chinese query."""
        processor = QueryProcessor()
        result = processor.process("配置数据库")
        
        assert len(result.keywords) > 0
    
    def test_keywords_non_empty_mixed(self):
        """Test keywords non-empty for mixed query."""
        processor = QueryProcessor()
        result = processor.process("Azure 配置")
        
        assert len(result.keywords) > 0
    
    def test_filters_is_dict(self):
        """Test filters is always a dict (acceptance criteria)."""
        processor = QueryProcessor()
        
        # Without filters
        result1 = processor.process("simple query")
        assert isinstance(result1.filters, dict)
        
        # With filters
        result2 = processor.process("collection:docs query")
        assert isinstance(result2.filters, dict)
