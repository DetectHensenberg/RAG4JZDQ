# ALIGNMENT - 前端框架替换（Streamlit → FastAPI + Vue 3）

## 项目特性规范

### 现有项目技术栈
- **后端**: Python 3.10+，模块化 RAG 系统
- **前端**: Streamlit 1.54（即将替换）
- **LLM**: DashScope/OpenAI 兼容 API
- **向量数据库**: ChromaDB（本地持久化）
- **稀疏检索**: BM25（jieba 分词）
- **配置**: YAML + .env 环境变量

### 现有页面功能清单

| 页面 | 文件 | 核心功能 |
|------|------|----------|
| 知识库问答 | `knowledge_qa.py` (848行) | SSE 流式问答、Markdown/Mermaid 渲染、文件上传联合问答、历史持久化（SQLite）、导出文档 |
| 知识库构建 | `knowledge_base.py` (414行) | 文件夹递归扫描、批量摄取、实时进度条、安全停止按钮 |
| 系统总览 | `overview.py` (280行) | 集合统计、文档数量、存储空间 |
| 数据浏览 | `data_browser.py` (180行) | 按集合查看文档和分块内容 |
| 摄取管理 | `ingestion_manager.py` (140行) | 单文件上传摄取、文档删除 |
| 评估面板 | `evaluation_panel.py` (320行) | Ragas/Custom 评估、Golden Test Set |
| 系统配置 | `system_config.py` (380行) | API Key/LLM/Embedding 可视化配置、测试连接 |

### 现有服务层
- `DataService` — 数据浏览的只读门面
- `TraceService` — Trace 日志读取

### 现有数据流
- 问答: 用户输入 → HybridSearch 检索 → LLM 流式生成 → 前端渲染
- 摄取: 选择文件夹 → 后台线程逐文件 Pipeline → 进度回调 → 前端轮询
- 配置: 读取 YAML → 表单编辑 → 保存 YAML + .env

---

## 原始需求

用户要求将 Streamlit 前端替换为 FastAPI + Vue 3 前后端分离架构，解决以下问题：
1. Streamlit 每次交互全页面 rerun，体验卡顿
2. 流式输出不够流畅（SSE 被 rerun 打断）
3. 页面切换慢（服务端重新渲染）
4. 复杂交互受限（Streamlit 组件模型限制）

---

## 边界确认

### 在范围内
- 新建 `api/` 目录放置 FastAPI REST API 层
- 新建 `web/` 目录放置 Vue 3 前端
- 复用所有现有 `src/` 下的 Python 后端逻辑
- 7 个页面全部迁移
- 一键启动脚本

### 不在范围内
- 不修改 `src/` 下的核心业务逻辑
- 不删除现有 Streamlit 代码（保留可回退）
- 不更换数据库或检索引擎
- 不做用户认证/多用户支持

---

## 需求理解

### 关键交互需求
1. **问答页面**：SSE 流式逐 token 显示，无闪烁，支持 Markdown/Mermaid 实时渲染
2. **摄取页面**：SSE 实时进度推送，安全停止，不依赖轮询
3. **配置页面**：表单局部提交，测试连接即时反馈
4. **全局**：客户端路由瞬间切换，组件状态不丢失

### 技术约束
- 生产部署只需 Python（Vue 编译为静态文件，FastAPI 托管）
- 开发时需要 Node.js（Vite dev server）
- 保持单端口访问（生产模式 FastAPI 同时服务 API + 静态文件）

---

## 疑问澄清

### 已确认
- ✅ 使用 Vue 3 + Element Plus + TailwindCSS
- ✅ 保留 Streamlit 代码不删除
- ✅ Python 后端逻辑全部复用
- ✅ 前后端分离架构

### 需要确认的决策点

**Q1: 评估面板是否需要迁移？**
- 评估面板功能较复杂（Ragas 集成、Golden Test Set），使用频率低
- 建议：第一版先迁移核心 5 个页面（问答/构建/总览/浏览/配置），评估面板和摄取管理后续补充
- **请确认是否同意分期迁移？**

**Q2: 文档导出功能保留方式？**
- 现有 QA 页面支持导出 Markdown/Word 文档
- Vue 端可用 `file-saver` + `docx` 库实现，或由后端生成文件返回 blob
- **建议后端生成，前端下载，保持逻辑一致**

**Q3: Mermaid 图表渲染方式？**
- 方案 A：前端 mermaid.js 直接渲染（实时，但需要前端依赖）
- 方案 B：后端渲染为 SVG 返回（简单，但不实时）
- **建议方案 A，前端渲染更流畅**
