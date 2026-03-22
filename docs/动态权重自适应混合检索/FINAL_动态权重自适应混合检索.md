# FINAL - 动态权重自适应混合检索 (Auto-Tuning Hybrid Search)

## 1. 任务完成情况总结
成功在 RAG 检索链路中引入了基于意图的动态权重自适应逻辑。系统现在能够根据用户查询的句法特征（版本号、疑问词等），自动调节向量检索与关键词检索的融合比重。

## 2. 交付物清单
### 核心代码
- [src/core/types.py](file:///d:/WorkSpace/project/个人项目/RAG/src/core/types.py): 扩展 `ProcessedQuery` 数据类。
- [src/core/query_engine/query_processor.py](file:///d:/WorkSpace/project/个人项目/RAG/src/core/query_engine/query_processor.py): 核心意图识别引擎实现。
- [src/core/query_engine/hybrid_search.py](file:///d:/WorkSpace/project/个人项目/RAG/src/core/query_engine/hybrid_search.py): 检索链路集成与权重透传。

### 测试用例
- [tests/unit/test_auto_tuning.py](file:///d:/WorkSpace/project/个人项目/RAG/tests/unit/test_auto_tuning.py): 覆盖 Sparse、Dense、Neutral 意图的 15+ 种场景。

## 3. 技术收益
- **更精准的工程检索**: 对于包含精确版本号或错误代码的查询，系统现在优先信任 BM25 结果，减少了向量误匹配。
- **更好的问答体验**: 对于开放式提问，系统优先信任向量语义，确保回答更具有相关性。
- **高性能检测**: 采用启发式正则引擎，检测开销几乎可以忽略不计。

## 4. 后续建议
- **模型化升级**: 随着样本积累，可将正则引擎替换为专门的微型 Intent Classifier 模型。
- **权重微调**: 根据用户 RLHF 反馈，动态调整 `[0.3, 1.7]` 的具体系数。
