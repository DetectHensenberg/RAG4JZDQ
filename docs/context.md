
2. 修改 3 个文件:
   - settings.py — bool 改为三态 "auto"|"always"|"never"
   - deps.py — 接线 ParentStore / GraphStore / StrategyRouter
   - hybrid_search.py — 用路由器替换静态标志

  关键设计：复用主 LLM，temperature=0.0, max_tokens=100 极简 Prompt，三级容错降级，完全向后兼容旧配置。

* ▐▛███▜▌ *   Claude Code v2.0.69
* ▝▜█████▛▘ *  claude-opus-4-6-thinking · API Usage Billing
* ▘▘ ▝▝  *   D:\WorkSpace\project\个人项目\RAG

  /model to try Opus 4.5

> 你好

● 你好！有什么可以帮你的吗？

> D:\WorkSpace\project\个人项目\RAG\docs\context.md 阅读我的上下文

● Read(docs\context.md)
  ⎿  Read 91 lines

● 这是你的上下文文件，记录了之前的工作进展。总结如下：

  已完成的工作：

1. 数据库访问异步化 (SQLite I/O 优化) — 已完成。引入 aiosqlite，重构全链路路由，2026-03-21 完成。
2. HNSW 损坏修复 — 已完成。
3. 单元测试修复 — 已完成。
4. Git 历史清理 — 已完成。
5. 系统审查与优化报告已同步更新。

  待执行 / 进行中的工作：

- 优化 2：多模态图像处理 Pipeline 提速，已制定实施计划，尚未开始编码。计划包含两个核心改进：
  a. 持久化 — 在 image_index.db 增加 is_background 字段，背景图检测只需计算一次。
  b. 并行化 — 用 asyncio.create_task 在 LLM 回答生成的同时后台处理图像，提前推送给前端。

  需要我继续执行图像 Pipeline 优化，还是有其他任务？

> 文件更新了，重新读取

● Read(docs\context.md)
  ⎿  Read 127 lines

● 已读取更新后的上下文。总结如下：

  已完成：检索增强优化 (T1-T7)

  新增了 4 个文件，修改了 3 个核心文件，实现了：

- Parent Document Retrieval — 层级分块 + SQLite 父块存储 + 检索时父块溯源扩展
- GraphRAG — LLM 驱动实体/三元组提取 + SQLite 图存储 + 检索时图谱关联追加

  两项功能均默认关闭，通过 config/settings.yaml 配置开关，所有模块 import 测试已通过。

  下一步需求（你的最新指示）：

  不再手动配置开关，而是通过 LLM 意图识别来智能决定是否启用 Parent Retrieval 和 GraphRAG。即在查询时，先让 LLM 判断用户问题的类型，再自动决定是否激活对应的检索增强策略。

  需要我开始规划并实现这个"LLM 驱动的智能检索策略路由"功能吗？

> 需要

● 2 Explore agents finished (ctrl+o to expand)
   ├─ Explore query engine flow · 21 tool uses · 82.5k tokens
   │  ⎿  Done
   └─ Explore settings and types · 8 tool uses · 51.0k tokens
      ⎿  Done

● 探索完成，我已全面了解了当前代码结构。现在让我设计实现方案。

● Plan(Design intent routing plan)
  ⎿  Done (18 tool uses · 90.7k tokens · 3m 36s)

● 让我先验证几个关键文件的细节，确保方案准确。

● Read(src\core\settings.py)
  ⎿  Read 120 lines

● Read(src\core\query_engine\hybrid_search.py)
  ⎿  Read 50 lines

● Read(api\deps.py)
  ⎿  Read 165 lines

● Read(src\core\settings.py)
  ⎿  Read 80 lines

● Read(src\core\query_engine\hybrid_search.py)
  ⎿  Read 50 lines

● Read(src\ingestion\storage\parent_store.py)
  ⎿  Read 40 lines

● Read(src\ingestion\storage\graph_store.py)
  ⎿  Read 40 lines

● Read(src\libs\llm\base_llm.py)
  ⎿  Read 50 lines

● Read(src\libs\llm\base_llm.py)
  ⎿  Read 40 lines

● 所有关键文件已确认。在写最终方案前，有一个问题想确认一下：

● User answered Claude's questions:
  ⎿  · LLM 意图识别的调用方式：是复用现有主 LLM（DashScope/Qwen），还是希望支持指定一个独立的轻量模型？ → 复用主 LLM（推荐）

● 好，复用主 LLM。现在所有信息已齐全，我来写最终实施方案。

● Updated plan
  ⎿  /plan to preview · C:\Users\51178\.claude\plans\sunny-inventing-matsumoto.md

● 方案已写好。总结要点：

1. 新建 1 个文件: strategy_router.py — 核心路由器，包含 LLM 分类 + Pattern 降级
2. 修改 3 个文件:
   - settings.py — bool 改为三态 "auto"|"always"|"never"
   - deps.py — 接线 ParentStore / GraphStore / StrategyRouter
   - hybrid_search.py — 用路由器替换静态标志

  关键设计：复用主 LLM，temperature=0.0, max_tokens=100 极简 Prompt，三级容错降级，完全向后兼容旧配置。

─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Ready to code?

 Here is Claude's plan:
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 LLM 驱动的智能检索策略路由

 目标

 将 Parent Retrieval 和 GraphRAG 的静态配置开关 (parent_retrieval_enabled: bool) 替换为 LLM 意图识别驱动的动态路由。每次查询时，LLM
 分析用户问题类型，自动决定是否启用对应的检索增强策略。

 涉及文件

| 操作 | 文件路径                                                    |
| ---- | ----------------------------------------------------------- |
| 新建 | src/core/query_engine/strategy_router.py                    |
| 修改 | src/core/settings.py (L208-216, L355-363)                   |
| 修改 | src/core/query_engine/hybrid_search.py (L173-183, L400-406) |
| 修改 | api/deps.py (L70-80)                                        |

 实施步骤

 Step 1: 修改 src/core/settings.py — 配置模型改为三态模式

 RetrievalSettings (L208-216): 将布尔字段改为字符串模式字段

# 替换:

 parent_retrieval_enabled: bool = False
 graph_rag_enabled: bool = False

# 改为:

 parent_retrieval_mode: str = "never"   # "auto" | "always" | "never"
 graph_rag_mode: str = "never"          # "auto" | "always" | "never"

 Settings.from_dict() (L355-363): 解析新字段，兼容旧布尔值

# 向后兼容: 旧 bool 映射到新 mode

 if "parent_retrieval_enabled" in retrieval and "parent_retrieval_mode" not in retrieval:
     parent_retrieval_mode = "always" if retrieval["parent_retrieval_enabled"] else "never"
 else:
     parent_retrieval_mode = retrieval.get("parent_retrieval_mode", "never")

# graph_rag_mode 同理

 Step 2: 新建 src/core/query_engine/strategy_router.py — 核心路由器

 类: StrategyRouter

 @dataclass
 class RoutingDecision:
     use_parent_retrieval: bool = False
     use_graph_rag: bool = False
     reasoning: str = ""
     method: str = "config"       # "llm" | "pattern" | "config"
     elapsed_ms: float = 0.0

 核心方法: route(query, trace) -> RoutingDecision

 逻辑流程:

1. 若两个 mode 都是 "always"/"never" → 直接返回静态决策，不调 LLM
2. 至少一个 mode 为 "auto" → 调用 LLM 分类
3. LLM 失败 → 降级到正则模式匹配 (pattern fallback)
4. 静态 mode ("always"/"never") 覆盖 auto 结果

 LLM 分类 Prompt (极简，~50 tokens):

 你是一个查询分类器。分析用户查询，判断需要哪些检索增强策略。

- parent_retrieval: 查询需要长段落、完整章节或上下文连续性时开启
- graph_rag: 查询涉及实体关系、比较、因果链或概念关联时开启

 用户查询: {query}

 仅输出JSON: {"parent": true/false, "graph": true/false, "reason": "一句话理由"}

 调用参数: temperature=0.0, max_tokens=100

 Pattern 降级规则 (LLM 不可用时):

- Parent 触发词: 全文|完整|详细|上下文|章节|总结|概括
- Graph 触发词: 关系|关联|比较|对比|区别|差异|因果|影响

 LLM 实例: 复用主 LLM，通过 deps.py 传入，StrategyRouter 内部不创建 LLM。

 Step 3: 修改 api/deps.py — 接线 ParentStore / GraphStore / StrategyRouter

 在 get_hybrid_search() 中 (L70-80 之后)，增加:

# 1. 按需实例化 ParentStore

 parent_mode = settings.retrieval.parent_retrieval_mode
 if parent_mode != "never":
     from src.ingestion.storage.parent_store import ParentStore
     db_path = str(resolve_path(f"data/db/parent_store/{collection}.db"))
     try:
         _hybrid_search.parent_store = ParentStore(db_path=db_path)
     except Exception as e:
         logger.warning(f"ParentStore init failed: {e}")

# 2. 按需实例化 GraphStore

 graph_mode = settings.retrieval.graph_rag_mode
 if graph_mode != "never":
     from src.ingestion.storage.graph_store import GraphStore
     db_path = str(resolve_path(f"data/db/graph_store/{collection}.db"))
     try:
         _hybrid_search.graph_store = GraphStore(db_path=db_path)
     except Exception as e:
         logger.warning(f"GraphStore init failed: {e}")

# 3. 创建 StrategyRouter (复用主 LLM)

 from src.core.query_engine.strategy_router import StrategyRouter
 llm = get_llm() if parent_mode == "auto" or graph_mode == "auto" else None
 _hybrid_search.strategy_router = StrategyRouter(settings=settings, llm=llm)

 Step 4: 修改 src/core/query_engine/hybrid_search.py — 集成路由器

 init (L173): 新增属性

 self.strategy_router: Optional[Any] = None  # StrategyRouter, set externally

 search() (L400-406): 替换静态检查为动态路由

# 替换原来的 Step 6.5 + Step 6.7:

 if self.strategy_router is not None:
     routing = self.strategy_router.route(query, trace=trace)
     if routing.use_parent_retrieval and self.parent_store is not None:
         final_results = self._expand_with_parents(final_results)
     if routing.use_graph_rag and self.graph_store is not None:
         final_results = self._expand_with_graph(final_results, query)
 else:
     # Legacy path: 静态标志 (向后兼容)
     if self._parent_retrieval_enabled and self.parent_store is not None:
         final_results = self._expand_with_parents(final_results)
     if self._graph_rag_enabled and self.graph_store is not None:
         final_results = self._expand_with_graph(final_results, query)

 容错策略 (三级降级)

 LLM 分类 (primary) → Pattern 正则匹配 (secondary) → 默认关闭 (tertiary)

- LLM 创建失败 / API 超时 / 返回非 JSON → 降级到 Pattern
- Pattern 异常 → 默认 RoutingDecision(False, False)
- Store 初始化失败 → store 为 None，即使路由开启也不执行扩展

 YAML 配置示例

 retrieval:
   dense_top_k: 20
   sparse_top_k: 20
   fusion_top_k: 10
   rrf_k: 60
   parent_retrieval_mode: "auto"   # LLM 智能判断
   graph_rag_mode: "auto"          # LLM 智能判断
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

 Would you like to proceed?

 ❯ 1. Yes, and auto-accept edits
   2. Yes, and manually approve edits
   3. Type here to tell Claude what to change

---

2026-03-22 更新

已完成：LLM 驱动的智能检索策略路由

本次实现：
- 新增 `src/core/query_engine/strategy_router.py`
- `src/core/settings.py` 将检索增强开关升级为三态模式：`auto | always | never`
- `src/core/settings.py` 保留旧布尔配置兼容映射：`parent_retrieval_enabled/graph_rag_enabled -> mode`
- `api/deps.py` 接入 `ParentStore` / `GraphStore` / `StrategyRouter`
- `src/core/query_engine/hybrid_search.py` 改为按查询动态路由是否执行 Parent Retrieval / GraphRAG
- `config/settings.yaml` 已切换为 `parent_retrieval_mode: "auto"` 与 `graph_rag_mode: "auto"`

容错策略：
- 一级：LLM 分类
- 二级：关键词 Pattern fallback
- 三级：默认关闭增强

测试与修复：
- 新增 `tests/unit/test_strategy_router.py`
- 扩展 `tests/unit/test_config_loading.py`
- 扩展 `tests/integration/test_hybrid_search.py`
- 修复测试污染：`tests/conftest.py` 新增自动清理 RetrievalCache 的 fixture

验证结果：
- `tests/unit/test_config_loading.py`
- `tests/unit/test_strategy_router.py`
- `tests/integration/test_hybrid_search.py`
- `tests/unit/test_smoke_imports.py`
- 合计 64 个测试通过

当前状态：
- 智能策略路由已实现并接线完成
- 默认配置已启用 auto 模式
- 旧布尔配置仍可继续使用
