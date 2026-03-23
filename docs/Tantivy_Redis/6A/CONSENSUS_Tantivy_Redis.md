# CONSENSUS - Tantivy 稀疏检索 + Redis 异步摄取

> 日期：2026-03-23
> 6A 阶段：Align → **Consensus（共识）**

---

## 1. 明确需求描述

### A7 - Tantivy 稀疏检索
用 Rust 引擎 `tantivy-py` 替代现有的 Python Pickle BM25 索引，提供：
- 磁盘级索引存储（Mmap），内存占用降低 80%+
- 毫秒级查询延迟
- 原生增量索引更新（无需全量重建）

### A8 - Redis 异步摄取队列
引入 Redis Streams 作为任务队列，将摄取入口（API 上传）与实际处理解耦：
- API 层仅负责文件保存 + 入队
- Worker 进程异步消费任务，执行完整的 Pipeline
- 支持任务持久化、失败重试、进度查询

## 2. 验收标准

### A7 验收标准
- [ ] `TantivyIndexer` 实现 `build()` / `load()` / `query()` / `add_documents()` / `remove_document()` 全部接口
- [ ] `settings.yaml` 新增 `sparse_provider: tantivy | bm25` 配置项
- [ ] 通过单元测试覆盖：构建索引 → 查询 → 增量更新 → 删除
- [ ] 提供 BM25 → Tantivy 一次性索引迁移脚本
- [ ] 查询延迟 ≤ 10ms（1000 文档规模）

### A8 验收标准
- [ ] Redis Stream 生产者（enqueue）/ 消费者（worker）完整实现
- [ ] Worker 进程可独立启动：`python -m src.ingestion.worker`
- [ ] 支持任务状态查询：`pending` / `processing` / `done` / `failed`
- [ ] 失败任务自动重试（最多 3 次）
- [ ] `settings.yaml` 新增 `ingestion.queue_backend: redis | memory` 配置项

## 3. 技术实现方案

### A7 架构
```
SparseRetriever ──→ TantivyIndexer (新) ──→ Tantivy Index (磁盘)
                 └→ BM25Indexer (现有) ──→ Pickle (磁盘) [保留兼容]
```
通过工厂方法 `create_sparse_retriever()` 中根据 `settings.retrieval.sparse_provider` 决定注入哪个 Indexer。

### A8 架构
```
API Upload ──→ Redis Stream (入队) ──→ Worker Process ──→ IngestionPipeline.run()
                     │                        │
                     └── 状态查询 ←────────── 状态更新
```

## 4. 技术约束
- Tantivy: 依赖 `tantivy` PyPI 包（Rust 编译的 Wheel）
- Redis: 依赖 `redis[hiredis]` + 本地或远程 Redis 6.2+ 实例
- 两者均通过 `settings.yaml` 控制开关，不影响现有功能
