# 项目技术知识库 — 面试官参考手册

> 本文件供面试官（AI Agent）使用，包含本项目的关键实现细节、高频面试题及参考答案。
> 面试过程中用于生成精准追问和评估候选人回答质量。

---

## 模块一：Hybrid Search 混合检索

### 核心实现
- **双路并行召回**：Dense（向量语义）+ Sparse（BM25 关键词）同时执行
- **融合算法**：RRF（Reciprocal Rank Fusion）  
  公式：`Score = 1/(k + Rank_Dense) + 1/(k + Rank_Sparse)`，k 通常取 60
- **为什么用 RRF 而不是线性加权**：RRF 无需对不同路的分数值做归一化，对排名稳健，不依赖各路分数的绝对尺度
- **Dense Route**：计算 Query Embedding → Cosine Similarity → Top-N 语义候选
- **Sparse Route**：BM25 倒排索引 → Top-N 关键词候选

### 高频面试题

**Q: 为什么要做 Hybrid Search？BM25 和向量检索各有什么优劣？**  
A: BM25（稀疏检索）擅长精确关键词匹配，对专有名词（如 API 名称、产品型号）效果好；Dense Embedding（稠密检索）擅长语义理解，处理同义词、模糊表达时优势明显。两者互补：BM25 查准率高但泛化差，Dense 泛化好但关键词精确度弱。Hybrid Search 结合两者，用 RRF 融合，平衡 Precision 和 Recall。

**Q: RRF 公式里 k=60 是怎么来的？**  
A: k 是平滑因子，防止排名靠前的文档分数过度高估。k=60 是学术论文（Cormack et al. 2009）中的经验推荐值，实践中通常无需调整。调大 k 会使分数分布更均匀（减弱头部文档优势），调小 k 会使分数差异更大。

**Q: 你们的 BM25 索引存在哪里？IDF 怎么算的？**  
A: BM25 索引元数据存储在 `data/db/bm25/` 目录下（当前用 pickle，可迁移至 SQLite）。IDF 基于语料库中文档频率计算：`IDF(t) = ln((N - df + 0.5) / (df + 0.5) + 1)`，N 是总文档数，df 是包含词 t 的文档数。

---

## 模块二：Reranker 精排

### 核心实现
- **两段式架构**：粗排召回（低成本泛召回）→ 精排过滤（高成本精确排序）
- **支持三种后端**：
  1. `None`：直接返回 RRF Top-K
  2. `Cross-Encoder`：本地 Sentence-Transformers 模型，输入 `[Query, Chunk]` 对打分
  3. `LLM Rerank`：用 LLM 对候选集排序，输出 JSON ranked ids
- **Graceful Fallback**：精排失败/超时时自动回退到 RRF 排名，保证系统可用性

### 高频面试题

**Q: Cross-Encoder 和 Bi-Encoder 的区别？为什么 Cross-Encoder 不能做粗排召回？**  
A: Bi-Encoder（如 Dense Embedding 模型）将 Query 和 Document **分别**编码为向量，再算相似度。可以预先离线计算 Document 向量，查询时只需对比一次，效率高，适合大规模召回。Cross-Encoder 将 Query 和 Document **拼接**后一起输入模型，能捕捉 Query-Document 的交互特征，精度更高，但必须对每对 (Query, Chunk) 实时推理，复杂度 O(n)，不适合大规模召回，只适合对小候选集（10-30 条）精排。

**Q: 精排阶段你们用的什么模型？用 CPU 跑 Cross-Encoder 会有延迟问题吗？**  
A: 支持 Sentence-Transformers 系列的 Cross-Encoder 模型（如 `cross-encoder/ms-marco-MiniLM-L-6-v2`）。CPU 环境下建议候选集 M ≤ 30，设置超时回退，超时后直接用 RRF 结果。

---

## 模块三：Ingestion Pipeline 数据摄取流水线

### 五阶段流程
```
Load → Split → Transform → Embed → Upsert
```

1. **Load**：MarkItDown 将 PDF 转为 canonical Markdown；抽取 metadata（`source_path`, `doc_type`, `title`, `images` 等）；**前置 SHA256 哈希去重**（已处理过的文件直接跳过）
2. **Split**：LangChain `RecursiveCharacterTextSplitter`，按 Markdown 结构（标题/段落/代码块）语义切分，产出带 `chunk_index`/`start_offset` 的 Chunk
3. **Transform**（三个 LLM 增强步骤）：
   - **ChunkRefiner**：LLM 合并逻辑相关但被物理切断的段落，去噪（页眉页脚/乱码）
   - **MetadataEnricher**：LLM 为每个 Chunk 生成 `Title`/`Summary`/`Tags`，注入 metadata
   - **ImageCaptioner**：Vision LLM（GPT-4o）为图片生成文字描述，缝合进 Chunk 正文
4. **Embed**：双路向量化（Dense embedding + BM25 sparse），按内容哈希差量计算（未变更的 Chunk 不重复调用 API）
5. **Upsert**：写入 Chroma 向量库 + BM25 索引，幂等设计

### 幂等性设计
- **chunk_id 生成**：`hash(source_path + section_path + content_hash)` → 确定性哈希，相同内容永远相同 ID
- **为什么不用 UUID**：UUID 随机，重复摄取同一文件会产生重复 chunk；确定哈希保证幂等 Upsert
- **文件级去重**：SHA256 文件哈希 → 查 `ingestion_history.db`，已成功处理直接跳过

### 高频面试题

**Q: ChunkRefiner 做了什么？为什么需要 LLM 来做 Chunking 优化？**  
A: RecursiveCharacterTextSplitter 是按字符边界做物理切分，可能把语义上连续的段落切断（如"问题描述"和"解决方案"分属两个 Chunk）。ChunkRefiner 让 LLM 识别这种情况并合并，同时去除页眉页脚乱码，确保每个 Chunk 是 Self-contained 的语义单元，提高检索精度。

**Q: MetadataEnricher 产出的 Title/Summary/Tags 存在哪里？对检索有什么用？**  
A: 存入 Chunk 的 `metadata` 字段（Chroma 的 document metadata）。检索时可以基于这些字段做 metadata filtering（如按 Tags 过滤），也可以将 Summary 拼入检索文本，提升召回率。Title 还会展示在 Dashboard 数据浏览器中。

**Q: 图片检索是怎么实现的？用户怎么通过文字找到图片？**  
A: Caption 文本被"缝合"进 Chunk 正文（作为 text 的一部分），参与 Embedding。用户查询时，Caption 文本会被向量检索命中。检索命中后，系统从 `image_index.db`（`image_id → 文件路径`映射）读取原始图片文件，编码为 Base64，通过 MCP 返回 `ImageContent` 给 Client，实现"搜文出图"。

---

## 模块四：可插拔架构

### 核心设计
- 6 大组件均有抽象 Base 类：`BaseLoader` / `BaseSplitter` / `BaseTransform` / `BaseEmbedding` / `BaseVectorStore` / `BaseReranker`
- **工厂模式**：各组件通过 Factory 函数根据 YAML 配置实例化，调用方不直接 new 具体实现类
- **配置驱动**：修改 `config/settings.yaml` 即可切换后端，零代码修改

### 新增 Provider 流程（面试经典追问）
1. 新建 `src/libs/{component}/your_provider.py`，继承对应 Base 类，实现接口方法
2. 在对应 Factory 函数中注册新 provider 名称和类映射
3. 在 `config/settings.yaml` 中配置 `provider: your_provider`
4. 只需增量修改，不需要改已有代码

### 当前支持
- LLM：Azure OpenAI / OpenAI / Ollama / DeepSeek
- Embedding：OpenAI / Azure / Ollama
- Vector Store：Chroma（接口预留 Qdrant/Pinecone 替换）
- Reranker：Cross-Encoder / LLM Rerank / None

---

## 模块五：MCP 协议集成

### 核心规范
- **协议**：MCP（Model Context Protocol），基于 JSON-RPC 2.0
- **传输层**：Stdio Transport（Client 以子进程方式启动 Server，双方通过 stdin/stdout 通信）
- **为什么用 Stdio**：零网络依赖，无需端口/鉴权，天然适合私有知识库；stdout 只输出合法 MCP 消息，日志走 stderr

### 暴露的 Tools
| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `query_knowledge_hub` | 主检索入口，Hybrid Search + Rerank | `query`, `top_k?`, `collection?` |
| `list_collections` | 列举可用文档集合 | 无 |
| `get_document_summary` | 获取文档摘要与元信息 | `doc_id` |

### Citation 设计
每个检索结果携带结构化引用：来源文件名、页码、chunk 内容摘要，方便 Client 展示"回答依据"，增强用户对 AI 输出的信任。

### 高频面试题

**Q: MCP 和普通 REST API 有什么区别？**  
A: MCP 是专为 AI Agent 设计的上下文协议，定义了标准的 `tools`/`resources`/`prompts` 接口，任何合规的 MCP Client（Copilot、Claude Desktop 等）都能即插即用，无需定制集成。REST API 需要客户端专门适配，MCP 通过协议标准化消除了这一成本。

**Q: Stdio Transport 有什么局限性？什么情况下需要换 HTTP Transport？**  
A: Stdio 适合本地单进程场景。局限：不支持远程调用（Client 和 Server 必须在同一机器），不支持多 Client 并发连接。如需远程访问、多用户并发或负载均衡，需切换到 HTTP+SSE Transport。

---

## 模块六：文档生命周期管理（DocumentManager）

### 核心功能
- `list_documents(collection?)`：列出已摄入文档（含 chunk 数、图片数、摄入时间）
- `get_document_detail(doc_id)`：查看单文档所有 Chunks + metadata + 关联图片
- `delete_document(source_path, collection)`：**协调删除四路存储**：
  1. Chroma：按 `metadata.source` 删除所有 chunk 向量
  2. BM25 Indexer：移除倒排索引条目
  3. ImageStorage：删除关联图片文件
  4. FileIntegrity（`ingestion_history.db`）：移除处理记录，使文件可重新摄入

### 高频面试题

**Q: 为什么删除文档需要同步操作四个存储？如果其中一个删除失败怎么办？**  
A: 四个存储各自独立维护索引，如果只删 Chroma 但没删 BM25 索引，下次 Hybrid Search 会从 BM25 召回已不存在于 Chroma 的 chunk，造成不一致。FileIntegrity 如果不删，重新摄取同一文件会被认为已处理而跳过。当前实现采用尽力删除策略，各存储独立尝试删除，失败时记录错误但不阻塞其他存储的删除。生产级改进可引入事务记录或两阶段提交。

---

## 模块七：可观测性与追踪系统

### Trace 体系
- **双链路**：Ingestion Trace（Load→Split→Transform→Embed→Upsert 5阶段）+ Query Trace（QueryProcess→DenseRecall→SparseRecall→Fusion→Rerank 5阶段）
- **存储**：JSON Lines 结构化日志，零外部依赖（无需 LangSmith/LangFuse）
- **TraceContext**：显式调用模式，低侵入，记录各阶段耗时、候选数量、分数分布

### Dashboard 6个页面
1. **系统总览**：当前组件配置 + Collection 统计
2. **数据浏览器**：文档/Chunk/图片详情查看
3. **Ingestion 管理**：文件上传、实时进度、文档删除
4. **Ingestion 追踪**：阶段耗时瀑布图
5. **Query 追踪**：Dense/Sparse 召回对比、Rerank 前后排名变化
6. **评估面板**：Ragas 指标、历史趋势

### 动态渲染设计
Dashboard 基于 Trace 中的 `method`/`provider` 字段**动态渲染**，更换可插拔组件后 Dashboard 自动适配，无需修改代码。

---

## 模块八：评估体系

### 指标体系
- **Hit Rate@K**：Top-K 结果中至少有一条命中 Golden Answer 的比例
- **MRR（Mean Reciprocal Rank）**：第一条命中结果的排名倒数均值，衡量头部排序质量
- **Ragas 指标集**：Faithfulness（回答是否基于检索内容）、Answer Relevancy（回答与问题相关性）、Context Precision（检索结果精准度）
- **可插拔**：CompositeEvaluator 支持多评估器并行执行，Ragas / 自定义指标均可挂载

### Golden Test Set
存于 `tests/fixtures/golden_test_set.json`，EvalRunner 基于此进行回归评估，确保每次策略调整（改 Chunk Size / 换 Reranker）都有量化分数对比。

---

## 模块九：工程化实践

### 测试体系
- **分层金字塔**：Unit（单元）→ Integration（集成）→ E2E（端到端）
- **单元测试 mock 策略**：用 `unittest.mock.patch` mock LLM 客户端，返回预设响应，避免实际 API 调用；测试关注业务逻辑而非外部依赖
- **测试覆盖**：1198+ 单元测试 + 30 E2E 全绿
- **E2E 测试**：`tests/e2e/test_mcp_client.py` 启动真实 MCP Server 子进程，发送 JSON-RPC 消息端到端验证

### 持久化存储架构
| 存储 | 文件 | 用途 |
|------|------|------|
| Chroma | `data/db/chroma/` | Dense 向量 + metadata |
| BM25 | `data/db/bm25/` | 稀疏倒排索引 |
| ingestion_history.db | `data/db/` | 文件处理记录（SHA256） |
| image_index.db | `data/db/` | image_id → 文件路径映射 |

**设计原则**：Local-First，零外部数据库依赖，`pip install` 即可运行。

---

## 常见"露馅"警示点

面试中如候选人无法解释以下细节，需在报告中标记：

| 简历描述 | 深挖问题 | 露馅信号 |
|---------|---------|---------|
| "混合检索命中率提升 XX%" | 怎么测的？用什么指标？ | 说不清 Hit Rate@K 定义或无测试数据 |
| "RRF 融合算法" | 公式是什么？k 值怎么设的？ | 无法说出公式，或说成线性加权 |
| "设计可插拔架构" | 新增 Provider 要改哪些文件？ | 不知道抽象接口在哪定义 |
| "幂等 Upsert" | chunk_id 怎么生成的？ | 说是 UUID，或说不清楚 |
| "MCP 协议实现" | Stdio Transport 是怎么工作的？ | 不知道 stdout/stderr 分工 |
| "TDD 开发，1200+ 测试" | 单元测试怎么 mock LLM？ | 不知道 mock 策略 |
| "多模态检索" | Caption 文本怎么参与检索？ | 说不清与正文的关系 |
| "跨存储协调删除" | 删一个文档要操作几个存储？ | 只说 Chroma 或说不知道 |
