# CONSENSUS — 需求1：产品技术资料真伪性辨别助手

## 明确的需求描述

在现有 RAG 平台左侧导航栏新增"标书助手"入口，以**对话式交互**（类似现有知识库问答 ChatView）引导用户完成**顺序工作流**：

```
Step 1: 用户输入招标技术要求 → 系统从产品知识库检索推荐产品列表
Step 2: 用户选定产品，上传厂家送审的技术资料（PDF/DOCX）
Step 3: 系统自动提取参数 → 与知识库基准比对 → 流式输出偏差报告
```

偏差报告同时提供 **Markdown 流式输出** 和 **结构化可排序表格**，并标注偏差在 PDF 中的**页码和章节**。

## 技术实现方案

### 复用现有组件

| 现有组件 | 复用方式 |
|----------|----------|
| `ChatView.vue` | 参考其对话式 UI 模式，新页面采用相同交互范式 |
| `HybridSearch` | 从 `products` collection 检索匹配产品 |
| `IngestionPipeline` | 摄取产品文档到 `products` collection（通过现有摄取管理） |
| `LLMFactory` | 创建 LLM 实例用于参数提取和比对 |
| SSE 流式输出 | 比对报告流式传输（复用 chat.py 的 SSE 模式） |

### 新增组件

| 组件 | 说明 |
|------|------|
| `src/bid/param_extractor.py` | 参数提取器，调用 LLM 提取参数 JSON（含页码、章节） |
| `src/bid/param_comparator.py` | 参数比对器，调用 LLM 语义比对，SSE 流式输出 |
| `src/bid/product_db.py` | 产品参数 SQLite 存储（提取结果持久化） |
| `api/routers/bid.py` | 标书助手 API 路由（对话驱动的顺序工作流） |
| `web/src/views/BidAssistant.vue` | 标书助手前端 — **对话式 UI**，含文件上传、产品选择卡片、结构化表格 |

### 对话式顺序工作流设计

前端维护一个 **workflow state machine**：

```
idle → searching → product_selected → uploading → comparing → done
```

每个状态对应不同的对话消息类型和用户可执行操作：

| 状态 | 系统行为 | 用户操作 |
|------|----------|----------|
| idle | 显示引导提示 | 输入招标技术要求 |
| searching | 调用 /api/bid/search，展示产品卡片列表 | 点击选择某个产品 |
| product_selected | 提示上传送审资料 | 上传 PDF/DOCX 文件 |
| uploading | 摄取文件 + 提取参数 | 等待 |
| comparing | SSE 流式输出比对报告 + 渲染结构化表格 | 查看、排序、筛选 |
| done | 展示完整报告 | 可重新开始 / 导出 |

## 技术约束

- ChromaDB 路径不能含中文（已有 fix，使用相对路径）
- 前端设计延续暗黑毛玻璃风格
- 不影响现有 `default` collection 和知识库问答功能
- API Key 复用现有 `.env` 中的 DashScope 配置
- 产品知识库暂时为空，框架先行

## 验收标准

1. 左侧导航栏出现"标书助手"，点击进入**对话式**标书助手页面
2. 输入招标技术要求后，系统以对话形式返回匹配产品列表（卡片式）
3. 选定产品后，页面提示上传送审资料，支持拖拽上传 PDF/DOCX
4. 上传后自动提取参数并与知识库比对，**流式输出** Markdown 偏差报告
5. 偏差报告中标注 **PDF 页码 + 章节**
6. 同时在前端渲染**结构化表格**（可排序、可筛选偏差类型和风险等级）
7. 现有知识库问答功能完全不受影响
