# ALIGNMENT - Tantivy 稀疏检索 + Redis 异步摄取

> 日期：2026-03-23
> 适用范围：RAG 系统 A7（Tantivy 稀疏检索替代）+ A8（Redis 异步摄取队列）
> 6A 阶段：Align（对齐）

---

## 1. 原始需求

在 `SOLUTION_剩余工作收敛方案` 中定义的主线最后两项：
- **A7**: Tantivy 稀疏检索替代评估（现有 Python BM25 → Rust Tantivy）
- **A8**: Redis 队列化摄取评估（同步内存摄取 → 异步持久队列）

## 2. 现有项目理解

### 2.1 稀疏检索现状
| 组件 | 文件 | 职责 |
|------|------|------|
| `BaseSparseRetriever` | `src/core/query_engine/base_sparse_retriever.py` | Protocol 接口，定义 `retrieve()` 契约 |
| `SparseRetriever` | `src/core/query_engine/sparse_retriever.py` | 实现类，依赖注入 `bm25_indexer` |
| `BM25Indexer` | `src/ingestion/storage/bm25_indexer.py` | 601行，Pickle 序列化，内存全量加载 |
| `SparseEncoder` | `src/ingestion/embedding/sparse_encoder.py` | 分词 + TF 统计，输出 `term_stats` |

**关键接口**：`BM25Indexer` 提供 `build()` / `load()` / `query()` / `add_documents()` / `remove_document()` 五个方法。`SparseRetriever.retrieve()` 内部调用 `bm25_indexer.query()` + `vector_store.get_by_ids()`。

### 2.2 摄取流水线现状
| 组件 | 文件 | 职责 |
|------|------|------|
| `IngestionPipeline` | `src/ingestion/pipeline.py` | 770行，6 阶段同步流水线 |
| `DocumentManager` | `src/ingestion/document_manager.py` | 文档增删改管理 |

**调用入口**：`IngestionPipeline.run()` 是 `async` 方法，但内部的密集计算（Embedding、PDF 解析）仍在当前进程中执行，无队列化能力。

### 2.3 无 Redis 依赖
项目中目前无任何 Redis 引用代码，需全新集成。

## 3. 边界确认

### 做什么
- **A7**: 实现 `TantivyIndexer`，与 `BM25Indexer` 提供相同接口，通过配置切换。
- **A8**: 引入 Redis 队列，`IngestionPipeline` 仅负责入队，Worker 独立消费并处理文件。

### 不做什么
- 不修改 `BaseSparseRetriever` 协议接口
- 不替换 `DenseRetriever` 或向量存储
- 不引入 Kubernetes/Docker 编排
- 不修改前端 Dashboard 代码

## 4. 技术约束
- Windows 开发环境（`tantivy-py` wheels 需兼容 Windows）
- Python 3.13
- 已有 `asyncio` 异步框架，Redis 客户端使用 `redis[hiredis]` 异步模式
- 配置通过 `settings.yaml` 统一管理

## 5. 疑问澄清（已自行决策）
| # | 疑问 | 决策 |
|---|------|------|
| 1 | Tantivy 与 BM25 是否共存？ | **是**，通过 `settings.yaml` 的 `sparse_provider` 字段切换 |
| 2 | Redis 使用哪个客户端库？ | `redis[hiredis]`，使用 Redis Streams 而非 RQ |
| 3 | Worker 是否独立进程？ | **是**，通过 `python -m src.ingestion.worker` 启动 |
| 4 | 索引格式迁移？ | 提供 `migrate_bm25_to_tantivy.py` 一次性迁移脚本 |
