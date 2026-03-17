# CONSENSUS: 检索增强优化

> 6A 工作流 - Phase 1: Align（对齐阶段）- 最终共识
> 创建时间：2026-03-17

---

## 1. 需求描述

### 1.1 核心目标

实现两项检索增强优化，提升 RAG 系统的检索质量：

1. **BGE-M3 混合检索**：用 FlagEmbedding 库的 BGE-M3 模型替代/补充现有 embedding，一次推理同时输出 Dense + Learned Sparse 向量
2. **Contextual Retrieval**：在 chunk 嵌入前注入文档上下文前缀，解决独立 chunk 语义漂移问题

### 1.2 预期收益

| 优化项 | 预期收益 |
|--------|---------|
| BGE-M3 Learned Sparse | 替代 jieba+BM25 词频统计，语义理解更强 |
| Dense + Sparse 同源 | 同一模型产出，RRF 融合更有效 |
| Contextual Retrieval | 论文数据：检索准确率提升 49% |

---

## 2. 技术方案

### 2.1 BGE-M3 Embedding Provider

**决策**：方案 A - 并行运行，BGE-M3 作为独立 provider

```yaml
# config/settings.yaml
embedding:
  provider: "bge-m3"  # 或保持 "openai"
  bge_m3:
    model: "BAAI/bge-m3"
    use_fp16: true
    device: "auto"  # auto/cpu/cuda
```

**实现要点**：
- 新建 `src/libs/embedding/bge_m3_embedding.py`
- 继承 `BaseEmbedding`，实现 `embed()` 返回 dense
- 新增 `embed_with_sparse()` 方法同时返回 dense + sparse
- 注册到 `EmbeddingFactory`

**Sparse 处理**：
- BGE-M3 sparse 输出 `{token_id: weight}`
- 存储到独立的 sparse index（不修改现有 BM25）
- HybridSearch 支持三路融合：Dense + BM25 + BGE-M3 Sparse

### 2.2 Contextual Retrieval

**决策**：规则式实现（零成本先上线）

```python
# 前缀格式
prefix = f"[文档: {filename}] "  # 从 source_path 提取文件名
embedding_text = prefix + chunk.text
```

**实现要点**：
- 新建 `src/ingestion/transform/context_enricher.py`
- 继承 `BaseTransform`
- 在 `chunk.metadata["embedding_text"]` 存储带前缀的文本
- `DenseEncoder` 优先使用 `embedding_text`，fallback 到 `text`

---

## 3. 技术约束

| 约束 | 说明 |
|------|------|
| 向后兼容 | 现有 `openai` provider 必须继续工作 |
| 配置驱动 | 通过 `settings.yaml` 切换，无需改代码 |
| 依赖管理 | `FlagEmbedding` 添加到 `pyproject.toml` |
| 测试覆盖 | 新代码必须有单元测试 |
| 代码风格 | 遵循 ruff/mypy 配置 |

---

## 4. 集成方案

### 4.1 Pipeline 集成

```
Document → Chunker → [ContextEnricher] → ChunkRefiner → MetadataEnricher → ImageCaptioner
                                ↓
                    chunk.metadata["embedding_text"] = prefix + text
                                ↓
                         DenseEncoder.encode()
                                ↓
                    使用 embedding_text 计算向量
```

### 4.2 检索集成

```
Query → QueryProcessor → HybridSearch
                              ↓
            ┌─────────────────┼─────────────────┐
            ↓                 ↓                 ↓
      Dense Search      BM25 Search      BGE-M3 Sparse
            ↓                 ↓                 ↓
            └─────────────────┼─────────────────┘
                              ↓
                         RRF Fusion
                              ↓
                          Reranker
```

---

## 5. 验收标准

### 5.1 功能验收

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | BGE-M3 Provider 可用 | `EmbeddingFactory.create(settings)` 返回 BGE-M3 实例 |
| 2 | Dense 向量正确 | 维度 1024，与 OpenAI 兼容存储 |
| 3 | Sparse 向量可用 | `embed_with_sparse()` 返回 dict |
| 4 | ContextEnricher 工作 | chunk.metadata 包含 embedding_text |
| 5 | Pipeline 集成 | 入库流程正常完成 |
| 6 | 配置切换 | 修改 yaml 即可切换 provider |

### 5.2 测试验收

| # | 测试文件 | 覆盖内容 |
|---|----------|---------|
| 1 | `test_bge_m3_embedding.py` | embed/embed_with_sparse/错误处理 |
| 2 | `test_context_enricher.py` | 前缀注入/元数据/空值处理 |

### 5.3 非功能验收

- [ ] 代码通过 ruff lint
- [ ] 代码通过 mypy 类型检查
- [ ] 所有现有测试仍然通过
- [ ] 文档更新（README 或 settings.yaml 注释）

---

## 6. 任务边界

### 6.1 本次范围（In Scope）

- [x] BGE-M3 Embedding Provider
- [x] Contextual Retrieval Transform（规则式）
- [x] Pipeline 集成
- [x] 配置更新
- [x] 单元测试

### 6.2 范围外（Out of Scope）

- LLM 版 Contextual Retrieval（后续迭代）
- BGE-M3 Sparse 完全替换 BM25（需验证效果后决定）
- heading_path 层级标签（独立任务）
- Query Rewriting / HyDE（独立任务）

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| BGE-M3 模型下载慢 | 首次启动延迟 | 使用 hf-mirror.com 镜像 |
| GPU 不可用 | 推理较慢 | 支持 CPU fallback，添加 device 配置 |
| Sparse 存储格式不兼容 | 无法检索 | 独立存储，不修改现有 BM25 |
| 向量维度不匹配 | ChromaDB 报错 | BGE-M3 默认 1024 维，与现有一致 |

---

**共识确认**：以上方案已确认，进入架构设计阶段。
