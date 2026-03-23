# ALIGNMENT: 用户反馈闭环 (User Feedback Loop)

## 1. 原始需求
- 实现 `👍/👎` 反馈落库。
- 提供简单的运营看板（统计功能）。
- 确保反馈与具体的查询请求（Query/Trace）关联。

## 2. 现有项目理解
- **存储架构**：项目使用 SQLite 作为轻量级持久化层（GraphStore, ParentStore, ImageStorage）。
- **工具链**：已有 `QueryKnowledgeHubTool` 等 MCP 工具。
- **可观察性**：已有 `TraceContext` 系统，可以生成 `trace_id`。

## 3. 边界确认
- **任务范围**：
  - 新增 `FeedbackStore` (SQLite) 用于存储反馈。
  - 新增 `submit_feedback` MCP Tool。
  - 扩展 `QueryKnowledgeHubTool` 返回 `trace_id` 以便前端后续反馈。
  - 开发简单的统计接口或工具（运营看板初步实现）。
- **非任务范围**：
  - 复杂的管理后台 UI（仅提供基础数据统计能力）。
  - 用户鉴权（目前项目环境默认单用户/内网信赖）。

## 4. 关键决策
- **关联键**：反馈必须关联 `trace_id`。
- **存储位置**：新建 `data/feedback.db`，由 `src/ingestion/storage/feedback_store.py` 管理。
- **反馈粒度**：支持对整个回答的反馈。

## 5. 疑问澄清
1. 是否需要支持针对单条引用的反馈？（初步决定仅支持对整体回答的反馈，以保持简单）。
2. 运营看板的形式？（初步决定提供一个 `get_feedback_stats` 的工具或简单的日志汇总）。

## 6. 验收标准
- [ ] 调用 `submit_feedback` 时，数据能正确存入 SQLite。
- [ ] 存入的数据包含：`trace_id`, `rating` (1/-1), `comment` (optional), `timestamp`。
- [ ] 提供一个方法能够查询反馈总数及正负比例。
