# 九洲 RAG 管理平台

> 一个可插拔、可观测的模块化 RAG (检索增强生成) 知识库管理平台，支持智能问答、文档上传、方案生成，并通过 MCP (Model Context Protocol) 协议对外暴露工具接口。

---

## 🏗️ 项目概览

- **知识库问答**：基于知识库检索的智能问答，支持文件上传（招标文件/需求文档/目录模板）、三种检索模式（模型自动判断/每次都检索/不检索）、超长文档自动分段续写
- **富内容渲染**：回答中自动生成 Mermaid 架构图/流程图、数据图表（柱状图/饼图/折线图）、知识库图片展示、AI 配图
- **Ingestion Pipeline**：PDF / DOCX / TXT / MD → Markdown → Chunk → Transform → Embedding → Upsert（支持多模态图片描述）
- **Hybrid Search**：Dense (向量) + Sparse (BM25) + RRF Fusion + 可选 Rerank
- **MCP Server**：通过标准 MCP 协议暴露 `query_knowledge_hub`、`list_collections`、`get_document_summary` 三个 Tools
- **Dashboard**：Streamlit 管理平台（知识库问答 / 知识库构建 / 系统总览 / 数据浏览 / 摄取管理 / 追踪可视化 / 评估面板）
- **Evaluation**：Ragas + Custom 评估体系，支持 golden test set 回归测试

> 📖 详细架构设计和任务排期请参阅 [DEV_SPEC.md](DEV_SPEC.md)

---

##  快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd Modular-RAG-MCP-Server

# 创建虚拟环境 (Python 3.10+)
python -m venv .venv

# 激活虚拟环境
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置 API Key

编辑 `config/settings.yaml`，填入你的 LLM 和 Embedding 服务配置：

```yaml
llm:
  provider: "openai"           # 使用 DashScope OpenAI 兼容 API
  model: "qwen-plus"           # 通义千问模型
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "your-api-key"      # 替换为你的 DashScope API Key

embedding:
  provider: "openai"           # 使用 DashScope OpenAI 兼容 API
  model: "text-embedding-v3"   # 通义向量模型
  dimensions: 1024
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "your-api-key"      # 替换为你的 DashScope API Key

vision_llm:
  enabled: true
  provider: "openai"
  model: "qwen-vl-plus"        # 通义视觉模型
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "your-api-key"
```

> **提示**：当前默认配置使用阿里云 DashScope（通义千问）系列模型。也支持 Azure OpenAI、OpenAI、Ollama 等其他提供商。

### 3. 运行首次数据摄取

```bash
# 摄取示例文档
python scripts/ingest.py --path tests/fixtures/sample_documents/ --collection default

# 摄取单个 PDF 文件
python scripts/ingest.py --path /path/to/your/document.pdf --collection my_collection
```

### 4. 执行查询

```bash
# 基础查询
python scripts/query.py --query "你的查询问题"

# 带详细输出的查询
python scripts/query.py --query "Azure OpenAI 如何配置？" --verbose

# 指定 collection 查询
python scripts/query.py --query "测试查询" --collection my_collection
```

---

## ⚙️ 配置说明

所有配置集中在 `config/settings.yaml`，各字段含义如下：

| 配置块 | 字段 | 说明 | 默认值 |
|--------|------|------|--------|
| **llm** | `provider` | LLM 提供商 | `openai` (DashScope 兼容) |
| | `model` | 模型名称 | `qwen-plus` |
| | `base_url` | API 地址 | DashScope 兼容端点 |
| | `temperature` | 创造性程度 (0-1) | `0.0` |
| | `max_tokens` | 最大输出 token 数 | `4096` |
| **embedding** | `provider` | Embedding 提供商 | `openai` (DashScope 兼容) |
| | `model` | 模型名称 | `text-embedding-v3` |
| | `dimensions` | 向量维度 | `1024` |
| **vision_llm** | `enabled` | 是否启用视觉能力 | `true` |
| | `model` | 视觉模型 | `qwen-vl-plus` |
| **vector_store** | `provider` | 向量存储引擎 | `chroma` |
| | `persist_directory` | 持久化路径 | `./data/db/chroma` |
| | `collection_name` | 默认集合名 | `knowledge_hub` |
| **retrieval** | `dense_top_k` | 稠密检索返回数 | `20` |
| | `sparse_top_k` | 稀疏检索返回数 | `20` |
| | `fusion_top_k` | 融合后保留数 | `10` |
| | `rrf_k` | RRF 常数 | `60` |
| **rerank** | `enabled` | 是否启用重排 | `false` |
| | `provider` | 重排器类型 | `none` |
| **ingestion** | `chunk_size` | 分块大小 (字符) | `1000` |
| | `chunk_overlap` | 块间重叠 | `200` |
| | `splitter` | 分割策略 | `recursive` |
| **observability** | `log_level` | 日志级别 | `INFO` |
| | `trace_enabled` | 是否启用追踪 | `true` |
| | `trace_file` | 追踪日志路径 | `./logs/traces.jsonl` |

---

## 🔌 MCP 配置

### GitHub Copilot（VS Code）

在项目根目录创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "modular-rag": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### Claude Desktop

编辑 `claude_desktop_config.json`（路径因系统而异）：

```json
{
  "mcpServers": {
    "modular-rag": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/Modular-RAG-MCP-Server"
    }
  }
}
```

> 配置文件位置：
> - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
> - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

### 可用工具 (Tools)

| Tool 名称 | 功能 | 参数 |
|-----------|------|------|
| `query_knowledge_hub` | 混合检索知识库 | `query` (必填), `top_k`, `collection` |
| `list_collections` | 列出所有集合 | `include_stats` |
| `get_document_summary` | 获取文档摘要 | `doc_id` (必填), `collection` |

---

## 📊 Dashboard 使用指南

### 启动 Dashboard

```bash
# 默认端口 8501
python scripts/start_dashboard.py

# 指定端口
python scripts/start_dashboard.py --port 8502
```

访问 `http://localhost:8501` 即可打开管理平台。

### 页面功能

**主功能：**

| 页面 | 功能 | 说明 |
|------|------|------|
| **� 知识库问答** | 智能问答（默认页） | 基于知识库检索 + LLM 生成专业方案，支持文件上传、检索模式切换、Mermaid 图表、数据图表、超长文档自动续写 |
| **📂 知识库构建** | 批量摄取 | 指定本地文件夹一键构建知识库，后台运行，支持页面切换后进度不丢失 |

**系统管理（侧边栏折叠）：**

| 页面 | 功能 | 说明 |
|------|------|------|
| **📊 系统总览** | Overview | 展示组件配置、集合统计 |
| **🔍 数据浏览** | Data Browser | 浏览文档列表、chunk 内容、元数据 |
| **📥 摄取管理** | Ingestion Manager | 上传文件、触发 Pipeline、实时进度条 |
| **🔬 摄取追踪** | Ingestion Traces | 查看摄取链路各阶段耗时、详细日志 |
| **🔎 查询追踪** | Query Traces | 查看检索链路各阶段、Dense/Sparse 对比 |
| **📏 评估面板** | Evaluation Panel | 运行评估、查看 hit_rate/MRR 等指标 |

### 知识库问答功能特性

- **📎 文件上传**：支持上传 PDF、DOCX、PPTX、XLSX、TXT、MD、CSV 等格式的招标文件、需求文档或目录模板，AI 将结合上传内容与知识库一起生成方案
- **🔍 检索模式**：三种模式可选 —— 🤖 模型自动判断（LLM 决定是否需要检索）、📚 每次都检索、🚫 不检索
- **📝 超长文档续写**：单次生成上限 4096 token，超长方案自动分段续写（最多 6 轮），生成完整长文档
- **🧜 Mermaid 图表**：方案中涉及架构、流程时自动生成 Mermaid 图表
- **📊 数据图表**：涉及数据对比时自动生成柱状图、饼图、折线图
- **🖼️ 知识库图片**：从检索到的文档中提取并展示相关图片
- **🎨 AI 配图**：可选通过通义万相 API 自动生成方案配图
- **📤 导出**：支持将生成的方案导出为 Markdown 文档

---

## 🧪 运行测试

```bash
# 运行全部测试
pytest -q

# 仅运行单元测试（快速，无外部依赖）
pytest tests/unit/ -q

# 仅运行集成测试（可能需要外部服务）
pytest tests/integration/ -q -m integration

# 仅运行 E2E 测试
pytest tests/e2e/ -q -m e2e

# 跳过需要真实 LLM API 的测试
pytest -m "not llm" -q

# 带覆盖率报告
pytest --cov=src --cov-report=term-missing -q
```

### 测试分层

| 层级 | 目录 | 覆盖范围 | 运行速度 |
|------|------|---------|---------|
| 单元测试 | `tests/unit/` | 独立模块逻辑，Mock 外部依赖 | 快 (~10s) |
| 集成测试 | `tests/integration/` | 模块间交互，可选真实后端 | 中等 (~30s) |
| E2E 测试 | `tests/e2e/` | 完整链路（MCP Client / Dashboard） | 慢 (~30s) |

---

## 🔧 常见问题

### API Key 配置

**Q: 报错 `AuthenticationError` 或 `401`**

检查 `config/settings.yaml` 中 API Key 是否正确：
- DashScope: 确认 `api_key` 以 `sk-` 开头，`base_url` 为 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Azure: 确认 `azure_endpoint`、`api_key`、`deployment_name` 三者匹配
- OpenAI: 确认 `api_key` 以 `sk-` 开头
- Ollama: 确认本地服务已启动 (`ollama serve`)

### 依赖安装

**Q: 安装 `chromadb` 失败**

```bash
# Windows 需要 Visual C++ Build Tools
pip install chromadb --no-binary :all:

# 或者使用预编译版本
pip install chromadb
```

**Q: 安装 `PyMuPDF` 失败**

```bash
pip install PyMuPDF
# 如果报 wheel 错误，尝试升级 pip
pip install --upgrade pip setuptools wheel
```

### 连接问题

**Q: MCP Server 无响应**

1. 确认虚拟环境已激活
2. 尝试直接运行：`python -m src.mcp_server.server`
3. 检查 stderr 输出（MCP 使用 stdout 传输 JSON-RPC，日志在 stderr）

**Q: Dashboard 无法启动**

```bash
# 确认 Streamlit 已安装
pip install streamlit

# 检查端口占用
python scripts/start_dashboard.py --port 8502
```

**Q: 查询返回空结果**

1. 确认已执行数据摄取：`python scripts/ingest.py --path <file>`
2. 检查 collection 名称是否匹配
3. 查看 `logs/traces.jsonl` 中的错误信息

---

## 📁 项目结构

```
├── config/
│   ├── settings.yaml              # 主配置文件（LLM/Embedding/VectorStore 等）
│   └── prompts/                   # LLM prompt 模板
├── src/
│   ├── core/                      # 核心：类型、设置、查询引擎、响应构建
│   ├── ingestion/                 # 摄取：Pipeline、Chunking、Transform、Storage
│   ├── libs/                      # 可插拔层：LLM/Embedding/Splitter/VectorStore/Reranker
│   ├── mcp_server/                # MCP Server：Protocol Handler + Tools
│   └── observability/
│       └── dashboard/
│           ├── app.py             # Dashboard 主入口（导航 + 路由）
│           └── pages/
│               ├── knowledge_qa.py    # 💬 知识库问答（主页）
│               ├── knowledge_base.py  # 📂 知识库构建
│               ├── overview.py        # 📊 系统总览
│               ├── data_browser.py    # 🔍 数据浏览
│               ├── ingestion_manager.py # 📥 摄取管理
│               ├── ingestion_traces.py  # 🔬 摄取追踪
│               ├── query_traces.py    # 🔎 查询追踪
│               └── evaluation_panel.py # 📏 评估面板
├── scripts/                       # CLI 入口脚本
├── tests/                         # 测试：unit / integration / e2e / fixtures
├── data/                          # 数据存储（ChromaDB / BM25 / 图片）
└── logs/                          # 追踪日志
```

---

## 📄 License

MIT
