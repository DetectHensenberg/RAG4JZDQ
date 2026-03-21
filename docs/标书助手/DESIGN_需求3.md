# DESIGN — 需求3：标书商务文件编写助手

## 现有代码结构

### 前端
- `web/src/views/BidAssistant.vue` — 标书助手主页面，下拉选择模块
- `web/src/components/bid/` — 已有 3 个组件（需求1/2/4）
- 需求3 key: `compliance` → 改为 `document-writer`

### 后端
- `api/routers/bid.py` — 需求1 API
- `api/routers/bid_achievement.py` — 需求2 API
- `api/routers/bid_review.py` — 需求4 API
- `src/bid/` — 业务逻辑模块

## 实现清单

### 1. 前端修改

#### 1.1 BidAssistant.vue 修改
```diff
- { key: 'compliance',  label: '需求3：招标合规性检查助手', disabled: true },
+ { key: 'document-writer', label: '需求3：标书商务文件编写助手' },
```

```diff
+ import BidDocumentWriter from '@/components/bid/BidDocumentWriter.vue'

+ <BidDocumentWriter v-else-if="activeModule === 'document-writer'" />
```

#### 1.2 新增 BidDocumentWriter.vue
6 步向导式交互组件，结构：

```
<template>
  <div class="doc-writer">
    <!-- Step indicator -->
    <div class="step-indicator">...</div>
    
    <!-- Step content -->
    <div class="step-content">
      <Step1Upload v-if="step === 1" />
      <Step2Clauses v-else-if="step === 2" />
      <Step3Outline v-else-if="step === 3" />
      <Step4Fill v-else-if="step === 4" />
      <Step5Watermark v-else-if="step === 5" />
      <Step6Export v-else-if="step === 6" />
    </div>
  </div>
</template>
```

### 2. 后端新增

#### 2.1 数据库模型 `src/bid/document_db.py`

```python
from dataclasses import dataclass
from typing import Optional
import sqlite3
import json
from pathlib import Path

DB_PATH = Path("data/db/bid_document.db")

@dataclass
class BidMaterial:
    id: Optional[int]
    name: str
    category: str  # certificate/financial/declaration/license/template
    file_path: Optional[str]
    content: Optional[str]
    valid_from: Optional[str]
    valid_to: Optional[str]
    metadata: Optional[dict]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class BidTemplate:
    id: Optional[int]
    name: str
    template_type: str  # commitment/declaration/introduction/outline
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class DocumentSession:
    id: Optional[int]
    project_name: Optional[str]
    project_code: Optional[str]
    tender_file_path: Optional[str]
    extracted_clauses: Optional[list]
    outline: Optional[list]
    filled_content: Optional[dict]
    status: str = "draft"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class DocumentDB:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS bid_materials (...);
                CREATE TABLE IF NOT EXISTS bid_templates (...);
                CREATE TABLE IF NOT EXISTS document_sessions (...);
            """)
```

#### 2.2 条款提取器 `src/bid/clause_extractor.py`

```python
CLAUSE_EXTRACTION_PROMPT = """
你是一个专业的招标文件分析助手。请从以下招标文件内容中提取商务文件要求条款。

招标文件内容：
{content}

请以 JSON 格式输出，每个条款包含：
- id: 序号
- title: 条款标题（如"企业营业执照"）
- description: 具体要求描述
- category: 分类（certificate/financial/declaration/license/other）
- required: 是否必须（true/false）
- source_page: 来源页码（如有）

输出格式：
```json
[
  {"id": 1, "title": "...", "description": "...", "category": "...", "required": true, "source_page": "第X页"}
]
```
"""

async def extract_clauses(content: str, llm) -> list[dict]:
    """从招标文件中提取商务文件条款"""
    prompt = CLAUSE_EXTRACTION_PROMPT.format(content=content[:8000])
    response = await llm.agenerate(prompt)
    # 解析 JSON
    return parse_json_from_response(response)
```

#### 2.3 大纲生成器 `src/bid/outline_generator.py`

```python
OUTLINE_GENERATION_PROMPT = """
根据以下商务文件条款要求，生成投标文件商务部分的大纲。

条款要求：
{clauses}

请生成结构化大纲，JSON 格式：
```json
[
  {"id": "1", "title": "公司简介", "level": 1, "clause_ids": [1], "material_category": "introduction"},
  {"id": "1.1", "title": "企业概况", "level": 2, "clause_ids": [1], "material_category": null},
  ...
]
```
"""

async def generate_outline(clauses: list[dict], llm) -> list[dict]:
    """根据条款生成商务文件大纲"""
    pass
```

#### 2.4 内容填充器 `src/bid/content_filler.py`

```python
async def fill_section(section: dict, materials: list, templates: list, llm) -> str:
    """填充单个章节内容"""
    # 1. 从知识库检索相关材料
    # 2. 如果有模板，使用模板填充
    # 3. 否则用 LLM 生成
    pass

async def fill_outline_stream(outline: list, db: DocumentDB, llm):
    """流式填充整个大纲"""
    for section in outline:
        content = await fill_section(section, ...)
        yield {"section_id": section["id"], "content": content}
```

#### 2.5 水印处理器 `src/bid/watermark.py`

```python
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

def add_watermark_to_image(
    image_path: str,
    watermark_text: str,
    output_path: str,
    opacity: int = 50,
    angle: int = -30
) -> str:
    """为图片添加斜向水印"""
    img = Image.open(image_path).convert("RGBA")
    txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    # 计算字体大小（图片宽度的 1/10）
    font_size = max(20, img.width // 10)
    try:
        font = ImageFont.truetype("simhei.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    # 平铺水印
    bbox = draw.textbbox((0, 0), watermark_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    for y in range(0, img.height, text_height * 3):
        for x in range(0, img.width, text_width + 50):
            draw.text((x, y), watermark_text, font=font, fill=(128, 128, 128, opacity))
    
    # 旋转水印层
    txt_layer = txt_layer.rotate(angle, expand=False, center=(img.width//2, img.height//2))
    
    # 合并
    result = Image.alpha_composite(img, txt_layer)
    result.convert("RGB").save(output_path)
    return output_path


def add_watermark_to_pdf(
    pdf_path: str,
    watermark_text: str,
    output_path: str
) -> str:
    """为 PDF 添加水印"""
    from pdf2image import convert_from_path
    from PIL import Image
    import tempfile
    
    # PDF 转图片
    images = convert_from_path(pdf_path)
    watermarked = []
    
    for i, img in enumerate(images):
        temp_path = f"{tempfile.gettempdir()}/page_{i}.png"
        img.save(temp_path)
        wm_path = f"{tempfile.gettempdir()}/page_{i}_wm.png"
        add_watermark_to_image(temp_path, watermark_text, wm_path)
        watermarked.append(Image.open(wm_path).convert("RGB"))
    
    # 合并为 PDF
    watermarked[0].save(output_path, save_all=True, append_images=watermarked[1:])
    return output_path
```

#### 2.6 Word 导出器 `src/bid/docx_exporter.py`

```python
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pathlib import Path

def export_to_docx(
    outline: list[dict],
    content: dict[str, str],
    attachments: dict[str, str],  # section_id -> file_path
    output_path: str,
    project_name: str = ""
) -> str:
    """导出 Word 文档"""
    doc = Document()
    
    # 设置页面边距
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)
    
    # 添加标题
    title = doc.add_heading(f"{project_name} 商务文件", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 遍历大纲
    for item in outline:
        # 添加章节标题
        doc.add_heading(item["title"], level=item.get("level", 1))
        
        # 添加内容
        section_id = item["id"]
        if section_id in content:
            doc.add_paragraph(content[section_id])
        
        # 添加附件图片
        if section_id in attachments:
            file_path = attachments[section_id]
            if Path(file_path).suffix.lower() in [".jpg", ".jpeg", ".png"]:
                doc.add_picture(file_path, width=Inches(5.5))
    
    doc.save(output_path)
    return output_path
```

#### 2.7 API 路由 `api/routers/bid_document.py`

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter(prefix="/api/bid/document", tags=["bid-document"])

# ── 材料管理 ──────────────────────────────────────────────────────

@router.post("/materials")
async def upload_material(file: UploadFile, name: str, category: str, ...):
    """上传投标材料"""
    pass

@router.get("/materials")
async def list_materials(category: Optional[str] = None):
    """列表查询"""
    pass

@router.get("/materials/{id}")
async def get_material(id: int):
    """获取单个材料"""
    pass

@router.delete("/materials/{id}")
async def delete_material(id: int):
    """删除材料"""
    pass

# ── 模板管理 ──────────────────────────────────────────────────────

@router.post("/templates")
async def create_template(name: str, template_type: str, content: str):
    """创建模板"""
    pass

@router.get("/templates")
async def list_templates(template_type: Optional[str] = None):
    """列表查询"""
    pass

# ── 商务文件编写流程 ──────────────────────────────────────────────

class ExtractRequest(BaseModel):
    session_id: int

@router.post("/upload")
async def upload_tender_file(file: UploadFile = File(...)):
    """上传招标文件，创建会话"""
    # 1. 保存文件
    # 2. 创建 session
    # 3. 返回 session_id
    pass

@router.post("/extract")
async def extract_clauses(req: ExtractRequest):
    """提取商务文件条款 (SSE 流式)"""
    async def generate():
        # 1. 读取招标文件
        # 2. LLM 提取条款
        # 3. 流式返回
        pass
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/outline")
async def generate_outline(session_id: int):
    """生成大纲"""
    pass

@router.put("/outline")
async def update_outline(session_id: int, outline: list):
    """更新大纲（用户编辑）"""
    pass

@router.post("/fill")
async def fill_content(session_id: int):
    """填充内容 (SSE 流式)"""
    async def generate():
        pass
    return StreamingResponse(generate(), media_type="text/event-stream")

class WatermarkRequest(BaseModel):
    material_ids: list[int]
    project_code: str

@router.post("/watermark")
async def add_watermark(req: WatermarkRequest):
    """为指定材料添加水印"""
    pass

@router.post("/export")
async def export_document(session_id: int, format: str = "docx"):
    """导出 Word 文档"""
    pass

# ── 会话管理 ──────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    """获取会话列表"""
    pass

@router.get("/sessions/{id}")
async def get_session(id: int):
    """获取会话详情"""
    pass

@router.delete("/sessions/{id}")
async def delete_session(id: int):
    """删除会话"""
    pass
```

## 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/bid/document_db.py` | 数据库模型（材料、模板、会话） |
| `src/bid/clause_extractor.py` | 条款提取器 |
| `src/bid/outline_generator.py` | 大纲生成器 |
| `src/bid/content_filler.py` | 内容填充器 |
| `src/bid/watermark.py` | 水印处理器 |
| `src/bid/docx_exporter.py` | Word 导出器 |
| `api/routers/bid_document.py` | API 路由 |
| `web/src/components/bid/BidDocumentWriter.vue` | 前端组件 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `web/src/views/BidAssistant.vue` | 更新模块配置，引入新组件 |
| `api/main.py` | 注册新路由 |
| `pyproject.toml` | 添加依赖 python-docx, PyPDF2, pdf2image |

## 依赖项

```toml
# pyproject.toml 新增
python-docx = "^0.8.11"
PyPDF2 = "^3.0.0"
pdf2image = "^1.16.0"
```

> **注意**: pdf2image 需要系统安装 poppler，Windows 需要下载 poppler-windows 并配置 PATH

---

**请审批以上 DESIGN 详细设计文档，确认后我将进入 ACCEPTANCE 阶段（验收标准）。**
