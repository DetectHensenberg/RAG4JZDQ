# TASK - 检索性能综合优化

## 原子任务拆解

### T1: BM25 基础架构升级 [x]
- [x] 定义 `BaseSparseRetriever` 接口协定。
- [x] 将检索器实例化逻辑迁移至协议，隔离业务层。
- [x] 实现基于 `pickle` 的高效序列化。
- [x] 实现原子写入机制（Temp Folder + atomic move）。

### T2: Ingestion 异步流水线改造 [x]
- [x] `IngestionPipeline` 全链路 `async def` 化。
- [x] 实现 `Transform` 阶段的 `asyncio.gather` 并行调用（LLM 任务）。
- [x] 对接异步进度回调，支持 UI 实时反馈。

### T3: 多模态图像预检测持久化 [x]
- [x] `ImageStorage` 增加 `is_background` 字段存储。
- [x] 封装异步背景检测 `adetect_background`。
- [x] 在摄取阶段（`register_image`）自动执行预检并保存。

### T4: SSE 推送与性能验证 [x]
- [x] 新增 `/ingest/upload-stream` 端点。
- [x] 优化 `chat_stream` 中的并行评分逻辑（去除冗余检测）。
- [x] 编写 `verify_image_opt.py` 与 `test_ingestion_pipeline.py` 进行回归。

## 验证计划
- [x] 运行 BM25 往返测试: `pytest tests/unit/test_bm25_indexer_roundtrip.py`
- [x] 运行摄取进度测试: `pytest tests/unit/test_pipeline_progress.py`
- [x] 运行图像优化脚本: `python tests/verify_image_opt.py`
