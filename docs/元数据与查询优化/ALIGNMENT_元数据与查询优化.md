# ALIGNMENT: 元数据增强与查询优化

## 需求来源
整改方案 #6-#11，属于 Phase 1b 和 Phase 2 优化项。

## 优化项清单

| # | 优化项 | 优先级 | 复杂度 | 依赖 |
|---|--------|--------|--------|------|
| 6 | 层级标签 heading_path | P1 | 低 | 无 |
| 7 | content_type + file_name + ingested_at | P1 | 低 | 无 |
| 8 | 元数据过滤 API + 前端 | P2 | 中 | #6, #7 |
| 9 | Chunk 大小 A/B 实验 | P2 | 低 | 无 |
| 10 | 离线质量监控仪表盘 | P2 | 中 | 无 |
| 11 | Query Rewriting / HyDE | P1 | 高 | 无 |

## 决策点

### D1: #9 Chunk 大小调整策略
- **选项 A**: 直接调大到 1500/300，无实验
- **选项 B**: 保持现状 1000/200，后续做 RAGAS 实验
- **推荐**: B（保守，避免影响现有数据）

### D2: #10 监控仪表盘实现方式
- **选项 A**: 新建独立 Dashboard 页面
- **选项 B**: 在现有系统页面增加统计卡片
- **推荐**: B（复用现有 UI，工作量小）

### D3: #11 Query Rewriting 实现范围
- **选项 A**: 仅 LLM Query Rewriting
- **选项 B**: 仅 HyDE
- **选项 C**: 两者都实现，可配置开关
- **推荐**: C（灵活性最高）

## 实施顺序

```
#6 heading_path → #7 content_type → #8 元数据过滤 API
                                  ↘
#11 Query Rewriting/HyDE (独立)    → #10 监控仪表盘
                                  ↗
#9 保持现状（后续 RAGAS 实验）
```

## 预期产出

1. **#6**: `document_chunker.py` 增加 heading_path 字段
2. **#7**: `document_chunker.py` 增加 content_type/file_name/file_ext/ingested_at
3. **#8**: API 增加 filters 参数，前端增加过滤 UI
4. **#9**: 保持现状，记录待实验
5. **#10**: 系统页面增加 ingestion 统计卡片
6. **#11**: 新建 `query_rewriter.py`，支持 LLM 改写 + HyDE
