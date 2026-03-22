# ALIGNMENT - 动态权重自适应混合检索 (Auto-Tuning Hybrid Search)

## 1. 项目上下文分析
目前的 RAG 系统使用固定的 RRF (Reciprocal Rank Fusion) 参数进行混合检索，无法根据查询特性（如：专有名词 vs 语义宽泛的问题）自动优化检索侧重。

## 2. 需求理解确认
### 2.1 任务目标
引入查询意图识别（Query Intent Classification），自动为 Dense 和 Sparse 检索路径分配动态权重。

### 2.2 核心策略
- **侧重 Sparse (BM25)**: 
  - 包含大量数字、版本号、专有名词、长尾术语。
  - 示例：“SN12345 故障”、“Python 3.12 新特性”。
- **侧重 Dense (Embedding)**:
  - 语义描述性强、口语化问候、概念澄清。
  - 示例：“如何学习编程”、“请向我介绍一下 RAG”。

### 2.3 实现方案
- 在 `QueryProcessor` 中增加 `_detect_intent()` 方法，识别上述特征。
- `ProcessedQuery` 增加 `intent_weights` 属性。
- `HybridSearch` 调用 `RRFFusion.fuse_with_weights` 应用权重。

## 3. 技术约束
- **规则优先**: 初始版本采用启发式正则规则，确保低延迟且易于调试。
- **可插拔**: 意图检测逻辑应易于后期替换为 LLM 或分类模型。
- **平滑兼容**: 默认权重保持 [1.0, 1.0] 以维持现有表现。

## 4. 验收标准
- [ ] 系统能够正确识别包含数字/版本号的查询并调高 BM25 权重。
- [ ] 系统能够识别问句或简短问候并调高 Dense 权重。
- [ ] 检索链路日志中记录了每次查询的意图结果与权重分配。
- [ ] 单元测试覆盖各种意图场景。
