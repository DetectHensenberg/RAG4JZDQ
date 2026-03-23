# CONSENSUS: Suggested Questions (追问推荐)

## 1. 明确的需求描述与验收标准
- **需求**：RAG 系统返回回答后，自动推荐 3 个相关的后续问题。
- **验收标准**：
  - [ ] `query_knowledge_hub` 的响应结果中包含 `suggested_questions` 字段。
  - [ ] 追问内容必须与当前文档内容及用户提问高度一致。
  - [ ] 生成过程失败不应影响主回答的显示。
  - [ ] 支持通过 `settings.yaml` 灵活开关。

## 2. 技术实现方案与集成
- **方案**：使用 LLM 结合当前 `Query` + `Answer` 产出 3 个追问，要求 JSON 格式输出。
- **集成**：在 `QueryKnowledgeHubTool` 链路末端串联生成逻辑。

## 3. 技术约束与集成方案
- **超时控制**：生成追问的 LLM 调用不得超过 5 秒。
- **Token 节省**：仅向 LLM 提供 Query 和生成的 Answer，不提供原始 Context（除非必要）。

## 4. 任务边界限制
- 仅支持文本追问，不支持基于图像的追问推荐。
- 仅在主查询工具 `query_knowledge_hub` 中实现。

## 5. 最终确认
- 所有不确定性已解决。
- 技术路线对齐现有性能调优目标。
