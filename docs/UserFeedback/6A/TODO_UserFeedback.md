# TODO: 后续动作建议

1. **[前端适配]**: 确保前端 UI 在展示回答后，调用 `submit_feedback` 时带上响应 `metadata` 中的 `trace_id`。
2. **[数据清理]**: 定期导出冷数据，由于 SQLite 是本地文件，需注意磁盘占用（当前单条记录极小，万条约 5MB）。
3. **[追问推荐逻辑确认]**: 询问用户：追问推荐（Suggested Questions）是基于当前 Context 静态生成，还是需要调用一次 LLM 异步生成？
