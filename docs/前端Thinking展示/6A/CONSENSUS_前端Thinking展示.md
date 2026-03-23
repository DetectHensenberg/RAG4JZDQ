# CONSENSUS - 前端 Thinking 阶段化展示

> 日期：2026-03-22  
> 状态：确认中 (Consensus Ready)

## 1. 明确的验收标准
- [ ] 后端检索链路中，每个核心阶段都有明确的 `stderr` 日志输出。
- [ ] 每个日志带有标准前缀 `[Thinking] [StageName] ...`。
- [ ] 对应阶段：`Strategy Routing` -> `Hybrid Retrieval` -> `Reranking` -> `Context Expansion` -> `Finalizing`.
- [ ] 前端宿主（如 Trae）调用 `query_knowledge_hub` 时，用户能看到上述分阶段进度。

## 2. 技术方案与约束
- **日志改造**：在 `QueryKnowledgeHubTool.execute` 及 `HybridSearch.search` 中增加特定的 `logger.info` 调用。
- **格式规范**：使用 `[Thinking] <Stage>` 格式，便于 IDE 宿主识别解析。
- **性能影响**：仅增加少量日志，对检索延迟几乎无影响。
- **集成方案**：无需修改 MCP 协议定义，复用现有的 `tools/call` 链路，利用 `stderr` 的异步流特性实现展示。

## 3. 任务边界限制
- 仅针对 `query_knowledge_hub` 工具。
- 不涉及前端 React/Vue 源码修改（宿主 UI 逻辑由 IDE 掌控）。
- 不通过 `types.Progress` (因为 Trae/VSCode 目前对 stderr 渲染的兼容性更好且无感接入)。

## 4. 关键决策确认
1. 确认采用 `stderr` 增强方案：✅ 已确认。
2. 确认状态阶段名称：`Routing`, `Retrieving`, `Reranking`, `Expanding`, `Assembling`: ✅ 已确认。
