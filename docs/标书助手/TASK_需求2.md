# TASK — 需求2：业绩库智能检索助手

## 原子任务列表

| # | 任务 | 依赖 | 产出文件 |
|---|------|------|----------|
| T1 | 业绩数据 SQLite 模型 + CRUD | - | `src/bid/achievement_db.py` |
| T2 | 附件管理器 | - | `src/bid/attachment_manager.py` |
| T3 | ChromaDB 同步写入（create/update/delete 时双写） | T1 | `achievement_db.py` 内集成 |
| T4 | Excel/CSV 批量导入 | T1 | `src/bid/achievement_import.py` |
| T5 | 合同 PDF LLM 智能提取 | T1 | `src/bid/achievement_pdf_extractor.py` |
| T6 | 后端 API Router（CRUD + 筛选 + 语义检索 + 附件 + 导入） | T1-T5 | `api/routers/bid_achievement.py` |
| T7 | 前端子组件（Tab 业绩管理 + Tab 智能检索） | T6 | `web/src/components/bid/BidAchievementSearch.vue` |
| T8 | BidAssistant.vue 注册需求2模块 | T7 | `web/src/views/BidAssistant.vue` |
| T9 | 联调验证（构建 + import + 路由） | T8 | - |

## 验收标准

- [ ] 业绩 CRUD 可正常新增/编辑/删除/列表查询
- [ ] 支持按关键词、时间范围、金额范围筛选
- [ ] 语义检索返回相似度排序的业绩记录
- [ ] 附件可上传/下载/删除
- [ ] Excel/CSV 批量导入正常工作
- [ ] PDF 智能提取能解析出结构化字段
- [ ] 前端两个 Tab 均可正常操作
- [ ] Vite 构建通过，不影响现有功能
