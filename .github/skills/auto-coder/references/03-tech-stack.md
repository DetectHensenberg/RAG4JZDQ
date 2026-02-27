## 3. 技术选型

### 3.1 RAG 核心流水线设计 

#### 3.1.1 数据摄取流水线 

**目标：** 构建统一、可配置且可观测的数据摄取流水线，覆盖文档加载、格式解析、语义切分、多模态增强、嵌入计算、去重与批量上载到向量存储。该能力应是可重用的库模块，便于在 `ingest.py`、Dashboard 管理面板、离线批处理和测试中调用。

- **自研 Pipeline 框架（设计灵感参考 LlamaIndex 分层思想，但不依赖 LlamaIndex 库）：**
	- 采用自定义抽象接口（`BaseLoader`/`BaseSplitter`/`BaseTransform`/`BaseEmbedding`/`BaseVectorStore`），实现完全可控的可插拔架构。
	- 支持可组合的 Loader -> Splitter -> Transform -> Embed -> Upsert 流程，便于实现可观测的流水线。
	- 与主流 embedding provider 有良好适配，架构中统一使用 Chroma 作为向量存储。


设计要点：
- **明确分层职责**：
  - Loader：负责把原始文件解析为统一的 `Document` 对象（`text` + `metadata`；类型定义集中在 `src/core/types.py`）。**在当前阶段，仅实现 PDF 格式的 Loader。**
		- 统一输出格式采用规范化 Markdown作为 `Document.text`：这样可以更好的配合后面的Splitte（Langchain RecursiveCharacterTextSplitte））方法产出高质量切块。
		- Loader 同时抽取/补齐基础 metadata（如 `source_path`, `doc_type=pdf`, `page`, `title/heading_outline`, `images` 引用列表等），为定位、回溯与后续 Transform 提供依据。
	- Splitter：基于 Markdown 结构（标题/段落/代码块等）与参数配置把 `Document` 切为若干 Chunk，保留原始位置与上下文引用。
	- Transform：可插入的处理步骤（ImageCaptioning、OCR、code-block normalization、html-to-text cleanup 等），Transform 可以选择把额外信息追加到 chunk.text 或放入 chunk.metadata（推荐默认追加到 text 以保证检索覆盖）。
	- Embed & Upsert：按批次计算 embedding，并上载到向量存储；支持向量 + metadata 上载，并提供幂等 upsert 策略（基于 id/hash）。
	- Dedup & Normalize：在上载前运行向量/文本去重与哈希过滤，避免重复索引。

关键实现要素：

- Loader（统一格式与元数据）
	- **前置去重 (Early Exit / File Integrity Check)**：
		- 机制：在解析文件前，计算原始文件的 SHA256 哈希指纹。
		- 动作：检索 `ingestion_history` 表，若发现相同 Hash 且状态为 `success` 的记录，则认定该文件未发生变更，直接跳过后续所有处理（解析、切分、LLM重写），实现**零成本 (Zero-Cost)** 的增量更新。
		- **存储方案**（初期实现，可插拔）：
			- **默认选择：SQLite**，存储于 `data/db/ingestion_history.db`
			- **表结构**：
				```sql
				CREATE TABLE ingestion_history (
				    file_hash TEXT PRIMARY KEY,
				    file_path TEXT NOT NULL,
				    file_size INTEGER,
				    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'processing')),
				    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
				    error_msg TEXT,
				    chunk_count INTEGER
				);
				CREATE INDEX idx_status ON ingestion_history(status);
				CREATE INDEX idx_processed_at ON ingestion_history(processed_at);
				```
			- **查询逻辑**：`SELECT status FROM ingestion_history WHERE file_hash = ? AND status = 'success'`
			- **替换路径**：后续可升级为 Redis（分布式缓存）或 PostgreSQL（企业级中心化存储）
	
	> **📌 持久化存储架构统一说明**
	> 
	> 本项目在多个核心模块中采用 **SQLite** 作为轻量级持久化存储方案，避免引入重量级数据库依赖，保持本地优先（Local-First）的设计理念：
	> 
	> | 存储模块 | 数据库文件 | 用途 | 表结构关键字段 |
	> |---------|-----------|------|---------------|
	> | **文件完整性检查** | `data/db/ingestion_history.db` | 记录已处理文件的 SHA256 哈希，实现增量摄取 | `file_hash`, `status`, `processed_at` |
	> | **图片索引映射** | `data/db/image_index.db` | 记录 image_id → 文件路径映射，支持图片检索与引用 | `image_id`, `file_path`, `collection` |
	> | **BM25 索引元数据** | `data/db/bm25/` | 存储倒排索引和 IDF 统计信息（未来可扩展用 SQLite） | 当前使用 pickle，可迁移至 SQLite |
	> 
	> **设计优势**：
	> - **零依赖部署**：无需安装 MySQL/PostgreSQL 等数据库服务，`pip install` 即可运行
	> - **并发安全**：WAL (Write-Ahead Logging) 模式支持多进程安全读写
	> - **持久化保证**：摄取历史和索引映射在进程重启后自动恢复，避免重复计算
	> - **架构一致性**：所有 SQLite 模块遵循相同的初始化、查询与错误处理模式，便于维护与扩展
	> 
	> **升级路径**：当系统规模扩展至分布式场景时，可通过统一的抽象接口将 SQLite 替换为 PostgreSQL 或 Redis，无需修改上层业务逻辑。
	
	- **解析与标准化**：
		- 当前范围：**仅实现 PDF -> canonical Markdown 子集** 的转换。
	- 技术选型（Python PDF -> Markdown）：
		- **首选：MarkItDown**（作为默认 PDF 解析/转换引擎）。优点是直接产出 Markdown 形态文本，便于与后续 `RecursiveCharacterTextSplitter` 的 separators 配合。
	- 输出标准 `Document`：`id|source|text(markdown)|metadata`。metadata 至少包含 `source_path`, `doc_type`, `title/heading_outline`, `page/slide`（如适用）, `images`（图片引用列表）。
	- Loader 不负责切分：只做“格式统一 + 结构抽取 + 引用收集”，确保切分策略可独立迭代与度量。

- Splitter（LangChain 负责切分；独立、可控）
	- **实现方案：使用 LangChain 的 `RecursiveCharacterTextSplitter` 进行切分。**
		- 优势：该方法对 Markdown 文档的结构（标题、段落、列表、代码块）有天然的适配性，能够通过配置语义断点（Separators）实现高质量、语义完整的切块。
	- Splitter 输入：Loader 产出的 Markdown `Document`。
	- Splitter 输出：若干 `Chunk`（或 Document-like chunks），每个 chunk 必须携带稳定的定位信息与来源信息：`source`, `chunk_index`, `start_offset/end_offset`（或等价定位字段）。

- Transform & Enrichment（结构转换与深度增强）
	本阶段是 ETL 管道的核心“智力”环节，负责将 Splitter 产出的非结构化文本块转化为结构化、富语义的智能切片（Smart Chunk）。
	- **结构转换 (Structure Transformation)**：将原始的 `String` 类型数据转化为强类型的 `Record/Object`，为下游检索提供字段级支持。
	- **核心增强策略**：
		1. **智能重组 (Smart Chunking & Refinement)**：
			- 策略：利用 LLM 的语义理解能力，对上一阶段“粗切分”的片段进行二次加工。
			- 动作：合并在逻辑上紧密相关但被物理切断的段落，剔除无意义的页眉页脚或乱码（去噪），确保每个 Chunk 是自包含（Self-contained）的语义单元。
		2. **语义元数据注入 (Semantic Metadata Enrichment)**：
			- 策略：在基础元数据（路径、页码）之上，利用 LLM 提取高维语义特征。
			- 产出：为每个 Chunk 自动生成 `Title`（精准小标题）、`Summary`（内容摘要）和 `Tags`（主题标签），并将其注入到 Metadata 字段中，支持后续的混合检索与精确过滤。
		3. **多模态增强 (Multimodal Enrichment / Image Captioning)**：
			- 策略：扫描文档片段中的图像引用，调用 Vision LLM（如 GPT-4o）进行视觉理解。
			- 动作：生成高保真的文本描述（Caption），描述图表逻辑或提取截图文字。
			- 存储：将 Caption 文本“缝合”进 Chunk 的正文或 Metadata 中，打通模态隔阂，实现“搜文出图”。
	- **工程特性**：Transform 步骤设计为原子化与幂等操作，支持针对特定 Chunk 的独立重试与增量更新，避免因 LLM 调用失败导致整个文档处理中断。

- **Embedding (双路向量化)**
	- **差量计算 (Incremental Embedding / Cost Optimization)**：
		- 策略：在调用昂贵的 Embedding API 之前，计算 Chunk 的内容哈希（Content Hash）。仅针对数据库中不存在的新内容哈希执行向量化计算，对于文件名变更但内容未变的片段，直接复用已有向量，显著降低 API 调用成本。
	- **核心策略**：为了支持高精度的混合检索（Hybrid Search），系统对每个 Chunk 并行执行双路编码计算。
		- **Dense Embeddings（语义向量）**：调用 Embedding 模型（如 OpenAI text-embedding-3 或 BGE）生成高维浮点向量，捕捉文本的深层语义关联，解决“词不同意同”的检索难题。
		- **Sparse Embeddings（稀疏向量）**：利用 BM25 编码器或 SPLADE 模型生成稀疏向量（Keyword Weights），捕捉精确的关键词匹配信息，解决专有名词查找问题。
	- **批处理优化**：所有计算均采用 `batch_size` 驱动的批处理模式，最大化 CPU 利用率并减少网络 RTT。

- **Upsert & Storage (索引存储)**
	- **存储后端**：统一使用向量数据库（如 Chroma/Qdrant）作为存储引擎，同时持久化存储 Dense Vector、Sparse Vector 以及 Transform 阶段生成的富 Metadata。
	- **All-in-One 存储策略**：执行原子化存储，每条记录同时包含：
		1. **Index Data**: 用于计算相似度的 Dense Vector 和 Sparse Vector。
		2. **Payload Data**: 完整的 Chunk 原始文本 (Content) 及 Metadata。
		**机制优势**：确保检索命中 ID 后能立即取回对应的正文内容，无需额外的查库操作 (Lookup)，保障了 Retrieve 阶段的毫秒级响应。
- **幂等性设计 (Idempotency)**：
		- 为每个 Chunk 生成全局唯一的 `chunk_id`，生成算法采用确定的哈希组合：`hash(source_path + section_path + content_hash)`。
		- 写入时采用 "Upsert"（更新或插入）语义，确保同一文档即使被多次处理，数据库中也永远只有一份最新副本，彻底避免重复索引问题。
	- **原子性保证**：以 Batch 为单位进行事务性写入，确保索引状态的一致性。

- **文档生命周期管理 (Document Lifecycle Management)**

	为支持 Dashboard 管理面板中的文档浏览与删除功能，Ingestion 层需要提供完整的文档生命周期管理能力：

	- **DocumentManager（文档管理器）**：独立于 Pipeline 的文档管理模块（`src/ingestion/document_manager.py`），负责跨存储的协调操作：
		- `list_documents(collection?) -> List[DocumentInfo]`：列出已摄入文档及其统计信息（chunk 数、图片数、摄入时间）。
		- `get_document_detail(doc_id) -> DocumentDetail`：获取单个文档的详细信息（所有 chunk 内容、metadata、关联图片）。
		- `delete_document(source_path, collection) -> DeleteResult`：协调删除跨 4 个存储的关联数据：
			1. **Chroma** — 按 `metadata.source` 删除所有 chunk 向量
			2. **BM25 Indexer** — 移除对应文档的倒排索引条目
			3. **ImageStorage** — 删除该文档关联的所有图片文件
			4. **FileIntegrity** — 移除处理记录，使文件可重新摄入
		- `get_collection_stats(collection?) -> CollectionStats`：返回集合级统计（文档数、chunk 数、存储大小等）。

	- **Pipeline 进度回调 (Progress Callback)**：在 `IngestionPipeline.run()` 方法中新增可选 `on_progress` 参数：
		```python
		def run(self, source_path: str, collection: str = "default",
		        on_progress: Callable[[str, int, int], None] | None = None) -> IngestionResult:
		```
		- 回调签名：`on_progress(stage_name: str, current: int, total: int)`
		- 各阶段（load / split / transform / embed / upsert）在处理每个 batch 时调用回调，Dashboard 据此展示实时进度条。
		- `on_progress` 为 `None` 时行为与当前完全一致，不影响 CLI 和测试场景。

	- **存储层接口扩展**：为支持 DocumentManager 的删除操作，需扩展以下存储接口：
		- `BaseVectorStore` 新增 `delete_by_metadata(filter: dict) -> int` — 按 metadata 条件批量删除
		- `BM25Indexer` 新增 `remove_document(source: str) -> None` — 移除指定文档的索引条目
		- `FileIntegrityChecker` 新增 `remove_record(file_hash: str) -> None` 和 `list_processed() -> List[dict]`

#### 3.1.2 检索流水线


本模块实现核心的 RAG 检索引擎，采用 **“多阶段过滤 (Multi-stage Filtering)”** 架构，负责接收已消歧的独立查询（Standalone Query），并精准召回 Top-K 最相关片段。

- **Query Processing (查询预处理)**
	- **核心假设**：输入 Query 已由上游（Client/MCP Host）完成会话上下文补全（De-referencing），不仅如此，还进行了指代消歧。
	- **查询转换 (Transformation) 与扩张策略 (Expansion Strategy)**：
		- **Keyword Extraction**：利用 NLP 工具提取 Query 中的关键实体与动词（去停用词），生成用于稀疏检索的 Token 列表。
		- **Query Expansion **：
			- 系统可做 Synonym/Alias Expansion（同义词/别名/缩写扩展），默认策略采用“**扩展融入稀疏检索、稠密检索保持单次**”以控制成本与复杂度。
			- **Sparse Route (BM25)**：将“关键词 + 同义词/别名”合并为一个查询表达式（逻辑上按 `OR` 扩展），**只执行一次稀疏检索**。原始关键词可赋予更高权重以抑制语义漂移。
			- **Dense Route (Embedding)**：使用原始 query（或轻度改写后的语义 query）生成 embedding，**只执行一次稠密检索**；默认不为每个同义词单独触发额外的向量检索请求。

- **Hybrid Search Execution (双路混合检索)**
	- **并行召回 (Parallel Execution)**：
		- **Dense Route**：计算 Query Embedding -> 检索向量库（Cosine Similarity）-> 返回 Top-N 语义候选。
		- **Sparse Route**：使用 BM25 算法 -> 检索倒排索引 -> 返回 Top-N 关键词候选。
	- **结果融合 (Fusion)**：
		- 采用 **RRF (Reciprocal Rank Fusion)** 算法，不依赖各路分数的绝对值，而是基于排名的倒数进行加权融合。
		- 公式策略：`Score = 1 / (k + Rank_Dense) + 1 / (k + Rank_Sparse)`，平滑因单一模态缺陷导致的漏召回。

- **Filtering & Reranking (精确过滤与重排)**
	- **Metadata Filtering Strategy (通用过滤策略)**：
		- **原则：先解析、能前置则前置、无法前置则后置兜底。**
		- Query Processing 阶段应将结构化约束解析为通用 `filters`（例如 `collection`/`doc_type`/`language`/`time_range`/`access_level` 等）。
		- 若底层索引支持且属于硬约束（Hard Filter），则在 Dense/Sparse 检索阶段做 Pre-filter 以缩小候选集、降低成本。
		- 无法前置的过滤（索引不支持或字段缺失/质量不稳）在 Rerank 前统一做 Post-filter 作为 safety net；对缺失字段默认采取“宽松包含”(missing->include) 以避免误杀召回。
		- 软偏好（Soft Preference，例如“更近期更好”）不应硬过滤，而应作为排序信号在融合/重排阶段加权。
	- **Rerank Backend (可插拔精排后端)**：
		- **目标**：在 Top-M 候选上进行高精度排序/过滤；该模块必须可关闭，并提供稳定回退策略。
		- **后端选项**：
			1. **None (关闭精排)**：直接返回融合后的 Top-K（RRF 排名作为最终结果）。
			2. **Cross-Encoder Rerank (本地/托管模型)**：输入为 `[Query, Chunk]` 对，输出相关性分数并排序；适合稳定、结构化输出。CPU 环境下建议默认仅对较小的 Top-M 执行（例如 M=10~30），并提供超时回退。
			3. **LLM Rerank (可选)**：使用 LLM 对候选集排序/选择；适合需要更强指令理解或无本地模型环境时。为控制成本与稳定性，候选数应更小（例如 M<=20），并要求输出严格结构化格式（如 JSON 的 ranked ids）。
		- **默认与回退 (Fallback)**：
			- 默认策略面向通用框架与 CPU 环境：优先保证“可用与可控”，Cross-Encoder/LLM 均为可选增强。
			- 当精排不可用/超时/失败时，必须回退到融合阶段的排序（RRF Top-K），确保系统可用性与结果稳定性。

### 3.2 MCP 服务设计 (MCP Service Design)

**目标：** 设计并实现一个符合 Model Context Protocol (MCP) 规范的 Server，使其能够作为知识上下文提供者，无缝对接主流 MCP Clients（如 GitHub Copilot、Claude Desktop 等），让用户通过现有 AI 助手即可查询私有知识库。

#### 3.2.1 核心设计理念

- **协议优先 (Protocol-First)**：严格遵循 MCP 官方规范（JSON-RPC 2.0），确保与任何合规 Client 的互操作性。
- **开箱即用 (Zero-Config for Clients)**：Client 端无需任何特殊配置，只需在配置文件中添加 Server 连接信息即可使用全部功能。
- **引用透明 (Citation Transparency)**：所有检索结果必须携带完整的来源信息，支持 Client 端展示"回答依据"，增强用户对 AI 输出的信任。
- **多模态友好 (Multimodal-Ready)**：返回格式应支持文本与图像等多种内容类型，为未来的富媒体展示预留扩展空间。

#### 3.2.2 传输协议：Stdio 本地通信

本项目采用 **Stdio Transport** 作为唯一通信模式。

- **工作方式**：Client（VS Code Copilot、Claude Desktop）以子进程方式启动我们的 Server，双方通过标准输入/输出交换 JSON-RPC 消息。
- **选型理由**：
	- **零配置**：无需网络端口、无需鉴权，用户只需在 Client 配置文件中指定启动命令即可使用。
	- **隐私安全**：数据不经过网络，天然适合处理私有知识库与敏感业务数据。
	- **契合定位**：Stdio 完美适配开发者本地工作流，满足私有知识管理与快速原型验证需求。
- **实现约束**：
	- `stdout` 仅输出合法 MCP 消息，禁止混入任何日志或调试信息。
	- 日志统一输出至 `stderr`，避免污染通信通道。

#### 3.2.3 SDK 与实现库选型

- **首选：Python 官方 MCP SDK (`mcp`)**
	- **优势**：
		- 官方维护，与协议规范同步更新，保证最新特性支持（如 `outputSchema`、`annotations` 等）。
		- 提供 `@server.tool()` 等装饰器，声明式定义 Tools/Resources/Prompts，代码简洁。
		- 内置 Stdio 与 HTTP Transport 支持，无需手动处理 JSON-RPC 序列化与生命周期管理。
	- **适用**：本项目的默认实现方案。

- **备选：FastAPI + 自定义协议层**
	- **场景**：需要深度定制 HTTP 行为（如自定义中间件、复杂鉴权流程）或希望学习 MCP 协议底层细节时可考虑。
	- **权衡**：开发成本更高，需自行实现能力协商 (Capability Negotiation)、错误码映射等，且需持续跟进协议版本更新。

- **协议版本**：跟踪 MCP 最新稳定版本（如 `2025-06-18`），在 `initialize` 阶段进行版本协商，确保 Client/Server 兼容性。

#### 3.2.4 对外暴露的工具函数设计 (Tools Design)

Server 通过 `tools/list` 向 Client 注册可调用的工具函数。工具设计应遵循"单一职责、参数明确、输出丰富"原则。

- **核心工具集**：

| 工具名称 | 功能描述 | 典型输入参数 | 输出特点 |
|---------|---------|-------------|---------|
| `query_knowledge_hub` | 主检索入口，执行混合检索 + Rerank，返回最相关片段 | `query: string`, `top_k?: int`, `collection?: string` | 返回带引用的结构化结果 |
| `list_collections` | 列举知识库中可用的文档集合 | 无 | 集合名称、描述、文档数量 |
| `get_document_summary` | 获取指定文档的摘要与元信息 | `doc_id: string` | 标题、摘要、创建时间、标签 |

- **扩展工具（Agentic 演进方向）**：
	- `search_by_keyword` / `search_by_semantic`：拆分独立的检索策略，供 Agent 自主选择。
	- `verify_answer`：事实核查工具，检测生成内容是否有依据支撑。
	- `list_document_sections`：浏览文档目录结构，支持多步导航式检索。

#### 3.2.5 返回内容与引用透明设计 (Response & Citation Design)

MCP 协议的 Tool 返回格式支持多种内容类型（`content` 数组），本项目将充分利用这一特性实现"可溯源"的回答：

- **结构化引用设计**：
	- 每个检索结果片段应包含完整的定位信息：`source_file`（文件名/路径）、`page`（页码，如适用）、`chunk_id`（片段标识）、`score`（相关性分数）。
	- 推荐在返回的 `structuredContent` 中采用统一的 Citation 格式：
		```
		{
		  "answer": "...",
		  "citations": [
		    { "id": 1, "source": "xxx.pdf", "page": 5, "text": "原文片段...", "score": 0.92 },
		    ...
		  ]
		}
		```
	- 同时在 `content` 数组中以 Markdown 格式呈现人类可读的带引用回答（`[1]` 标注），保证 Client 无论是否解析结构化内容都能展示引用。

- **多模态内容返回**：
	- **文本内容 (TextContent)**：默认返回类型，Markdown 格式，支持代码块、列表等富文本。
	- **图像内容 (ImageContent)**：当检索结果关联图像时，Server 读取本地图片文件并编码为 Base64 返回。
		- **格式**：`{ "type": "image", "data": "<base64>", "mimeType": "image/png" }`
		- **工作流程**：数据摄取阶段存储图片本地路径 → 检索命中后 Server 动态读取 → 编码为 Base64 → 嵌入返回消息。
		- **Client 兼容性**：图像展示能力取决于 Client 实现，GitHub Copilot 可能降级处理，Claude Desktop 支持完整渲染。Server 端统一返回 Base64 格式，由 Client 决定如何渲染。

- **Client 适配策略**：
	- **GitHub Copilot (VS Code)**：当前对 MCP 的支持集中在 Tools 调用，返回的 `content` 中的文本会展示给用户。建议以清晰的 Markdown 文本（含引用标注）为主，图像作为补充。
	- **Claude Desktop**：对 MCP Tools/Resources 有完整支持，图像与资源链接可直接渲染。可更激进地使用多模态返回。
	- **通用兼容原则**：始终在 `content` 数组第一项提供纯文本/Markdown 版本的答案，确保最低兼容性；将结构化数据、图像等放在后续项或 `structuredContent` 中，供高级 Client 解析。

### 3.3 可插拔架构设计 (Pluggable Architecture Design)

**目标：** 定义清晰的抽象层与接口契约，使 RAG 链路的每个核心组件都能够独立替换与升级，避免技术锁定，支持低成本的 A/B 测试与环境迁移。

> **术语说明**：本节中的"提供者 (Provider)"、"实现 (Implementation)"指的是完成某项功能的**具体技术方案**，而非传统 Web 架构中的"后端服务器"。例如，LLM 提供者可以是远程的 Azure OpenAI API，也可以是本地运行的 Ollama；向量存储可以是本地嵌入式的 Chroma，也可以是云端托管的 Pinecone。本项目作为本地 MCP Server，通过统一接口对接这些不同的提供者，实现灵活切换。

#### 3.3.1 设计原则

- **接口隔离 (Interface Segregation)**：为每类组件定义最小化的抽象接口，上层业务逻辑仅依赖接口而非具体实现。
- **配置驱动 (Configuration-Driven)**：通过统一配置文件（如 `settings.yaml`）指定各组件的具体后端，代码无需修改即可切换实现。
- **工厂模式 (Factory Pattern)**：使用工厂函数根据配置动态实例化对应的实现类，实现"一处配置，处处生效"。
- **优雅降级 (Graceful Fallback)**：当首选后端不可用时，系统应自动回退到备选方案或安全默认值，保障可用性。

**通用结构示意（适用于 3.3.2 / 3.3.3 / 3.3.4 等可插拔组件）**：

```
业务代码
  │
  ▼
<Component>Factory.get_xxx()  ← 读取配置，决定用哪个实现
  │
  ├─→ ImplementationA()
  ├─→ ImplementationB()  
  └─→ ImplementationC()
      │
      ▼
    都实现了统一的抽象接口
```

#### 3.3.2 LLM 与 Embedding 提供者抽象

这是可插拔设计的核心环节，因为模型提供者的选择直接影响成本、性能与隐私合规。

- **统一接口层 (Unified API Abstraction)**：
	- **设计思路**：无论底层使用 Azure OpenAI、OpenAI 原生 API、DeepSeek 还是本地 Ollama，上层调用代码应保持一致。
	- **关键抽象**：
		- `LLMClient`：暴露 `chat(messages) -> response` 方法，屏蔽不同 Provider 的认证方式与请求格式差异。
		- `EmbeddingClient`：暴露 `embed(texts) -> vectors` 方法，统一处理批量请求与维度归一化。

- **提供者选项与切换场景**：

| 提供者类型 | 典型场景 | 配置切换点 |
|---------|---------|-----------|
| **Azure OpenAI** | 企业合规、私有云部署、区域数据驻留 | `provider: azure`, `endpoint`, `api_key`, `deployment_name` |
| **OpenAI 原生** | 通用开发、最新模型尝鲜 | `provider: openai`, `api_key`, `model` |
| **DeepSeek / 其他云端** | 成本优化、特定语言优化 | `provider: deepseek`, `api_key`, `model` |
| **Ollama / vLLM (本地)** | 完全离线、隐私敏感、无 API 成本 | `provider: ollama`, `base_url`, `model` |

- **技术选型建议**：
	- 本项目采用自研的 `BaseLLM` / `BaseEmbedding` 抽象基类，配合工厂模式（`llm_factory.py` / `embedding_factory.py`）实现统一调用接口。已内置 Azure OpenAI、OpenAI、Ollama、DeepSeek 四种 Provider 适配。
	- 对于其他 Provider，可通过 **OpenAI-Compatible 模式**接入（设置自定义 `api_base`），或实现 `BaseLLM` 接口并在工厂中注册。

	- 对于企业级需求，可在其基础上增加统一的 **重试、限流、日志** 中间层，提升生产可靠性，但本项目暂不实现，这里仅提供思路。
	- **Vision LLM 扩展**：针对图像描述生成（Image Captioning）需求，系统扩展了 `BaseVisionLLM` 接口，支持文本+图片的多模态输入。当前实现：
		- **Azure OpenAI Vision**（GPT-4o/GPT-4-Vision）：企业级合规部署，支持复杂图表解析，与 Azure 生态深度集成。

#### 3.3.3 检索策略抽象

检索层的可插拔性决定了系统在不同数据规模与查询模式下的适应能力。

**设计模式：抽象工厂模式**

与 3.3.2 节的 LLM 抽象类似，检索层各组件的可插拔性同样依赖两层设计：

1. **自研的统一抽象接口**：本项目为向量数据库（`BaseVectorStore`）、Embedding（`BaseEmbedding`）、分块（`BaseSplitter`）等核心组件定义了统一的抽象基类，不同实现只需遵循相同接口即可无缝替换。

2. **工厂函数路由**：每个抽象层配套工厂函数（如 `embedding_factory.py`、`splitter_factory.py`），根据 `settings.yaml` 中的配置字段自动实例化对应实现，实现"改配置不改代码"的切换体验。


通用的“配置驱动 + 工厂路由”结构示意见 3.3.1 节。

下面分别说明各组件如何应用这一模式：

---

**1. 分块策略 (Chunking Strategy)**

分块是 Ingestion Pipeline 的核心环节之一，决定了文档如何被切分为适合检索的语义单元。本项目的 Splitter 层采用可插拔设计（BaseSplitter 抽象接口 + SplitterFactory 工厂），不同分块实现只需遵循相同接口即可无缝替换。

常见的分块策略包括：
- **固定长度切分**：按字符数或 Token 数切分，简单但可能破坏语义完整性。
- **递归字符切分**：按层级分隔符（段落→句子→字符）递归切分，在长度限制内尽量保持语义边界。
- **语义切分**：利用 Embedding 相似度检测语义断点，确保每个 Chunk 是自包含的语义单元。
- **结构感知切分**：根据文档结构（Markdown 标题、代码块、列表等）进行切分。

本项目当前采用 **LangChain 的 `RecursiveCharacterTextSplitter`** 进行切分，该方法对 Markdown 文档的结构（标题、段落、列表、代码块）有天然的适配性，能够通过配置语义断点（Separators）实现高质量、语义完整的切块。

> **当前实现说明**：目前系统使用 LangChain RecursiveCharacterTextSplitter。架构设计上预留了切换能力，如需切换为 SentenceSplitter、SemanticSplitter 或自定义切分器，只需实现 BaseSplitter 接口并在配置中指定即可。

---

**2. 向量数据库 (Vector Store)**

本项目自定义了统一的 BaseVectorStore 抽象接口，暴露 .add()、.query()、.delete() 等方法。所有向量数据库后端（Chroma、Qdrant、Pinecone 等）只需实现该接口即可插拔替换，通过 VectorStoreFactory 根据配置自动选择具体实现。

本项目选用 **Chroma** 作为向量数据库。相比 Qdrant、Milvus、Weaviate 等需要 Docker 容器或分布式架构支撑的方案，Chroma 采用嵌入式设计，`pip install chromadb` 即可使用，无需额外部署数据库服务，非常适合本地开发与快速原型验证。同时 ChromaStore 适配器（src/libs/vector_store/chroma_store.py），与 Pipeline 无缝集成。

> **当前实现说明**：目前系统仅实现了 Chroma 后端。虽然架构设计上预留了工厂模式以支持未来扩展，但当前版本尚未实现其他向量数据库的适配器。

---

**3. 向量编码策略 (Embedding Strategy)**

向量编码是 Ingestion Pipeline 的关键环节，决定了 Chunk 如何被转换为可检索的向量表示。本项目自定义了 BaseEmbedding 抽象接口（src/libs/embedding/base.py），支持不同 Embedding 模型的可插拔替换。

常见的编码策略包括：
- **纯稠密编码（Dense Only）**：仅生成语义向量，适合通用场景。
- **纯稀疏编码（Sparse Only）**：仅生成关键词权重向量，适合精确匹配场景。
- **双路编码（Dense + Sparse）**：同时生成稠密向量和稀疏向量，为混合检索提供数据基础。

本项目当前采用 **双路编码（Dense + Sparse）** 策略：
- **Dense Embeddings（语义向量）**：调用 Embedding 模型（如 OpenAI text-embedding-3）生成高维浮点向量，捕捉文本的深层语义关联。
- **Sparse Embeddings（稀疏向量）**：利用 BM25 编码器生成稀疏向量（Keyword Weights），捕捉精确的关键词匹配信息。

存储时，Dense Vector 和 Sparse Vector 与 Chunk 原文、Metadata 一起原子化写入向量数据库，确保检索时可同时利用两种向量。

> **当前实现说明**：目前系统实现了 Dense + Sparse 双路编码。架构设计上预留了切换能力，如需使用其他 Embedding 模型（如 BGE、Ollama 本地模型）或调整编码策略，可在 Pipeline 中替换相应组件。

---

**4. 召回策略 (Retrieval Strategy)**

召回策略决定了查询阶段如何从知识库中检索相关内容。基于 Ingestion 阶段存储的向量类型，可采用不同的召回方案：
- **纯稠密召回（Dense Only）**：仅使用语义向量进行相似度匹配。
- **纯稀疏召回（Sparse Only）**：仅使用 BM25 进行关键词匹配。
- **混合召回（Hybrid）**：并行执行稠密和稀疏两路召回，再通过融合算法合并结果。
- **混合召回 + 精排（Hybrid + Rerank）**：在混合召回基础上，增加精排步骤进一步提升相关性。

本项目当前采用 **混合召回 + 精排（Hybrid + Rerank）** 策略：
- **稠密召回（Dense Route）**：计算 Query Embedding，在向量库中进行 Cosine Similarity 检索，返回 Top-N 语义候选。
- **稀疏召回（Sparse Route）**：使用 BM25 算法检索倒排索引，返回 Top-N 关键词候选。
- **融合（Fusion）**：使用 RRF (Reciprocal Rank Fusion) 算法将两路结果合并排序。
- **精排（Rerank）**：对融合后的候选集进行重排序，支持 None / Cross-Encoder / LLM Rerank 三种模式。

> **当前实现说明**：目前系统实现了 Hybrid + Rerank 策略。架构设计上预留了策略切换能力，如需使用纯稠密或纯稀疏召回，可通过配置切换；融合算法和 Reranker 同样支持替换。

#### 3.3.4 评估框架抽象

评估体系的可插拔性确保团队可以根据业务目标灵活选择或组合不同的质量度量维度。

- **设计思路**：
	- 定义统一的 `Evaluator` 接口，暴露 `evaluate(query, retrieved_chunks, generated_answer, ground_truth) -> metrics` 方法。
	- 各评估框架实现该接口，输出标准化的指标字典。

- **可选评估框架**：

| 框架 | 特点 | 适用场景 |
|-----|------|---------|
| **Ragas** | RAG 专用、指标丰富（Faithfulness, Answer Relevancy, Context Precision 等） | 全面评估 RAG 质量、学术对比 |
| **DeepEval** | LLM-as-Judge 模式、支持自定义评估标准 | 需要主观质量判断、复杂业务规则 |
| **自定义指标** | Hit Rate, MRR, Latency P99 等基础工程指标 | 快速回归测试、上线前 Sanity Check |

- **组合与扩展**：
	- 评估模块设计为**组合模式**，可同时挂载多个 Evaluator，生成综合报告。
	- 配置示例：`evaluation.backends: [ragas, custom_metrics]`，系统并行执行并汇总结果。

#### 3.3.5 配置管理与切换流程

- **配置文件结构示例** (`config/settings.yaml`)：
	```yaml
	llm:
	  provider: azure  # azure | openai | ollama | deepseek
	  model: gpt-4o
	  # provider-specific configs...
	
	embedding:
	  provider: openai
	  model: text-embedding-3-small
	
	vector_store:
	  backend: chroma  # chroma | qdrant | pinecone
	
	retrieval:
	  sparse_backend: bm25  # bm25 | elasticsearch
	  fusion_algorithm: rrf  # rrf | weighted_sum
	  rerank_backend: cross_encoder  # none | cross_encoder | llm
	
	evaluation:
	  backends: [ragas, custom_metrics]
	
	dashboard:
	  enabled: true
	  port: 8501
	  traces_dir: ./logs
	```

- **切换流程**：

	1. 修改 `settings.yaml` 中对应组件的 `backend` / `provider` 字段。
	2. 确保新后端的依赖已安装、凭据已配置。
	3. 重启服务，工厂函数自动加载新实现，无需修改业务代码。

### 3.4 可观测性与可视化管理平台设计 (Observability & Visual Management Platform Design)

**目标：** 针对 RAG 系统常见的"黑盒"问题，设计全链路可观测的追踪体系与完整的可视化管理平台。覆盖 **Ingestion（摄取链路）** 与 **Query（查询链路）** 两条完整流水线的追踪记录，同时提供数据浏览、文档管理、组件概览等管理功能，使整个系统**透明可见**、**可管理**且**可量化**。

#### 3.4.1 设计理念

- **双链路全覆盖追踪 (Dual-Pipeline Tracing)**：
    - **Ingestion Trace**：以 `trace_id` 为核心，记录一次摄取从文件加载到存储完成的全过程（load → split → transform → embed → upsert），包含各阶段耗时、处理的 chunk 数量、跳过/失败详情。
    - **Query Trace**：以 `trace_id` 为核心，记录一次查询从 Query 输入到 Response 输出的全过程（query_processing → dense → sparse → fusion → rerank），包含各阶段候选数量、分数分布与耗时。
- **透明可回溯 (Transparent & Traceable)**：每个阶段的中间状态都被记录，开发者可以清晰看到"系统为什么召回了这些文档"、"Rerank 前后排名如何变化"，从而精准定位问题。
- **低侵入性 (Low Intrusiveness)**：追踪逻辑与业务逻辑解耦，通过 `TraceContext` 显式调用模式注入，避免污染核心代码。
- **轻量本地化 (Lightweight & Local)**：采用结构化日志 + 本地 Dashboard 的方案，零外部依赖，开箱即用。
- **动态组件感知 (Dynamic Component Awareness)**：Dashboard 基于 Trace 中的 `method`/`provider`/`details` 字段动态渲染，更换可插拔组件后自动适配展示内容，无需修改 Dashboard 代码。


#### 3.4.2 追踪数据结构

系统定义两类 Trace 记录，分别覆盖查询与摄取两条链路：

**A. Query Trace（查询追踪）**

每次查询请求生成唯一的 `trace_id`，记录从 Query 输入到 Response 输出的全过程：

**基础信息**：
- `trace_id`：请求唯一标识
- `trace_type`：`"query"`
- `timestamp`：请求时间戳
- `user_query`：用户原始查询
- `collection`：检索的知识库集合

**各阶段详情 (Stages)**：

| 阶段 | 记录内容 |
|-----|---------|
| **Query Processing** | 原始 Query、改写后 Query（若有）、提取的关键词、method、耗时 |
| **Dense Retrieval** | 返回的 Top-N 候选及相似度分数、provider、耗时 |
| **Sparse Retrieval** | 返回的 Top-N 候选及 BM25 分数、method、耗时 |
| **Fusion** | 融合后的统一排名、algorithm、耗时 |
| **Rerank** | 重排后的最终排名及分数、backend、是否触发 Fallback、耗时 |

**汇总指标**：
- `total_latency`：端到端总耗时
- `top_k_results`：最终返回的 Top-K 文档 ID
- `error`：异常信息（若有）

**评估指标 (Evaluation Metrics)**：
- `context_relevance`：召回文档与 Query 的相关性分数
- `answer_faithfulness`：生成答案与召回文档的一致性分数（若有生成环节）

**B. Ingestion Trace（摄取追踪）**

每次文档摄取生成唯一的 `trace_id`，记录从文件加载到存储完成的全过程：

**基础信息**：
- `trace_id`：摄取唯一标识
- `trace_type`：`"ingestion"`
- `timestamp`：摄取开始时间
- `source_path`：源文件路径
- `collection`：目标集合名称

**各阶段详情 (Stages)**：

| 阶段 | 记录内容 |
|-----|---------|
| **Load** | 文件大小、解析器（method: markitdown）、提取的图片数、耗时 |
| **Split** | splitter 类型（method）、产出 chunk 数、平均 chunk 长度、耗时 |
| **Transform** | 各 transform 名称与处理详情（refined/enriched/captioned 数量）、LLM provider、耗时 |
| **Embed** | embedding provider、batch 数、向量维度、dense + sparse 编码耗时 |
| **Upsert** | 存储后端（method: chroma）、upsert 数量、BM25 索引更新、图片存储、耗时 |

**汇总指标**：
- `total_latency`：端到端总耗时
- `total_chunks`：最终存储的 chunk 数量
- `total_images`：处理的图片数量
- `skipped`：跳过的文件/chunk 数（已存在、未变更等）
- `error`：异常信息（若有）


#### 3.4.3 技术方案：结构化日志 + 本地 Web Dashboard

本项目采用 **"结构化日志 + 本地 Web Dashboard"** 作为可观测性的实现方案。

**选型理由**：
- **零外部依赖**：不依赖 LangSmith、LangFuse 等第三方平台，无需网络连接与账号注册，完全本地化运行。
- **轻量易部署**：仅需 Python 标准库 + 一个轻量 Web 框架（如 Streamlit），`pip install` 即可使用，无需 Docker 或数据库服务。
- **学习成本低**：结构化日志是通用技能，调试时可直接用 `jq`、`grep` 等命令行工具查询；Dashboard 代码简单直观，便于理解与二次开发。
- **契合项目定位**：本项目面向本地 MCP Server 场景，单用户、单机运行，无需分布式追踪或多租户隔离等企业级能力。

**实现架构**：

```
RAG Pipeline
    │
    ▼
Trace Collector (装饰器/回调)
    │
    ▼
JSON Lines 日志文件 (logs/traces.jsonl)
    │
    ▼
本地 Web Dashboard (Streamlit)
    │
    ▼
按 trace_id 查看各阶段详情与性能指标
```

**核心组件**：
- **结构化日志层**：基于 Python `logging` + JSON Formatter，将每次请求的 Trace 数据以 JSON Lines 格式追加写入本地文件。每行一条完整的请求记录，包含 `trace_id`、各阶段详情与耗时。
- **本地 Web Dashboard**：基于 Streamlit 构建的轻量级 Web UI，读取日志文件并提供交互式可视化。核心功能是按 `trace_id` 检索并展示单次请求的完整追踪链路。

#### 3.4.4 追踪机制实现

为确保各 RAG 阶段（可替换、可自定义）都能输出统一格式的追踪日志，系统采用 **TraceContext（追踪上下文）** 作为核心机制。

**工作原理**：

1. **请求开始**：Pipeline 入口创建一个 `TraceContext` 实例，生成唯一 `trace_id`，记录请求基础信息（Query、Collection 等）。

2. **阶段记录**：`TraceContext` 提供 `record_stage()` 方法，各阶段执行完毕后调用该方法，传入阶段名称、耗时、输入输出等数据。

3. **请求结束**：调用 `trace.finish()`，`TraceContext` 将收集的完整数据序列化为 JSON，追加写入日志文件。

**与可插拔组件的配合**：
- 各阶段组件（Retriever、Reranker 等）的接口约定中包含 `TraceContext` 参数。
- 组件实现者在执行核心逻辑后，调用 `trace.record_stage()` 记录本阶段的关键信息。
- 这是**显式调用**模式：不强制、不会因未调用而报错，但依赖开发者主动记录。好处是代码透明，开发者清楚知道哪些数据被记录；代价是需要开发者自觉遵守约定。

**阶段划分原则**：
- **Stage 是固定的通用大类**：`retrieval`（检索）、`rerank`（重排）、`generation`（生成）等，不随具体实现方案变化。
- **具体实现是阶段内部的细节**：在 `record_stage()` 中通过 `method` 字段记录采用的具体方法（如 `bm25`、`hybrid`），通过 `details` 字段记录方法相关的细节数据。
- 这样无论底层方案怎么替换，阶段结构保持稳定，Dashboard 展示逻辑无需调整。

#### 3.4.5 Dashboard 功能设计（六页面架构）

Dashboard 基于 Streamlit 构建多页面应用（`st.navigation`），提供六大功能页面：

**页面 1：系统总览 (Overview)**
- **组件配置卡片**：读取 `Settings`，展示当前可插拔组件的配置状态：
    - LLM：provider + model（如 `azure / gpt-4o`）
    - Embedding：provider + model + 维度
    - Splitter：类型 + chunk_size + overlap
    - Reranker：backend + model（或 None）
    - Evaluator：已启用的 backends 列表
- **数据资产统计**：调用 `DocumentManager.get_collection_stats()` 展示各集合的文档数、chunk 数、图片数。
- **系统健康指标**：最近一次 Ingestion/Query trace 的时间与耗时。

**页面 2：数据浏览器 (Data Browser)**
- **文档列表视图**：展示已摄入的文档（source_path、集合、chunk 数、摄入时间），支持按集合筛选与关键词搜索。
- **Chunk 详情视图**：点击文档展开其所有 chunk，每个 chunk 显示：
    - 原文内容（可折叠长文本）
    - Metadata 各字段（title、summary、tags、page、image_refs 等）
    - 关联图片预览（从 ImageStorage 读取并展示缩略图）
- **数据来源**：通过 `ChromaStore.get_all()` 或 `get_by_metadata()` 读取 chunk 数据。

**页面 3：Ingestion 管理 (Ingestion Manager)**
- **文件选择与摄取触发**：
    - 文件上传组件（`st.file_uploader`）或目录路径输入
    - 选择目标集合（下拉选择或新建）
    - 点击"开始摄取"按钮触发 `IngestionPipeline.run()`
    - 利用 `on_progress` 回调驱动 Streamlit 进度条（`st.progress`），实时显示当前阶段与处理进度
- **文档删除**：
    - 在文档列表中提供"删除"按钮
    - 调用 `DocumentManager.delete_document()` 协调跨存储删除
    - 删除完成后刷新列表
- **注意**：Pipeline 执行为同步阻塞操作，Streamlit 的 rerun 机制天然支持（进度条在同一 request 中更新）。

**页面 4：Ingestion 追踪 (Ingestion Traces)**
- **摄取历史列表**：按时间倒序展示 `trace_type == "ingestion"` 的历史记录，显示文件名、集合、总耗时、状态（成功/失败）。
- **单次摄取详情**：
    - **阶段耗时瀑布图**：横向条形图展示 load/split/transform/embed/upsert 各阶段时间分布。
    - **处理统计**：chunk 数、图片数、跳过数、失败数。
    - **各阶段详情展开**：点击查看 method/provider、输入输出样本。

**页面 5：Query 追踪 (Query Traces)**
- **查询历史列表**：按时间倒序展示 `trace_type == "query"` 的历史记录，支持按 Query 关键词筛选。
- **单次查询详情**：
    - **耗时瀑布图**：展示 query_processing/dense/sparse/fusion/rerank 各阶段时间分布。
    - **Dense vs Sparse 对比**：并列展示两路召回结果的 Top-N 文档 ID 与分数。
    - **Rerank 前后对比**：展示融合排名与精排后排名的变化（排名跃升/下降标记）。
    - **最终结果表**：展示 Top-K 候选文档的标题、分数、来源。

**页面 6：评估面板 (Evaluation Panel)**
- **评估运行**：选择评估后端（Ragas / Custom / All）与 golden test set，点击运行。
- **指标展示**：以表格和图表展示 hit_rate、mrr、faithfulness 等指标。
- **历史趋势**：对比不同时间的评估结果，观察策略调整的效果。
- **注意**：评估面板在 Phase H 实现，Phase G 完成后该页面显示"评估模块尚未启用"的占位提示。

**Dashboard 技术架构**：

```
src/observability/dashboard/
├── app.py                    # Streamlit 入口，页面导航注册
├── pages/
│   ├── overview.py           # 页面 1：系统总览
│   ├── data_browser.py       # 页面 2：数据浏览器
│   ├── ingestion_manager.py  # 页面 3：Ingestion 管理
│   ├── ingestion_traces.py   # 页面 4：Ingestion 追踪
│   ├── query_traces.py       # 页面 5：Query 追踪
│   └── evaluation_panel.py   # 页面 6：评估面板
└── services/
    ├── trace_service.py      # Trace 数据读取服务（解析 traces.jsonl）
    ├── data_service.py       # 数据浏览服务（封装 ChromaStore/ImageStorage 读取）
    └── config_service.py     # 配置读取服务（封装 Settings 读取与展示）
```

**Dashboard 与 Trace 的数据关系**：
- Dashboard 页面 4/5 读取 `logs/traces.jsonl`（通过 `TraceService`），按 `trace_type` 分类展示。
- Dashboard 页面 1/2/3 直接读取存储层（通过 `DataService` 封装 ChromaStore/ImageStorage/FileIntegrity），不依赖 Trace。
- 所有页面基于 Trace 中 `method`/`provider` 字段动态渲染标签，更换组件后自动适配。


#### 3.4.6 配置示例

```yaml
observability:
  enabled: true
  
  # 日志配置
  logging:
    log_file: logs/traces.jsonl  # JSON Lines 格式日志文件
    log_level: INFO  # DEBUG | INFO | WARNING
  
  # 追踪粒度控制
  detail_level: standard  # minimal | standard | verbose

# Dashboard 管理平台配置
dashboard:
  enabled: true
  port: 8501                     # Streamlit 服务端口
  traces_dir: ./logs             # Trace 日志文件目录
  auto_refresh: true             # 是否自动刷新（轮询新 trace）
  refresh_interval: 5            # 自动刷新间隔（秒）
```


### 3.5 多模态图片处理设计 (Multimodal Image Processing Design)

**目标：** 设计一套完整的图片处理方案，使 RAG 系统能够理解、索引并检索文档中的图片内容，实现"用自然语言搜索图片"的能力，同时保持架构的简洁性与可扩展性。

#### 3.5.1 设计理念与策略选型

多模态 RAG 的核心挑战在于：**如何让纯文本的检索系统"看懂"图片**。业界主要有两种技术路线：

| 策略 | 核心思路 | 优势 | 劣势 |
|-----|---------|------|------|
| **Image-to-Text (图转文)** | 利用 Vision LLM 将图片转化为文本描述，复用纯文本 RAG 链路 | 架构统一、实现简单、成本可控 | 描述质量依赖 LLM 能力，可能丢失视觉细节 |
| **Multi-Embedding (多模态向量)** | 使用 CLIP 等模型将图文统一映射到同一向量空间 | 保留原始视觉特征，支持图搜图 | 需引入额外向量库，架构复杂度高 |

**本项目选型：Image-to-Text（图转文）策略**

选型理由：
- **架构统一**：无需引入 CLIP 等多模态 Embedding 模型，无需维护独立的图像向量库，完全复用现有的文本 RAG 链路（Ingestion → Hybrid Search → Rerank）。
- **语义对齐**：通过 LLM 将图片的视觉信息转化为自然语言描述，天然与用户的文本查询在同一语义空间，检索效果可预期。
- **成本可控**：仅在数据摄取阶段一次性调用 Vision LLM，检索阶段无额外成本。
- **渐进增强**：未来如需支持"图搜图"等高级能力，可在此基础上叠加 CLIP Embedding，无需重构核心链路。

#### 3.5.2 图片处理全流程设计

图片处理贯穿 Ingestion Pipeline 的多个阶段，整体流程如下：

```
原始文档 (PDF/PPT/Markdown)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Loader 阶段：图片提取与引用收集                           │
│  - 解析文档，识别并提取嵌入的图片资源                        │
│  - 为每张图片生成唯一标识 (image_id)                       │
│  - 在文档文本中插入图片占位符/引用标记                       │
│  - 输出：Document (text + metadata.images[])             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Splitter 阶段：保持图文关联                               │
│  - 切分时保留图片引用标记在对应 Chunk 中                     │
│  - 确保图片与其上下文段落保持关联                            │
│  - 输出：Chunks (各自携带关联的 image_refs)                │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Transform 阶段：图片理解与描述生成                         │
│  - 调用 Vision LLM 对每张图片生成结构化描述                  │
│  - 将描述文本注入到关联 Chunk 的正文或 Metadata 中           │
│  - 输出：Enriched Chunks (含图片语义信息)                  │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Storage 阶段：双轨存储                                    │
│  - 向量库：存储增强后的 Chunk (含图片描述) 用于检索           │
│  - 文件系统/Blob：存储原始图片文件用于返回展示                │
└─────────────────────────────────────────────────────────┘
```

#### 3.5.3 各阶段技术要点

**1. Loader 阶段：图片提取与引用收集**

- **提取策略**：
  - 解析文档时识别嵌入的图片资源（PDF 中的 XObject、PPT 中的媒体文件、Markdown 中的 `![]()` 引用）。
  - 为每张图片生成全局唯一的 `image_id`（建议格式：`{doc_hash}_{page}_{seq}`）。
  - 将图片二进制数据提取并暂存，记录其在原文档中的位置信息。

- **引用标记**：
  - 在转换后的 Markdown 文本中，于图片原始位置插入占位符（如 `[IMAGE: {image_id}]`）。
  - 在 Document 的 Metadata 中维护 `images` 列表，记录每张图片的 `image_id`、原始路径、页码、尺寸等基础信息。

- **存储原始图片**：
  - 将提取的图片保存至本地文件系统的约定目录（如 `data/images/{collection}/{image_id}.png`）。
  - 仅保存需要的图片格式（推荐统一转换为 PNG/JPEG），控制存储体积。

**2. Splitter 阶段：保持图文关联**

- **关联保持原则**：
  - 图片引用标记应与其说明性文字（Caption、前后段落）尽量保持在同一 Chunk 中。
  - 若图片出现在章节开头或结尾，切分时应将其归入语义上最相关的 Chunk。

- **Chunk Metadata 扩展**：
  - 每个 Chunk 的 Metadata 中增加 `image_refs: List[image_id]` 字段，记录该 Chunk 关联的图片列表。
  - 此字段用于后续 Transform 阶段定位需要处理的图片，以及检索命中后定位需要返回的图片。

**3. Transform 阶段：图片理解与描述生成**

这是多模态处理的核心环节，负责将视觉信息转化为可检索的文本语义。

- **Vision LLM 选型**：

| 模型 | 提供商 | 特点 | 适用场景 | 推荐指数 |
|-----|--------|------|---------|---------|
| **GPT-4o** | OpenAI / Azure | 理解能力强，支持复杂图表解读，英文文档表现优异 | 高质量需求、复杂业务文档、国际化场景 | ⭐⭐⭐⭐⭐ |
| **Qwen-VL-Max** | 阿里云 (DashScope) | 中文理解能力出色，性价比高，对中文图表/文档支持好 | 中文文档、国内部署、成本敏感场景 | ⭐⭐⭐⭐⭐ |
| **Qwen-VL-Plus** | 阿里云 (DashScope) | 速度更快，成本更低，适合大批量处理 | 大批量中文文档、快速迭代场景 | ⭐⭐⭐⭐ |
| **Claude 3.5 Sonnet** | Anthropic | 多模态原生支持，长上下文 | 需要结合大段文字理解图片 | ⭐⭐⭐⭐ |
| **Gemini Pro Vision** | Google | 成本较低，速度较快 | 大批量处理、成本敏感场景 | ⭐⭐⭐ |
| **GLM-4V** | 智谱 AI (ZhipuAI) | 国内老牌，稳定性好，中文支持佳 | 国内部署备选、企业级应用 | ⭐⭐⭐⭐ |

**双模型选型策略（推荐）**：

本项目采用**国内 + 国外双模型**方案，通过配置切换，兼顾不同部署环境和文档类型：

| 部署环境 | 主选模型 | 备选模型 | 说明 |
|---------|---------|---------|------|
| **国际化 / Azure 环境** | GPT-4o (Azure) | Qwen-VL-Max | 英文文档优先用 GPT-4o，中文文档可切换 Qwen-VL |
| **国内部署 / 纯中文场景** | Qwen-VL-Max | GPT-4o | 中文图表理解用 Qwen-VL，特殊需求可切换 GPT-4o |
| **成本敏感 / 大批量** | Qwen-VL-Plus | Gemini Pro Vision | 牺牲部分质量换取速度和成本 |

**选型理由**：

1. **GPT-4o (国外首选)**：
   - 视觉理解能力业界领先，复杂图表解读准确率高
   - Azure 部署可满足企业合规要求
   - 英文技术文档理解效果最佳

2. **Qwen-VL-Max (国内首选)**：
   - 中文场景下表现与 GPT-4o 接近，部分中文图表任务甚至更优
   - 通过阿里云 DashScope API 调用，国内访问稳定、延迟低
   - 价格约为 GPT-4o 的 1/3 ~ 1/5，性价比极高
   - 原生支持中文 OCR，对中文截图、表格识别更准确

- **描述生成策略**：
  - **结构化 Prompt**：设计专用的图片理解 Prompt，引导 LLM 输出结构化描述，而非自由发挥。
  - **上下文感知**：将图片的前后文本段落一并传入 Vision LLM，帮助其理解图片在文档中的语境与作用。
  - **分类型处理**：针对不同类型的图片采用差异化的理解策略：

| 图片类型 | 理解重点 | Prompt 引导方向 |
|---------|---------|----------------|
| **流程图/架构图** | 节点、连接关系、流程逻辑 | "描述这张图的结构和流程步骤" |
| **数据图表** | 数据趋势、关键数值、对比关系 | "提取图表中的关键数据和结论" |
| **截图/UI** | 界面元素、操作指引、状态信息 | "描述截图中的界面内容和关键信息" |
| **照片/插图** | 主体对象、场景、视觉特征 | "描述图片中的主要内容" |

- **描述注入方式**：
  - **推荐：注入正文**：将生成的描述直接替换或追加到 Chunk 正文中的图片占位符位置，格式如 `[图片描述: {caption}]`。这样描述会被 Embedding 覆盖，可被直接检索。
  - **备选：注入 Metadata**：将描述存入 `chunk.metadata.image_captions` 字段。需确保检索时该字段也被索引。

- **幂等与增量处理**：
  - 为每张图片的描述计算内容哈希，存入 `processing_cache` 表。
  - 重复处理时，若图片内容未变且 Prompt 版本一致，直接复用缓存的描述，避免重复调用 Vision LLM。

**4. Storage 阶段：双轨存储**

- **向量库存储（用于检索）**：
  - 存储增强后的 Chunk，其正文已包含图片描述，Metadata 包含 `image_refs` 列表。
  - 检索时通过文本相似度即可命中包含相关图片描述的 Chunk。

- **原始图片存储（用于返回）**：
  - 图片文件存储于本地文件系统，路径记录在独立的 `images` 索引表中。
  - 索引表字段：`image_id`, `file_path`, `source_doc`, `page`, `width`, `height`, `mime_type`。
  - 检索命中后，根据 Chunk 的 `image_refs` 查询索引表，获取图片文件路径用于返回。

#### 3.5.4 检索与返回流程

当用户查询命中包含图片的 Chunk 时，系统需要将图片与文本一并返回：

```
用户查询: "系统架构是什么样的？"
    │
    ▼
Hybrid Search 命中 Chunk（正文含 "[图片描述: 系统采用三层架构...]"）
    │
    ▼
从 Chunk.metadata.image_refs 获取关联的 image_id 列表
    │
    ▼
查询 images 索引表，获取图片文件路径
    │
    ▼
读取图片文件，编码为 Base64
    │
    ▼
构造 MCP 响应，包含 TextContent + ImageContent
```

**MCP 响应格式**：

```json
{
  "content": [
    {
      "type": "text",
      "text": "根据文档，系统架构如下：...\n\n[1] 来源: architecture.pdf, 第5页"
    },
    {
      "type": "image",
      "data": "<base64-encoded-image>",
      "mimeType": "image/png"
    }
  ]
}
```

#### 3.5.5 质量保障与边界处理

- **描述质量检测**：
  - 对生成的描述进行基础质量检查（长度、是否包含关键信息）。
  - 若描述过短或 LLM 返回"无法识别"，标记该图片为 `low_quality`，可选择人工复核或跳过索引。

- **大尺寸/特殊图片处理**：
  - 超大图片在传入 Vision LLM 前进行压缩（保持宽高比，限制最大边长）。
  - 对于纯装饰性图片（如分隔线、背景图），可通过尺寸或位置规则过滤，不进入描述生成流程。

- **批量处理优化**：
  - 图片描述生成支持批量异步调用，提高吞吐量。
  - 单个文档处理失败时，记录失败的图片 ID，不影响其他图片的处理进度。

- **降级策略**：
  - 当 Vision LLM 不可用时，系统回退到"仅保留图片占位符"模式，图片不参与检索但不阻塞 Ingestion 流程。
  - 在 Chunk 中标记 `has_unprocessed_images: true`，后续可增量补充描述。
