# DESIGN - 数据库异步化重构

## 1. 整体架构图
```mermaid
graph TD
    subage API["FastAPI Layer"]
        A[api/main.py] --> B[api/routers/chat.py]
        A --> C[api/routers/data.py]
        A --> D[api/routers/system.py]
    end

    subgraph DB["Database Connection Layer"]
        E[api/db.py]
        E -->|get_async_connection| F[aiosqlite.Connection]
        E -->|get_connection| G[sqlite3.Connection]
    end

    subgraph Storage["Persistence Layer"]
        H[ImageStorage]
        H -->|get_image_path| G
        H -->|aget_image_path| F
        I[QA History]
        I -->|save_history| G
        I -->|asave_history| F
    end

    B -.->|SSE Streaming| H
    B -.->|History| I
    B -.-> E
```

## 2. 模块依赖关系图与接口契约
### 2.1 `api/db.py` 改造
- 原接口：`def get_connection(...) -> Generator[sqlite3.Connection, ...]`
- 新增接口：`async def get_async_connection(db_path, row_factory=False) -> AsyncGenerator[aiosqlite.Connection, ...]`
- **职责**：为 FastAPI 路由层提供基于上下文管理器（`async with`）的异步连接生成器。

### 2.2 `api/routers/chat.py` 改造
- `_init_history_db()` -> 变为启动事件加载，或 `async def _ainit_history_db()`。
- `def _save_history` -> 改为 `async def _asave_history`。
- `chat_stream(req)` -> 在协程中，使用异步方式存储缓存和历史：`await _asave_history(...)`。在解析图片时调用 `await ImageStorage.aget_image_path(...)`。
- `/history` GET/DELETE 路由 -> 全面换用 `async with get_async_connection(...)`。

### 2.3 `src/ingestion/storage/image_storage.py` 改造
- 原有 `get_image_path(image_id: str) -> Optional[str]` 予以保留（供提取、离线构建等环节使用）。
- 新增 `async def aget_image_path(self, image_id: str) -> Optional[str]` 供 SSE Stream 流式处理图片时非阻塞调用。

## 3. 设计原则
1. **最小侵入原则**：只动会被高频/并发调用的 SQLite 操作，后台纯管理脚本（如 Chroma 统计）可缓行。
2. **前后向兼容**：提供显式 `a-` 开头的异步方法命名（例如 `aget_image_path`），避免混淆和强迫重构 CLI 端。
3. **安全并发**：验证 `aiosqlite` 工作在 WAL 模式下的稳定性，避免 `database is locked` 报错。

## 4. 异常处理策略
- 处理所有 `aiosqlite.DatabaseError` 和 `aiosqlite.OperationalError`。
- 若连接池/并发达到上限，确保抛出适当的 HTTPException 并通过 logger 记录。
