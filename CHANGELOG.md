# 更新日志 (CHANGELOG)

本文档记录九洲 RAG 管理平台的重要变更。

---

## [2026-04-06] 代码审查修复 — P0/P1/P2 全量修复

### 🔒 安全修复 (P0)

- **修复 API Key 泄露**：`.env` 文件包含真实密钥且被 Git 跟踪
  - `.gitignore` 恢复 `.env` 排除规则
  - `git rm --cached .env` 移除追踪
  - 创建 `.env.example` 安全模板
  - ⚠️ **需手动操作**：前往 DashScope 控制台轮换 API Key

### ⚡ 性能与稳定性 (P1)

- **LLM 超时修复**：`achat_stream` 超时从 `120s` → `None`，解决长文档流式输出中断
- **连接池优化**：`OpenAILLM` 引入持久化 `_async_http_client`，复用 TCP 连接
- **热路径优化**：`import json` 从循环内部移至文件顶部

### 🏗️ 架构优化 (P1)

- **FastAPI Lifespan 迁移**：`on_event("startup/shutdown")` → `lifespan` context manager
- **并发安全**：`deps.py` 添加 `threading.Lock` + double-checked locking
- **Git 跟踪修复**：恢复 `tests/` 和 `docs/` 目录跟踪，排除大型测试文件
- **日志规范化**：`api/main.py` 全部 `print()` → `logger.info/error`

### 📋 代码质量 (P2)

- **类型标注优化**：`deps.py` 返回类型 `Any` → 具体类型 (`Settings`/`HybridSearch`/`BaseLLM`/`IngestionPipeline`)
- **Service 层解耦**：从 `bid_document.py` (783行) 提取 `BidDocumentService` 类
  - 文件解析、条款提取、大纲生成、内容填充、DOCX 导出、水印功能独立为 Service 方法
  - Router 层仅保留参数校验和响应包装
- **`__all__` 导出**：`src/__init__.py`、`src/services/__init__.py`、`api/routers/__init__.py` 添加公开接口声明
- **命名常量**：硬编码魔法数字提取为带文档注释的模块级常量

### 📝 文档更新

- `README.md`：移除"内置 API Key"不安全描述，更新 `.env` 配置说明
- `docs/CODE_REVIEW_REPORT.md`：完整审查报告 + 修复记录

### 修改文件清单

| 文件 | 操作 |
|------|------|
| `.gitignore` | 修改 — 恢复 .env 排除 |
| `.env.example` | 新增 — 安全配置模板 |
| `api/deps.py` | 重写 — 类型标注 + 并发安全 |
| `api/main.py` | 重构 — lifespan 迁移 + logger |
| `api/routers/__init__.py` | 修改 — 添加 `__all__` |
| `api/routers/bid_document.py` | 重构 — 委托 BidDocumentService |
| `api/middlewares/rate_limiter.py` | 修改 — 常量文档化 |
| `src/__init__.py` | 修改 — 补全 `__all__` |
| `src/bid/clause_extractor.py` | 修改 — 提取常量 |
| `src/libs/llm/openai_llm.py` | 重构 — 连接池 + 超时修复 |
| `src/services/__init__.py` | 修改 — 添加 `__all__` |
| `src/services/bid_document_service.py` | 新增 — 标书助手 Service 层 |
| `src/services/cache_service.py` | 修改 — DEFAULT_TTL 常量 |
| `src/services/chat_service.py` | 修改 — 常量文档化 |
| `docs/CODE_REVIEW_REPORT.md` | 新增 — 完整代码审查报告 |
| `README.md` | 修改 — 安全说明更新 |
