# TASK — 需求3：标书商务文件编写助手

## 实现状态

| 任务 | 状态 | 说明 |
|------|------|------|
| ALIGNMENT 文档 | ✅ 完成 | `ALIGNMENT_需求3.md` |
| CONSENSUS 文档 | ✅ 完成 | `CONSENSUS_需求3.md` |
| DESIGN 文档 | ✅ 完成 | `DESIGN_需求3.md` |
| ACCEPTANCE 文档 | ✅ 完成 | `ACCEPTANCE_需求3.md` |
| 后端数据库模型 | ✅ 完成 | `src/bid/document_db.py` |
| 条款提取器 | ✅ 完成 | `src/bid/clause_extractor.py` |
| 大纲生成器 | ✅ 完成 | `src/bid/outline_generator.py` |
| 内容填充器 | ✅ 完成 | `src/bid/content_filler.py` |
| 水印处理器 | ✅ 完成 | `src/bid/watermark.py` |
| Word 导出器 | ✅ 完成 | `src/bid/docx_exporter.py` |
| API 路由 | ✅ 完成 | `api/routers/bid_document.py` |
| 前端组件 | ✅ 完成 | `web/src/components/bid/BidDocumentWriter.vue` |
| 主页面集成 | ✅ 完成 | `web/src/views/BidAssistant.vue` 已更新 |
| 依赖更新 | ✅ 完成 | `pyproject.toml` 添加 python-docx, pdf2image |

## 新增文件清单

### 后端
- `src/bid/document_db.py` — 数据库模型（材料、模板、会话）
- `src/bid/clause_extractor.py` — 条款提取器
- `src/bid/outline_generator.py` — 大纲生成器
- `src/bid/content_filler.py` — 内容填充器
- `src/bid/watermark.py` — 水印处理器
- `src/bid/docx_exporter.py` — Word 导出器
- `api/routers/bid_document.py` — API 路由

### 前端
- `web/src/components/bid/BidDocumentWriter.vue` — 商务文件编写组件

### 修改文件
- `api/main.py` — 注册 bid_document 路由
- `web/src/views/BidAssistant.vue` — 更新模块配置，引入新组件
- `pyproject.toml` — 添加 python-docx, pdf2image 依赖

## 依赖安装

```bash
# 安装 Python 依赖
pip install python-docx pdf2image

# Windows 需要安装 poppler (用于 pdf2image)
# 下载: https://github.com/oschwartz10612/poppler-windows/releases
# 解压后将 bin 目录添加到 PATH
```

## 启动验证

```bash
# 后端
python main.py

# 前端
cd web && npm run dev
```

访问 http://localhost:5173 → 标书助手 → 选择"需求3：标书商务文件编写助手"

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bid-document/materials/upload` | 上传投标材料 |
| POST | `/api/bid-document/materials` | 创建文本材料 |
| GET | `/api/bid-document/materials` | 列表查询 |
| GET | `/api/bid-document/materials/{id}` | 获取单个材料 |
| PUT | `/api/bid-document/materials/{id}` | 更新材料 |
| DELETE | `/api/bid-document/materials/{id}` | 删除材料 |
| POST | `/api/bid-document/templates` | 创建模板 |
| GET | `/api/bid-document/templates` | 列表查询 |
| POST | `/api/bid-document/upload` | 上传招标文件 |
| POST | `/api/bid-document/extract` | 提取条款 (SSE) |
| POST | `/api/bid-document/outline` | 生成大纲 |
| PUT | `/api/bid-document/outline` | 更新大纲 |
| POST | `/api/bid-document/fill` | 填充内容 (SSE) |
| POST | `/api/bid-document/watermark` | 添加水印 |
| POST | `/api/bid-document/export` | 导出 Word |
| GET | `/api/bid-document/sessions` | 会话列表 |
| GET | `/api/bid-document/sessions/{id}` | 会话详情 |
| DELETE | `/api/bid-document/sessions/{id}` | 删除会话 |

## 数据存储

- SQLite: `data/bid_document.db`
  - `bid_materials` — 投标材料
  - `bid_templates` — 文档模板
  - `document_sessions` — 编写会话
- ChromaDB: `bid_materials` collection（语义检索）
- 文件系统:
  - `data/bid_materials/` — 材料文件
  - `data/tender_files/` — 招标文件
  - `data/exports/` — 导出文件
