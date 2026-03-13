# 九洲 RAG 管理平台

> 模块化 RAG（检索增强生成）知识管理平台，支持多格式文档摄取、混合检索、智能问答，并通过 MCP 协议对外暴露标准化工具接口。

---

## 📖 目录

- [项目概述](#-项目概述)
- [系统架构](#-系统架构)
- [核心功能](#-核心功能)
- [快速开始](#-快速开始)
- [配置说明](#-配置说明)
- [Dashboard 使用指南](#-dashboard-使用指南)
- [MCP 集成](#-mcp-集成)
- [项目结构](#-项目结构)
- [开发指南](#-开发指南)

---

## 🏗️ 项目概述

九洲 RAG 管理平台是一个面向企业级知识管理场景的检索增强生成系统，提供从文档摄取、向量化、混合检索到智能问答的完整链路。系统采用全链路可插拔架构，支持多种 LLM / Embedding / VectorStore Provider 一键切换，并通过 Streamlit Dashboard 提供可视化管理界面。

### 技术栈

| 组件 | 技术选型 |
|------|----------|
| LLM | DashScope (qwen-plus) / OpenAI / Azure / DeepSeek / Ollama |
| Embedding | DashScope (text-embedding-v3) / OpenAI / Azure / Ollama |
| Vision LLM | DashScope (qwen-vl-plus) / OpenAI / Azure |
| 向量数据库 | ChromaDB（本地持久化，WAL 模式） |
| 稀疏检索 | BM25（jieba 中文分词 + 自研倒排索引） |
| 文档解析 | MarkItDown（PDF / DOCX / MD）+ python-pptx（PPTX） |
| 前端 | Streamlit Dashboard（8 页面管理平台） |
| MCP 协议 | 官方 Python MCP SDK（stdio 传输） |
| 配置管理 | YAML + .env 环境变量 |
| 测试 | pytest（50+ 单元测试文件，三层测试体系） |

---

## 🏛️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                       │
│  知识库问答 │ 知识库构建 │ 数据浏览 │ 摄取追踪 │ 评估面板  │
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

6 阶段全自动摄取流程：

1. **文件完整性检查** — SHA256 哈希去重，相同文件自动跳过
2. **文档加载** — 支持 PDF / PPTX / DOCX / MD / TXT，自动提取图片
3. **智能分块** — 递归文本分割，保持语义完整性
4. **内容增强** — Chunk 精炼 + 元数据增强 + Vision LLM 图片描述
5. **向量编码** — Dense Embedding + BM25 稀疏编码，批量处理
6. **持久化存储** — ChromaDB 向量存储 + BM25 倒排索引 + 图片索引

### 混合检索引擎（Hybrid Search）

- **Dense Retrieval** — 语义向量相似度检索
- **Sparse Retrieval** — BM25 关键词精确匹配（jieba 中文分词）
- **RRF Fusion** — Reciprocal Rank Fusion 合并双路召回结果
- **可选 Rerank** — Cross-Encoder / LLM 重排序精排

### 知识库问答

- **流式输出** — LLM 回答实时逐 token 显示
- **上下文控制** — 自动截断检索上下文，防止超时
- **多轮续写** — 答案截断时自动续写
- **文件上传** — 支持上传文档与知识库联合问答
- **图表生成** — 自动渲染 Mermaid 流程图 + 数据图表
- **历史持久化** — SQLite 存储问答历史，支持清空

### MCP 协议服务

通过标准 MCP 协议暴露 3 个工具，可对接 GitHub Copilot / Claude Desktop 等 AI 助手：

| 工具 | 说明 |
|------|------|
| `query_knowledge_hub` | 混合检索知识库并返回相关文档片段 |
| `list_collections` | 列出所有已建集合及统计信息 |
| `get_document_summary` | 获取指定文档的摘要和元数据 |

### 可观测性

- **全链路追踪** — Ingestion 和 Query 每个阶段的中间状态透明可见
- **结构化日志** — JSON Lines 格式，API Key 自动脱敏
- **Dashboard 8 页面** — 系统总览 / 知识库问答 / 知识库构建 / 数据浏览 / 摄取管理 / 摄取追踪 / 查询追踪 / 评估面板

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- DashScope API Key（或 OpenAI / Azure API Key）

### 2. 安装依赖

```bash
git clone <repo-url>
cd RAG
pip install -e .
pip install "markitdown[docx]"  # DOCX 支持
```

### 3. 配置 API Key

```bash
# 复制配置模板
cp config/settings.yaml.example config/settings.yaml

# 创建 .env 文件（不会被提交到 Git）
echo "DASHSCOPE_API_KEY=你的API密钥" > .env
```

### 4. 启动 Dashboard

```bash
# Windows
start_dashboard.bat

# Linux / macOS
bash start_dashboard.sh
```

访问 `http://localhost:8501` 即可使用。

### 5. 使用 MCP Server

```bash
python main.py
```

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

## 📊 Dashboard 使用指南

### 知识库构建

1. 进入 **知识库构建** 页面
2. 设置知识库文件夹路径（支持递归扫描子文件夹）
3. 选择文件类型（PDF / PPTX / DOCX / MD）
4. 点击 **开始构建**，实时查看摄取进度
5. 支持 **停止摄取** 按钮，当前文件完成后安全停止

### 知识库问答

1. 进入 **知识库问答** 页面
2. 输入问题，系统自动检索知识库并流式生成回答
3. 侧边栏可调整检索数量、最大 Token 等参数
4. 支持上传文档与知识库联合问答
5. 历史记录自动持久化，支持清空

### 安全关闭

- 摄取过程中可点击 **⏹️ 停止摄取** 按钮安全停止
- 系统注册了 `atexit` 优雅关闭，Ctrl+C 时自动执行 WAL checkpoint
- 避免在 `💾 Stage 6: Storage` 阶段强制终止进程

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
├── config/
│   ├── settings.yaml           # 运行配置（gitignore）
│   └── settings.yaml.example   # 配置模板
├── src/
│   ├── core/                   # 核心层
│   │   ├── types.py            # 全局数据契约 (Document, Chunk, RetrievalResult)
│   │   ├── settings.py         # 配置加载与校验
│   │   ├── query_engine/       # 检索引擎 (Dense + Sparse + RRF + Rerank)
│   │   ├── response/           # 响应构建
│   │   └── trace/              # 追踪上下文
│   ├── ingestion/              # 摄取管道
│   │   ├── pipeline.py         # 6 阶段编排器
│   │   ├── chunking/           # 文档分块
│   │   ├── embedding/          # Dense + Sparse 编码
│   │   ├── storage/            # ChromaDB + BM25 + Image 存储
│   │   └── transform/          # Chunk 精炼 + 元数据增强 + 图片描述
│   ├── libs/                   # 基础设施层（可插拔 Provider）
│   │   ├── llm/                # LLM 工厂 + 5 个 Provider
│   │   ├── embedding/          # Embedding 工厂 + 3 个 Provider
│   │   ├── loader/             # 文档加载器 (PDF, PPTX, DOCX, MD)
│   │   ├── vector_store/       # 向量存储工厂 (ChromaDB)
│   │   ├── splitter/           # 文本分割器
│   │   └── reranker/           # 重排序器 (Cross-Encoder, LLM)
│   ├── mcp_server/             # MCP 协议服务
│   │   ├── server.py           # stdio 入口
│   │   ├── protocol_handler.py # JSON-RPC 协议处理
│   │   └── tools/              # 3 个 MCP 工具实现
│   └── observability/          # 可观测性
│       ├── logger.py           # 结构化日志 + API Key 脱敏
│       ├── dashboard/          # Streamlit Dashboard (8 页面)
│       └── evaluation/         # 评估框架
├── tests/                      # 三层测试体系 (unit / integration / e2e)
├── data/                       # 运行时数据（gitignore）
│   ├── db/                     # ChromaDB + BM25 + SQLite 索引
│   └── images/                 # 提取的文档图片
├── log/                        # 工程日志与评审报告
├── scripts/maintenance/        # 数据库维护脚本
├── .env                        # API Key（gitignore）
├── pyproject.toml              # 项目配置与依赖
├── start_dashboard.bat         # Windows 启动脚本
└── start_dashboard.sh          # Linux/macOS 启动脚本
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
