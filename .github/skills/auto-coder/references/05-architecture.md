## 5. 系统架构与模块设计

### 5.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     MCP Clients (外部调用层)                                  │
│                                                                                             │
│    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐                        │
│    │  GitHub Copilot │    │  Claude Desktop │    │  其他 MCP Agent │                        │
│    └────────┬────────┘    └────────┬────────┘    └────────┬────────┘                        │
│             │                      │                      │                                 │
│             └──────────────────────┼──────────────────────┘                                 │
│                                    │  JSON-RPC 2.0 (Stdio Transport)                       │
└────────────────────────────────────┼────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   MCP Server 层 (接口层)                                     │
│                                                                                             │
│    ┌─────────────────────────────────────────────────────────────────────────────────┐      │
│    │                              MCP Protocol Handler                               │      │
│    │                    (tools/list, tools/call, resources/*)                        │      │
│    └─────────────────────────────────────────────────────────────────────────────────┘      │
│                                           │                                                 │
│    ┌──────────────────────┬───────────────┼───────────────┬──────────────────────┐          │
│    ▼                      ▼               ▼               ▼                      ▼          │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│ │query_knowledge│ │list_collections│ │get_document_ │  │search_by_    │  │  其他扩展    │    │
│ │    _hub      │  │              │  │   summary    │  │  keyword     │  │   工具...    │    │
│ └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Core 层 (核心业务逻辑)                                     │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                            Query Engine (查询引擎)                                   │    │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐    │    │
│  │  │                         Query Processor (查询预处理)                         │    │    │
│  │  │            关键词提取 | 查询扩展 (同义词/别名) | Metadata 解析               │    │    │
│  │  └─────────────────────────────────────────────────────────────────────────────┘    │    │
│  │                                       │                                             │    │
│  │  ┌────────────────────────────────────┼────────────────────────────────────┐        │    │
│  │  │                     Hybrid Search Engine (混合检索引擎)                  │        │    │
│  │  │                                    │                                    │        │    │
│  │  │    ┌───────────────────┐    ┌──────┴──────┐    ┌───────────────────┐    │        │    │
│  │  │    │   Dense Route     │    │   Fusion    │    │   Sparse Route    │    │        │    │
│  │  │    │ (Embedding 语义)  │◄───┤    (RRF)    ├───►│   (BM25 关键词)   │    │        │    │
│  │  │    └───────────────────┘    └─────────────┘    └───────────────────┘    │        │    │
│  │  └─────────────────────────────────────────────────────────────────────────┘        │    │
│  │                                       │                                             │    │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐    │    │
│  │  │                        Reranker (重排序模块) [可选]                          │    │    │
│  │  │          None (关闭) | Cross-Encoder (本地模型) | LLM Rerank               │    │    │
│  │  └─────────────────────────────────────────────────────────────────────────────┘    │    │
│  │                                       │                                             │    │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐    │    │
│  │  │                      Response Builder (响应构建器)                           │    │    │
│  │  │            引用生成 (Citation) | 多模态内容组装 (Text + Image)               │    │    │
│  │  └─────────────────────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                          Trace Collector (追踪收集器)                                │    │
│  │                   trace_id 生成 | 各阶段耗时记录 | JSON Lines 输出                  │    │
│  └─────────────────────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Storage 层 (存储层)                                        │
│                                                                                             │
│    ┌─────────────────────────────────────────────────────────────────────────────────┐      │
│    │                             Vector Store (向量存储)                              │      │
│    │                                                                                 │      │
│    │     ┌─────────────────────────────────────────────────────────────────────┐     │      │
│    │     │                         Chroma DB                                   │     │      │
│    │     │    Dense Vector | Sparse Vector | Chunk Content | Metadata          │     │      │
│    │     └─────────────────────────────────────────────────────────────────────┘     │      │
│    └─────────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                             │
│    ┌──────────────────────────────────┐    ┌──────────────────────────────────┐             │
│    │       BM25 Index (稀疏索引)       │    │       Image Store (图片存储)     │             │
│    │        倒排索引 | IDF 统计        │    │    本地文件系统 | Base64 编码     │             │
│    └──────────────────────────────────┘    └──────────────────────────────────┘             │
│                                                                                             │
│    ┌──────────────────────────────────┐    ┌──────────────────────────────────┐             │
│    │     Trace Logs (追踪日志)         │    │   Processing Cache (处理缓存)    │             │
│    │     JSON Lines 格式文件           │    │   文件哈希 | Chunk 哈希 | 状态   │             │
│    └──────────────────────────────────┘    └──────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Ingestion Pipeline (离线数据摄取)                               │
│                                                                                             │
│    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐   │
│    │   Loader   │───►│  Splitter  │───►│ Transform  │───►│  Embedding │───►│   Upsert   │   │
│    │ (文档解析) │    │  (切分器)  │    │ (增强处理) │    │  (向量化)  │    │  (存储)    │   │
│    └────────────┘    └────────────┘    └────────────┘    └────────────┘    └────────────┘   │
│         │                  │                  │                  │                │         │
│         ▼                  ▼                  ▼                  ▼                ▼         │
│    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐   │
│    │MarkItDown │    │Recursive   │    │LLM重写     │    │Dense:      │    │Chroma      │   │
│    │PDF→MD     │    │Character   │    │Image       │    │OpenAI/BGE  │    │Upsert      │   │
│    │元数据提取 │    │TextSplitter│    │Captioning  │    │Sparse:BM25 │    │幂等写入    │   │
│    └────────────┘    └────────────┘    └────────────┘    └────────────┘    └────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                Libs 层 (可插拔抽象层)                                        │
│                                                                                             │
│    ┌────────────────────────────────────────────────────────────────────────────────┐       │
│    │                            Factory Pattern (工厂模式)                           │       │
│    └────────────────────────────────────────────────────────────────────────────────┘       │
│                                           │                                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│  │ LLM Client │ │ Embedding  │ │  Splitter  │ │VectorStore │ │  Reranker  │ │ Evaluator  │  │
│  │  Factory   │ │  Factory   │ │  Factory   │ │  Factory   │ │  Factory   │ │  Factory   │  │
│  ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤  │
│  │ · Azure    │ │ · OpenAI   │ │ · Recursive│ │ · Chroma   │ │ · None     │ │ · Ragas    │  │
│  │ · OpenAI   │ │ · BGE      │ │ · Semantic │ │ · Qdrant   │ │ · CrossEnc │ │ · DeepEval │  │
│  │ · Ollama   │ │ · Ollama   │ │ · FixedLen │ │ · Pinecone │ │ · LLM      │ │ · Custom   │  │
│  │ · DeepSeek │ │ · ...      │ │ · ...      │ │ · ...      │ │            │ │            │  │
│  │ · Vision✨ │ │            │ │            │ │            │ │            │ │            │  │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                             Observability 层 (可观测性)                                      │
│                                                                                             │
│    ┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐     │
│    │          Trace Context               │    │         Web Dashboard                │     │
│    │   trace_id | stages[] | metrics      │    │        (Streamlit)                   │     │
│    │   record_stage() | finish()          │    │    请求列表 | 耗时瀑布图 | 详情展开   │     │
│    └──────────────────────────────────────┘    └──────────────────────────────────────┘     │
│                                                                                             │
│    ┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐     │
│    │          Evaluation Module           │    │         Structured Logger            │     │
│    │   Hit Rate | MRR | Faithfulness      │    │    JSON Formatter | File Handler     │     │
│    └──────────────────────────────────────┘    └──────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 目录结构

```
smart-knowledge-hub/
│
├── config/                              # 配置文件目录
│   ├── settings.yaml                    # 主配置文件 (LLM/Embedding/VectorStore 配置)
│   └── prompts/                         # Prompt 模板目录
│       ├── image_captioning.txt         # 图片描述生成 Prompt
│       ├── chunk_refinement.txt         # Chunk 重写 Prompt
│       └── rerank.txt                   # LLM Rerank Prompt
│
├── src/                                 # 源代码主目录
│   │
│   ├── mcp_server/                      # MCP Server 层 (接口层)
│   │   ├── __init__.py
│   │   ├── server.py                    # MCP Server 入口 (Stdio Transport)
│   │   ├── protocol_handler.py          # JSON-RPC 协议处理
│   │   └── tools/                       # MCP Tools 定义
│   │       ├── __init__.py
│   │       ├── query_knowledge_hub.py   # 主检索工具
│   │       ├── list_collections.py      # 列出集合工具
│   │       └── get_document_summary.py  # 文档摘要工具
│   │
│   ├── core/                            # Core 层 (核心业务逻辑)
│   │   ├── __init__.py
│   │   ├── settings.py                   # 配置加载与校验 (Settings：load_settings/validate_settings)
│   │   ├── types.py                      # 核心数据类型/契约（Document/Chunk/ChunkRecord），供 ingestion/retrieval/mcp 复用
│   │   │
│   │   ├── query_engine/                # 查询引擎模块
│   │   │   ├── __init__.py
│   │   │   ├── query_processor.py       # 查询预处理 (关键词提取/查询扩展)
│   │   │   ├── hybrid_search.py         # 混合检索引擎 (Dense + Sparse + RRF)
│   │   │   ├── dense_retriever.py       # 稠密向量检索
│   │   │   ├── sparse_retriever.py      # 稀疏检索 (BM25)
│   │   │   ├── fusion.py                # 结果融合 (RRF 算法)
│   │   │   └── reranker.py              # 重排序模块 (None/CrossEncoder/LLM)
│   │   │
│   │   ├── response/                    # 响应构建模块
│   │   │   ├── __init__.py
│   │   │   ├── response_builder.py      # 响应构建器
│   │   │   ├── citation_generator.py    # 引用生成器
│   │   │   └── multimodal_assembler.py  # 多模态内容组装 (Text + Image)
│   │   │
│   │   └── trace/                       # 追踪模块
│   │       ├── __init__.py
│   │       ├── trace_context.py         # 追踪上下文 (trace_id/stages)
│   │       └── trace_collector.py       # 追踪收集器
│   │
│   ├── ingestion/                       # Ingestion Pipeline (离线数据摄取)
│   │   ├── __init__.py
│   │   ├── pipeline.py                  # Pipeline 主流程编排 (支持 on_progress 回调)
│   │   ├── document_manager.py          # 文档生命周期管理 (list/delete/stats)
│   │   │
│   │   ├── chunking/                    # Chunking 模块 (文档切分)
│   │   │   ├── __init__.py
│   │   │   └── document_chunker.py      # Document → Chunks 转换（调用 libs.splitter）
│   │   │
│   │   ├── transform/                   # Transform 模块 (增强处理)
│   │   │   ├── __init__.py
│   │   │   ├── base_transform.py        # Transform 抽象基类
│   │   │   ├── chunk_refiner.py         # Chunk 智能重组/去噪
│   │   │   ├── metadata_enricher.py     # 语义元数据注入 (Title/Summary/Tags)
│   │   │   └── image_captioner.py       # 图片描述生成 (Vision LLM)
│   │   │
│   │   ├── embedding/                   # Embedding 模块 (向量化)
│   │   │   ├── __init__.py
│   │   │   ├── dense_encoder.py         # 稠密向量编码
│   │   │   ├── sparse_encoder.py        # 稀疏向量编码 (BM25)
│   │   │   └── batch_processor.py       # 批处理优化
│   │   │
│   │   └── storage/                     # Storage 模块 (存储)
│   │       ├── __init__.py
│   │       ├── vector_upserter.py       # 向量库 Upsert
│   │       ├── bm25_indexer.py          # BM25 索引构建
│   │       └── image_storage.py         # 图片文件存储
│   │
│   ├── libs/                            # Libs 层 (可插拔抽象层)
│   │   ├── __init__.py
│   │   │
│   │   ├── loader/                      # Loader 抽象 (文档加载)
│   │   │   ├── __init__.py
│   │   │   ├── base_loader.py           # Loader 抽象基类
│   │   │   ├── pdf_loader.py            # PDF Loader (MarkItDown)
│   │   │   └── file_integrity.py        # 文件完整性检查 (SHA256 哈希)
│   │   │
│   │   ├── llm/                         # LLM 抽象
│   │   │   ├── __init__.py
│   │   │   ├── base_llm.py              # LLM 抽象基类
│   │   │   ├── llm_factory.py           # LLM 工厂
│   │   │   ├── azure_llm.py             # Azure OpenAI 实现
│   │   │   ├── openai_llm.py            # OpenAI 实现
│   │   │   ├── ollama_llm.py            # Ollama 本地模型实现
│   │   │   ├── deepseek_llm.py          # DeepSeek 实现
│   │   │   ├── base_vision_llm.py       # Vision LLM 抽象基类（支持图像输入）
│   │   │   └── azure_vision_llm.py      # Azure Vision 实现 (GPT-4o/GPT-4-Vision)
│   │   │
│   │   ├── embedding/                   # Embedding 抽象
│   │   │   ├── __init__.py
│   │   │   ├── base_embedding.py        # Embedding 抽象基类
│   │   │   ├── embedding_factory.py     # Embedding 工厂
│   │   │   ├── openai_embedding.py      # OpenAI Embedding 实现
│   │   │   ├── azure_embedding.py       # Azure Embedding 实现
│   │   │   └── ollama_embedding.py      # Ollama 本地模型实现
│   │   │
│   │   ├── splitter/                    # Splitter 抽象 (切分策略)
│   │   │   ├── __init__.py
│   │   │   ├── base_splitter.py         # Splitter 抽象基类
│   │   │   ├── splitter_factory.py      # Splitter 工厂
│   │   │   ├── recursive_splitter.py    # RecursiveCharacterTextSplitter 实现
│   │   │   ├── semantic_splitter.py     # 语义切分实现
│   │   │   └── fixed_length_splitter.py # 定长切分实现
│   │   │
│   │   ├── vector_store/                # VectorStore 抽象
│   │   │   ├── __init__.py
│   │   │   ├── base_vector_store.py     # VectorStore 抽象基类
│   │   │   ├── vector_store_factory.py  # VectorStore 工厂
│   │   │   └── chroma_store.py          # Chroma 实现
│   │   │
│   │   ├── reranker/                    # Reranker 抽象
│   │   │   ├── __init__.py
│   │   │   ├── base_reranker.py         # Reranker 抽象基类
│   │   │   ├── reranker_factory.py      # Reranker 工厂
│   │   │   ├── cross_encoder_reranker.py# CrossEncoder 实现
│   │   │   └── llm_reranker.py          # LLM Rerank 实现
│   │   │
│   │   └── evaluator/                   # Evaluator 抽象
│   │       ├── __init__.py
│   │       ├── base_evaluator.py        # Evaluator 抽象基类
│   │       ├── evaluator_factory.py     # Evaluator 工厂
│   │       ├── ragas_evaluator.py       # Ragas 实现
│   │       └── custom_evaluator.py      # 自定义指标实现
│   │
│   └── observability/                   # Observability 层 (可观测性)
│       ├── __init__.py
│       ├── logger.py                    # 结构化日志 (JSON Formatter)
│       ├── dashboard/                   # Web Dashboard (可视化管理平台)
│       │   ├── __init__.py
│       │   ├── app.py                   # Streamlit 入口 (页面导航注册)
│       │   ├── pages/                   # 六大功能页面
│       │   │   ├── overview.py          # 系统总览 (组件配置 + 数据统计)
│       │   │   ├── data_browser.py      # 数据浏览器 (文档/Chunk/图片查看)
│       │   │   ├── ingestion_manager.py # Ingestion 管理 (触发摄取/删除文档)
│       │   │   ├── ingestion_traces.py  # Ingestion 追踪 (摄取历史与详情)
│       │   │   ├── query_traces.py      # Query 追踪 (查询历史与详情)
│       │   │   └── evaluation_panel.py  # 评估面板 (运行评估/查看指标)
│       │   └── services/                # Dashboard 数据服务层
│       │       ├── trace_service.py     # Trace 读取服务 (解析 traces.jsonl)
│       │       ├── data_service.py      # 数据浏览服务 (ChromaStore/ImageStorage)
│       │       └── config_service.py    # 配置读取服务 (Settings 展示)
│       └── evaluation/                  # 评估模块
│           ├── __init__.py
│           ├── eval_runner.py           # 评估执行器
│           ├── ragas_evaluator.py       # Ragas 评估实现
│           └── composite_evaluator.py   # 组合评估器 (多后端并行)

│
├── data/                                # 数据目录
│   ├── documents/                       # 原始文档存放
│   │   └── {collection}/                # 按集合分类
│   ├── images/                          # 提取的图片存放
│   │   └── {collection}/                # 按集合分类（实际存储在 {doc_hash}/ 子目录下）
│   └── db/                              # 数据库与索引文件目录
│       ├── ingestion_history.db         # 文件完整性历史记录 (SQLite)
│       │                                # 表结构：file_hash, file_path, status, processed_at, error_msg
│       │                                # 用途：增量摄取，避免重复处理未变更文件
│       ├── image_index.db               # 图片索引映射 (SQLite)
│       │                                # 表结构：image_id, file_path, collection, doc_hash, page_num
│       │                                # 用途：快速查询 image_id → 本地文件路径，支持图片检索与引用
│       ├── chroma/                      # Chroma 向量库目录
│       │                                # 存储 Dense Vector、Sparse Vector 与 Chunk Metadata
│       └── bm25/                        # BM25 索引目录
│                                        # 存储倒排索引与 IDF 统计信息（当前使用 pickle）
│
├── cache/                               # 缓存目录
│   ├── embeddings/                      # Embedding 缓存 (按内容哈希)
│   ├── captions/                        # 图片描述缓存
│   └── processing/                      # 处理状态缓存 (文件哈希/Chunk 哈希)
│
├── logs/                                # 日志目录
│   ├── traces.jsonl                     # 追踪日志 (JSON Lines)
│   └── app.log                          # 应用日志
│
├── tests/                               # 测试目录
│   ├── unit/                            # 单元测试
│   │   ├── test_dense_retriever.py      # D2: 稠密检索器测试
│   │   ├── test_sparse_retriever.py     # D3: 稀疏检索器测试
│   │   ├── test_fusion_rrf.py           # D4: RRF 融合测试
│   │   ├── test_reranker_fallback.py    # D6: Reranker 回退测试
│   │   ├── test_protocol_handler.py     # E2: 协议处理器测试
│   │   ├── test_response_builder.py     # E3: 响应构建器测试
│   │   ├── test_list_collections.py     # E4: 集合列表工具测试
│   │   ├── test_get_document_summary.py # E5: 文档摘要工具测试
│   │   ├── test_trace_context.py        # F1: 追踪上下文测试
│   │   ├── test_jsonl_logger.py         # F2: JSON Lines 日志测试
│   │   └── ...                          # 其他已有单元测试
│   ├── integration/                     # 集成测试
│   │   ├── test_ingestion_pipeline.py
│   │   ├── test_hybrid_search.py        # D5: 混合检索集成测试
│   │   └── test_mcp_server.py           # E1-E6: MCP 服务器集成测试
│   ├── e2e/                             # 端到端测试
│   │   ├── test_data_ingestion.py
│   │   ├── test_recall.py               # G2: 召回回归测试
│   │   └── test_mcp_client.py           # G1: MCP Client 模拟测试
│   └── fixtures/                        # 测试数据
│       ├── sample_documents/
│       └── golden_test_set.json         # F5/G2: 黄金测试集
│
├── scripts/                             # 脚本目录
│   ├── ingest.py                        # 数据摄取脚本（离线摄取入口）
│   ├── query.py                         # 查询测试脚本（在线查询入口）
│   ├── evaluate.py                      # 评估运行脚本
│   └── start_dashboard.py               # Dashboard 启动脚本
│
├── main.py                              # MCP Server 启动入口
├── pyproject.toml                       # Python 项目配置
├── requirements.txt                     # 依赖列表
└── README.md                            # 项目说明
```

### 5.3 模块说明

#### 5.3.1 MCP Server 层

| 模块 | 职责 | 关键技术点 |
|-----|-----|----------|
| `server.py` | MCP Server 主入口，处理 Stdio Transport 通信 | Python MCP SDK，JSON-RPC 2.0 |
| `protocol_handler.py` | 协议解析与能力协商 | `initialize`、`tools/list`、`tools/call` |
| `tools/*` | 对外暴露的工具函数实现 | 装饰器定义，参数校验，响应格式化 |

#### 5.3.2 Core 层

| 模块 | 职责 | 关键技术点 |
|-----|-----|----------|
| `settings.py` | 配置加载与校验 | 读取 `config/settings.yaml`，解析为 `Settings`，必填字段校验（fail-fast） |
| `types.py` | 核心数据类型/契约（全链路复用） | 定义 `Document/Chunk/ChunkRecord/ProcessedQuery/RetrievalResult`；序列化稳定；作为 ingestion/retrieval/mcp 的数据契约中心 |
| `query_processor.py` | 查询预处理 | 关键词提取、同义词扩展、Metadata 解析 |
| `hybrid_search.py` | 混合检索编排 | 并行 Dense/Sparse 召回，结果融合，Metadata 过滤 |
| `dense_retriever.py` | 语义向量检索 | Query Embedding + VectorStore 检索，Cosine Similarity |
| `sparse_retriever.py` | BM25 关键词检索 | 倒排索引查询，TF-IDF 打分 |
| `fusion.py` | 结果融合 | RRF 算法，排名倒数加权 |
| `reranker.py` | 精排重排 | CrossEncoder / LLM Rerank / Fallback 回退 |
| `response_builder.py` | 响应构建 | MCP 响应格式化，Markdown 生成 |
| `citation_generator.py` | 引用生成 | 从检索结果生成结构化引用列表 |
| `multimodal_assembler.py` | 多模态组装 | Text + Image Base64 编码，MCP 多内容类型 |
| `trace_context.py` | 追踪上下文 | trace_id 生成，阶段记录，finish 汇总 |
| `trace_collector.py` | 追踪收集器 | 收集 trace 并触发持久化到 JSON Lines |

#### 5.3.3 Scripts 层（命令行入口）

| 脚本 | 职责 | 关键技术点 |
|-----|-----|----------|
| `ingest.py` | 离线数据摄取入口 | CLI 参数解析，调用 Ingestion Pipeline，支持 `--collection`/`--path`/`--force` |
| `query.py` | 在线查询测试入口 | CLI 参数解析，调用 HybridSearch + Reranker，支持 `--query`/`--top-k`/`--verbose` |
| `evaluate.py` | 评估运行入口 | 加载 golden_test_set，运行评估，输出 metrics |
| `start_dashboard.py` | Dashboard 启动入口 | Streamlit 应用启动 |

#### 5.3.4 Ingestion Pipeline 层

| 模块 | 职责 | 关键技术点 |
|-----|-----|----------|
| `pipeline.py` | Pipeline 流程编排 | 串行执行（或分阶段可观测），异常处理，增量更新；支持 `on_progress` 回调；统一使用 `core/types.py` 的数据契约 |
| `document_manager.py` | 文档生命周期管理 | list/delete/stats 操作；跨 4 个存储（Chroma/BM25/ImageStorage/FileIntegrity）的协调删除；供 Dashboard 与 CLI 调用 |

| `chunking/document_chunker.py` | Document→Chunks 转换 | 调用 `libs.splitter` 进行文本切分；生成稳定 Chunk ID（格式：`{doc_id}_{index:04d}_{hash}`）；继承 metadata；建立 source_ref 溯源链接 |
| `transform/base_transform.py` | Transform 抽象 | 原子化、幂等；可独立重试；失败降级不阻塞 |
| `transform/chunk_refiner.py` | Chunk 智能重组 | 规则去噪 + 可选 LLM 二次加工；可回退 |
| `transform/metadata_enricher.py` | 元数据增强 | Title/Summary/Tags 规则生成 + 可选 LLM 增强 |
| `transform/image_captioner.py` | 图片描述生成 | Vision LLM；写回 metadata/text；禁用/失败降级 |
| `embedding/dense_encoder.py` | 稠密向量编码 | 通过 `libs.embedding` 调用具体 provider；批处理 |
| `embedding/sparse_encoder.py` | 稀疏向量编码 | BM25 编码/统计（或替换实现）；批处理 |
| `storage/vector_upserter.py` | 向量存储写入 | 通过 `libs.vector_store` Upsert；幂等；metadata 完整 |

#### 5.3.5 Libs 层 (可插拔抽象)

| 抽象接口 | 当前默认实现 | 可替换选项 |
|---------|------------|----------|
| `LLMClient` | Azure OpenAI | OpenAI / Ollama / DeepSeek |
| `VisionLLMClient` | Azure OpenAI Vision (GPT-4o) | OpenAI Vision / Ollama Vision (LLaVA) |
| `EmbeddingClient` | OpenAI text-embedding-3 | BGE / Ollama 本地模型 |
| `Loader` | PDF Loader（MarkItDown） | Markdown/HTML/Code Loader 等 |
| `FileIntegrity` | SQLite (`data/db/ingestion_history.db`) | Redis（分布式）/ PostgreSQL（企业级）/ JSON文件（测试） |
| `Splitter` | RecursiveCharacterTextSplitter | Semantic / FixedLen |
| `VectorStore` | Chroma | Qdrant / Pinecone / Milvus |
| `Reranker` | CrossEncoder | LLM Rerank / None (关闭) |
| `Evaluator` | Ragas | DeepEval / 自定义指标 |

#### 5.3.6 Observability 层

| 模块 | 职责 | 关键技术点 |
|-----|-----|----------|
| `logger.py` | 结构化日志 | JSON Formatter，JSON Lines 输出 |
| `trace_context.py` | 请求级追踪 | trace_id，trace_type（query/ingestion），阶段耗时记录，`finish()` + `to_dict()` 序列化 |
| `trace_collector.py` | 追踪收集器 | 收集 trace 并触发持久化到 JSON Lines |
| `dashboard/app.py` | Dashboard 入口 | Streamlit 多页面应用，`st.navigation` 页面注册 |
| `dashboard/pages/overview.py` | 系统总览 | 组件配置卡片，数据资产统计 |
| `dashboard/pages/data_browser.py` | 数据浏览器 | 文档列表，Chunk 详情，图片预览 |
| `dashboard/pages/ingestion_manager.py` | Ingestion 管理 | 文件上传，摄取触发（进度条），文档删除 |
| `dashboard/pages/ingestion_traces.py` | Ingestion 追踪 | 摄取历史，阶段耗时瀑布图 |
| `dashboard/pages/query_traces.py` | Query 追踪 | 查询历史，Dense/Sparse 对比，Rerank 变化 |
| `dashboard/pages/evaluation_panel.py` | 评估面板 | 运行评估，指标展示，历史趋势（Phase H 实现） |
| `dashboard/services/trace_service.py` | Trace 数据服务 | 解析 traces.jsonl，按 trace_type 分类 |
| `dashboard/services/data_service.py` | 数据浏览服务 | 封装 ChromaStore/ImageStorage 读取 |
| `dashboard/services/config_service.py` | 配置读取服务 | 封装 Settings 展示 |
| `evaluation/eval_runner.py` | 评估执行 | 黄金测试集，指标计算，报告生成 |
| `evaluation/ragas_evaluator.py` | Ragas 评估 | Faithfulness, Answer Relevancy, Context Precision |
| `evaluation/composite_evaluator.py` | 组合评估器 | 多后端并行执行，结果汇总 |


### 5.4 数据流说明

#### 5.4.1 离线数据摄取流 (Ingestion Flow)

```
原始文档 (PDF)
      │
      ▼
┌─────────────────┐     未变更则跳过
│ File Integrity  │───────────────────────────► 结束
│   (SHA256)      │
└────────┬────────┘
         │ 新文件/已变更
         ▼
┌─────────────────┐
│     Loader      │  PDF → Markdown + 图片提取 + 元数据收集
│   (MarkItDown)  │
└────────┬────────┘
         │ Document (text + metadata.images)
         ▼
┌─────────────────┐
│    Splitter     │  按语义边界切分，保留图片引用
│ (Recursive)     │
└────────┬────────┘
         │ Chunks[] (with image_refs)
         ▼
┌─────────────────┐
│   Transform     │  LLM 重写 + 元数据注入 + 图片描述生成
│ (Enrichment)    │
└────────┬────────┘
         │ Enriched Chunks[] (with captions in text)
         ▼
┌─────────────────┐
│   Embedding     │  Dense (OpenAI) + Sparse (BM25) 双路编码
│  (Dual Path)    │
└────────┬────────┘
         │ Vectors + Chunks + Metadata
         ▼
┌─────────────────┐
│    Upsert       │  Chroma Upsert (幂等) + BM25 Index + 图片存储
│   (Storage)     │
└─────────────────┘
```

#### 5.4.2 在线查询流 (Query Flow)

```
用户查询 (via MCP Client)
      │
      ▼
┌─────────────────┐
│  MCP Server     │  JSON-RPC 解析，工具路由
│ (Stdio Transport)│
└────────┬────────┘
         │ query + params
         ▼
┌─────────────────┐
│ Query Processor │  关键词提取 + 同义词扩展 + Metadata 解析
│                 │
└────────┬────────┘
         │ processed_query + filters
         ▼
┌─────────────────────────────────────────────┐
│              Hybrid Search                  │
│  ┌─────────────┐          ┌─────────────┐   │
│  │Dense Retrieval│  并行   │Sparse Retrieval│   │
│  │ (Embedding)  │◄───────►│  (BM25)     │   │
│  └──────┬──────┘          └──────┬──────┘   │
│         │                        │          │
│         └────────┬───────────────┘          │
│                  ▼                          │
│         ┌─────────────┐                     │
│         │   Fusion    │  RRF 融合           │
│         │   (RRF)     │                     │
│         └──────┬──────┘                     │
└────────────────┼────────────────────────────┘
                 │ Top-M 候选
                 ▼
┌─────────────────┐
│    Reranker     │  CrossEncoder / LLM / None
│   (Optional)    │
└────────┬────────┘
         │ Top-K 精排结果
         ▼
┌─────────────────┐
│ Response Builder│  引用生成 + 图片 Base64 编码 + MCP 格式化
│                 │
└────────┬────────┘
         │ MCP Response (TextContent + ImageContent)
         ▼
返回给 MCP Client (Copilot / Claude Desktop)
```

#### 5.4.3 管理操作流 (Management Flow)

```
Dashboard (Streamlit UI)
      │
      ├─── 数据浏览 ──────────────────────────────────────────┐
      │                                                       │
      │    DataService                                        │
      │    ├── ChromaStore.get_by_metadata(source=...)        │
      │    ├── ImageStorage.list_images(collection, doc_hash) │
      │    └── 返回文档列表 / Chunk 详情 / 图片预览            │
      │                                                       │
      ├─── Ingestion 管理 ────────────────────────────────────┤
      │                                                       │
      │    触发摄取：                                          │
      │    ├── IngestionPipeline.run(path, collection,        │
      │    │                         on_progress=callback)    │
      │    └── st.progress() 实时更新进度                      │
      │                                                       │
      │    删除文档：                                          │
      │    ├── DocumentManager.delete_document(source, col)   │
      │    │   ├── ChromaStore.delete_by_metadata(source=...) │
      │    │   ├── BM25Indexer.remove_document(source=...)    │
      │    │   ├── ImageStorage.delete_images(col, doc_hash)  │
      │    │   └── FileIntegrity.remove_record(file_hash)     │
      │    └── 刷新文档列表                                    │
      │                                                       │
      └─── Trace 查看 ───────────────────────────────────────┘
           │
           TraceService
           ├── 读取 logs/traces.jsonl
           ├── 按 trace_type 分类 (query / ingestion)
           └── 返回 Trace 列表与详情
```

### 5.5 配置驱动设计


系统通过 `config/settings.yaml` 统一配置各组件实现，支持零代码切换：

```yaml
# config/settings.yaml 示例

# LLM 配置
llm:
  provider: azure           # azure | openai | ollama | deepseek
  model: gpt-4o
  azure_endpoint: "..."
  api_key: "${AZURE_API_KEY}"

# Embedding 配置
embedding:
  provider: openai          # openai | azure | ollama (本地)
  model: text-embedding-3-small
  
# Vision LLM 配置 (图片描述)
vision_llm:
  provider: azure           # azure | dashscope (Qwen-VL)
  model: gpt-4o
  
# 向量存储配置
vector_store:
  backend: chroma           # chroma | qdrant | pinecone
  persist_path: ./data/db/chroma

# 检索配置
retrieval:
  sparse_backend: bm25      # bm25 | elasticsearch
  fusion_algorithm: rrf     # rrf | weighted_sum
  top_k_dense: 20
  top_k_sparse: 20
  top_k_final: 10

# 重排配置
rerank:
  backend: cross_encoder    # none | cross_encoder | llm
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  top_m: 30

# 评估配置
evaluation:
  backends: [ragas, custom]
  golden_test_set: ./tests/fixtures/golden_test_set.json

# 可观测性配置
observability:
  enabled: true
  log_file: ./logs/traces.jsonl

# Dashboard 管理平台配置
dashboard:
  enabled: true
  port: 8501                     # Streamlit 服务端口
  traces_dir: ./logs             # Trace 日志文件目录
  auto_refresh: true             # 是否自动刷新（轮询新 trace）
  refresh_interval: 5            # 自动刷新间隔（秒）
```

### 5.6 扩展性设计要点


1. **新增 LLM Provider**：实现 `BaseLLM` 接口，在 `llm_factory.py` 注册，配置文件指定 `provider` 即可
2. **新增文档格式**：实现 `BaseLoader` 接口，在 Pipeline 中注册对应文件扩展名的处理器
3. **新增检索策略**：实现检索接口，在 `hybrid_search.py` 中组合调用
4. **新增评估指标**：实现 `BaseEvaluator` 接口，在配置中添加到 `backends` 列表

