# ALIGNMENT: 检索增强优化

> 6A 工作流 - Phase 1: Align（对齐阶段）
> 创建时间：2026-03-17

---

## 1. 项目上下文分析

### 1.1 技术栈

| 层级 | 技术选型 |
|------|---------|
| 语言 | Python 3.10+ |
| 包管理 | pyproject.toml (hatchling) |
| Web 框架 | FastAPI (api/) + Streamlit (Dashboard) |
| 向量数据库 | ChromaDB |
| LLM | DashScope (qwen3.5-plus) OpenAI 兼容 API |
| Embedding | DashScope text-embedding-v3 (1024 维) |
| 分词 | jieba |
| 测试 | pytest |

### 1.2 项目架构

```
src/
├── core/           # 核心类型、设置、查询引擎
│   ├── types.py    # Document, Chunk, RetrievalResult
│   ├── settings.py # 配置加载
│   └── query_engine/
│       ├── hybrid_search.py   # Dense + Sparse + RRF
│       ├── reranker.py        # CoreReranker
│       └── query_processor.py # jieba 分词 + 停用词
├── ingestion/      # 入库流程
│   ├── pipeline.py           # 主 Pipeline
│   ├── chunking/
│   │   └── document_chunker.py
│   ├── embedding/
│   │   ├── dense_encoder.py  # 调用 libs.embedding
│   │   └── sparse_encoder.py # jieba 分词 + Counter
│   ├── transform/
│   │   ├── base_transform.py
│   │   ├── chunk_refiner.py
│   │   ├── metadata_enricher.py
│   │   └── image_captioner.py
│   └── storage/
│       ├── bm25_indexer.py   # JSON 倒排索引
│       └── vector_upserter.py
├── libs/           # 可插拔工具层
│   ├── embedding/
│   │   ├── base_embedding.py
│   │   ├── embedding_factory.py  # 注册 openai/azure/ollama
│   │   └── openai_embedding.py
│   ├── reranker/
│   │   ├── base_reranker.py
│   │   ├── reranker_factory.py
│   │   └── cross_encoder_reranker.py  # BGE-Reranker
│   └── splitter/
└── mcp_server/     # MCP 协议服务
```

### 1.3 现有代码模式

**Factory Pattern**：
- `EmbeddingFactory.create(settings)` → 根据 `settings.embedding.provider` 实例化
- `RerankerFactory.create(settings)` → 根据 `settings.rerank.provider` 实例化
- 新 Provider 通过 `register_provider()` 注册

**Transform Pipeline**：
- 所有 Transform 继承 `BaseTransform`
- 实现 `transform(chunks, trace) -> chunks`
- Pipeline 按顺序调用：ChunkRefiner → MetadataEnricher → ImageCaptioner

**配置驱动**：
- 所有配置在 `config/settings.yaml`
- 通过 `Settings` dataclass 加载
- 敏感信息从 `.env` 读取

---

## 2. 原始需求

基于 `docs/RAG优化/整改方案：离线解析与知识库构建优化.md` 中的优化项：

| # | 优化项 | 描述 | 优先级 |
|---|--------|------|--------|
| **#13** | **BGE-M3 混合检索** | 用 FlagEmbedding 替换手写 jieba+BM25，一次推理同时输出 Dense + Learned Sparse | P1 ⭐ |
| **#14** | **Contextual Retrieval** | chunk 嵌入前注入文档上下文，解决独立 chunk 语义漂移 | P1 |
| #6 | 层级标签 heading_path | 在 chunk 中维护章节路径 | P1 |
| #7 | content_type + ingested_at | 增加内容类型和入库时间元数据 | P1 |
| #11 | Query Rewriting / HyDE | 查询改写和假想文档扩展 | P1 |

**本次任务范围**：聚焦 **#13 BGE-M3** 和 **#14 Contextual Retrieval**，其他作为后续迭代。

---

## 3. 边界确认

### 3.1 任务范围（In Scope）

1. **BGE-M3 Embedding Provider**
   - 新建 `src/libs/embedding/bge_m3_embedding.py`
   - 实现 `BaseEmbedding` 接口
   - 同时返回 dense_vector 和 sparse_weights
   - 注册到 `EmbeddingFactory`

2. **Sparse Encoder 适配**
   - 修改 `src/ingestion/embedding/sparse_encoder.py`
   - 支持从 BGE-M3 获取 learned sparse（而非 jieba 分词）

3. **Contextual Retrieval Transform**
   - 新建 `src/ingestion/transform/context_enricher.py`
   - 实现规则式上下文注入（先不用 LLM）
   - 在 chunk 嵌入前添加 `[文档: xxx] [章节: xxx]` 前缀

4. **Pipeline 集成**
   - 修改 `src/ingestion/pipeline.py` 添加 ContextEnricher
   - 修改 `src/ingestion/embedding/dense_encoder.py` 使用 context_prefix

5. **配置更新**
   - `config/settings.yaml` 添加 `embedding.provider: "bge-m3"` 选项
   - 添加 `ingestion.context_enricher` 配置

6. **单元测试**
   - `tests/unit/test_bge_m3_embedding.py`
   - `tests/unit/test_context_enricher.py`

### 3.2 任务范围外（Out of Scope）

- #6 heading_path（依赖 StructureSplitter 改动）
- #7 content_type/ingested_at（简单元数据，可后续添加）
- #11 Query Rewriting / HyDE（查询端优化，独立任务）
- #15 docling PDF 解析升级（可选，独立任务）
- LLM 版 Contextual Retrieval（先上规则式）

---

## 4. 需求理解

### 4.1 BGE-M3 技术理解

**FlagEmbedding 库**：
```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
output = model.encode(texts, return_dense=True, return_sparse=True)

# output["dense_vecs"]       → List[np.ndarray]  (1024 维)
# output["lexical_weights"]  → List[Dict[int, float]]  (token_id → weight)
```

**与现有架构的集成点**：
- `BaseEmbedding.embed()` 只返回 `List[List[float]]`（dense）
- 需要扩展接口或新增方法返回 sparse
- `SparseEncoder` 当前依赖 jieba，需要适配 BGE-M3 输出

### 4.2 Contextual Retrieval 技术理解

**规则式方案**：
```python
def _inject_context(chunk: Chunk, doc: Document) -> str:
    title = doc.metadata.get("title", "")
    source = Path(doc.metadata.get("source_path", "")).stem
    prefix = f"[文档: {source or title}] "
    return prefix + chunk.text
```

**集成点**：
- 在 `DenseEncoder.encode()` 之前调用
- 前缀只参与 embedding 计算，不存储到 chunk.text
- 通过 `chunk.metadata["context_prefix"]` 传递

---

## 5. 疑问澄清

### Q1: BGE-M3 的 sparse 输出格式如何与现有 BM25Indexer 兼容？

**分析**：
- BGE-M3 输出 `{token_id: weight}`，token_id 是模型词表 ID
- 现有 BM25Indexer 期望 `{term: count}`，term 是中文词

**决策**：
- **方案 A**：保留现有 BM25Indexer，BGE-M3 sparse 作为独立检索通道
- **方案 B**：用 BGE-M3 sparse 完全替换 BM25，需要新的 sparse 存储和检索逻辑

**推荐**：方案 A（渐进式），先并行运行，验证效果后再决定是否替换。

### Q2: BGE-M3 模型下载和存储位置？

**决策**：
- 使用 HuggingFace 镜像 `hf-mirror.com`（与 BGE-Reranker 一致）
- 模型缓存到 `~/.cache/huggingface/`（默认）
- 首次加载约 2GB 下载

### Q3: Contextual Retrieval 的前缀是否影响 chunk 存储？

**决策**：
- 前缀**只用于 embedding 计算**，不修改 `chunk.text`
- 通过 `chunk.metadata["embedding_text"]` 或参数传递
- 检索展示时仍显示原始 chunk.text

### Q4: BGE-M3 是否支持 CPU 推理？

**分析**：
- 支持，但较慢（单条约 0.5-1s）
- GPU 推荐（批量 100 条约 2-3s）
- 可配置 `use_fp16=False` 降低显存

**决策**：
- 默认 `use_fp16=True`（有 GPU 时自动使用）
- 添加配置项 `embedding.bge_m3.device: "auto"` 支持手动指定

---

## 6. 技术约束

1. **依赖管理**：需在 `pyproject.toml` 添加 `FlagEmbedding` 依赖
2. **向后兼容**：现有 `openai` provider 必须继续工作
3. **配置驱动**：通过 `settings.yaml` 切换 provider，无需改代码
4. **测试覆盖**：新代码必须有单元测试
5. **代码风格**：遵循现有 ruff/mypy 配置

---

## 7. 待确认问题

> **需要用户确认后继续**

### 🔴 关键决策点

1. **BGE-M3 sparse 与现有 BM25 的关系**
   - [ ] 方案 A：并行运行，BGE-M3 sparse 作为独立检索通道（推荐）
   - [ ] 方案 B：完全替换现有 BM25

2. **Contextual Retrieval 实现方式**
   - [ ] 规则式：`[文档: xxx]` 前缀（零成本，先上线）
   - [ ] LLM 式：用 LLM 生成上下文描述（后续迭代）

3. **BGE-M3 是否作为默认 provider**
   - [ ] 是：新项目默认使用 BGE-M3
   - [ ] 否：保持 OpenAI 为默认，BGE-M3 作为可选

---

**请确认以上决策点，我将继续生成 CONSENSUS 文档。**
