---
name: bid-param-comparator
description: "比对两份产品技术参数（官方 vs 厂家送审），逐项识别一致/偏差/缺失/新增，生成带风险等级的偏差报告。用于标书助手的产品技术资料真伪性辨别。Use when user says '参数比对', '真伪比对', '对比参数', 'compare params', '偏差报告', or wants to verify vendor-provided technical specs against official product specs."
---

# 产品技术参数比对器

比对官方参数与厂家送审参数，生成结构化偏差报告，标注风险等级。

## 工作流

```
选择官方产品 + 厂家送审资料 → 获取两份参数 JSON → LLM 语义比对 → 偏差报告（SSE 流式）
```

## 核心难点：参数名不一致

不同厂家对同一参数命名不同，不能做字段名精确匹配：

| 官方参数名 | 厂家参数名 | 实际是同一参数 |
|-----------|-----------|--------------|
| 分辨率 | 像素数量 | ✅ |
| 工作温度 | Operating Temperature | ✅ |
| 防护等级 | 防水防尘等级 | ✅ |
| 背板带宽 | 交换容量 | ✅ |

解决方式：**LLM 语义对齐**，不依赖字段名匹配。

## 比对 Prompt

使用 `references/comparison_prompt.md` 中的模板。

## 风险等级判定规则

见 `references/risk_rules.md`。

## 输出格式

Markdown 表格 + 统计汇总 + 风险提示，通过 SSE 流式输出到前端。
