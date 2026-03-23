# ALIGNMENT: System Optimization (A4-A6)

## 1. 业务背景与原始需求
- **并发压测 (A4)**：需要量化 RAG 系统在多并发请求下的表现，识别 Bottle Neck。
- **SQLite 调优 (A5)**：解决 Windows 平台常见的 `database is locked` 报错，提升写入吞吐量。
- **异步化重构 (A6)**：彻底清理存量的同步 I/O（如文件读取、本地存储调用），防止协程阻塞产生的长尾延迟。

## 2. 需求理解与边界确认
- **压测范围**：
  - `query_knowledge_hub` 工具的并发调用性能。
  - 摄取链路（Ingestion）的并发执行稳定性。
- **优化指标**：
  - P95 延迟（目标：单次检索 < 3s）。
  - 并发数（目标：支持 5-10个并发搜索而不崩溃）。
- **异步化边界**：
  - 重点重构 `src/core` 和 `src/mcp_server` 中的文件 I/O 与 DB I/O。
  - CPU 密集型任务（如 Embedding 编码）保留线程池处理，不强求全异步。

## 3. 智能决策与技术方案
### A4: 压测策略
- 使用 **Subprocess JSON-RPC 压测脚本**。由于本项目是 Stdio 模式，无法直接用 Locust (HTTP)，需要自定义脚本模拟并发 Stdio 写入。
### A5: SQLite 参数
- 统一开启 `WAL` 模式。
- 设置 `busy_timeout = 20000` (20秒)。
- 评估 `journal_size_limit` 以控制磁盘膨胀。
### A6: 异步化路径
- 引入 `anyio` 的 `Path` 或 `aiofiles` 处理文件。
- 如果 `sqlite_utils` 不支持异步，考虑局部替换为 `aiosqlite` 或使用 `run_in_executor` 保护。

## 4. 疑问澄清
1. **压测基线**：用户是否提供具体的硬件配置？（若无，默认以当前运行环境为基准）。
2. **异步化深度**：三方库（如 `chromadb`）通常自带线程池，是否需要对其 Python Client 进行异步封装？（建议先优化内部 I/O）。

## 5. 验收标准
- [ ] 产出压测报告（Markdown 格式），包含多并发下的错误率与延迟。
- [ ] 系统在 5 并发写入反馈/查询时不再出现 `database is locked`。
- [ ] 通过 `grep` 扫描确保核心链路无 `open()` 或 `os.path` 的同步调用。
