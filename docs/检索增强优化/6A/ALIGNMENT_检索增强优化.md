# ALIGNMENT: 检索增强优化 (GraphRAG & Parent Document Retriever)

## 项目背景
当前 RAG 系统采用基础的 Chunk-based 检索。对于需要跨文档归纳、系统性总结的问题，容易出现“文脉断层”或召回片段过于细碎导致回答片面的问题。

## 需求理解与边界确认
本项目旨在通过两项核心优化提升检索深度与上下文连贯性：

### 1. Parent Document Retriever (父文档召回)
- **目标**：在向量库中使用较细的视角（Small Chunk）确保召回精度，但在喂给 LLM 时使用包含更多上下文的视角（Parent Chunk / Large Chunk）。
- **逻辑**：
  - Ingestion: 对文档进行二级切分（Parent -> Children）。
  - Storage: Children 存储向量，Parent 存储文本（及 parent_id 关联）。
  - Retrieval: 搜到 Child 后，根据 `parent_id` 自动溯源并返回其 Parent 的文本。

### 2. GraphRAG (知识图谱增强检索)
- **目标**：通过提取文档中的实体（Entity）与关系（Relationship），构建知识图谱，解决跨文档的宏观关联问题。
- **逻辑**：
  - Ingestion: 增加 Transform 节点，利用 LLM 提取 (S, P, O) 三元组或关键实体。
  - Storage: 将关系网持久化（初期采用简易 SQLite 关系表）。
  - Retrieval: 基于查询关键词在图中进行 1-2 跳路径搜索，作为补充上下文。

## 技术实现方案
- **分块策略**：扩展 `DocumentChunker` 支持 `hierarchical` 模式。
- **处理流水线**：在 `IngestionPipeline` 中新增 `GraphExtractor` 变换。
- **检索逻辑**：在 `HybridSearch` 中引入两阶段处理逻辑（检索 -> 溯源/图扩展 -> 排序）。

## 疑问与决策
- [ ] **Parent Chunk 存储位置**：是存入 ChromaDB 的 metadata（受限）还是存入单独的 DocStore？
  - *决策建议*：初期可尝试存入一个本地简单 KV 存储（如 SQLite 或 JSON 文件），避免 ChromaDB 元数据过大导致性能下降。
- [ ] **图提取开销**：LLM 提取三元组成本较高。
  - *决策建议*：提供开启开关，并仅针对高质量/长文档任务启用。

## 验收标准
1. 多层级分块能够正确关联 `parent_id`。
2. 检索到的 Context 能够成功切换/扩张为父文档内容。
3. 知识图谱能够存储并在检索时返回相关的实体关系链。
