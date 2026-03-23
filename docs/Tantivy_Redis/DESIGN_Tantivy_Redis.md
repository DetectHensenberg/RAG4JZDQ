# DESIGN - Tantivy 稀疏检索 + Redis 异步摄取

> 日期：2026-03-23
> 6A 阶段：Architect（架构设计）

---

## 1. 整体架构图

```mermaid
graph TB
    subgraph 查询链路
        QKH[QueryKnowledgeHubTool]
        HS[HybridSearch]
        SR[SparseRetriever]
        SF[SparseFactory]
        TI["TantivyIndexer (NEW)"]
        BI[BM25Indexer]
        
        QKH --> HS --> SR
        SR --> SF
        SF -->|sparse_provider=tantivy| TI
        SF -->|sparse_provider=bm25| BI
    end

    subgraph 摄取链路
        API[API Upload]
        RQ["RedisQueue (NEW)"]
        MQ["MemoryQueue (Fallback)"]
        WK["Worker Process (NEW)"]
        IP[IngestionPipeline]
        
        API --> RQ
        API --> MQ
        RQ --> WK --> IP
        MQ --> IP
    end

    subgraph 存储层
        TV[Tantivy Index Dir]
        PK[Pickle Files]
        RS[Redis Stream]
        
        TI --> TV
        BI --> PK
        RQ --> RS
    end
```

## 2. A7 - TantivyIndexer 模块设计

### 2.1 核心组件

```mermaid
classDiagram
    class BM25Indexer {
        +build(term_stats, collection)
        +load(collection) bool
        +query(query_terms, top_k) List
        +add_documents(term_stats, collection, doc_id)
        +remove_document(doc_id, collection) bool
    }
    
    class TantivyIndexer {
        +build(term_stats, collection)
        +load(collection) bool
        +query(query_terms, top_k) List
        +add_documents(term_stats, collection, doc_id)
        +remove_document(doc_id, collection) bool
        -_get_or_create_index(collection) tantivy.Index
        -_schema tantivy.Schema
    }
    
    class SparseRetriever {
        +retrieve(keywords, top_k, collection) List~RetrievalResult~
        -bm25_indexer: BM25Indexer | TantivyIndexer
    }
    
    SparseRetriever --> BM25Indexer : 注入 (bm25)
    SparseRetriever --> TantivyIndexer : 注入 (tantivy)
```

### 2.2 Tantivy Schema 设计
```python
schema_builder = tantivy.SchemaBuilder()
schema_builder.add_text_field("chunk_id", stored=True)
schema_builder.add_text_field("content", stored=False)  # 全文索引
schema_builder.add_unsigned_field("doc_length", stored=True)
schema = schema_builder.build()
```

### 2.3 数据流向
```
SparseEncoder.encode(chunks) → term_stats
    ↓
TantivyIndexer.add_documents(term_stats)
    ↓
tantivy.IndexWriter.add_document(chunk_id, content, doc_length)
    ↓
IndexWriter.commit()
    ↓
磁盘目录: data/db/tantivy/{collection}/
```

## 3. A8 - Redis 摄取队列设计

### 3.1 核心组件

```mermaid
classDiagram
    class BaseQueue {
        <<Protocol>>
        +enqueue(task_data) str
        +dequeue() Optional~dict~
        +get_status(task_id) str
        +ack(task_id)
    }
    
    class RedisQueue {
        -redis: redis.asyncio.Redis
        -stream_key: str
        -group_name: str
        +enqueue(task_data) str
        +dequeue() Optional~dict~
        +get_status(task_id) str
        +ack(task_id)
    }
    
    class MemoryQueue {
        -queue: asyncio.Queue
        -status: dict
        +enqueue(task_data) str
        +dequeue() Optional~dict~
        +get_status(task_id) str
        +ack(task_id)
    }
    
    class IngestionWorker {
        -queue: BaseQueue
        -pipeline: IngestionPipeline
        +start()
        +stop()
        -_process_task(task_data)
    }
    
    BaseQueue <|.. RedisQueue
    BaseQueue <|.. MemoryQueue
    IngestionWorker --> BaseQueue
```

### 3.2 Redis Stream 数据结构
```
Stream Key: rag:ingestion:tasks
Consumer Group: rag-workers

Entry Fields:
  task_id: str (UUID)
  file_path: str
  collection: str
  original_filename: str
  created_at: float (timestamp)
  status: pending | processing | done | failed
  retry_count: int
  error: str (optional)
```

### 3.3 异常处理策略
- **超时**: Worker 处理超过 10min 自动 NACK + 重入队
- **失败重试**: 最多 3 次，超过后标记为 `failed`
- **优雅关闭**: Worker 收到 SIGTERM 后完成当前任务再退出

## 4. settings.yaml 扩展

```yaml
retrieval:
  sparse_provider: "tantivy"  # NEW: tantivy | bm25

ingestion:
  queue_backend: "redis"  # NEW: redis | memory
  redis:                  # NEW section
    url: "redis://localhost:6379/0"
    stream_key: "rag:ingestion:tasks"
    consumer_group: "rag-workers"
    max_retries: 3
    task_timeout: 600  # seconds
```

## 5. 依赖关系图

```mermaid
graph LR
    A7[A7: TantivyIndexer] --> A7T1[T1: Schema + 核心类]
    A7T1 --> A7T2[T2: build/query 实现]
    A7T2 --> A7T3[T3: add/remove 增量实现]
    A7T3 --> A7T4[T4: Factory 集成]
    A7T4 --> A7T5[T5: 迁移脚本]
    A7T5 --> A7T6[T6: 单元测试]
    
    A8[A8: Redis Queue] --> A8T1[T1: BaseQueue Protocol]
    A8T1 --> A8T2[T2: MemoryQueue 实现]
    A8T2 --> A8T3[T3: RedisQueue 实现]
    A8T3 --> A8T4[T4: IngestionWorker]
    A8T4 --> A8T5[T5: settings 集成]
    A8T5 --> A8T6[T6: 单元测试]
```
