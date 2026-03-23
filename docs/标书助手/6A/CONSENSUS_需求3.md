# CONSENSUS — 需求3：标书商务文件编写助手

## 明确的需求描述

在标书助手页面新增"商务文件编写"Tab（第三个功能），以**混合交互模式**（向导式上传 + 对话式生成）帮助用户快速编制商务文件：

```
Step 1: 上传招标文件（PDF/DOCX）
Step 2: LLM 自动解析商务文件条款要求，生成结构化大纲
Step 3: 用户编辑大纲（拖拽排序、勾选章节）
Step 4: 系统从投标知识库检索并填充内容
Step 5: 用户输入项目编号，系统为证照添加水印
Step 6: 导出 Word 文档
```

## 技术实现方案

### 复用现有组件

| 现有组件 | 复用方式 |
|----------|----------|
| `IngestionPipeline` | 解析招标文件（PDF/DOCX → 文本） |
| `LLMFactory` | 创建 LLM 实例用于条款提取和内容生成 |
| `HybridSearch` | 从 `bid_materials` collection 检索投标材料 |
| SSE 流式输出 | 内容生成流式传输 |
| 需求2 附件管理模式 | 证照文件存储（文件系统 + SQLite 元数据） |

### 新增组件

| 组件 | 说明 |
|------|------|
| `src/bid/clause_extractor.py` | 条款提取器，LLM 解析招标文件提取商务文件要求 |
| `src/bid/outline_generator.py` | 大纲生成器，基于条款和模板生成结构化大纲 |
| `src/bid/content_filler.py` | 内容填充器，从知识库检索并填充各章节 |
| `src/bid/watermark.py` | 水印处理器，为 PDF/图片添加项目水印 |
| `src/bid/docx_exporter.py` | Word 导出器，生成 .docx 文件 |
| `api/routers/bid_document.py` | 商务文件 API 路由 |
| `web/src/components/bid/DocumentWriter.vue` | 商务文件编写前端组件 |

### 数据库设计

#### SQLite 表结构

```sql
-- 投标材料表
CREATE TABLE bid_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- 材料名称
    category TEXT NOT NULL,                -- 分类: certificate/financial/declaration/license/template
    file_path TEXT,                        -- 文件路径 (相对于 data/bid_materials/)
    content TEXT,                          -- 文本内容 (用于检索)
    valid_from TEXT,                       -- 有效期起始 (YYYY-MM-DD)
    valid_to TEXT,                         -- 有效期截止 (YYYY-MM-DD)
    metadata TEXT,                         -- JSON 扩展字段
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 商务文件模板表
CREATE TABLE bid_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- 模板名称
    template_type TEXT NOT NULL,           -- 类型: commitment/declaration/introduction/outline
    content TEXT NOT NULL,                 -- 模板内容 (支持 {{变量}} 占位符)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 商务文件编写会话表 (保存进度)
CREATE TABLE bid_document_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,                     -- 项目名称
    project_code TEXT,                     -- 项目编号 (用于水印)
    tender_file_path TEXT,                 -- 招标文件路径
    extracted_clauses TEXT,                -- 提取的条款 (JSON)
    outline TEXT,                          -- 大纲 (JSON)
    filled_content TEXT,                   -- 已填充内容 (JSON)
    status TEXT DEFAULT 'draft',           -- 状态: draft/completed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### ChromaDB Collection

- **Collection**: `bid_materials`
- **Document**: `{name} {content}`（用于语义检索）
- **Metadata**: `{ id, category, valid_from, valid_to }`

### API 设计

#### 1. 投标材料管理

```
POST   /api/bid/materials              # 上传投标材料
GET    /api/bid/materials              # 列表查询 (支持分类筛选)
GET    /api/bid/materials/{id}         # 获取单个材料
PUT    /api/bid/materials/{id}         # 更新材料
DELETE /api/bid/materials/{id}         # 删除材料
GET    /api/bid/materials/{id}/file    # 下载原始文件
```

#### 2. 模板管理

```
POST   /api/bid/templates              # 创建模板
GET    /api/bid/templates              # 列表查询
GET    /api/bid/templates/{id}         # 获取单个模板
PUT    /api/bid/templates/{id}         # 更新模板
DELETE /api/bid/templates/{id}         # 删除模板
```

#### 3. 商务文件编写流程

```
POST   /api/bid/document/upload        # 上传招标文件
POST   /api/bid/document/extract       # 提取商务文件条款 (SSE 流式)
POST   /api/bid/document/outline       # 生成大纲
PUT    /api/bid/document/outline       # 更新大纲 (用户编辑)
POST   /api/bid/document/fill          # 填充内容 (SSE 流式)
POST   /api/bid/document/watermark     # 为指定材料添加水印
POST   /api/bid/document/export        # 导出 Word 文档
GET    /api/bid/document/sessions      # 获取会话列表
GET    /api/bid/document/sessions/{id} # 获取会话详情
DELETE /api/bid/document/sessions/{id} # 删除会话
```

### 前端组件设计

#### DocumentWriter.vue 结构

```
DocumentWriter.vue
├── Step1: TenderUpload        # 招标文件上传区
├── Step2: ClauseReview        # 条款审查 (LLM 提取结果)
├── Step3: OutlineEditor       # 大纲编辑 (可拖拽表格)
├── Step4: ContentPreview      # 内容预览 (流式填充)
├── Step5: WatermarkConfig     # 水印配置 (项目编号输入)
└── Step6: ExportPanel         # 导出面板 (Word 下载)
```

#### 交互流程

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 上传招标文件                                        │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  📄 拖拽或点击上传招标文件 (PDF/DOCX)                    ││
│  └─────────────────────────────────────────────────────────┘│
│                         ↓ 上传成功                          │
├─────────────────────────────────────────────────────────────┤
│  Step 2: 条款识别                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🔍 正在解析招标文件...                                  ││
│  │  ✅ 识别到 12 条商务文件要求                             ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │ □ 1. 企业营业执照副本                               │││
│  │  │ □ 2. 法人代表身份证                                 │││
│  │  │ □ 3. 近三年财务报表                                 │││
│  │  │ ...                                                 │││
│  │  └─────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
│                         ↓ 确认条款                          │
├─────────────────────────────────────────────────────────────┤
│  Step 3: 大纲编辑                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  📋 商务文件大纲 (可拖拽排序)                            ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │ ☰ 1. 公司简介                    [知识库匹配: ✓]    │││
│  │  │ ☰ 2. 企业资质证书                [知识库匹配: ✓]    │││
│  │  │ ☰ 3. 财务报表                    [知识库匹配: ✓]    │││
│  │  │ ☰ 4. 投标承诺书                  [模板匹配: ✓]      │││
│  │  └─────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
│                         ↓ 开始填充                          │
├─────────────────────────────────────────────────────────────┤
│  Step 4: 内容填充 (流式)                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ⏳ 正在填充内容...                                      ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │ ## 1. 公司简介                                      │││
│  │  │ 中关村科金是一家专注于...                            │││
│  │  │ ▌ (流式输出)                                        │││
│  │  └─────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
│                         ↓ 填充完成                          │
├─────────────────────────────────────────────────────────────┤
│  Step 5: 水印配置                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🔖 项目编号: [________________]                         ││
│  │  水印文字: "仅限于 XXX 项目投标使用"                      ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │ □ 营业执照.pdf                   [添加水印]         │││
│  │  │ □ 法人身份证.jpg                 [添加水印]         │││
│  │  │ □ 资质证书.pdf                   [添加水印]         │││
│  │  └─────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
│                         ↓ 水印添加完成                       │
├─────────────────────────────────────────────────────────────┤
│  Step 6: 导出                                                │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  📥 导出格式: [Word (.docx) ▼]                           ││
│  │  [        导出商务文件        ]                          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 水印处理方案

```python
# src/bid/watermark.py

def add_watermark_to_image(image_path: str, watermark_text: str, output_path: str):
    """为图片添加斜向水印"""
    # 使用 PIL 添加半透明斜向水印
    pass

def add_watermark_to_pdf(pdf_path: str, watermark_text: str, output_path: str):
    """为 PDF 添加水印"""
    # 方案1: 使用 PyPDF2 添加水印层
    # 方案2: pdf2image 转图片 → 添加水印 → img2pdf 转回
    pass
```

### Word 导出方案

```python
# src/bid/docx_exporter.py

from docx import Document
from docx.shared import Inches, Pt

def export_to_docx(outline: list, content: dict, attachments: list, output_path: str):
    """导出 Word 文档"""
    doc = Document()
    
    for section in outline:
        # 添加章节标题
        doc.add_heading(section['title'], level=section['level'])
        
        # 添加内容
        if section['id'] in content:
            doc.add_paragraph(content[section['id']])
        
        # 添加附件图片
        if section.get('attachment'):
            doc.add_picture(section['attachment'], width=Inches(6))
    
    doc.save(output_path)
```

## 依赖项

```
# 新增依赖
python-docx>=0.8.11      # Word 文档生成
PyPDF2>=3.0.0            # PDF 处理
pdf2image>=1.16.0        # PDF 转图片 (需要 poppler)
Pillow>=9.0.0            # 图片处理 (已有)
```

## 技术约束

- ChromaDB 路径不能含中文（已有 fix，使用相对路径）
- 前端设计延续暗黑毛玻璃风格
- 不影响现有知识库问答、需求1、需求2 功能
- 水印处理在后端完成，避免前端安全问题
- Word 导出使用 python-docx，保持简洁排版

## 文件结构

```
src/bid/
├── __init__.py
├── clause_extractor.py      # 条款提取
├── outline_generator.py     # 大纲生成
├── content_filler.py        # 内容填充
├── watermark.py             # 水印处理
├── docx_exporter.py         # Word 导出
└── models.py                # 数据模型

api/routers/
├── bid.py                   # 需求1 API (已有)
├── bid_achievement.py       # 需求2 API (已有)
└── bid_document.py          # 需求3 API (新增)

web/src/components/bid/
├── ProductVerify.vue        # 需求1 组件 (已有)
├── AchievementSearch.vue    # 需求2 组件 (已有)
└── DocumentWriter.vue       # 需求3 组件 (新增)
```

---

**请审批以上 CONSENSUS 共识文档，确认技术方案和 API 设计后，我将进入下一阶段（DESIGN 详细设计）。**
