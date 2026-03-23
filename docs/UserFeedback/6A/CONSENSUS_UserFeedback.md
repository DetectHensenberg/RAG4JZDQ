# CONSENSUS: 用户反馈闭环 (User Feedback Loop)

## 1. 明确的需求描述与验收标准
- **需求**：用户评价回答质量，系统持久化存储并支持统计。
- **验收标准**：
  - [ ] `submit_feedback` 工具响应成功。
  - [ ] `data/feedback.db` 中包含 `rating` (1/-1) 和 `trace_id`。
  - [ ] 统计工具显示准确的累计评分。

## 2. 技术实现方案与集成
- **方案**：SQLite 单表维护反馈，不引入外部数据库。
- **集成**：修改 `QueryKnowledgeHubTool` 以透出 `trace_id`。

## 3. 技术约束
- **并发性**：SQLite 需开启 WAL 模式以处理并发写入及读取。
- **性能**：查询 `get_feedback_stats` 不应在大规模数据下造成延迟。

## 4. 任务边界限制
- 仅支持对 `query_knowledge_hub` 产出的完整回答进行反馈。
- 不提供复杂的管理后台，仅提供 MCP 统计工具。

## 5. 最终确认
- 所有不确定性已解决。
- 方案与现有项目架构对齐。
