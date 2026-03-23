# ACCEPTANCE - Tantivy 稀疏检索 + Redis 异步摄取

> 日期：2026-03-23
> 6A 阶段：Assess（评估验收）

---

## Sprint-1: Tantivy 稀疏检索 (A7)

| 任务 | 交付物 | 测试结果 | 状态 |
|------|--------|----------|------|
| T1: Schema 骨架 | `tantivy_indexer.py` | 类可实例化 ✓ | ✅ |
| T2: build + query | 同上 | BM25 查询返回正确排序 ✓ | ✅ |
| T3: add + remove | 同上 (`raw` 分词器修复) | 增量更新/精确删除 ✓ | ✅ |
| T4: Factory 集成 | `sparse_retriever.py` + `settings.py` | `sparse_provider` 切换 ✓ | ✅ |
| T5: 迁移脚本 | `scripts/migrate_bm25_to_tantivy.py` | 可读取 Pickle 重建 ✓ | ✅ |
| T6: 单元测试 | `tests/test_tantivy_indexer.py` | **18/18 passed** | ✅ |

### 关键修复
- `chunk_id` 使用 `raw` 分词器：解决删除操作时默认分词器将 ID 拆分为多个 token 导致误删的问题。

---

## Sprint-2: Redis 异步摄取 (A8)

| 任务 | 交付物 | 测试结果 | 状态 |
|------|--------|----------|------|
| T1: BaseQueue Protocol | `queue/__init__.py` | 接口契约 ✓ | ✅ |
| T2: MemoryQueue | `queue/memory_queue.py` | FIFO/状态追踪 ✓ | ✅ |
| T3: RedisQueue | `queue/redis_queue.py` | Streams API + Protocol ✓ | ✅ |
| T4: IngestionWorker | `worker.py` | Mock Pipeline 闭环 ✓ | ✅ |
| T5: Settings 集成 | `settings.py` (RedisSettings) | YAML 解析 ✓ | ✅ |
| T6: 单元测试 | `tests/test_ingestion_queue.py` | **11/11 passed** | ✅ |

---

## 综合结果

- **A 组主线 8 项任务全部完成** ✅
- 新增依赖：`tantivy==0.25.1`、`redis[hiredis]`
- 新增配置字段：`retrieval.sparse_provider`、`ingestion.queue_backend`、`ingestion.redis`
