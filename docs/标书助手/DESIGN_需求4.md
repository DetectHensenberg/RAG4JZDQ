# DESIGN — 需求4：标书智能化审查助手

## 1. 架构总览

```
┌──────────────────────────────────────────────────────┐
│  BidAssistant.vue (顶层壳)                            │
│  ┌──────────────────────────────────────────────────┐ │
│  │ 需求4: BidReviewAssistant.vue                    │ │
│  │                                                  │ │
│  │  Step 1          Step 2          Step 3          │ │
│  │  上传招标文件 →  确认废标项清单 → 上传投标文件 →  │ │
│  │                  (可编辑)                         │ │
│  │                                Step 4            │ │
│  │                                审查报告           │ │
│  │                                (流式MD+结构表格)  │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI: api/routers/bid_review.py                   │
│  POST /api/bid-review/parse-tender    (解析招标文件)   │
│  POST /api/bid-review/identify-items  (识别废标项)     │
│  POST /api/bid-review/parse-bid       (解析投标文件)   │
│  POST /api/bid-review/check           (SSE 核查报告)   │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────┐  ┌────────────────────────────────────┐
│  LLM         │  │  src/bid/review_engine.py           │
│  (流式输出)  │  │  - extract_disqualification_items() │
│              │  │  - check_bid_response()             │
│              │  │  - parse_review_table()             │
└──────────────┘  └────────────────────────────────────┘
```

## 2. 后端模块

### 2.1 核心引擎：`src/bid/review_engine.py`

**废标项识别（规则 + LLM 混合）：**
1. `_rule_based_scan(text) -> List[RawItem]`：正则/关键词粗筛
   - ★ / ☆ 号项
   - "否则废标"、"不予受理"、"按无效投标处理"
   - "符合性审查"、"资格性审查"、"实质性要求"
   - "必须"、"应当"、"不得"等强制性用语
2. `_llm_refine(raw_items, full_text, llm) -> List[DisqualItem]`：LLM 精化
   - 分类（符合性/资格性/实质性/★号/其他强制）
   - 提取具体要求文本
   - 标注来源页码/章节

**核查（SSE 流式）：**
- `check_bid_response_stream(items, bid_text, llm) -> AsyncGenerator`
  - 逐项核查投标文件中是否有对应响应
  - 流式输出 Markdown 审查报告
  - 完成后解析表格数据

**数据结构：**
```python
@dataclass(frozen=True)
class DisqualItem:
    id: str              # 唯一标识
    category: str        # 符合性/资格性/实质性/★号/其他
    requirement: str     # 具体要求描述
    source_section: str  # 来源章节
    source_page: int     # 来源页码
    original_text: str   # 原文摘录
```

### 2.2 PDF/文档解析

复用现有 PyMuPDF/pdfminer 提取文本，同需求5的 `achievement_pdf_extractor.py` 模式。

### 2.3 API Router：`api/routers/bid_review.py`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/parse-tender` | POST multipart | 上传招标文件，返回提取文本 |
| `/identify-items` | POST JSON | 发送文本 → 规则+LLM识别废标项 |
| `/parse-bid` | POST multipart | 上传投标文件，返回提取文本 |
| `/check` | POST JSON → SSE | 发送废标项清单+投标文本 → 流式核查报告 |

## 3. 前端模块

### 3.1 `web/src/components/bid/BidReviewAssistant.vue`

**El-Steps 向导：**

- **Step 1 - 上传招标文件**
  - 文件上传区（PDF/DOCX）
  - 上传后显示文件名和页数
  - "开始识别废标项" 按钮

- **Step 2 - 确认废标项清单**
  - El-Table 可编辑表格：类型、要求描述、来源章节、页码
  - 操作列：编辑/删除
  - "新增废标项" 按钮
  - "确认清单，进入下一步" 按钮

- **Step 3 - 上传投标文件**
  - 文件上传区
  - "开始审查" 按钮

- **Step 4 - 审查报告**
  - 双 Tab：流式 Markdown 报告 / 结构化表格
  - 表格列：废标项、类型、响应状态(✅已响应/⚠️不完整/❌缺失)、风险等级、详细说明
  - "复制报告"、"重新审查" 按钮

## 4. 技术选型

| 组件 | 选型 |
|------|------|
| PDF解析 | PyMuPDF (fitz) / pdfminer |
| 规则引擎 | Python re 正则 |
| LLM 识别+核查 | 现有 LLM 调用 + 自定义 prompt |
| 流式输出 | SSE (useSSE composable) |
| 表格解析 | 复用 param_comparator 的 parse_table_data 模式 |
| 前端向导 | ElementPlus el-steps |
