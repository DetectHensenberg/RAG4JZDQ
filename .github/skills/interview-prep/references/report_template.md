# 面试报告模板 — 面试官使用手册

> 本文件在 Phase 3 报告生成时读取。包含：①完整报告 Markdown 模板 ②12 道题预置参考答案 ③评分细则。

---

## 一、报告 Markdown 模板

生成规则：
- 表格"参考答案"列使用 `[→ 查看](#a-锚点关键词)` 锚链接，指向本文件第二节对应答案
- 只为**本次实际问到的题目**复制对应答案块，未问到的不放入报告
- 严格按评分细则打分，不得因情绪照顾调分

```markdown
# 模拟面试报告

**项目**：Modular RAG MCP Server
**面试时间**：{datetime}
**评分**：{score}/10

---

## 一、面试记录

> ✅ 答对核心要点 | ⚠️ 方向正确但细节缺失 | ❌ 未能答出或方向错误

### 方向 1：项目综述

| 轮次 | 问题 | 候选人回答摘要 | 评估 | 参考答案 |
|-----|------|-------------|------|---------|
| 1 | {问题原文} | {2-3 句摘要} | ✅/⚠️/❌ | [→ 查看](#a-{锚点}) |
| 2 | ... | ... | ... | [→ 查看](#a-{锚点}) |
| 3 | ... | ... | ... | [→ 查看](#a-{锚点}) |

### 方向 2：简历深挖

| 轮次 | 问题 | 候选人回答摘要 | 评估 | 露馅 | 参考答案 |
|-----|------|-------------|------|-----|---------|
| 1 | {问题原文} | {摘要} | ✅/⚠️/❌ | 是/否 | [→ 查看](#a-{锚点}) |
| 2 | ... | ... | ... | ... | [→ 查看](#a-{锚点}) |
| 3 | ... | ... | ... | ... | [→ 查看](#a-{锚点}) |

### 方向 3：技术深挖

| 轮次 | 问题 | 候选人回答摘要 | 评估 | 参考答案 |
|-----|------|-------------|------|---------|
| 1 | {问题原文} | {摘要} | ✅/⚠️/❌ | [→ 查看](#a-{锚点}) |
| 2 | ... | ... | ... | [→ 查看](#a-{锚点}) |
| 3 | ... | ... | ... | [→ 查看](#a-{锚点}) |

---

## 二、参考答案

> 仅复制本次实际问到的题目对应答案块，保留 <a id> 锚点。

{从下方"预置参考答案库"按需复制}

---

## 三、简历包装点评

### 包装合理 ✅
- **"{简历描述}"**：{说明候选人能自圆其说之处，具体指出哪句回答支撑了该判断}

### 露馅点 ❌
- **"{简历描述}"** → {面试中的具体表现}。**严重性：高/中/低**（{说明原因}）

### 改进建议
- {针对每个露馅点的具体、可操作建议，如"建议背下 RRF 公式并能解释 k 参数含义"}

---

## 四、综合评价

**优势**：
- {具体到哪道题答得好、好在哪个关键点}

**薄弱点**：
- {具体技术点 + 答错/答浅的表现描述}

**面试官建议**：
{针对每个薄弱点的具体改进方向，避免笼统表述}

---

## 五、评分

| 维度 | 分数（满分 10）| 评分依据（必须说明具体扣分原因） |
|-----|--------------|--------------------------------|
| 项目架构掌握 | x | {哪些点答到了，哪些点缺失} |
| 简历真实性 | x | {几处包装合理，几处露馅，差距} |
| 算法理论深度 | x | {RRF/Cross-Encoder/评估指标等作答情况} |
| 实现细节掌握 | x | {chunk_id/可插拔三步骤/MCP Tool 参数等} |
| 表达清晰度 | x | {回答完整性、逻辑清晰度、因果说明} |
| **综合** | **x** | {加权说明} |
```

---

## 二、预置参考答案库

> 按需复制到报告"二、参考答案"节，保留 `<a id>` 锚点不变。

---

### <a id="a-项目架构"></a>Q: 介绍项目整体架构和你具体负责的部分

**参考答案**：
系统分三大层次：
1. **Ingestion 层**：5 阶段流水线（Load → Split → Transform → Embed → Upsert），文档解析、分块、LLM 增强、向量化后写入存储
2. **检索层**：Hybrid Search（BM25 + Dense Embedding 并行召回）→ RRF 融合 → Cross-Encoder 精排
3. **服务层**：MCP Server 封装，Stdio Transport 对外暴露 3 个 Tool，AI Client 可直接调用

核心亮点：全链路可插拔（6 大组件均有 Base 抽象类 + Factory 模式），配置文件驱动零代码切换后端。

---

### <a id="a-ingestion链路"></a>Q: Ingestion 链路有哪些阶段？

**参考答案**：
共 5 个阶段：
1. **Load**：MarkItDown 将 PDF 转为 Markdown，前置 SHA256 文件哈希去重（已处理文件直接跳过）
2. **Split**：LangChain `RecursiveCharacterTextSplitter` 按 Markdown 结构语义切分，产出带 `chunk_index`/`start_offset` 的 Chunk
3. **Transform**（3 个 LLM 增强步骤）：ChunkRefiner（合并语义断裂段落、去噪）→ MetadataEnricher（生成 Title/Summary/Tags）→ ImageCaptioner（Vision LLM 生成图片描述，缝合进 Chunk 正文）
4. **Embed**：BM25 + Dense Embedding 双路向量化，按内容哈希差量计算（未变更 Chunk 不重复调 API）
5. **Upsert**：幂等写入 Chroma 向量库 + BM25 倒排索引

---

### <a id="a-mcp协议"></a>Q: MCP 是什么规范？暴露了哪些 Tool？

**参考答案**：
MCP（Model Context Protocol）是 Anthropic 提出的开放协议，基于 JSON-RPC 2.0，定义 AI Client 与外部工具/数据源之间的标准通信接口。任何合规 Client（Copilot、Claude Desktop）即插即用。

本项目采用 **Stdio Transport**：Client 以子进程启动 Server，stdin/stdout 通信，日志走 stderr，零网络依赖。

对外暴露 3 个 Tool：

| Tool | 功能 | 关键参数 |
|------|------|---------|
| `query_knowledge_hub` | 主检索入口（Hybrid Search + Rerank） | `query`, `top_k?`, `collection?` |
| `list_collections` | 列举可用文档集合 | 无 |
| `get_document_summary` | 获取文档摘要与元信息 | `doc_id` |

每条检索结果携带结构化 Citation（来源文件名、页码、chunk 摘要），可选返回 Base64 图片。

---

### <a id="a-rrf公式"></a>Q: RRF 融合公式是什么？k 值含义？为什么不用线性加权？

**参考答案**：

$$Score_{RRF}(d) = \frac{1}{k + Rank_{Dense}(d)} + \frac{1}{k + Rank_{Sparse}(d)}$$

- **k 的含义**：平滑因子，防止排名头部文档分数被过度高估。k = 60 是 Cormack et al. 2009 论文的经验推荐值；调大 k → 分布更均匀，调小 k → 差异更大。
- **为什么不用线性加权**：BM25 分数无上界，余弦相似度在 [-1,1]，两路量纲不同，线性加权必须先归一化且引入额外超参。RRF 只依赖排名（序数信息），天然无需归一化，鲁棒性更强。

---

### <a id="a-cross-encoder"></a>Q: Cross-Encoder 和 Bi-Encoder 的区别？为什么不能做粗排召回？

**参考答案**：

| | Bi-Encoder | Cross-Encoder |
|--|-----------|--------------|
| 编码方式 | Query 和 Document **分别**编码为向量，算相似度 | Query 和 Document **拼接**一起输入模型，联合建模 |
| Document 向量 | 可**离线预计算**，查询时 O(1) | 每对 (Query, Chunk) 必须**实时推理**，O(n) |
| 精度 | 较低（无交互） | 更高（充分建模交互特征） |
| 适合场景 | 粗排召回（大规模） | 精排（10-30 条小候选集） |

**Cross-Encoder 不能做粗排**：5000+ 文档场景每次查询需推理 5000 次，延迟不可接受、成本极高。必须先用 Bi-Encoder 粗召回 Top-N，再用 Cross-Encoder 精排。

---

### <a id="a-chunkrefiner"></a>Q: ChunkRefiner 做了什么？为什么需要额外的 LLM 步骤？

**参考答案**：
`RecursiveCharacterTextSplitter` 按字符边界物理切分，会将语义连续的段落切断（如"问题背景"和"解决方案"分入不同 Chunk），导致检索命中的 Chunk 缺乏上下文。

ChunkRefiner 的工作：
1. **合并语义断裂的段落**：LLM 判断相邻 Chunk 是否逻辑连续，若是则合并
2. **去噪清理**：移除 PDF 转换产生的页眉页脚乱码、重复标题

使每个 Chunk 成为 **Self-contained 的语义单元**，提升检索精度和 LLM 生成质量。

---

### <a id="a-hit-rate"></a>Q: Hit Rate@K 是怎么计算的？

**参考答案**：

$$HitRate@K = \frac{\text{Top-K 结果中至少命中一条 Golden Answer 的查询数}}{\text{总查询数}}$$

对 Golden Test Set 中每条 `(query, expected_chunks)`，取 Top-K 检索结果，至少一条匹配则 hit=1，否则 hit=0。Hit Rate@K = 命中次数 / 总 case 数。

**@K 含义**：只要正确文档出现在 Top-K 内即算命中，不要求排第一。@10 = 正确文档在 Top-10 内即可。

---

### <a id="a-可插拔架构"></a>Q: 新增一个 Embedding Provider 需要改哪些文件？

**参考答案**：
只需改 **3 处**，已有代码零修改（开闭原则）：

1. **新建** `src/libs/embedding/your_provider.py`：继承 `BaseEmbedding`，实现 `embed_texts()` 等接口方法
2. **修改** `src/libs/embedding/factory.py`：在 `provider_map` 中注册 `"your_provider": YourProviderClass`
3. **修改** `config/settings.yaml`：将 `embedding.provider` 改为 `"your_provider"`

其他组件（LLM / Reranker / VectorStore / Loader / Splitter）遵循同一套三步流程。

---

### <a id="a-幂等性"></a>Q: chunk_id 是怎么生成的？为什么不用 UUID？

**参考答案**：
`chunk_id = hash(source_path + section_path + content_hash)`

确定性哈希（SHA256 截断），相同来源+位置+内容的 Chunk 永远生成相同 ID。

**为什么不用 UUID**：UUID 随机，重复摄取同一文件会产生新 ID，导致向量库出现重复 Chunk。确定性哈希保证**幂等 Upsert**：相同内容多次写入只有一条，内容变更时 ID 变化自然触发更新。

文件级去重：前置 SHA256 文件哈希查 `ingestion_history.db`，已处理文件直接跳过。

---

### <a id="a-多模态检索"></a>Q: 图片的 Caption 如何参与检索？检索命中后图片怎么返回？

**参考答案**：
1. **摄取**：ImageCaptioner（Vision LLM，如 GPT-4o）为图片生成 Caption，文本**缝合进 Chunk 正文**，参与 Embedding 向量化
2. **检索**：用户文字查询时，Caption 文本被向量检索命中；BM25 也索引 Caption 关键词
3. **返回**：从 `image_index.db`（`image_id → 文件路径`映射）读取图片，Base64 编码，通过 MCP 返回 `ImageContent` 给 Client，实现"**搜文字出图**"

整个链路复用纯文本检索路径，无需额外特殊处理。

---

### <a id="a-测试体系"></a>Q: 测试分几层？单元测试怎么 mock LLM？

**参考答案**：
三层金字塔：
- **Unit（单元测试）**：1198+ 个，只测业务逻辑，用 `unittest.mock.patch` 替换 LLM 客户端返回预设响应，避免真实 API 调用
- **Integration（集成测试）**：验证模块间协作（Ingestion Pipeline / Chroma 存储读写），使用真实组件
- **E2E（端到端测试）**：`test_mcp_client.py` 启动真实 MCP Server 子进程，发送 JSON-RPC 消息验证完整链路；`test_dashboard_smoke.py` 用 Streamlit AppTest 无头渲染验证

---

### <a id="a-评估体系"></a>Q: Hit Rate@K 和 MRR 怎么计算？Ragas Faithfulness 衡量什么？

**参考答案**：
- **Hit Rate@K**：见 [→ 查看](#a-hit-rate)

- **MRR（Mean Reciprocal Rank）**：

$$MRR = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{rank_i}$$

$rank_i$ 是第 $i$ 条查询中第一条正确结果的排名。第一条命中得 1 分，第 2 位得 0.5 分，衡量**头部排序质量**。

- **Ragas Faithfulness**：衡量 LLM 回答是否**完全基于检索到的 Context**，防止幻觉。分数接近 1 = 回答有据可查，接近 0 = 大量幻觉。

---

### <a id="a-document-manager"></a>Q: 删除一个文档需要操作哪几个存储？失败怎么办？

**参考答案**：
必须**协调删除四路存储**：
1. **Chroma 向量库**：按 `metadata.source` 删除所有 Chunk 向量
2. **BM25 倒排索引**（`data/db/bm25/`）：移除所有词条的倒排条目
3. **ImageStorage**（`data/images/`）：删除关联图片文件
4. **FileIntegrity**（`ingestion_history.db`）：删除 SHA256 处理记录，使文件可重新摄取

**为什么必须四路同步**：只删 Chroma 不删 BM25 → 下次 Hybrid Search 从 BM25 召回已不存在的 Chunk，数据不一致；不删 FileIntegrity → 重传同一文件被认为"已处理"而跳过。

**失败策略**：尽力删除（best-effort），各存储独立尝试，失败记录错误日志但不阻塞其他存储。生产级可引入两阶段提交。

---

### <a id="a-可观测性"></a>Q: Trace 是怎么实现的？Ingestion 的 5 个阶段各是什么？

**参考答案**：
**Trace 实现**：显式调用模式（非 AOP 拦截），各阶段手动向 TraceContext 写入耗时、数量、分数分布，存为 JSON Lines 结构化日志，零外部依赖（无需 LangSmith/LangFuse）。

**Ingestion 5 阶段**：Load → Split → Transform → Embed → Upsert

**Query Trace 5 阶段**：QueryProcess → DenseRecall → SparseRecall → Fusion → Rerank

Dashboard 展示：Query 追踪页面（Dense/Sparse 召回对比、Rerank 前后排名变化）、Ingestion 追踪（阶段耗时瀑布图）。

---

## 三、评分细则

**分档标准（严格执行，不得调整）**：

| 分档 | 标准 |
|-----|------|
| 9-10 | 所有核心问题答出关键细节，无露馅，表达清晰且有深度延伸 |
| 7-8 | 大部分问题答出主干，偶有细节遗漏（1-2 处），无严重露馅 |
| 5-6 | 架构层面基本掌握，但算法/实现细节有 3 处以上明显缺失，或有 1 处严重露馅 |
| 3-4 | 仅能描述表面概念，追问即露馅，简历存在明显虚报 |
| 1-2 | 核心技术点均无法解释，简历与实际能力严重不符 |

**5 个评分维度**：

| 维度 | 重点考察内容 |
|-----|------------|
| 项目架构掌握 | 三层架构、模块分工、可插拔设计能否清楚表达 |
| 简历真实性 | 量化指标有无测量方法支撑，强动词能否说清决策过程 |
| 算法理论深度 | RRF 公式、Cross-Encoder 原理、Hit Rate/MRR 计算 |
| 实现细节掌握 | chunk_id 生成、可插拔三步骤、MCP Tool 参数、四路删除 |
| 表达清晰度 | 回答完整性、逻辑链完整、能说清"为什么"而非只说"是什么" |
