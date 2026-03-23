# ACCEPTANCE: Suggested Questions (追问推荐)

## 验收核对清单

- [x] **T1: SuggestedQuestionGenerator 实现**
  - [x] 基于 LLM 的 Prompt 设计符合预期。
  - [x] JSON 提取逻辑稳健，支持从 Markdown 块中恢复。
  - [x] 数量限制（固定 3 个）生效。
- [x] **T2: MCPToolResponse 协议扩展**
  - [x] `metadata` 成功挂载 `suggested_questions` 数据。
  - [x] `to_mcp_content` 成功在 Markdown 文本末尾追加展示。
- [x] **T3: QueryKnowledgeHubTool 集成**
  - [x] 检索完成后异步触发追问生成。
  - [x] 成功将结果合并至最终 Response。
- [x] **T4: 配置与开关**
  - [x] `settings.yaml` 中包含 `enable_suggested_questions`。
  - [x] 修改配置可即时生效（无需重启 Tool 实例，按需加载）。
- [x] **T5: 自动化测试**
  - [x] `tests/test_suggested_questions.py` 覆盖 4 个核心场景，全部 Passed。

## 异常测试
- **LLM 返回非 JSON**: 能够记录 Warning 并返回空列表，不中断正常回答流程。
- **追问数量异常**: 模型返回 5 个追问时，代码自动截断前 3 个。
