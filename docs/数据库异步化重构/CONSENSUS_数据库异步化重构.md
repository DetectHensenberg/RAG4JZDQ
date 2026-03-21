# CONSENSUS - 数据库异步化重构

## 1. 明确的需求描述和验收标准
**需求描述**：
将后端（FastAPI）运行链路中涉及到同步 SQLite I/O 的调用，改造为异步无阻塞调用（基于 `aiosqlite`），以提升系统整体的并发吞吐量。重点改造对象包括：问答历史的存取、图片提取时的元数据查询、知识库构建状态的查询。

**验收标准**：
1. 后端应用能正常启动，无 Syntax/Import 错误。
2. Web UI 的“知识库问答”仍能正常产生流式回应，且图文能正确解析展示。
3. 对 `/history` 接口的访问和清空操作全部生效且为异步处理。
4. 不破坏原有的离线数据摄取逻辑（CLI Ingestion）、Streamlit 可视化面板中依赖同步调用的逻辑，确保系统整体功能的后向兼容。

## 2. 技术实现方案和技术约束
- **核心组件迁移**：通过 `aiosqlite` 替换 `sqlite3`。`api/db.py` 需新增 `get_async_connection` 生成异步的 `AsyncConnection`。
- **兼容性设计 (Dual-Mode)**：对于跨平台共享的核心工具类（如 `ImageStorage`, `FileIntegrityManager`），我们将同时保留原来的同步方法（如 `get_image_path`），并增加异步版本（如 `aget_image_path`），以防波及非异步上下文的脚本。
- **依赖注入改造**：更新 FastAPI 中的 `Depends(get_connection)` 为基于 `async with get_async_connection()`。

## 3. 任务边界限制
- **不改动**：ChromaDB 内部的同步 SQLite 调用（属第三方集成限制）。
- **不改动**：Streamlit 端的 DB 查询逻辑，依然保留同步形态。
- **不改动**：离线大批量 Embed 的纯同步批处理 CLI 代码。

## 4. 确认所有不确定性已解决
已向开发者确认改造边界。实施过程中采用“最小切口”防劣化原则，保障前后端原有特性的绝对稳定。
