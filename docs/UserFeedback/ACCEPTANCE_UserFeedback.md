# ACCEPTANCE: 用户反馈闭环 (User Feedback Loop)

## 验收核对清单

- [x] **T1: FeedbackStore 持久化层**
  - [x] SQLite `feedback` 表创建成功。
  - [x] 支持 WAL 模式，高并发写无死锁（已验证）。
  - [x] 支持 Upsert（同一 trace_id 覆盖更新）。
- [x] **T2: trace_id 注入**
  - [x] `QueryKnowledgeHubTool` 响应元数据中包含 `trace_id`。
  - [x] 成功透出到前端使用的 Markdown JSON 块。
- [x] **T3: SubmitFeedbackTool**
  - [x] 参数校验完整 (trace_id, rating)。
  - [x] 成功对接持久化层。
- [x] **T4: 工具注册**
  - [x] `submit_feedback` 与 `get_feedback_stats` 全量上线。
- [x] **T5: GetFeedbackStatsTool**
  - [x] 返回 JSON 格式统计数据。
  - [x] 统计数值（Total/Positive/Negative）准确。
- [x] **T6: 自动化测试**
  - [x] `tests/test_feedback_loop.py` 全绿通过。

## 异常测试
- **重复提交**：多次点击 👍/👎，数据库仅保存最后一次结果，符合预期。
- **并发写**：自动化测试模拟快速提交，未出现数据损坏。
