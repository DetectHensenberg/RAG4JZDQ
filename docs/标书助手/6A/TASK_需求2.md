# TASK �?需�?：业绩库智能检索助�?
## 原子任务列表

| # | 任务 | 依赖 | 产出文件 |
|---|------|------|----------|
| T1 | 业绩数据 SQLite 模型 + CRUD | - | `src/bid/achievement_db.py` |
| T2 | 附件管理�?| - | `src/bid/attachment_manager.py` |
| T3 | ChromaDB 同步写入（create/update/delete 时双写） | T1 | `achievement_db.py` 内集�?|
| T4 | Excel/CSV 批量导入 | T1 | `src/bid/achievement_import.py` |
| T5 | 合同 PDF LLM 智能提取 | T1 | `src/bid/achievement_pdf_extractor.py` |
| T6 | 后端 API Router（CRUD + 筛�?+ 语义检�?+ 附件 + 导入�?| T1-T5 | `api/routers/bid_achievement.py` |
| T7 | 前端子组件（Tab 业绩管理 + Tab 智能检索） | T6 | `web/src/components/bid/BidAchievementSearch.vue` |
| T8 | BidAssistant.vue 注册需�?模块 | T7 | `web/src/views/BidAssistant.vue` |
| T9 | 联调验证（构�?+ import + 路由�?| T8 | - |

## 验收标准

- [X] 业绩 CRUD 可正常新�?编辑/删除/列表查询
- [X] 支持按关键词、时间范围、金额范围筛�?- [X] 语义检索返回相似度排序的业绩记�?- [X] 附件可上�?下载/删除
- [X] Excel/CSV 批量导入正常工作
- [X] PDF 智能提取能解析出结构化字�?- [X] 前端两个 Tab 均可正常操作
- [X] Vite 构建通过，不影响现有功能
