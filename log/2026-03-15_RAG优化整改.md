# 修改记录：RAG 离线解析与知识库构建优化

> 日期：2026-03-15
> 基于：《阿里面试官：5000份文档扔进去就算建知识库了》整改方案

---

## 一、背景

对标小红书文章中 RAG 知识库构建的 10 个关键优化点，对项目现有实现进行 gap analysis，识别出 3 项核心缺失（#1 PDF 版面分析、#2 OCR 回退、#4 三层语义切分），已完成整改实施。

## 二、新增文件

| 文件 | 说明 |
|------|------|
| `src/libs/loader/layout_pdf_loader.py` | 版面分析 PDF 加载器：基于 PyMuPDF text block 坐标实现多栏检测、阅读顺序重排、扫描页 OCR 回退 |
| `src/libs/splitter/structure_splitter.py` | 三层结构化切分器：结构感知切分 → 语义连贯性合并 → 长度平衡 |
| `docs/RAG优化/阿里面试官：5000份文档扔进去就算建知识库了.md` | 小红书文章转录（17张图片 → Markdown） |
| `docs/RAG优化/整改方案：离线解析与知识库构建优化.md` | 10 点逐项对标分析 + 整改方案 + 面试话术 |
| `tests/unit/test_structure_splitter_quick.py` | StructureSplitter 冒烟测试 |
| `tests/unit/test_layout_loader_quick.py` | LayoutPdfLoader 冒烟测试 |

## 三、修改文件

### 3.1 `src/core/settings.py`

- `IngestionSettings` 新增 `pdf_parser: str = "markitdown"` 字段
- `from_dict()` 解析 `ingestion.pdf_parser` 配置项

### 3.2 `config/settings.yaml`

- `ingestion.splitter`: `"recursive"` → `"structure"`
- `ingestion.pdf_parser`: 新增，值为 `"layout"`

### 3.3 `src/libs/loader/loader_factory.py`

- `create()` 新增 `pdf_parser` 参数
- `.pdf` 文件在 `pdf_parser="layout"` 时路由到 `LayoutPdfLoader`

### 3.4 `src/libs/splitter/splitter_factory.py`

- `_register_builtin_providers()` 新增 `"structure"` → `StructureSplitter` 注册

### 3.5 `src/ingestion/pipeline.py`

- Stage 2 (Document Loading) 从 `settings.ingestion.pdf_parser` 读取配置，传递给 `LoaderFactory.create()`

### 3.6 `src/observability/evaluation/ragas_evaluator.py`

- `_build_wrappers()`: RAGAS LLM `max_tokens` 从 4096 → 8192

### 3.7 `api/routers/evaluation.py`

- RAGAS 评估传参优化：答案截断 500 字符、context 限制 3 个 × 200 字符，避免 faithfulness 指标输出超限

## 四、整改点对照

| # | 整改点 | 状态 | 实现 |
|---|--------|------|------|
| 1 | PDF 多栏版面分析 | ✅ 完成 | `LayoutPdfLoader` — PyMuPDF X坐标聚类检测列边界，按阅读顺序重排 |
| 2 | OCR 表格/代码还原 | ✅ 完成 | `LayoutPdfLoader` — 扫描页检测 + PaddleOCR/Tesseract 自动选择 |
| 3 | PPT 图片信息提取 | ✅ 已有 | `PptxLoader` — Vision LLM 幻灯片理解 |
| 4 | 三层语义切分 | ✅ 完成 | `StructureSplitter` — 结构切分 + 连贯性合并 + 长度平衡 |
| 5 | Chunk Overlap | ✅ 已有 | 200/1000 配置，StructureSplitter 最终阶段统一添加 overlap |

## 五、RAGAS 评估面板修复

- 修复 `Request timed out`：`AsyncOpenAI` 传入 `base_url`（DashScope）
- 修复 `max_tokens` 截断：答案和 context 截断后送评，`max_tokens` 调至 8192
- 评估结果：Faithfulness 17% / Answer Relevancy 84% / Context Precision 100%

## 六、技术栈变更

- 新增可选依赖：`pytesseract`（OCR）、`paddleocr`（OCR，可选）
- 已有依赖无变化：`PyMuPDF`、`langchain-text-splitters`、`Pillow` 均已在项目中
