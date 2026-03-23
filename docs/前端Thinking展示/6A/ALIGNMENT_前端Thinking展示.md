# ALIGNMENT - 前端 Thinking 阶段化展示

> 日期：2026-03-22  
> 状态：对齐中 (Aligning)

## 1. 原始需求描述
在前端（MCP 客户端，如 Trae/VSCode）展示 RAG 检索的实时进度，包括：
- **初始化** (Initialization)
- **智能选择策略** (Strategy Routing)
- **检索中** (Hybrid Search: Vector + Sparse)
- **重排中** (Reranking)
- **上下文注入** (GraphRAG / Parent Retrieval Expansion)
- **生成结果** (Final Response)

## 2. 技术规格对齐

### 2.1 状态枚举定义
我们将中间状态统一定义为以下枚举值：
1. `routing`: 意图识别与策略调度
2. `retrieval`: 混合检索执行
3. `reranking`: 结果重排序
4. `expansion`: 画布/图谱/父文档扩展
5. `finalizing`: 结果组装

### 2.2 通信方案决策
目前 MCP Server 通过 `tools/call` 返回结果。标准的 `tools/call` 是请求-响应模式，不支持流式返回中间状态。

**候选方案：**
- **方案 A: stderr 日志协议** (推荐)
  - 优点：Trae 等主流 MCP 宿主会自动捕获 `stderr` 的日志并展示为 "Thinking" 过程。
  - 实现：将核心阶段的 `logger.info` 格式化为特定前缀。
- **方案 B: MCP Progress Notifications**
  - 优点：正式的协议支持。
  - 缺点：需要宿主在调用时提供 `progressToken`，且宿主对该通知的 UI 渲染支持程度不一。
- **方案 C: 自定义 XML 标记包裹**
  - 在最终文本前注入 `<thinking>...</thinking>`。

**当前决策：** 优先采用 **方案 A** (增强 stderr 日志渲染) + **方案 C** (如果前端支持解析文本流)。

## 3. 边界确认
- **非目标**：不修改前端 UI 源码（宿主 UI 逻辑由 Trae/VSCode 控制）。
- **目标**：优化后端输出，确保宿主能正确识别并展示“思考中”的不同阶段。

## 4. 待澄清问题
1. 前端宿主（如 Trae）是否能解构 `stderr` 中的 JSON 格式日志？还是只需要纯文本？
   - *假设：Trae 识别 stderr 中的原始文本作为思考过程。*
