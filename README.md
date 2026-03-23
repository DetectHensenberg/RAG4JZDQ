# 九洲 RAG 管理平台

> 模块化 RAG（检索增强生成）知识管理平台，支持多格式文档摄取、混合检索、智能问答，并通过 MCP 协议对外暴露标准化工具接口。

**🎉 稳定版本 v1.0** — 开箱即用，已内置 API Key，朋友们可直接使用！

---

## 📖 目录

- [项目概述](#-项目概述)
- [系统架构](#-系统架构)
- [核心功能](#-核心功能)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [Web 界面使用指南](#-web-界面使用指南)
- [MCP 集成](#-mcp-集成)
- [项目结构](#-项目结构)
- [开发指南](#-开发指南)

---

## 🏗️ 项目概述

九洲 RAG 管理平台是一个面向企业级知识管理场景的检索增强生成系统，提供从文档摄取、向量化、混合检索到智能问答的完整链路。系统采用全链路可插拔架构，支持多种 LLM / Embedding / VectorStore Provider 一键切换。

### 技术栈

| 组件                 | 技术选型                                                   |
| -------------------- | ---------------------------------------------------------- |
| **后端**       | FastAPI + Uvicorn                                          |
| **前端**       | Vue 3 + Vite + TypeScript + Element Plus + TailwindCSS     |
| **LLM**        | DashScope (qwen-plus) / OpenAI / Azure / DeepSeek / Ollama |
| **Embedding**  | DashScope (text-embedding-v3) / OpenAI / Azure / Ollama    |
| **Vision LLM** | DashScope (qwen-vl-plus) / OpenAI / Azure（图片描述生成）  |
| **向量数据库** | ChromaDB（本地持久化，WAL 模式）                           |
| **稀疏检索**   | **Tantivy** 高性能文本索引基座（替代传统 BM25）      |
| **重排序**     | BGE-Reranker（本地 Cross-Encoder）/ LLM Rerank             |
| **异步队列**   | Redis / Memory Queue（海量文档吞吐缓冲层）                 |
| **文档解析**   | MarkItDown + LayoutPDF（OCR）+ python-pptx                 |
| **MCP 协议**   | 官方 Python MCP SDK（stdio 传输）                          |
| **配置管理**   | YAML + .env 环境变量                                       |
| **测试**       | pytest（三层测试体系）                                     |

---

## 🏛️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                Vue 3 Web Dashboard (暗黑毛玻璃风格)           │
│  知识库问答 │ 知识库构建 │ 数据浏览 │ 系统配置 │ 评估面板   │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────┼──────────────────────────────────────┐
│                FastAPI Backend (Port 8001)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│                  Core Layer                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐    │
│  │ QueryEngine │  │  Settings   │  │   TraceContext    │    │
│  │ HybridSearch│  │  (YAML)     │  │   (可观测性)      │    │
│  │ Dense+Sparse│  │             │  │                   │    │
│  │ RRF Fusion  │  │             │  │                   │    │
│  └─────────────┘  └─────────────┘  └──────────────────┘    │
└──────────────────────┼──────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│              Ingestion Pipeline                              │
│  Integrity → Load → Chunk → Transform → Encode → Store      │
│                       │                                      │
│  ┌────────────────────┼───────────────────────────────┐     │
│  │ ChunkRefiner │ MetadataEnricher │ ImageCaptioner   │     │
│  └────────────────────┼───────────────────────────────┘     │
└──────────────────────┼──────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│                  Libs Layer (可插拔)                         │
│  ┌─────┐ ┌───────────┐ ┌────────┐ ┌───────────┐ ┌───────┐ │
│  │ LLM │ │ Embedding │ │ Loader │ │VectorStore│ │Reranker│ │
│  │     │ │           │ │        │ │           │ │       │  │
│  │OpenAI│ │  OpenAI   │ │  PDF   │ │  Chroma   │ │Cross- │ │
│  │Azure │ │  Azure    │ │  PPTX  │ │           │ │Encoder│ │
│  │Ollama│ │  Ollama   │ │  DOCX  │ │           │ │ LLM   │ │
│  └─────┘ └───────────┘ └────────┘ └───────────┘ └───────┘ │
└─────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│                MCP Server (stdio)                            │
│  query_knowledge_hub │ list_collections │ get_document_summary│
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 核心功能

### 文档摄取管道（Ingestion Pipeline）

基于消息队列（Redis/Memory）的分发式异步摄取流程：

1. **分布式投递** — 基于异步队列机制管理摄取任务，提升系统的并发承载稳定性。
2. **文件完整性检查** — SHA256 哈希去重，相同文件无缝熔断。
3. **文档加载** — 支持 PDF / PPTX / DOCX / MD / TXT，自动提取流式图文内容。
4. **智能分块与内容增强** — 递归文本分割，并引入 Chunk 精炼、元数据增强与 Vision LLM 图片描述补充。
5. **异步向量化** — Dense Embedding + Sparse Tantivy 高性能编码处理。
6. **双路落盘存储** — ChromaDB 持久化向量空间 + Tantivy 本地域倒排索引合并落盘。

### 混合检索引擎（Hybrid Search）

- **Dense Retrieval** — 语义向量相似度检索。
- **Sparse Retrieval** — Tantivy 高效倒排检索体系，提供亿级数据下毫秒级的关键词精确召回响应。
- **RRF Fusion** — Reciprocal Rank Fusion 合并双路召回结果。
- **可选 Rerank** — Cross-Encoder / LLM 重排序完成最后一公里精排。

### 🤖 自动化工作流与 AI Agent (Antigravity & ECC)

本平台不仅拥有完善的业务功能，更内置了以 AI 自动化协同规范 为核心的“自演进工作流”，全面接入了跨项目 Agent 底座：

- **6A 工程协作受控 (6A Workflow)**：贯彻落实 Align -> Architect -> Atomize -> Approve -> Automate -> Assess 的智能生成与代码流转机制。所有技术方案文档化，于 `docs/` 进行全生命周期追溯。
- **白名单能力层挂载 (.agents/skills)**：内置项目级私有能力库（譬如 `qa-tester` 自动化测试闭环, `search-first` 工程化排查策略，以及 `python-patterns` 语法底线），确保持续工程迭代中的代码质量完全不劣化甚至反向赋能人类。

### 知识库问答

- **流式输出** — LLM 回答实时逐 token 显示
- **上下文控制** — 自动截断检索上下文，防止超时
- **多轮续写** — 答案截断时自动续写
- **文件上传** — 支持上传文档与知识库联合问答
- **图表生成** — 自动渲染 Mermaid 流程图 + 数据图表
- **历史持久化** — SQLite 存储问答历史，支持清空

### MCP 协议服务

通过标准 MCP 协议暴露 3 个工具，可对接 GitHub Copilot / Claude Desktop 等 AI 助手：

| 工具                     | 说明                             |
| ------------------------ | -------------------------------- |
| `query_knowledge_hub`  | 混合检索知识库并返回相关文档片段 |
| `list_collections`     | 列出所有已建集合及统计信息       |
| `get_document_summary` | 获取指定文档的摘要和元数据       |

### 可观测性

- **全链路追踪** — Ingestion 和 Query 每个阶段的中间状态透明可见
- **结构化日志** — JSON Lines 格式，API Key 自动脱敏
- **Dashboard 8 页面** — 系统总览 / 知识库问答 / 知识库构建 / 数据浏览 / 摄取管理 / 摄取追踪 / 查询追踪 / 评估面板

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+（前端构建）
- DashScope API Key（[申请地址](https://dashscope.console.aliyun.com/)）

### 2. 一键安装

```bash
git clone <repo-url>
cd RAG

# Windows
setup.bat

# Linux / Mac
chmod +x setup.sh && ./setup.sh
```

安装脚本会自动完成：创建虚拟环境 → 安装依赖 → 生成配置文件 → 构建前端。

> **首次安装后**：打开 `.env` 文件，将 `your-dashscope-api-key-here` 替换为你的 API Key。

> **OCR 功能**（可选）需额外安装 [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)（安装时勾选中文语言包）。

### 3. 启动平台

```bash
# 生产模式（推荐，需先 cd web && npm run build）
start_vue.bat          # Windows
./start_vue.sh         # Linux / Mac
# 访问 http://localhost:8000

# 开发模式（前后端分离）
# 后端: python -m uvicorn api.main:app --port 8001
# 前端: cd web && npm run dev
# 访问 http://localhost:5173
```

### 4. 使用 MCP Server（可选）

```bash
python main.py
```

可对接 VS Code Copilot / Claude Desktop 等 AI 助手。

### 5. Docker 部署（可选）

```bash
# 1. 准备配置
cp .env.example .env                          # 编辑 .env 填入 API Key
cp config/settings.yaml.example config/settings.yaml  # 按需修改配置

# 2. 一键启动
docker compose up -d

# 3. 访问
# http://localhost:8000
```

> **数据持久化**：`./data/` 目录通过 volume 自动挂载，容器重建不丢数据。
> **自定义端口**：修改 `.env` 中的 `RAG_PORT=8000` 即可。

---

## ⚙️ 配置说明

所有配置集中在 `config/settings.yaml`，API Key 通过 `.env` 文件管理。

### API Key 优先级

1. `settings.yaml` 中的显式值（非空时使用）
2. `.env` 文件中的 `DASHSCOPE_API_KEY`
3. 系统环境变量 `OPENAI_API_KEY`

### 关键配置项

```yaml
llm:
  provider: "openai"          # Provider: openai / azure / ollama / deepseek
  model: "qwen-plus"          # 模型名称
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

embedding:
  provider: "openai"
  model: "text-embedding-v3"
  dimensions: 1024

vector_store:
  provider: "chroma"
  persist_directory: "./data/db/chroma"
  collection_name: "default"

retrieval:
  dense_top_k: 20             # Dense 检索返回数量
  sparse_top_k: 20            # BM25 检索返回数量
  fusion_top_k: 10            # RRF 融合后最终返回数量

ingestion:
  chunk_size: 1000            # 分块大小（字符）
  chunk_overlap: 200          # 分块重叠（字符）
```

---

## 📊 Web 界面使用指南

### 知识库问答

1. 进入 **知识库问答** 页面
2. 输入问题，系统自动检索知识库并**流式生成回答**
3. 支持 **Mermaid 流程图**自动渲染
4. 右侧显示**检索来源**和**相关图片**
5. 历史记录自动持久化

### 知识库构建

1. 进入 **知识库构建** 页面
2. 输入知识库文件夹路径，点击 **扫描**
3. 确认文件列表后点击 **开始构建**
4. 实时查看摄取进度（支持**断线重连**，切换页面不丢失进度）
5. 支持 **停止** 按钮安全中断

### 数据浏览

- 查看已摄取文档列表
- 支持按集合筛选
- 可删除单个文档

### 系统配置

- 在线修改 LLM / Embedding / 检索参数
- 无需重启即可生效

### 安全关闭

- 摄取过程中可点击 **停止** 按钮安全停止
- 系统注册了 `atexit` 优雅关闭，Ctrl+C 时自动执行 WAL checkpoint
- 避免在存储阶段强制终止进程

---

## 📡 MCP 集成

### VS Code (GitHub Copilot)

在 `.vscode/mcp.json` 中配置：

```json
{
  "servers": {
    "rag-server": {
      "command": "python",
      "args": ["main.py"],
      "cwd": "<项目路径>"
    }
  }
}
```

### Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "rag-server": {
      "command": "python",
      "args": ["<项目路径>/main.py"]
    }
  }
}
```

---

## 📁 项目结构

```
├── api/                        # FastAPI 后端
│   ├── main.py                 # 应用入口
│   ├── routers/                # API 路由 (chat, ingest, knowledge, config)
│   ├── models.py               # 请求/响应模型
│   └── deps.py                 # 依赖注入
├── web/                        # Vue 3 前端
│   ├── src/
│   │   ├── views/              # 页面组件 (ChatView, KnowledgeBase, etc.)
│   │   ├── composables/        # 组合式函数 (useSSE, useApi)
│   │   └── stores/             # Pinia 状态管理
│   ├── dist/                   # 构建产物（生产模式）
│   └── package.json
├── config/
│   └── settings.yaml           # 运行配置
├── .agents/                    # 🤖 存放 Agent 白名单专属能力库 (ECC/Skills)
├── src/
│   ├── core/                   # 核心层
│   │   ├── types.py            # 全局数据契约
│   │   ├── settings.py         # 配置加载
│   │   └── query_engine/       # Dense / Sparse Tantivy 混合检索
│   ├── ingestion/              # 摄取管道
│   │   ├── pipeline.py         # 队列编排器
│   │   ├── queue/              # 消息缓冲队列池 (Memory/Redis)
│   │   ├── chunking/           # Doc 分块拆解
│   │   ├── embedding/          # Dense + Sparse Tantivy 编码
│   │   ├── storage/            # ChromaDB + Tantivy 落盘
│   │   └── transform/          # 内容精炼与增强
│   ├── libs/                   # 可插拔 Provider 层
│   │   ├── llm/                # LLM 工厂
│   │   ├── embedding/          # Embedding 工厂
│   │   ├── loader/             # 文档加载器
│   │   ├── vector_store/       # 向量存储
│   │   └── reranker/           # 重排序器
│   └── mcp_server/             # MCP 协议服务
├── tests/                      # 三层测试体系
├── data/                       # 运行时数据（gitignore）
│   ├── db/                     # ChromaDB + BM25 索引
│   └── images/                 # 提取的文档图片
├── .env                        # API Key（已内置）
├── start_vue.bat               # Windows 一键启动
└── pyproject.toml              # 项目配置
```

---

## 🛠️ 开发指南

### 架构设计原则

- **Config-Driven** — 所有组件通过 `settings.yaml` 配置，零代码切换 Provider
- **Factory Pattern** — LLM / Embedding / Loader / VectorStore / Reranker 统一工厂创建
- **Graceful Degradation** — LLM 调用失败自动降级到规则引擎，不阻塞管道
- **Observable** — TraceContext 贯穿全链路，每个 Stage 记录耗时和详细数据

### 添加新 Provider

以添加新 LLM Provider 为例：

1. 继承 `src/libs/llm/base_llm.py::BaseLLM`
2. 实现 `chat()` 和可选的 `chat_stream()` 方法
3. 在 `LLMFactory` 中注册 Provider
4. 在 `settings.yaml` 中配置

### 运行测试

```bash
# 全量测试
pytest tests/ -v

# 仅单元测试
pytest tests/unit/ -v

# 跳过需要 API 的测试
pytest tests/ -v -m "not llm"
```

### 数据安全

- API Key 存储在 `.env` 文件，通过 `.gitignore` 排除
- 日志系统内置 `_SecretFilter`，自动脱敏 API Key 和 Bearer Token
- `LoaderFactory` 内置路径遍历防护
- SQLite 全部使用参数化查询，防止 SQL 注入
- ChromaDB 启用 WAL 模式 + `atexit` 优雅关闭，防止索引损坏

---

## 📄 License

MIT License
