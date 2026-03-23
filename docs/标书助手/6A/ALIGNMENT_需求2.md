# ALIGNMENT — 需求2：业绩库智能检索助手

## 已确认决策

| # | 问题 | 决策 |
|---|------|------|
| 1 | 数据存储方案 | **SQLite + ChromaDB 双写**：结构化字段存 SQLite（筛选/排序/CRUD），文本摘要写入 ChromaDB（语义检索） |
| 2 | 附件管理 | **上传到系统管理**：前端上传附件，后端存到 `data/attachments/{record_id}/`，提供下载 API |
| 3 | 交互方式 | **混合模式**：Tab 切换「业绩管理」（表格+CRUD+导入）和「智能检索」（对话式问答），共享数据 |
| 4 | 批量导入 | **两者都支持**：Excel/CSV 批量导入 + 合同 PDF LLM 智能提取 |
| 5 | 布局方案 | **Tab 切换**：两个 Tab 独立视图，业绩管理 Tab 做表格 CRUD，智能检索 Tab 做对话式 |

## 数据模型

### 业绩记录表 `achievements`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| project_name | TEXT NOT NULL | 项目名称 |
| project_content | TEXT | 项目内容/描述 |
| amount | REAL | 合同金额（万元） |
| sign_date | TEXT | 合同签订时间 (YYYY-MM-DD) |
| acceptance_date | TEXT | 验收时间 (YYYY-MM-DD) |
| client_contact | TEXT | 甲方联系人 |
| client_phone | TEXT | 联系方式 |
| tags | TEXT | 标签（JSON 数组，如 ["智慧城市","安防"]） |
| attachments | TEXT | 附件列表（JSON 数组，含 filename + path） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### ChromaDB 同步

每条业绩记录同步写入 ChromaDB `achievements` collection：
- **text**: `{project_name} {project_content}`（用于语义检索）
- **metadata**: `{ id, amount, sign_date, acceptance_date, client_contact, tags }`

## 不变约束

- 不影响现有知识库问答、需求1 功能
- 复用现有暗黑毛玻璃 UI 风格
- 前端作为 BidAssistant 下拉菜单的第二个选项
- Git 提交由用户手动控制
