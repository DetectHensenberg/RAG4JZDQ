# TASK: 元数据增强与查询优化

## 原子任务清单

### #6 层级标签 heading_path
| ID | 任务 | 文件 | 验收标准 |
|----|------|------|----------|
| T1 | 实现 `_extract_heading_path()` [x] | `document_chunker.py` | 正确解析 Markdown 标题层级 |
| T2 | 在 `_inherit_metadata()` 中添加 heading_path [x] | `document_chunker.py` | chunk.metadata 包含 heading_path |
| T3 | 编写单元测试 [x] | `tests/unit/test_heading_path.py` | 测试通过 |

### #7 内容类别 + 源标签
| ID | 任务 | 文件 | 验收标准 |
|----|------|------|----------|
| T4 | 实现 `_detect_content_type()` [x] | `document_chunker.py` | 正确识别 table/code/list/text |
| T5 | 添加 file_name/file_ext/ingested_at [x] | `document_chunker.py` | chunk.metadata 包含这些字段 |
| T6 | 编写单元测试 [x] | `tests/unit/test_content_type.py` | 测试通过 |

### #8 元数据过滤 API
| ID | 任务 | 文件 | 验收标准 |
|----|------|------|----------|
| T7 | QueryRequest 增加 filters 字段 [x] | `api/routers/query.py` | API 接受 filters 参数 |
| T8 | 传递 filters 到 HybridSearch [x] | `api/routers/query.py` | filters 正确传递 |

### #10 离线质量监控
| ID | 任务 | 文件 | 验收标准 |
|----|------|------|----------|
| T9 | 创建 IngestionStats 数据类 [x] | `src/ingestion/stats.py` | 统计数据结构定义 |
| T10 | Pipeline 完成后记录统计 [x] | `src/ingestion/pipeline.py` | 统计数据持久化 |
| T11 | 新增 /api/system/ingestion-stats [x] | `api/routers/system.py` | API 返回统计数据 |

### #11 Query Rewriting + HyDE
| ID | 任务 | 文件 | 验收标准 |
|----|------|------|----------|
| T12 | 创建 QueryRewriter 类 [x] | `src/core/query_engine/query_rewriter.py` | 支持 rewrite + hyde |
| T13 | 更新 Settings 配置 [x] | `src/core/settings.py` | 添加 query_rewrite/hyde_enabled |
| T14 | 集成到 HybridSearch [x] | `src/core/query_engine/hybrid_search.py` | 检索前调用 rewriter |
| T15 | 更新 settings.yaml [x] | `config/settings.yaml` | 添加配置项 |
| T16 | 编写单元测试 [x] | `tests/unit/test_query_rewriter.py` | 测试通过 |

### 集成验证
| ID | 任务 | 验收标准 |
|----|------|----------|
| T17 | 运行全部单元测试 [x] | pytest 通过 |
| T18 | 更新整改方案.md [x] | 标记 #6-#11 为已完成 |

## 执行顺序

```
T1 → T2 → T3 (heading_path)
      ↓
T4 → T5 → T6 (content_type)
      ↓
T7 → T8 (filters API)
      ↓
T9 → T10 → T11 (监控统计)
      ↓
T12 → T13 → T14 → T15 → T16 (Query Rewriter)
      ↓
T17 → T18 (验证 + 文档更新)
```

## 预计工作量

- #6 heading_path: 30 分钟
- #7 content_type: 20 分钟
- #8 filters API: 15 分钟
- #10 监控统计: 30 分钟
- #11 Query Rewriter: 45 分钟
- 测试 + 文档: 20 分钟

**总计: ~2.5 小时**
