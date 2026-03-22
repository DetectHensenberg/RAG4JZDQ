import pytest
from src.core.query_engine.query_processor import create_query_processor
from src.core.types import ProcessedQuery

@pytest.fixture
def processor():
    return create_query_processor()

def test_intent_detection_sparse(processor):
    # Test case: Version numbers should trigger sparse boost [0.3, 1.7]
    queries = [
        "Upgrade to v3.11.5", # Removed 'How to' to avoid conflict
        "SN-88099 logs",
        "Fix config.json",
        "0xFF"
    ]
    for q in queries:
        result = processor.process(q)
        assert result.intent_weights == [0.3, 1.7], f"Failed for query: {q}, actual: {result.intent_weights}"

def test_intent_detection_dense(processor):
    # Test case: Question starters should trigger dense boost [1.7, 0.3]
    queries = [
        "什么是 RAG 架构？",
        "如何配置开发环境？",
        "请介绍下这个项目", # Matches '介绍下'
        "Hello assistant",
        "Explain vectors"
    ]
    for q in queries:
        result = processor.process(q)
        assert result.intent_weights == [1.7, 0.3], f"Failed for query: {q}, actual: {result.intent_weights}"

def test_intent_detection_neutral(processor):
    # Test case: Regular queries or conflicting ones should be [1.0, 1.0]
    queries = [
        "Normal search query",
        "Python tutorial",
        "How to upgrade to v3.11.5?" # Both match [Dense: How, Sparse: v3.1]
    ]
    for q in queries:
        result = processor.process(q)
        assert result.intent_weights == [1.0, 1.0], f"Failed for query: {q}"

def test_intent_detection_case_insensitivity(processor):
    # Test case: Regex should be case-insensitive
    result = processor.process("WHAT IS THIS?")
    assert result.intent_weights == [1.7, 0.3]
    
    result = processor.process("CONFIG.PY")
    assert result.intent_weights == [0.3, 1.7]
