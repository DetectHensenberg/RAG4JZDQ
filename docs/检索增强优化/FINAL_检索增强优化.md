# FINAL: 检索增强优化

## 完成状态: ✅ 全部完成

## 实现摘要

本次优化实现了两个核心功能：

### 1. BGE-M3 混合检索支持
- **文件**: `src/libs/embedding/bge_m3_embedding.py`
- **功能**: 支持 Dense + Learned Sparse 双向量输出
- **配置**: 通过 `embedding.provider: "bge-m3"` 启用
- **依赖**: `FlagEmbedding>=1.2.0` (可选依赖)

### 2. Contextual Retrieval (上下文注入)
- **文件**: `src/ingestion/transform/context_enricher.py`
- **功能**: 在 embedding 前注入文档名前缀 `[文档: {filename}]`
- **配置**: `ingestion.context_enricher.enabled: true`
- **成本**: 零 LLM 调用，纯规则实现

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `pyproject.toml` | 修改 | 添加 `FlagEmbedding>=1.2.0` 可选依赖 |
| `src/libs/embedding/bge_m3_embedding.py` | 新增 | BGE-M3 Embedding Provider |
| `src/libs/embedding/embedding_factory.py` | 修改 | 注册 bge-m3 provider |
| `src/core/settings.py` | 修改 | 添加 BGEM3Config, ContextEnricherConfig |
| `src/ingestion/transform/context_enricher.py` | 新增 | ContextEnricher Transform |
| `src/ingestion/embedding/dense_encoder.py` | 修改 | 优先使用 embedding_text |
| `src/ingestion/pipeline.py` | 修改 | 集成 ContextEnricher |
| `config/settings.yaml` | 修改 | 添加配置示例 |
| `tests/unit/test_bge_m3_embedding.py` | 新增 | BGE-M3 单元测试 |
| `tests/unit/test_context_enricher.py` | 新增 | ContextEnricher 单元测试 |

## 测试结果

```
tests/unit/test_bge_m3_embedding.py: 4 passed
tests/unit/test_context_enricher.py: 5 passed
```

## 使用方式

### 启用 BGE-M3 (可选)
```yaml
embedding:
  provider: "bge-m3"
  model: "BAAI/bge-m3"
  dimensions: 1024
  bge_m3:
    model: "BAAI/bge-m3"
    use_fp16: true
    device: "auto"
```

### 启用 Contextual Retrieval (默认开启)
```yaml
ingestion:
  context_enricher:
    enabled: true
```

## 架构决策

1. **BGE-M3 sparse vs BM25**: 并行运行，BGE-M3 sparse 作为独立检索通道
2. **Contextual Retrieval**: 规则注入 `[文档: xxx]` 前缀，零成本
3. **BGE-M3 默认 provider**: 否，保持 OpenAI/DashScope 为默认

## 后续优化建议

1. 实现 BGE-M3 sparse 向量的独立检索通道
2. 添加 LLM-based Contextual Retrieval 作为高级选项
3. 性能基准测试对比不同 embedding 方案
