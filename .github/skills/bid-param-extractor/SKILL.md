---
name: bid-param-extractor
description: "从产品技术文档（PDF/PPTX/DOCX）中提取结构化技术参数。支持任意产品品类（摄像头、服务器、交换机、音响等），输出动态 KV 参数列表。用于标书助手的产品知识库构建和厂家送审资料解析。Use when user says '提取参数', '解析技术资料', 'extract params', '产品参数', or uploads vendor technical documents for parameter extraction."
---

# 产品技术参数提取器

从产品技术文档中提取结构化参数，支持任意品类，输出统一的动态 KV 格式。

## 工作流

```
上传文档 → IngestionPipeline 解析 → LLM 参数提取 → 参数汇总 → 存储
```

## 参数输出格式（动态 KV）

不同品类参数字段完全不同，采用统一的动态数组格式：

```json
{
  "product_name": "产品名称",
  "model": "型号",
  "vendor": "厂家",
  "category": "品类",
  "params": [
    {"name": "参数名", "value": "参数值", "unit": "单位"}
  ]
}
```

## 提取 Prompt

使用 `references/extraction_prompt.md` 中的 prompt 模板。关键要求：

1. **不预设字段** — LLM 自行从文本中识别所有技术参数
2. **保留原始值** — 不做单位转换或数值推算
3. **区分品类** — 输出 category 字段供后续检索过滤
4. **处理表格** — 技术参数常出现在表格中，需识别行列对应关系

## 多 Chunk 参数合并

一份文档会产生多个 chunk，每个 chunk 可能提取出部分参数。合并规则：

1. 以 `(vendor, model)` 为唯一键分组
2. 同名参数取**最详细**的值（如"400万"vs"400万像素 2688×1520"取后者）
3. 合并后去重

合并脚本: `scripts/merge_params.py`

## 品类参考

不同品类的典型参数字段见 `references/category_examples.md`。
这份文件仅作为**参考**，LLM 不强制按此提取，而是从文档实际内容中自主识别。
