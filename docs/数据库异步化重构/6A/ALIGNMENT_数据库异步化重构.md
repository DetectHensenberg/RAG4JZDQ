# ALIGNMENT - 数据库异步化重构

## 本文档目标
梳理 RAG 管理平台中所有同步 `sqlite3` 的调用点，明确将数据库操作迁移至全异步架构（如 `aiosqlite`）的任务范围边界、技术实现路线及潜在的上下文约束。

## 1. 原始需求
- **需求描述**：将原本同步的 SQLite 数据库访问改造为异步调用，作为“性能优化1”的具体落地。
- **业务价值**：解决 FastAPI 中由于同步 I/O（特别是在高并发多路知识检索或多租户会话保存时）造成的 Event Loop 阻塞问题，全面释放 FastAPI 的高并发处理能力。

## 2. 现有项目上下文理解
经过代码全局检索，目前直接使用 `sqlite3` 建立连接执行 SQL 的模块分布如下：

### 2.1 API 路由层与核心依赖 (FastAPI) [**核心优化区**]
- `api/db.py`: `get_connection()` 提供的 FastAPI Dependency，生成同步 `sqlite3.Connection`。
- `api/routers/chat.py`: 同步保存历史记录 `_save_history`, 查询历史 `get_history`, 清空历史。并在流式输出中**同步调用** `ImageStorage` 计算并提取图片引用路径。
- `api/routers/data.py` & `api/routers/system.py`: 统计数据查询，直接同步读取 `chroma.sqlite3` 或 `ingestion_history.db`。

### 2.2 数据持久化层 (Libs Layer)
- `src/ingestion/storage/image_storage.py`: 管理 `image_index.db`，所有函数 (`get_image_path`, `save_image_metadata`, etc.) 为同步。
- `src/libs/loader/file_integrity.py`: 管理 `ingestion_history.db`，同步执行文件哈希检查及状态更新。
- `src/libs/vector_store/chroma_store.py`: Chroma 本身提供同步API，但内部统计查询通过手动执行 `sqlite3` 连通 `chroma.sqlite3` 拿数据。

### 2.3 工具与界面模块 [**边缘非高并发区**]
- `src/observability/dashboard/pages/knowledge_qa.py`: Streamlit 控制面板，作为独立的同步 Python 进程运行，目前自身无严重异步诉求。由于 Streamlit 天生对 async 支持有限，此处强制改写异步成本高且收益低。
- `src/bid/product_db.py` 及相关 `ingestion/stats.py`: 这部分多为离线批处理的同步任务。

## 3. 需求边界确认与疑问澄清

### 3.1 改造范围的初步界定
不建议强行将工程的每一个角落都改为 `async def`（如导致脱离 FastAPI 运行的纯命令行脚本、Streamlit面板报错）。**本次改造的边界应严格锁定在“FastAPI 运行生命周期内被调用的所有代码路径”**。

- **需改写为异步 (aiosqlite) 的模块**：
  1. `api/db.py` -> 改造为提供异步连接池或异步 Session 生成器 `get_async_connection()`。
  2. `api/routers/*.py` -> 所有直接调用 SQLite 的接口（如 `/history`），及其依赖注入。
  3. `src/ingestion/storage/image_storage.py` -> 增加异步方法 `get_image_path_async`（或者整体改造为工厂模式支持 Async），保障在 `chat.py` 流式传输（SSE）时不会造成长时阻塞。
  4. `file_integrity.py` -> 在 API 层面若有被路由调用的接口需支持异步。如果是纯属后端 Python 离线 ingestion，则可保持或兼容同步。

### 3.2 疑问与决策点（需向设计者/人工确认）
- 决策点 A：持久化类（如 `ImageStorage`, `FileIntegrityManager`）是否同时保留同步与异步两套方法？因为后端的 `ingest.py` (CLI 批处理)、Streamlit 界面仍在使用同步模式调用它们。
  - **建议策略**：在这些类中提供双修支持（例：保留 `get_image_path` 用于 CLI，新增 `aget_image_path` 用于 FastAPI），这样对系统稳定性的冲击最小，能平滑实现“按需异步”。

## 4. 结论与下一步计划
经过以上分析，我们已完全明确项目现状和可能踩的坑。下一步将进入 [**Architect**] 阶段，出具《DESIGN_数据库异步化重构.md》并提出接口切分方案。
