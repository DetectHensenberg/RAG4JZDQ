# 项目复习题库 — Modular RAG MCP Server

> 本题库按模块分章节，每道题标注难度（⭐基础 / ⭐⭐进阶 / ⭐⭐⭐深挖）和预估复习时长。
> 老师（Agent）根据用户当前复习章节顺序出题，不随机跳题，确保知识体系完整建立。

---

## 第 1 章：项目全景与设计理念

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 1-01 | 这个项目叫什么名字，整体要解决什么问题？ | ⭐ | 项目定位 | Modular RAG MCP Server，将私有文档知识库暴露为 MCP 标准接口，供 Copilot/Claude 等 AI 助手使用 |
| 1-02 | RAG 是什么？和 Fine-tuning 相比最大的区别是什么？ | ⭐ | RAG 基础 | RAG=检索增强生成，实时检索外部知识，避免重新训练模型；更新成本低，幻觉可追溯 |
| 1-03 | 项目整体分哪几层架构？每层职责是什么？ | ⭐ | 分层设计 | Ingestion Pipeline（摄取）/ Query Engine（检索）/ MCP Server（协议暴露）/ Dashboard（可视化） |
| 1-04 | 为什么不用 LlamaIndex 或 LangChain 等现成框架，而要自研 Pipeline？ | ⭐⭐ | 架构决策 | 完全可控的可插拔架构，避免框架版本/依赖锁定，支持幂等设计、差量计算等自定义工程特性 |
| 1-05 | 项目有哪 5 种可插拔组件？每种举一个具体的可替换例子 | ⭐⭐ | 可插拔架构 | LLM(Azure→Ollama)、Embedding(OpenAI→BGE)、VectorStore(Chroma→Qdrant)、Splitter、Reranker(CrossEncoder→LLM) |
| 1-06 | 这个项目里有哪几类存储后端？各自存什么数据？ | ⭐⭐ | 数据存储 | Chroma(向量+metadata)、SQLite-IngestionHistory(文件哈希)、SQLite-ImageIndex(图片路径)、BM25(倒排索引/pickle)、本地文件(图片) |
| 1-07 | 用户从 Copilot 发问到拿到答案，整个链路经过哪些关键步骤？ | ⭐⭐ | 端到端流程 | Copilot → MCP Host → MCP Server(stdio) → QueryEngine → HybridSearch → Rerank → Response构建 → 返回带引用结果 |
| 1-08 | 项目的幂等性在哪里体现？为什么幂等很重要？ | ⭐⭐⭐ | 工程设计 | 文件Hash检查(早退)、ChunkID用hash组合生成、Upsert语义写入；避免重复索引，支持重跑不污染数据 |

---

## 第 2 章：数据摄取流水线（Ingestion Pipeline）

### 2A：Loader 阶段

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 2A-01 | Loader 阶段的职责是什么？输入输出分别是什么？ | ⭐ | Loader职责 | 输入：原始文件路径；输出：Document对象(text=Markdown + metadata含source_path/doc_type/page/images) |
| 2A-02 | 为什么 Loader 输出的格式选择了 Markdown？ | ⭐⭐ | 技术选型 | 方便配合 RecursiveCharacterTextSplitter 的 Markdown Separators，结构感知切分质量更高 |
| 2A-03 | 前置去重（File Integrity Check）是怎么工作的？用了什么算法？ | ⭐⭐ | 幂等设计 | 计算文件 SHA256 哈希 → 查 SQLite ingestion_history → status='success' 则跳过，实现零成本增量更新 |
| 2A-04 | ingestion_history 表结构有哪些字段？status 有哪几种状态？ | ⭐⭐ | 存储设计 | file_hash(PK)/file_path/file_size/status(success/failed/processing)/processed_at/error_msg/chunk_count |
| 2A-05 | 使用 MarkItDown 解析 PDF 的核心优势是什么？有什么局限？ | ⭐⭐ | 技术选型 | 优势：直接输出 Markdown，与 Splitter 天然兼容；局限：复杂表格/图形可能解析不完整，需 LLM 后处理 |

### 2B：Splitter 阶段

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 2B-01 | 什么是 RecursiveCharacterTextSplitter？它如何做到"语义感知切分"？ | ⭐⭐ | 切分原理 | 按层级分隔符递归尝试：Markdown标题→段落→句子→字符，在 chunk_size 限制内保持最大语义完整性 |
| 2B-02 | Chunk 必须包含哪些定位字段？为什么这些字段很重要？ | ⭐ | 元数据设计 | source/chunk_index/start_offset(或等价定位字段)；支持检索命中后溯源定位，Dashboard 展示原文来源 |
| 2B-03 | 固定长度切分 vs 递归字符切分 vs 语义切分的优缺点各是什么？ | ⭐⭐⭐ | 切分策略比较 | 固定切：简单但破坏语义；递归字符：平衡，当前选择；语义切：质量最高但需Embedding计算，成本高 |
| 2B-04 | chunk_overlap 参数的作用是什么？太大或太小有什么问题？ | ⭐⭐ | 参数影响 | 确保跨边界信息不丢失；太小：边界处语义断裂；太大：冗余数据多、存储成本高 |

### 2C：Transform & Enrichment 阶段

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 2C-01 | Transform 阶段有哪 3 大增强策略？分别解决什么问题？ | ⭐⭐ | 增强策略 | ①智能重组(LLM合并碎片/去噪) ②语义元数据注入(LLM生成Title/Summary/Tags) ③多模态增强(图片Captioning) |
| 2C-02 | 什么是 Image Captioning？为什么用"图转文"而不是多模态向量？ | ⭐⭐ | 多模态策略 | 用Vision LLM描述图片→文字Caption→嵌入Chunk；无需CLIP等多模态库，复用现有文本检索链路，架构统一 |
| 2C-03 | image_index.db 的作用是什么？表里存什么？ | ⭐⭐ | 图片存储 | 存储 image_id → 文件路径映射；检索命中含图片的Chunk时，可通过image_id找到本地图片文件路径 |
| 2C-04 | 语义元数据注入产出的 Title/Summary/Tags 存在哪里？如何影响检索？ | ⭐⭐⭐ | 元数据检索 | 存入 Chunk 的 Metadata 字段；增强 Metadata Filtering 能力；Summary/Tags 也可追加进 Chunk.text 提升语义召回覆盖 |
| 2C-05 | Transform 为什么要设计为"原子化 + 幂等操作"？ | ⭐⭐⭐ | 工程健壮性 | LLM 调用不稳定，原子化支持单 Chunk 独立重试；幂等确保重跑不产生重复处理，支持中断续跑 |

### 2D：Embedding 阶段

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 2D-01 | 什么是 Dense Embedding？什么是 Sparse Embedding？各自的优势是什么？ | ⭐ | 向量基础 | Dense：高维浮点向量，捕捉语义，解决"词不同意同"；Sparse：关键词权重，捕捉精确匹配，解决专有名词 |
| 2D-02 | 为什么要做差量计算（Incremental Embedding）？是怎么实现的？ | ⭐⭐ | 成本优化 | 计算 Chunk 内容哈希(ContentHash)，仅对库中未存在的哈希调用 Embedding API，文件改名不重算 |
| 2D-03 | 批处理（Batch Processing）在 Embedding 阶段如何优化性能？ | ⭐⭐ | 工程优化 | 按 batch_size 分批调用 API，减少网络 RTT；最大化 GPU/CPU 利用率；避免单条高频调用触发限流 |
| 2D-04 | BM25 是什么算法？为什么叫"稀疏向量"？ | ⭐⭐ | BM25原理 | BM25=Best Match 25，基于词频(TF)和逆文档频率(IDF)计算相关性；大多数词权重为0，高维但稀疏 |
| 2D-05 | Embedding 存储时和什么一起原子化写入？为什么要原子化？ | ⭐⭐⭐ | All-in-One存储 | Dense Vector + Sparse Vector + Chunk原文 + Metadata 一起写入；命中后无需二次查库，保证毫秒级响应 |

### 2E：文档生命周期管理

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 2E-01 | DocumentManager 的职责是什么？和 IngestionPipeline 有什么区别？ | ⭐⭐ | 模块边界 | Pipeline处理摄取流；DocumentManager负责摄取后的管理操作(list/detail/delete)，独立于摄取逻辑 |
| 2E-02 | 删除一个文档需要同时清理哪 4 个存储？为什么需要协调删除？ | ⭐⭐⭐ | 跨存储协调 | Chroma(向量)/BM25(倒排索引)/ImageStorage(图片文件)/FileIntegrityDB(哈希记录)；确保无悬空引用，使文件可重新摄入 |
| 2E-03 | on_progress 回调的设计目的是什么？签名是怎样的？ | ⭐⭐ | 接口设计 | 供Dashboard实时展示进度条；签名 `on_progress(stage_name: str, current: int, total: int)`；None 时行为不变 |

---

## 第 3 章：检索查询流水线（Query Pipeline）

### 3A：查询预处理

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 3A-01 | 为什么 Query Engine 假设"输入 Query 已完成会话上下文补全"？这个职责在哪里完成？ | ⭐⭐ | 职责分离 | 历史对话消歧由上游(MCP Client/Host)完成；Query Engine 专注检索，不处理多轮上下文，职责清晰 |
| 3A-02 | 关键词提取（Keyword Extraction）在查询预处理中起什么作用？ | ⭐⭐ | 稀疏检索优化 | 提取实体/动词(去停用词)，生成稀疏检索的Token列表；提升BM25查准率，避免噪声词干扰 |
| 3A-03 | Query Expansion（同义词/别名扩展）的策略是什么？为什么稠密路不扩展？ | ⭐⭐⭐ | 扩展策略 | 扩展词合并进稀疏路(BM25 OR扩展)；稠密路保持单次调用（原始Query语义覆盖足够广，多次调用成本高） |

### 3B：混合检索（Hybrid Search）

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 3B-01 | Hybrid Search 的 Dense Route 和 Sparse Route 分别是什么？各解决什么问题？ | ⭐ | 混合检索基础 | Dense：Embedding相似度匹配语义(词不同意同)；Sparse：BM25关键词匹配(专有名词精确查找) |
| 3B-02 | RRF 算法的公式是什么？为什么用排名而不是分数直接融合？ | ⭐⭐⭐ | RRF原理 | `Score = 1/(k+Rank_Dense) + 1/(k+Rank_Sparse)`；分数量纲不同，直接融合易失衡；排名融合更鲁棒 |
| 3B-03 | 两路检索是并行执行还是串行执行的？为什么？ | ⭐⭐ | 性能设计 | 并行执行；Dense和Sparse彼此独立，并行可减少50%+等待时间 |
| 3B-04 | RRF 中的平滑因子 k 起什么作用？k 值越大越小怎么影响结果？ | ⭐⭐⭐ | 参数理解 | 避免排名1文档分数远高于第2名；k越大，高低排名分数差距越小（更平滑）；通常取k=60 |

### 3C：过滤与重排（Filtering & Reranking）

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 3C-01 | Metadata Filtering 的"先解析、能前置则前置"原则是什么意思？ | ⭐⭐ | 过滤策略 | 硬约束(collection/doc_type)在检索阶段Pre-filter缩小候选集；软偏好/不稳定字段做Post-filter或排序信号 |
| 3C-02 | Reranker 支持哪 3 种后端？默认是哪种？不可用时如何降级？ | ⭐⭐ | Reranker设计 | ①None ②Cross-Encoder(本地/托管) ③LLM Rerank；超时/失败必须回退到RRF排序，保证可用性 |
| 3C-03 | Cross-Encoder 和 Bi-Encoder（Dense Embedding）在架构上有什么区别？ | ⭐⭐⭐ | 模型原理 | Bi-Encoder独立编码Query和Doc(快，离线可用)；Cross-Encoder联合编码[Query,Doc]对(慢但更精准，需实时计算) |
| 3C-04 | 为什么 LLM Rerank 的候选数量要比 Cross-Encoder 更小（M<=20）？ | ⭐⭐⭐ | 成本控制 | LLM 逐对打分 Token 成本高；候选数越大成本指数级增加；需要严格结构化输出(JSON)降低解析风险 |

---

## 第 4 章：MCP 服务设计

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 4-01 | MCP 是什么协议？和普通 REST API 相比有什么优势？ | ⭐ | MCP基础 | Model Context Protocol，标准化 AI 助手与外部工具的对接；无需自建 Chat UI，直接复用 Copilot/Claude 入口 |
| 4-02 | 为什么选择 Stdio Transport 而不是 HTTP？Stdio 的工作方式是什么？ | ⭐⭐ | 传输选型 | Client 以子进程启动 Server，通过 stdin/stdout 交换 JSON-RPC；零配置、隐私安全、无需端口管理 |
| 4-03 | Stdio Transport 有什么严格约束必须遵守？ | ⭐⭐ | 实现约束 | stdout 仅输出合法 MCP 消息，禁止混入日志；日志统一写 stderr，避免污染通信通道 |
| 4-04 | Server 对外暴露哪 3 个核心工具（Tools）？分别是什么？ | ⭐ | 工具设计 | `query_knowledge_hub`(主检索入口) / `list_collections`(列举集合) / `get_document_summary`(获取文档摘要) |
| 4-05 | `query_knowledge_hub` 的返回格式是什么？如何体现"引用透明"？ | ⭐⭐ | 返回设计 | structuredContent 含 citations 数组(source/page/text/score)；content 数组含 Markdown 带[1]标注的人类可读版本 |
| 4-06 | 多模态图片是怎么通过 MCP 返回给 Client 的？Client 侧如何处理？ | ⭐⭐⭐ | 多模态返回 | 检索命中图片 → Server 读本地文件 → Base64 编码 → `{type:image, data:base64, mimeType:image/png}`；Client 决定渲染策略 |
| 4-07 | 为什么 MCP 返回的 content 数组第一项要始终是纯文本/Markdown 版本？ | ⭐⭐ | 兼容性设计 | 最低兼容性保证；不同 Client 的多模态支持能力不同，纯文本是最通用的降级兜底格式 |

---

## 第 5 章：可插拔架构设计

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 5-01 | 工厂模式在这个项目里是怎么实现的？举一个具体文件名 | ⭐⭐ | 工厂模式 | 读取settings.yaml中provider字段 → 工厂函数(如embedding_factory.py)动态实例化对应实现类 |
| 5-02 | 要新增一个 LLM Provider（如 Claude），需要修改哪些文件？不需要修改哪些？ | ⭐⭐⭐ | 扩展点 | 新增Provider实现类(继承BaseLLM) + 在Factory注册 + settings.yaml配置；上层业务代码**不需要修改** |
| 5-03 | `settings.yaml` 里的 `retrieval.rerank_backend` 字段有哪几个合法值？ | ⭐ | 配置结构 | `none` / `cross_encoder` / `llm` |
| 5-04 | Chroma 相对于 Qdrant/Milvus 的核心优势是什么？什么场景考虑换掉它？ | ⭐⭐ | 存储选型 | 嵌入式,pip install即用,零部署；规模到分布式/高并发/多节点时考虑换 Qdrant/Milvus |
| 5-05 | BaseEmbedding 接口最核心的方法是什么？签名是怎样的？ | ⭐⭐ | 接口设计 | `embed(texts: list[str]) -> list[list[float]]`；屏蔽不同Provider的请求格式和批处理差异 |
| 5-06 | 配置驱动切换的流程是什么？需要重启服务吗？ | ⭐ | 配置管理 | 修改settings.yaml对应字段 → 确保依赖已安装 → **重启服务** → 工厂函数自动加载新实现 |

---

## 第 6 章：可观测性与 Dashboard

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 6-01 | 项目里的 Trace 分哪两类？分别记录什么链路的数据？ | ⭐ | Trace设计 | Query Trace(查询链路) + Ingestion Trace(摄取链路)；每种都以trace_id为核心 |
| 6-02 | Query Trace 记录了哪 5 个阶段？每阶段记录了什么关键数据？ | ⭐⭐ | Query Trace | Query Processing(关键词)/Dense(分数)/Sparse(BM25分数)/Fusion(排名)/Rerank(前后排名变化+是否Fallback) |
| 6-03 | Ingestion Trace 记录了哪 5 个阶段？各阶段记录了什么？ | ⭐⭐ | Ingestion Trace | Load(图片数/解析器)/Split(chunk数/平均长度)/Transform(LLM处理量)/Embed(provider/批次/维度)/Upsert(upsert量/BM25更新) |
| 6-04 | Dashboard 有哪 6 个功能页面？各页面的核心功能是什么？ | ⭐⭐ | Dashboard设计 | 系统总览/数据浏览器/Ingestion管理/Query追踪/Ingestion追踪/评估面板 |
| 6-05 | 为什么说 Dashboard 可以"自动适配"更换组件？具体机制是什么？ | ⭐⭐⭐ | 动态渲染 | 基于 Trace 中的 method/provider/details 字段动态渲染；换组件→Trace写新provider名→Dashboard自动展示新内容，无需改UI代码 |
| 6-06 | 全链路白盒化解决了 RAG 系统的什么核心痛点？ | ⭐ | 可观测价值 | 传统 RAG 是"黑盒"，无法知道"为什么选了这些文档"；Trace 让每个中间状态可见，精准定位 Bad Case |

---

## 第 7 章：评估体系

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 7-01 | Hit Rate@K 是什么指标？衡量什么？ | ⭐ | 评估指标 | 在 Top-K 检索结果中，有多少查询至少命中了1个正确文档；衡量召回覆盖率 |
| 7-02 | MRR（Mean Reciprocal Rank）是什么？和 Hit Rate 的区别？ | ⭐⭐ | 评估指标 | MRR 关注正确答案在排名多靠前(`1/Rank`)；Hit Rate 只关注有没有命中；MRR 更关注位置质量 |
| 7-03 | Faithfulness 指标衡量什么？和 Answer Relevancy 有什么区别？ | ⭐⭐ | Ragas指标 | Faithfulness=生成答案是否有检索文档支撑(防幻觉)；Answer Relevancy=答案是否回答了问题 |
| 7-04 | 项目支持哪几个评估框架？如何同时启用多个？ | ⭐⭐ | 评估框架 | Ragas / DeepEval / 自定义指标；配置 `evaluation.backends: [ragas, custom_metrics]` 并行执行并汇总结果 |
| 7-05 | 评估闭环的核心价值是什么？"凭感觉调优"有什么风险？ | ⭐ | 评估价值 | 量化验证每次策略变更(Chunk Size/Reranker更换)的效果；凭感觉可能改了一个指标破坏另一个 |

---

## 第 8 章：测试体系与工程质量

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 8-01 | 项目测试分哪三层？各层的职责是什么？ | ⭐ | 测试分层 | Unit(单元/纯逻辑) / Integration(集成/组件协作) / E2E(端到端/真实链路) |
| 8-02 | 为什么 BM25 要有"roundtrip"测试？这个名字意味着什么？ | ⭐⭐ | 测试策略 | 验证"写入→保存→加载→查询"完整数据往返路径，确保序列化/反序列化没有数据丢失或精度损失 |
| 8-03 | `test_ingestion_pipeline.py` 属于哪层测试？应该测什么？ | ⭐⭐ | 测试定位 | 集成测试；测试 Loader→Splitter→Transform→Embed→Upsert 的组合行为，不Mock核心业务逻辑 |
| 8-04 | `conftest.py` 在 pytest 中的作用是什么？项目里用它来做什么？ | ⭐⭐ | pytest机制 | 定义共享 fixtures（测试夹具）；项目里用来提供测试用配置/Mock对象/临时文件路径等共享测试资源 |
| 8-05 | E2E 测试中的 Dashboard Smoke Test 是如何在不启动真实服务器的情况下测试的？ | ⭐⭐⭐ | 测试工具 | 使用 Streamlit AppTest（无头渲染）；在进程内运行 Dashboard 逻辑，无需实际启动 Web 服务器 |

---

## 第 9 章：存储与持久化架构

| # | 题目 | 难度 | 考察要点 | 参考答案要点 |
|---|------|------|---------|------------|
| 9-01 | 为什么项目选择 SQLite 而不是 MySQL/PostgreSQL？ | ⭐ | 存储选型 | 零依赖部署(pip install)，无需数据库服务；本地优先设计；支持WAL并发；可后续迁移 |
| 9-02 | WAL（Write-Ahead Logging）在 SQLite 中如何保证并发安全？ | ⭐⭐⭐ | 并发机制 | WAL模式下写入先记日志再合并，允许多Reader与1Writer并发；避免传统锁模式下的读写互斥 |
| 9-03 | ChunkID 的生成算法是什么？为什么选择这种方式？ | ⭐⭐ | ID设计 | `hash(source_path + section_path + content_hash)`；确定性生成(无随机)，相同内容永远相同ID，支持幂等Upsert |
| 9-04 | BM25 索引数据当前用什么格式持久化？有什么升级路径？ | ⭐⭐ | BM25持久化 | 当前使用 pickle 序列化；升级路径：迁移至 SQLite 存储倒排索引和IDF统计，提升可靠性和查询灵活性 |
| 9-05 | `delete_document` 操作为什么要清理 FileIntegrityDB？不清理会怎样？ | ⭐⭐⭐ | 数据一致性 | FileIntegrityDB记录"已成功处理"；不清理则下次摄取相同文件时触发早退跳过，无法重新摄入 |

---

## 题库统计

| 章节 | 题数 | ⭐基础 | ⭐⭐进阶 | ⭐⭐⭐深挖 |
|------|------|--------|----------|----------|
| 第1章：项目全景 | 8 | 2 | 4 | 2 |
| 第2章：摄取流水线 | 18 | 3 | 9 | 6 |
| 第3章：检索流水线 | 11 | 2 | 5 | 4 |
| 第4章：MCP服务 | 7 | 2 | 3 | 2 |
| 第5章：可插拔架构 | 6 | 2 | 3 | 1 |
| 第6章：可观测性 | 6 | 2 | 2 | 2 |
| 第7章：评估体系 | 5 | 2 | 2 | 1 |
| 第8章：测试体系 | 5 | 1 | 3 | 1 |
| 第9章：存储架构 | 5 | 1 | 2 | 2 |
| **合计** | **71** | **17** | **33** | **21** |
