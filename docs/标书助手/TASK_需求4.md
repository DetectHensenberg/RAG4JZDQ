# TASK — 需求4：标书智能化审查助手

## 原子任务列表

| # | 任务 | 依赖 | 产出文件 |
|---|------|------|----------|
| T1 | 废标项数据模型 + 规则引擎（正则粗筛） | - | `src/bid/review_engine.py` |
| T2 | LLM 废标项精化识别 + prompt | T1 | `src/bid/review_engine.py` |
| T3 | LLM 核查 + SSE 流式审查报告 + 表格解析 | T1 | `src/bid/review_engine.py` |
| T4 | 后端 API Router（解析/识别/核查 4个端点） | T1-T3 | `api/routers/bid_review.py` |
| T5 | 前端 Step Wizard 组件 | T4 | `web/src/components/bid/BidReviewAssistant.vue` |
| T6 | BidAssistant.vue 注册需求4模块 | T5 | `web/src/views/BidAssistant.vue` |
| T7 | 联调验证（构建 + import） | T6 | - |

## 验收标准

- [ ] 招标文件上传后能提取文本
- [ ] 规则+LLM 能识别废标项并返回结构化清单
- [ ] 废标项清单可编辑（增删改）
- [ ] 投标文件上传后能提取文本
- [ ] SSE 流式核查报告正常输出
- [ ] 完成后解析为结构化表格（响应状态+风险等级）
- [ ] 前端 Step Wizard 四步流程完整可用
- [ ] Vite 构建通过，不影响现有功能
