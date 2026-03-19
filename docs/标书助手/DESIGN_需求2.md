# DESIGN — 需求2：业绩库智能检索助手

## 1. 架构总览

```
┌─────────────────────────────────────────────────┐
│  BidAssistant.vue (顶层壳)                       │
│  ┌─────────────────────────────────────────────┐ │
│  │ 需求2: BidAchievementSearch.vue             │ │
│  │ ┌──────────────────┬──────────────────────┐ │ │
│  │ │  Tab: 业绩管理    │  Tab: 智能检索        │ │ │
│  │ │  - 筛选栏         │  - 对话式问答         │ │ │
│  │ │  - 业绩表格       │  - 业绩卡片结果       │ │ │
│  │ │  - 新增/编辑弹窗  │  - 附件下载           │ │ │
│  │ │  - 批量导入       │                      │ │ │
│  │ │  - 附件管理       │                      │ │ │
│  │ └──────────────────┴──────────────────────┘ │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  FastAPI: api/routers/bid_achievement.py         │
│  POST   /api/bid-achievement/list     (分页筛选)  │
│  POST   /api/bid-achievement/create   (新增)      │
│  PUT    /api/bid-achievement/{id}     (编辑)      │
│  DELETE /api/bid-achievement/{id}     (删除)      │
│  POST   /api/bid-achievement/search   (语义检索)   │
│  POST   /api/bid-achievement/import-excel (批量)   │
│  POST   /api/bid-achievement/import-pdf   (LLM)   │
│  POST   /api/bid-achievement/{id}/attachments     │
│  GET    /api/bid-achievement/{id}/attachments/{fn} │
│  DELETE /api/bid-achievement/{id}/attachments/{fn} │
└─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  SQLite      │  │  ChromaDB    │  │  文件系统     │
│  achievements│  │  achievements│  │  data/        │
│  (结构化CRUD)│  │  (语义检索)  │  │  attachments/ │
└──────────────┘  └──────────────┘  └──────────────┘
```

## 2. 后端模块

### 2.1 数据层：`src/bid/achievement_db.py`

- `AchievementRecord` frozen dataclass
- SQLite CRUD：`create`, `update`, `delete`, `get_by_id`, `list_records`（分页+筛选）
- ChromaDB 同步：create/update 时写入 `achievements` collection，delete 时移除
- 筛选支持：关键词（LIKE）、金额范围、时间范围、标签

### 2.2 附件管理：`src/bid/attachment_manager.py`

- 附件存储路径：`data/attachments/{record_id}/{filename}`
- `save_attachment(record_id, filename, content) -> path`
- `delete_attachment(record_id, filename)`
- `list_attachments(record_id) -> List[AttachmentInfo]`
- `get_attachment_path(record_id, filename) -> Path`

### 2.3 批量导入

- **Excel/CSV**：`src/bid/achievement_import.py` → 用 `openpyxl`/`csv` 解析，列映射，批量 create
- **PDF 智能提取**：`src/bid/achievement_pdf_extractor.py` → 用现有 LLM 调用，prompt 提取结构化字段

### 2.4 API Router：`api/routers/bid_achievement.py`

- prefix: `/api/bid-achievement`
- 所有端点都经过 `verify_api_key` 中间件
- 语义检索端点调用 ChromaDB hybrid search，返回匹配记录 + 相似度分数

## 3. 前端模块

### 3.1 `web/src/components/bid/BidAchievementSearch.vue`

**Tab 1: 业绩管理**
- 顶部筛选栏：关键词搜索 + 时间范围 + 金额范围 + 标签筛选
- 业绩表格：ElTable，分页，排序
- 操作：新增、编辑（弹窗表单）、删除
- 附件管理：每行展开后显示附件列表，可上传/下载/删除
- 批量导入按钮：Excel/CSV 上传 + PDF 智能提取

**Tab 2: 智能检索**
- 对话式聊天界面（复用 chat pattern）
- 用户输入自然语言查询
- 系统返回匹配的业绩卡片列表（含相似度分数）
- 卡片可展开查看详情和附件
- 支持"复制摘要"和"下载附件"操作

### 3.2 注册到 BidAssistant

在 `BidAssistant.vue` 的 `modules` 数组中添加需求2选项。

## 4. 技术选型

| 组件 | 选型 |
|------|------|
| 结构化存储 | SQLite（achievement_db.py） |
| 语义检索 | ChromaDB `achievements` collection |
| Excel 解析 | openpyxl（.xlsx）+ csv 标准库 |
| PDF 提取 | 现有 LLM 调用 + 自定义 prompt |
| 附件存储 | 本地文件系统 data/attachments/ |
| 前端表格 | ElementPlus ElTable + ElPagination |
| 前端对话 | 复用 useSSE composable + chat pattern |
