# QA 专项测试计划 — Modular RAG MCP Server

> **版本**: 1.0  
> **日期**: 2025-02-25  
> **测试范围**: 系统功能验证、Dashboard UI 交互、CLI 脚本、Provider 切换、数据生命周期、容错降级  
> **测试环境**: Windows, Python 3.11+, 虚拟环境 `.venv`  
> **当前配置**: Azure 全家桶 (LLM/Embedding/Vision LLM 均为 Azure OpenAI)

---

## 目录

- [A. Dashboard — Overview 页面](#a-dashboard--overview-页面)
- [B. Dashboard — Data Browser 页面](#b-dashboard--data-browser-页面)
- [C. Dashboard — Ingestion Manager 页面](#c-dashboard--ingestion-manager-页面)
- [D. Dashboard — Ingestion Traces 页面](#d-dashboard--ingestion-traces-页面)
- [E. Dashboard — Query Traces 页面](#e-dashboard--query-traces-页面)
- [F. Dashboard — Evaluation Panel 页面](#f-dashboard--evaluation-panel-页面)
- [G. CLI — 数据摄取 (ingest.py)](#g-cli--数据摄取-ingestpy)
- [H. CLI — 查询 (query.py)](#h-cli--查询-querypy)
- [I. CLI — 评估 (evaluate.py)](#i-cli--评估-evaluatepy)
- [J. MCP Server 协议交互](#j-mcp-server-协议交互)
- [K. Provider 切换 — DeepSeek LLM](#k-provider-切换--deepseek-llm)
- [L. Provider 切换 — Reranker 模式](#l-provider-切换--reranker-模式)
- [M. 配置变更与容错](#m-配置变更与容错)
- [N. 数据生命周期闭环](#n-数据生命周期闭环)
- [O. 文档替换与多场景验证](#o-文档替换与多场景验证)

---

## 系统状态定义

测试用例的"状态"列标明该测试需要系统处于哪个状态。测试脚本自动检测当前状态并切换。

| 状态值 | 含义 | 如何到达 |
|--------|------|---------|
| `Empty` | 全空：无数据、无 Trace | `qa_bootstrap.py` 中 clear 步骤，或 Dashboard Clear All Data |
| `Baseline` | 标准数据：default 集合(simple.pdf + with_images.pdf)、test_col 集合(complex_technical_doc.pdf)、有 Trace | `python .github/skills/qa-tester/scripts/qa_bootstrap.py` |
| `DeepSeek` | Baseline + LLM 切到 DeepSeek + Vision 关闭 | `qa_config.py apply deepseek`（需 test_credentials.yaml） |
| `Rerank_LLM` | Baseline + LLM 重排启用 | `qa_config.py apply rerank_llm` |
| `NoVision` | Baseline + Vision LLM 关闭 | `qa_config.py apply no_vision` |
| `InvalidKey` | Baseline + LLM API Key 无效 | `qa_config.py apply invalid_llm_key` |
| `InvalidEmbedKey` | Baseline + Embedding API Key 无效 | `qa_config.py apply invalid_embed_key` |
| `Any` | 任意状态均可 | 无需切换 |

> 所有 config 类状态（DeepSeek/Rerank_LLM 等）测完后执行 `qa_config.py restore` 回到 Baseline。

---

## A. Dashboard — Overview 页面

> 启动方式: `python scripts/start_dashboard.py` → 浏览器打开 `http://localhost:8501`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| A-01 | Overview 页面正常加载 | Baseline | 1. 打开浏览器访问 `http://localhost:8501` | 页面标题显示"📊 System Overview"，无报错 |
| A-02 | 组件配置卡片展示正确 | Baseline | 1. 查看"🔧 Component Configuration"区域 | 显示 LLM(azure/gpt-4o)、Embedding(azure/ada-002)、Vector Store(chroma)、Retrieval、Reranker(none)、Vision LLM(azure/gpt-4o)、Ingestion 共 7 张卡片，provider 和 model 与 settings.yaml 一致 |
| A-03 | 组件卡片详情展开 | Baseline | 1. 点击任意组件卡片的"Details"展开 | 展示该组件的额外配置信息（如 LLM 卡片展示 temperature、max_tokens 等） |
| A-04 | 集合统计显示正确 | Baseline | 1. 查看"📦 Data Assets"区域 | 显示 default 集合的 chunk 数量，数字 > 0 |
| A-05 | 空数据库时的集合统计 | Empty | 1. 查看"📦 Data Assets"区域 | 显示 "⚠️ No collections found or ChromaDB unavailable" 警告信息 |
| A-06 | Trace 统计显示正确 | Baseline | 1. 查看 Trace 统计区域 | 显示 "Total traces" 数字 > 0 |
| A-07 | 无 Trace 时的空状态 | Empty | 1. 查看 Trace 统计区域 | 显示 "No traces recorded yet" 信息提示 |
| A-08 | 修改 settings.yaml 后刷新 | Baseline | 1. 手动编辑 `settings.yaml` 将 `llm.model` 改为 `gpt-4`<br>2. 刷新浏览器页面 | LLM 卡片更新显示 gpt-4（因 ConfigService 重新读取配置），改回 gpt-4o 后再刷新恢复 |

---

## B. Dashboard — Data Browser 页面

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| B-01 | Data Browser 页面正常加载 | Baseline | 1. 左侧导航点击"Data Browser" | 页面显示集合选择下拉框，无报错 |
| B-02 | 集合下拉框选项正确 | Baseline | 1. 点击集合下拉框 | 下拉列表包含 default 和 test_col 两个选项 |
| B-03 | 选择集合后文档列表展示 | Baseline | 1. 下拉框选择 "default" | 页面展示 2 个文档条目（simple.pdf 和 with_images.pdf），每个显示文件名、chunk 数、图片数。simple.pdf 图片数=0，with_images.pdf 图片数≥1 |
| B-04 | 展开文档查看 Chunk 详情 | Baseline | 1. 点击 simple.pdf 文档的展开箭头 | 展示 simple.pdf 的所有 Chunk（数量 ≥ 1），每个 Chunk 显示文本内容（只读文本框，应含 "Sample Document" 相关内容）和 Metadata 展开按钮 |
| B-05 | 查看 Chunk Metadata | Baseline | 1. 展开 simple.pdf 的第一个 Chunk<br>2. 点击"📋 Metadata"展开 | 显示 JSON 格式的 metadata，包含 source 字段（值含 "simple.pdf"）、doc_hash（SHA256 哈希）、title、tags 等字段 |
| B-06 | 查看关联图片预览 | Baseline | 1. 展开含图片的文档(with_images.pdf)<br>2. 查看图片预览区域 | 页面显示图片缩略图（最多 4 列网格排列） |
| B-07 | 切换集合后文档列表刷新 | Baseline | 1. 下拉框从 default 切换到 test_col | 文档列表刷新，显示 test_col 集合的文档（包含 complex_technical_doc.pdf），不再显示 default 的 simple.pdf/with_images.pdf |
| B-08 | 空集合的显示 | Empty | 1. 选择空集合 | 显示 "No documents found" 信息提示 |
| B-09 | Clear All Data — 确认流程 | Baseline | 1. 展开"⚠️ Danger Zone"<br>2. 点击"🗑️ Clear All Data"<br>3. 观察确认对话框 | 出现"✅ Yes, delete everything"和"❌ Cancel"两个按钮，不会直接删除 |
| B-10 | Clear All Data — 取消操作 | Baseline | 1. 点击"❌ Cancel" | 对话框消失，数据未被删除，文档列表不变 |
| B-11 | Clear All Data — 确认删除 | Baseline | 1. 点击"✅ Yes, delete everything" | 显示成功提示，页面刷新后文档列表为空，所有集合数据清空 |
| B-12 | Clear All Data 后验证各存储 | Empty | 1. 切换到 Overview 页面查看集合统计<br>2. 检查 `data/db/chroma` 目录<br>3. 检查 `data/images` 目录<br>4. 检查 `logs/traces.jsonl` | Overview 显示无集合；Chroma 目录被清空或集合为空；Images 目录被清空；traces.jsonl 被清空 |

---

## C. Dashboard — Ingestion Manager 页面

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| C-01 | Ingestion Manager 页面正常加载 | Baseline | 1. 左侧导航点击"Ingestion Manager" | 页面显示文件上传区域和集合输入框，无报错 |
| C-02 | 上传 PDF 文件并摄取 | Baseline | 1. 点击文件上传区域，选择 `tests/fixtures/sample_documents/simple.pdf`<br>2. 集合名保持 "default"<br>3. 点击"🚀 Start Ingestion" | 进度条从 0% 推进，依次显示 integrity→load→split→transform→embed→upsert 各阶段，最终显示成功提示 |
| C-03 | 摄取完成后文档出现在列表 | Baseline | 1. 查看下方文档列表 | 列表中出现 simple.pdf 条目，显示 chunk 数量 > 0 |
| C-04 | 摄取含图片的 PDF | Baseline | 1. 上传 `tests/fixtures/sample_documents/with_images.pdf`<br>2. 点击"🚀 Start Ingestion" | 进度条正常推进，Transform 阶段处理图片 captioning，最终成功。文档列表显示图片数 > 0 |
| C-05 | 摄取到自定义集合 | Baseline | 1. 上传 `tests/fixtures/sample_documents/chinese_technical_doc.pdf`<br>2. 集合名输入 "my_collection"<br>3. 点击"🚀 Start Ingestion" | 摄取成功，文档归入 my_collection 集合。切换到 Data Browser 可看到 my_collection 集合，其中包含 chinese_technical_doc.pdf |
| C-06 | 重复摄取同一文件（幂等性） | Baseline | 1. 再次上传 simple.pdf 到 default 集合<br>2. 点击"🚀 Start Ingestion" | 系统检测到文件已处理（SHA256 匹配），跳过处理或快速完成，不产生重复 Chunk |
| C-07 | 强制重新摄取 | Baseline | 1. 在文档列表中删除 simple.pdf<br>2. 再次上传 simple.pdf 并摄取 | 重新处理全流程，Chunk 重新生成 |
| C-08 | 删除单个文档 | Baseline | 1. 在 default 集合中找到 simple.pdf 条目<br>2. 点击 simple.pdf 旁的"🗑️ Delete"按钮 | simple.pdf 从列表消失，显示成功提示。跨 4 个存储（Chroma、BM25、Images、FileIntegrity）均已清理 |
| C-09 | 删除文档后查询验证 | Baseline | 1. 承接 C-08 删除 simple.pdf 后<br>2. 执行 `python scripts/query.py --query "Sample Document PDF loader" --verbose` | 查询结果不再包含来源为 simple.pdf 的 Chunk，source_file 字段中无 simple.pdf |
| C-10 | 上传非 PDF 文件 | Baseline | 1. 上传 `tests/fixtures/sample_documents/sample.txt`<br>2. 集合名保持 "default"<br>3. 点击"🚀 Start Ingestion" | 文件上传组件接受 txt（支持 pdf/txt/md/docx）。摄取流程正常处理 sample.txt，生成 Chunk 并存入 default 集合 |
| C-11 | 不选择文件直接点击摄取 | Baseline | 1. 不上传任何文件<br>2. 观察是否有"🚀 Start Ingestion"按钮 | 按钮不显示（仅在文件上传后出现），无法误操作 |
| C-12 | 摄取大型 PDF（性能观察） | Baseline | 1. 上传 `tests/fixtures/sample_documents/chinese_long_doc.pdf`（30+ 页中文长文档）<br>2. 集合名保持 "default"<br>3. 点击"🚀 Start Ingestion" | 进度条正常推进，各阶段耗时合理（Transform 可能较慢因 LLM 调用，30+ 页预期 Split 生成较多 Chunk），最终完成无超时 |
| C-13 | 摄取过程中的阶段进度展示 | Baseline | 1. 上传 `tests/fixtures/sample_documents/chinese_technical_doc.pdf`（~8 页，可产生多个 Chunk）<br>2. 集合名保持 "default"，点击"🚀 Start Ingestion"<br>3. 观察进度条 | 进度条文字依次显示各阶段名称（如"transform 2/5"），百分比递增 |

---

## D. Dashboard — Ingestion Traces 页面

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| D-01 | Ingestion Traces 页面正常加载 | Baseline | 1. 左侧导航点击"Ingestion Traces" | 页面显示摄取历史列表，按时间倒序排列 |
| D-02 | Trace 列表条目信息完整 | Baseline | 1. 查看列表中的每个条目 | 每条显示：文件名、总耗时（秒）、时间戳 |
| D-03 | 展开单条 Trace 查看概览指标 | Baseline | 1. 点击 with_images.pdf 对应的 Trace 展开箭头（因含图片，指标更丰富） | 显示 5 个指标卡片：Doc Length、Chunks、Images（≥ 1）、Vectors、Total Time |
| D-04 | 查看耗时瀑布图 | Baseline | 1. 查看瀑布图区域 | 水平条形图显示 load/split/transform/embed/upsert 各阶段的耗时分布，阶段名和耗时(ms)可读 |
| D-05 | Load 阶段 Tab 详情 | Baseline | 1. 展开 simple.pdf 的 Trace<br>2. 点击"📄 Load"Tab | 显示 Doc ID、Text Length（> 0）、Images 数量（simple.pdf 为 0）指标，以及 Raw Text 预览（应含 "Sample Document" 文本） |
| D-06 | Split 阶段 Tab 详情 | Baseline | 1. 点击"✂️ Split"Tab | 显示 Chunks 数量和 Avg Size 指标，每个 Chunk 可展开查看文本内容 |
| D-07 | Transform 阶段 Tab 详情 | Baseline | 1. 展开 with_images.pdf 的 Trace（因含图片，可验证 captioning）<br>2. 点击"🔄 Transform"Tab | 显示 Refined/Enriched/Captioned 数量指标（Captioned ≥ 1），每个 Chunk 可展开查看 metadata (title/tags/summary) 和 before/after 文本对比（双列布局） |
| D-08 | Embed 阶段 Tab 详情 | Baseline | 1. 点击"🔢 Embed"Tab | 显示 Dense Vectors、Dimension、Sparse Docs、Method 指标，以及 Dense/Sparse 编码数据表格 |
| D-09 | Upsert 阶段 Tab 详情 | Baseline | 1. 点击"💾 Upsert"Tab | 显示 Dense Vectors、Sparse BM25、Images 存储数量，以及存储详情展开 |
| D-10 | 无 Trace 时的空状态 | Empty | 1. 打开 Ingestion Traces 页面 | 显示 "No ingestion traces recorded yet" 信息提示 |
| D-11 | 失败的摄取 Trace 展示 | InvalidKey | 1. 查看失败的 Trace | Trace 条目显示失败状态，展开后对应阶段显示红色错误信息 |
| D-12 | 多次摄取的 Trace 排序 | Baseline | 1. 查看 Trace 列表 | 最新的摄取记录排在最前面（倒序），时间戳递减 |

---

## E. Dashboard — Query Traces 页面

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| E-01 | Query Traces 页面正常加载 | Baseline | 1. 左侧导航点击"Query Traces" | 页面显示查询历史列表，有关键词搜索框 |
| E-02 | 关键词搜索过滤 | Baseline | 1. 在搜索框输入 "hybrid search"（Baseline 建立时 qa_bootstrap.py 会执行此查询）<br>2. 观察列表变化 | 仅显示 query 包含 "hybrid search" 的查询 Trace，其他查询 Trace 被过滤掉 |
| E-03 | 展开单条 Trace 查看概览指标 | Baseline | 1. 展开某条 Trace | 显示 5 个指标卡片：Dense Hits、Sparse Hits、Fused、After Rerank、Total Time |
| E-04 | 查看查询耗时瀑布图 | Baseline | 1. 查看瀑布图 | 显示 query_processing/dense/sparse/fusion/rerank 各阶段耗时 |
| E-05 | Query Processing Tab 详情 | Baseline | 1. 点击"🔤 Query Processing"Tab | 显示原始 Query、Method、提取的关键词列表 |
| E-06 | Dense Retrieval Tab 详情 | Baseline | 1. 点击"🟦 Dense"Tab | 显示 Method、Provider、Results 数量、Top-K 设置，以及按分数着色的 Chunk 列表（🟢≥0.8/🟡≥0.5/🔴<0.5） |
| E-07 | Sparse Retrieval Tab 详情 | Baseline | 1. 点击"🟨 Sparse"Tab | 显示 Method (BM25)、Keywords、Results 数量、Top-K，以及 Chunk 列表和分数 |
| E-08 | Fusion Tab 详情 | Baseline | 1. 点击"🟩 Fusion"Tab | 显示 Method (RRF)、Input Lists 数量、Fused Results 数量，以及融合后的统一排名列表 |
| E-09 | Rerank Tab — 未启用情况 | Baseline | 1. 点击"🟪 Rerank"Tab | 显示 "Rerank skipped (not enabled)" 信息提示 |
| E-10 | Dense vs Sparse 结果对比 | Baseline | 1. 分别查看 Dense 和 Sparse Tab | 可对比两路召回的不同 Chunk ID、文档来源、分数，观察互补性 |
| E-11 | Ragas Evaluate 按钮功能 | Baseline | 1. 展开 query 为 "What is hybrid search" 的 Trace（或最新一条 Trace）<br>2. 点击"📏 Ragas Evaluate"按钮<br>3. 等待 loading spinner 完成 | 显示 Ragas 评估结果指标卡片（faithfulness、answer_relevancy、context_precision），分数在 0-1 之间 |
| E-12 | Ragas Evaluate 失败处理 | InvalidKey | 1. 将 settings.yaml 的 llm api_key 改为无效值<br>2. 点击"📏 Ragas Evaluate" | 显示红色错误提示，不崩溃 |
| E-13 | 无查询 Trace 时的空状态 | Empty | 1. 打开 Query Traces 页面 | 显示 "No query traces recorded yet" 信息提示 |

---

## F. Dashboard — Evaluation Panel 页面

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| F-01 | Evaluation Panel 页面正常加载 | Baseline | 1. 左侧导航点击"Evaluation Panel" | 页面显示评估后端选择、参数配置区域 |
| F-02 | Ragas Evaluator 运行 | Baseline | 1. Backend 选择 "ragas"<br>2. Top-K 保持 10<br>3. Golden Path 保持默认<br>4. 点击"▶️ Run Evaluation" | 评估运行（可能较慢），显示 faithfulness、answer_relevancy、context_precision 指标 |
| F-03 | 每条查询的详细结果 | Baseline | 1. 完成一次 Ragas 评估后查看 per-query 结果区域 | 每条 golden test set query 展开显示：检索到的 Chunk ID、生成的答案、各项 Ragas 指标分数 |
| F-04 | Golden Test Set 路径无效 | Baseline | 1. 将 Golden Path 改为 `tests/fixtures/nonexistent_test_set.json`<br>2. 观察"▶️ Run Evaluation"按钮状态 | 按钮变为禁用状态（disabled），显示路径无效警告 |
| F-05 | 评估历史记录展示 | Baseline | 1. 滚动到页面底部的 History 区域 | 显示历史评估运行的表格（最近 10 条），包含时间和各项指标 |
| F-06 | 指定集合名评估 | Baseline | 1. 先在 Ingestion Manager 上传 `tests/fixtures/sample_documents/chinese_technical_doc.pdf` 到集合 "my_collection" 并完成摄取<br>2. 切换到 Evaluation Panel，Collection 输入 "my_collection"<br>3. 运行评估 | 评估仅针对 my_collection 集合的数据进行检索 |
| F-07 | 空知识库运行评估 | Empty | 1. 点击运行评估 | 评估完成但各项指标偏低或为 0，不崩溃 |

---

## G. CLI — 数据摄取 (ingest.py)

> 命令格式: `python scripts/ingest.py --path <路径> [选项]`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| G-01 | 摄取单个 PDF 文件 | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf` | 控制台输出各阶段处理信息，最终显示摄取成功，exit code=0 |
| G-02 | 摄取整个目录 | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/` | 自动发现目录下所有 .pdf 文件，逐个处理，最终显示摄取汇总（成功数/失败数） |
| G-03 | 指定集合名摄取 | Baseline | 1. 执行 `python scripts/ingest.py --path simple.pdf --collection test_col` | 文件摄取到 test_col 集合，可在 Dashboard Data Browser 中看到 |
| G-04 | --dry-run 模式 | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/ --dry-run` | 仅列出将要处理的文件列表，不实际执行摄取，无 API 调用 |
| G-05 | --force 强制重新处理 | Baseline | 1. 执行 `python scripts/ingest.py --path simple.pdf --force` | 跳过 SHA256 检查，强制重新处理全流程 |
| G-06 | 重复摄取（无 --force） | Baseline | 1. 执行 `python scripts/ingest.py --path simple.pdf`（不加 --force） | 控制台提示文件已处理/跳过，不产生重复 Chunk |
| G-07 | --verbose 详细输出 | Baseline | 1. 执行 `python scripts/ingest.py --path simple.pdf --verbose` | 输出 DEBUG 级别日志，包含各阶段详细信息 |
| G-08 | 指定配置文件 | Baseline | 1. 执行 `python scripts/ingest.py --path simple.pdf --config config/settings_test.yaml` | 使用指定配置文件的设置进行摄取 |
| G-09 | 路径不存在时的报错 | Any | 1. 执行 `python scripts/ingest.py --path /不存在的路径/abc.pdf` | 控制台显示清晰的 FileNotFoundError 信息，exit code ≠ 0 |
| G-10 | 非 PDF 文件的处理 | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/`（该目录包含 .pdf 和 sample.txt） | 处理所有 .pdf 文件，sample.txt 被跳过（或有对应 loader 处理），输出汇总显示对 txt 文件的处理情况 |
| G-11 | 摄取含图片 PDF 并验证 captioning | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/with_images.pdf --verbose` | 日志中显示 Image Captioning 处理信息，生成的 caption 文本可见 |

---

## H. CLI — 查询 (query.py)

> 命令格式: `python scripts/query.py --query <查询文本> [选项]`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| H-01 | 基本中文查询 | Baseline | 1. 执行 `python scripts/query.py --query "Transformer 注意力机制是什么"` | 返回相关 Chunk 列表，Top 结果中应包含来自 complex_technical_doc.pdf 或 Baseline 中含相关内容的文档，每个结果显示文本片段、来源文件、分数 |
| H-02 | 指定 top-k 参数 | Baseline | 1. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation modular architecture" --top-k 3` | 最多返回 3 条结果，结果中应包含 complex_technical_doc.pdf 的 Chunk |
| H-03 | 指定集合查询 | Baseline | 1. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation" --collection test_col` | 仅从 test_col 中检索，结果全部来自 complex_technical_doc.pdf，不混入 default 集合的 simple.pdf/with_images.pdf |
| H-04 | --verbose 查看检索详情 | Baseline | 1. 执行 `python scripts/query.py --query "混合检索" --verbose` | 分别显示 Dense 召回结果、Sparse 召回结果、Fusion 融合结果，可对比各路召回 |
| H-05 | --no-rerank 禁用重排 | Rerank_LLM | 1. 执行 `python scripts/query.py --query "BM25 混合检索融合策略" --no-rerank --verbose` | 跳过 Rerank 阶段，直接返回 RRF 融合后的结果，Verbose 中无 Rerank 步骤输出 |
| H-06 | 空查询的处理 | Any | 1. 执行 `python scripts/query.py --query ""` | 返回空结果或合理的提示信息，不崩溃 |
| H-07 | 超长查询的处理 | Any | 1. 执行 `python scripts/query.py --query "Transformer 模型中的自注意力机制如何工作，包括 Multi-Head Attention 和 RoPE 位置编码的原理，以及 KV Cache 优化策略。同时请解释 RAG 系统中混合检索的工作流程，包括 Dense Retrieval、BM25 Sparse Retrieval 和 RRF 融合算法的具体实现方式。还有 Cross-Encoder Reranker 和 LLM Reranker 的对比分析，以及在生产环境中如何选择合适的向量数据库（如 ChromaDB、FAISS、Milvus）来存储和检索 Embedding 向量。请详细说明每个组件的优缺点和适用场景。"`（约 250 字符） | 正常处理（查询可能被截断），返回结果，不超时不崩溃 |
| H-08 | 与摄取文档内容相关的查询 | Baseline | 1. 执行 `python scripts/query.py --query "Precision@5 Recall@10 performance benchmarks" --top-k 3`（该内容存在于 complex_technical_doc.pdf 的性能基准章节） | Top-3 结果中至少有 1 条来自 complex_technical_doc.pdf，文本片段包含 "Precision" 或 "benchmarks" 相关内容，source_file 字段为 complex_technical_doc.pdf |
| H-09 | 与摄取文档无关的查询 | Baseline | 1. 执行 `python scripts/query.py --query "量子力学薛定谔方程"` | 返回结果，但分数较低或无结果，行为合理 |
| H-10 | 查询后 Trace 记录验证 | Baseline | 1. 执行 `python scripts/query.py --query "What is hybrid search and how does it work"`<br>2. 打开 Dashboard Query Traces 页面 | 最新一条 Trace 的 query 文本显示 "What is hybrid search and how does it work"，时间戳为刚才执行的时间 |

---

## I. CLI — 评估 (evaluate.py)

> 命令格式: `python scripts/evaluate.py [选项]`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| I-01 | 默认评估运行 | Baseline | 1. 执行 `python scripts/evaluate.py` | 输出评估结果，包含 hit_rate 和 MRR 指标 |
| I-02 | 指定自定义 golden test set | Baseline | 1. 执行 `python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json` | 使用项目自带的 golden test set（5 条测试用例）运行评估，输出各项指标 |
| I-03 | --json 格式输出 | Baseline | 1. 执行 `python scripts/evaluate.py --json` | 输出 JSON 格式结果（而非格式化文本），可被程序解析 |
| I-04 | --no-search 模式 | Any | 1. 执行 `python scripts/evaluate.py --no-search` | 跳过实际检索，进行 mock 评估（验证评估框架本身可用） |
| I-05 | golden test set 不存在时报错 | Any | 1. 执行 `python scripts/evaluate.py --test-set /不存在.json` | 输出文件未找到的错误信息，exit code ≠ 0 |

---

## J. MCP Server 协议交互

> 启动方式: MCP Client (如 VS Code Copilot/Claude Desktop) 通过 Stdio 启动 `python main.py`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| J-01 | MCP Server 正常启动 | Baseline | 1. 在 VS Code 的 MCP 配置中添加 Server，指向 `python main.py`<br>2. 重启 VS Code / 重新加载 | MCP Server 成功启动，VS Code 显示连接成功 |
| J-02 | tools/list 返回工具列表 | Baseline | 1. 在 Copilot 中触发工具列表（或直接发送 JSON-RPC tools/list） | 返回 3 个工具：query_knowledge_hub、list_collections、get_document_summary |
| J-03 | query_knowledge_hub 查询 | Baseline | 1. 在 Copilot 聊天中提问 "What is hybrid search and how does it work?"（对应 golden_test_set.json 中的测试用例）<br>2. 让 Copilot 调用 query_knowledge_hub 工具 | 返回结构化结果，包含文本内容和引用信息（source_file=complex_technical_doc.pdf、page、score），文本中应含 "dense"、"sparse"、"BM25" 或 "RRF" 等混合检索相关关键词 |
| J-04 | list_collections 功能 | Baseline | 1. 触发 list_collections 工具调用 | 返回所有集合名称和文档数量统计 |
| J-05 | get_document_summary 功能 | Baseline | 1. 触发 get_document_summary 工具调用，传入 doc_id 为 simple.pdf 的文档 ID（可先通过 list_collections 获取） | 返回 simple.pdf 的 title（应含 "Sample Document"）、summary、tags 元信息，内容与文档实际内容匹配 |
| J-06 | 查询返回含图片的多模态结果 | Baseline | 1. 在 Copilot 中调用 query_knowledge_hub，query 参数为 "embedded image document with images"，collection 参数为 "default" | 返回的 content 数组中包含 TextContent 和 ImageContent（Base64），引用信息中 source_file 为 with_images.pdf，Copilot 中可看到图片或图片描述（caption 文本） |
| J-07 | 查询不存在的集合 | Any | 1. 调用 query_knowledge_hub，collection 参数指定 "nonexistent_collection_xyz" | 返回空结果或友好错误提示（如 "Collection not found"），不导致 Server 崩溃 |
| J-08 | 无效参数处理 | Baseline | 1. 发送一个缺少 query 参数的 query_knowledge_hub 调用 | 返回 JSON-RPC 错误码（如 InvalidParams），错误描述清晰 |
| J-09 | Server 长时间运行稳定性 | Baseline | 1. 保持 Server 运行 30 分钟<br>2. 期间执行以下 5 次查询（每隔 5 分钟一次）：<br>  a. "What is Modular RAG?"<br>  b. "How to configure Azure OpenAI?"<br>  c. "Explain the chunking strategy"<br>  d. "What is hybrid search?"<br>  e. "What evaluation metrics are supported?" | 所有 5 次查询均正常响应（返回检索结果），无内存泄漏迹象，无超时，响应时间无明显增长 |
| J-10 | 引用透明性检查 | Baseline | 1. 调用 query_knowledge_hub，query="Sample Document PDF loader"，collection="default"<br>2. 检查返回结果的引用信息 | 每个检索片段包含 source_file（值为 "simple.pdf"）、page（值为 1）、chunk_id（非空字符串）、score（分数在 0-1 之间），支持溯源 |

---

## K. Provider 切换 — DeepSeek LLM

> **前提**: 获取有效的 DeepSeek API Key  
> **范围**: DeepSeek 仅有 LLM（文本对话），无 Embedding API，无 Vision API  
> **切换方式**: 修改 `config/settings.yaml`

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| K-01 | settings.yaml 切换 LLM 到 DeepSeek | DeepSeek | 1. 执行 `python .github/skills/qa-tester/scripts/qa_config.py apply deepseek`<br>2. 检查输出确认切换成功 | 输出显示 "LLM -> deepseek / deepseek-chat"，settings.yaml 已更新 |
| K-02 | DeepSeek LLM — CLI 查询 | DeepSeek | 1. 执行 `python scripts/query.py --query "What is hybrid search and how does it work" --verbose` | 查询成功，返回检索结果（来自 Baseline 数据）。Verbose 输出中可看到 LLM provider 为 DeepSeek |
| K-03 | DeepSeek LLM — 摄取（Chunk Refiner） | DeepSeek | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force --verbose` | Transform 阶段使用 DeepSeek 进行 Chunk 重写，日志可见。重写后的 Chunk 内容合理、中文通顺 |
| K-04 | DeepSeek LLM — 摄取（Metadata Enricher） | DeepSeek | 1. 同 K-03 摄取流程<br>2. 查看 Dashboard Data Browser 中的 Chunk Metadata | Metadata 中 title/summary/tags 字段由 DeepSeek 生成，内容合理 |
| K-05 | DeepSeek LLM — Dashboard Overview 反映配置 | DeepSeek | 1. 打开 Dashboard Overview 页面 | LLM 卡片显示 provider=deepseek, model=deepseek-chat |
| K-06 | DeepSeek LLM — Dashboard Ingestion 管理 | DeepSeek | 1. 在 Dashboard Ingestion Manager 上传 `tests/fixtures/sample_documents/chinese_technical_doc.pdf` 并摄取到 default 集合 | 进度条正常推进，Transform 阶段使用 DeepSeek LLM 完成 Chunk Refine 和 Metadata Enrich，最终成功。Data Browser 中可看到该文档 |
| K-07 | DeepSeek LLM — 关闭 Vision LLM | DeepSeek | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/with_images.pdf --force --verbose` | 图片 Captioning 跳过（因 DeepSeek 无 Vision API），不阻塞流程。日志中显示跳过 captioning，with_images.pdf 的 Chunk 中图片引用保留但无 caption 文本 |
| K-08 | DeepSeek LLM — LLM Rerank 模式 | DeepSeek | 1. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation modular architecture" --verbose` | Rerank 阶段使用 DeepSeek LLM 进行重排序，Verbose 输出可见重排前后的顺序变化，结果来自 complex_technical_doc.pdf |
| K-09 | DeepSeek 回退 Azure 验证 | DeepSeek | 1. 执行 `python .github/skills/qa-tester/scripts/qa_config.py restore`<br>2. 执行 `python scripts/query.py --query "Sample Document PDF loader" --verbose` | 功能恢复正常，Verbose 输出显示使用 Azure LLM，查询结果包含 simple.pdf 相关内容，验证切换回来无副作用 |
| K-10 | DeepSeek API Key 无效的报错 | DeepSeek | 1. 设置 `llm.provider: deepseek`，`api_key` 填入一个无效值<br>2. 执行查询 | 返回清晰的认证失败错误信息（如 401 Unauthorized），不崩溃 |
| K-11 | DeepSeek + Azure Embedding 混合配置 | DeepSeek | 1. 保持 embedding 为 azure<br>2. 执行完整的 ingest→query 流程 | 摄取使用 Azure Embedding 生成向量 + DeepSeek LLM 做 Transform；查询使用 Azure Embedding 做向量检索 + DeepSeek 做 Rerank（如启用）。全流程跑通 |
| K-12 | Ragas 评估使用 DeepSeek LLM | DeepSeek | 1. 在 Dashboard Evaluation Panel 选择 ragas 后端<br>2. 运行评估 | Ragas 使用 DeepSeek 作为 Judge LLM，返回评估指标。（注意：Ragas 可能对 LLM 能力有要求，观察结果是否合理） |

---

## L. Provider 切换 — Reranker 模式

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| L-01 | Reranker=None 模式（默认） | Baseline | 1. 执行 `python scripts/query.py --query "What is hybrid search and how does it work" --verbose` | Verbose 输出显示 Rerank 阶段被跳过，最终结果 = RRF 融合结果，结果包含 complex_technical_doc.pdf 的 Chunk |
| L-02 | 切换到 LLM Reranker | Rerank_LLM | 1. 执行 `python scripts/query.py --query "Explain the chunking strategy and how documents are split" --verbose` | Verbose 输出显示 Rerank 使用 LLM 打分，结果包含 LLM 的相关性评分，重排后排序可能与 RRF 融合结果不同 |
| L-03 | Rerank 前后对比（Query Traces） | Rerank_LLM | 1. 打开 Dashboard Query Traces<br>2. 展开最新的查询 Trace<br>3. 对比 Fusion Tab 和 Rerank Tab | Rerank 之后的排序与 Fusion 排序不同（某些 Chunk 排名上升/下降） |
| L-04 | Reranker top_k 参数生效 | Rerank_LLM | 1. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation modular architecture" --verbose` | Rerank 后最终返回 3 条结果（而非 Fusion 的 10 条），结果应主要来自 complex_technical_doc.pdf |
| L-05 | Reranker 失败后 Fallback | Rerank_LLM | 1. 将 `llm.api_key` 临时改为无效值<br>2. 执行 `python scripts/query.py --query "performance benchmarks Precision Recall" --verbose` | 控制台显示 Rerank 失败的警告，但查询仍返回结果（Fallback 到 RRF 排序），不崩溃 |

---

## M. 配置变更与容错

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| M-01 | Azure LLM API key 错误 | InvalidKey | 1. 将 `llm.api_key` 改为 "invalid_key_12345"<br>2. 执行 `python scripts/query.py --query "测试"` | 终端输出清晰的 API 认证错误（如 "401 Unauthorized" 或 "Invalid API key"），exit code ≠ 0 |
| M-02 | Azure Embedding API key 错误 | InvalidEmbedKey | 1. 将 `embedding.api_key` 改为无效值<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force` | 在 Embed 阶段报错，错误信息明确指向 Embedding API 问题（如 "401 Unauthorized" 或 "Invalid API key"） |
| M-03 | Azure Endpoint URL 错误 | Baseline | 1. 将 `llm.azure_endpoint` 改为 "https://invalid.openai.azure.com/"<br>2. 执行 `python scripts/query.py --query "Sample Document PDF loader"` | 输出连接失败或 DNS 解析失败的错误，不挂起不卡死，exit code ≠ 0 |
| M-04 | Vision LLM 关闭后的摄取 | NoVision | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/with_images.pdf --force --verbose` | 摄取成功完成，日志中显示图片 Captioning 跳过。Dashboard Ingestion Trace 的 Transform Tab 显示 captioned=0，但 Chunk 数量正常 |
| M-05 | settings.yaml 语法错误 | Baseline | 1. 在 settings.yaml 中引入 YAML 语法错误（如缺少冒号）<br>2. 执行 `python scripts/query.py --query "测试"` | 输出配置文件解析错误的清晰提示，exit code=2 |
| M-06 | settings.yaml 缺少必填字段 | Baseline | 1. 删除 `embedding` 整个配置段<br>2. 执行摄取 | 输出明确的缺少配置项的错误提示 |
| M-07 | Chroma 数据目录不存在 | Baseline | 1. 将 `vector_store.persist_directory` 改为一个不存在的路径<br>2. 执行摄取 | 自动创建目录或输出清晰错误 |
| M-08 | traces.jsonl 被删除后的 Dashboard | Baseline | 1. 手动删除 `logs/traces.jsonl`<br>2. 刷新 Dashboard 各页面 | Overview：显示 "No traces recorded yet"；Ingestion/Query Traces：显示空状态提示。不崩溃不报错 |
| M-09 | traces.jsonl 含损坏行 | Baseline | 1. 在 `logs/traces.jsonl` 中手动插入一行非 JSON 内容（如 "broken line"）<br>2. 刷新 Dashboard Traces 页面 | 正常跳过损坏行，其他 Trace 正常展示 |
| M-10 | Chunk Size 参数调整 | Baseline | 1. 将 `ingestion.chunk_size` 从 1000 改为 500<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force`<br>3. 在 Dashboard Data Browser 查看 simple.pdf 的 Chunk 数量 | 生成更多更短的 Chunk（数量应比 chunk_size=1000 时多），每个 Chunk 文本长度 ≤ 500 字符（约） |
| M-11 | Chunk Overlap 参数调整 | Baseline | 1. 将 `ingestion.chunk_overlap` 从 200 改为 0<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force`<br>3. 在 Dashboard Data Browser 展开 simple.pdf 的相邻 Chunk | Chunk 之间无重叠文本（相邻 Chunk 的开头不应与前一个 Chunk 的结尾重复） |
| M-12 | 关闭 LLM Chunk Refiner | Baseline | 1. 将 `ingestion.chunk_refiner.provider` 改为非 LLM 模式（如 rule-based）<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force --verbose`<br>3. 在 Dashboard Data Browser 查看 Chunk 内容 | Transform 使用规则方式（非 LLM）精简 Chunk，摄取速度更快（日志无 LLM 调用记录），Chunk 文本与原始 Split 结果更接近 |
| M-13 | 关闭 LLM Metadata Enricher | Baseline | 1. 将 `ingestion.metadata_enricher.provider` 改为非 LLM 模式（如 rule-based）<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --force`<br>3. 在 Dashboard Data Browser 查看 simple.pdf 的 Chunk Metadata | Metadata 中 title/summary/tags 由规则方式生成（可能为空或简略），无 LLM 增强内容，summary 不会是 LLM 编写的自然语言摘要 |
| M-14 | 调整 retrieval.dense_top_k | Baseline | 1. 将 `retrieval.dense_top_k` 从 20 改为 5<br>2. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation" --verbose` | Dense 路召回最多 5 条结果（Verbose 中 Dense Results 数量 ≤ 5），减少候选集大小 |
| M-15 | 调整 retrieval.rrf_k 常数 | Baseline | 1. 将 `retrieval.rrf_k` 从 60 改为 10<br>2. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation" --verbose`<br>3. 对比与 rrf_k=60 时的融合排序 | RRF 融合使用不同的平滑常数（k=10 会让排名靠前的结果权重更大），Verbose 中可见 fusion 分数变化 |

---

## N. 数据生命周期闭环

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| N-01 | 完整闭环: 摄取→查询→删除→查询 | Empty | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf`<br>2. 执行 `python scripts/query.py --query "Sample Document PDF loader"` → 确认命中<br>3. 在 Dashboard Data Browser 删除 default 集合中的 simple.pdf<br>4. 再次执行 `python scripts/query.py --query "Sample Document PDF loader"` | 步骤 2 返回结果，source_file 含 simple.pdf；步骤 4 不再返回 simple.pdf 相关结果（结果为空或仅含其他文档） |
| N-02 | 删除后重新摄取 | Baseline | 1. 在 Dashboard 删除 default 集合中的 simple.pdf<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf`<br>3. 执行 `python scripts/query.py --query "Sample Document PDF loader"` | 摄取成功（FileIntegrity 记录已清理，不会被跳过），查询重新命中 simple.pdf 的 Chunk |
| N-03 | 多集合隔离验证 | Baseline | 1. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf --collection isolate_a`<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/complex_technical_doc.pdf --collection isolate_b`<br>3. 执行 `python scripts/query.py --query "Sample Document PDF loader" --collection isolate_a`<br>4. 执行 `python scripts/query.py --query "Retrieval-Augmented Generation" --collection isolate_b` | 集合 isolate_a 查询仅返回 simple.pdf 内容（source_file=simple.pdf）；集合 isolate_b 查询仅返回 complex_technical_doc.pdf 内容，互不干扰 |
| N-04 | Clear All Data 后全功能验证 | Baseline | 1. Dashboard Clear All Data<br>2. 执行 `python scripts/query.py --query "Sample Document"` → 无结果<br>3. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/simple.pdf`<br>4. 执行 `python scripts/query.py --query "Sample Document PDF loader"` → 命中 | 清空后查询返回空；重新摄取 simple.pdf 后查询命中，系统完全恢复正常 |
| N-05 | 同一文件摄取到多个集合 | Baseline | 1. 摄取 simple.pdf 到 collection_1<br>2. 再次摄取 simple.pdf 到 collection_2 | 两个集合各自独立拥有该文档的 Chunk，互不影响 |
| N-06 | 删除集合 A 中的文档不影响集合 B | Baseline | 1. 在 Dashboard 删除 collection_1 中的 simple.pdf<br>2. 查询 `--collection collection_2` | collection_2 中的数据不受影响，仍可查询命中 |

---

## O. 文档替换与多场景验证

> **重点**: 使用不同类型的中文 PDF 文档测试系统的通用性  
> **测试文档**: 项目自带，位于 `tests/fixtures/sample_documents/`（中文文档由 `generate_qa_test_pdfs.py` 生成）

| ID | 测试标题 | 状态 | 操作步骤 | 预期现象 |
|----|---------|------|---------|--------- |
| O-01 | 纯文本中文技术文档 | Baseline | 1. 摄取 `chinese_technical_doc.pdf`<br>2. 用中文关键词查询（如"Transformer 注意力"、"混合检索 RRF"） | 正确分块，中文 jieba 分词生效（Sparse 路可召回），查询命中相关内容 |
| O-02 | 含中文表格的 PDF | Baseline | 1. 摄取 `chinese_table_chart_doc.pdf`<br>2. 用表格中的数据关键词查询（如"BGE-large-zh"、"Cross-Encoder"） | 表格内容被正确解析到 Chunk 中，查询可命中表格数据 |
| O-03 | 含图表/流程图的 PDF | Baseline | 1. 确保 Vision LLM 启用<br>2. 摄取 `chinese_table_chart_doc.pdf`<br>3. 用图表描述的内容查询（如"流程图"、"耗时分布"） | 图片被提取、Caption 被生成，查询相关关键信息可命中 |
| O-04 | 多页长文档 (30+ 页) | Baseline | 1. 摄取 `chinese_long_doc.pdf`<br>2. 分别用文档前半部分（如"Transformer 位置编码"）和后半部分（如"项目实战经验"）的内容查询 | 所有页面均被处理；前后部分内容均可被召回；Chunk 的 page metadata 正确 |
| O-05 | 包含代码块的技术文档 | Baseline | 1. 摄取 `complex_technical_doc.pdf`（含大量技术术语和组件名）<br>2. 执行 `python scripts/query.py --query "ChromaDB text-embedding-ada-002 vector storage"` | 代码块和技术术语被保留在 Chunk 中（不被分块破坏），通过技术关键词 "ChromaDB" 或 "ada-002" 可召回对应内容段 |
| O-06 | 已摄取 DEV_SPEC 自身 | Baseline | 1. 摄取 DEV_SPEC.md（如果支持 md 格式）<br>2. 用 golden test set 中的查询测试 | 查询 "What is Modular RAG" 等命中 DEV_SPEC 相关内容 |
| O-07 | 替换文档后重新评估 | Baseline | 1. Dashboard Clear All Data<br>2. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/complex_technical_doc.pdf` → 运行 `python scripts/evaluate.py` → 记录分数<br>3. Dashboard Clear All Data<br>4. 执行 `python scripts/ingest.py --path tests/fixtures/sample_documents/chinese_technical_doc.pdf` → 运行 `python scripts/evaluate.py` → 记录分数 | complex_technical_doc.pdf 的评估分数应较高（英文内容与 golden_test_set 匹配度高）；chinese_technical_doc.pdf 的分数应较低（中文内容与英文 golden_test_set 匹配度低） |
| O-08 | 扫描目录批量摄取多份 PDF | Baseline | 1. `python scripts/ingest.py --path tests/fixtures/sample_documents/` | 所有 PDF 依次被处理，终端输出处理汇总（成功数/总数），Dashboard 可看到所有文档 |
| O-09 | 博客/非技术类短文档 | Baseline | 1. 摄取 `blogger_intro.pdf`（博主自我介绍类短文档）<br>2. 用文档内容关键词查询（如"博客"、"自我介绍"） | 短文档正确分块（Chunk 数量较少），查询可命中相关内容，验证非技术类文档的摄取兼容性 |

---

## 附录：测试环境准备清单

### 配置文件备份

| 文件 | 用途 | 说明 |
|------|------|------|
| `config/settings.yaml` | 基线 Azure 配置 | 测试前备份为 `settings.yaml.bak` |
| `config/settings_deepseek.yaml` | DeepSeek LLM 配置 | 复制 settings.yaml，修改 llm 为 deepseek |
| `config/settings_rerank_llm.yaml` | LLM 重排配置 | 修改 rerank 为 llm |

### 测试文档

所有测试文档均已包含在项目中，位于 `tests/fixtures/sample_documents/`，无需额外准备。

| 文档 | 说明 |
|------|------|
| `simple.pdf` | 简单纯文本 PDF |
| `with_images.pdf` | 含嵌入图片的 PDF |
| `complex_technical_doc.pdf` | 多页英文技术文档，含表格和图片 |
| `chinese_technical_doc.pdf` | 纯中文技术文档（~9 页），涵盖 LLM/RAG/Agent 等内容 |
| `chinese_table_chart_doc.pdf` | 含中文表格和流程图的 PDF（~6 页） |
| `chinese_long_doc.pdf` | 30+ 页中文长文档，15 章大模型面试知识手册 |
| `blogger_intro.pdf` | 博主自我介绍类短文档，非技术内容 |
| `sample.txt` | 纯文本文件，验证非 PDF 格式支持 |

### API Key 准备

| Provider | 用途 | 所需 Key | 配置方法 |
|----------|------|----------|---------|
| Azure OpenAI | 基线 LLM + Embedding + Vision | `api_key` (已有) | 已在 settings.yaml 中配置 |
| DeepSeek | 替代 LLM 测试 (K 系列) | `DEEPSEEK_API_KEY` | 见下方说明 |

#### 外部 API Key 配置步骤

K 系列测试需要 DeepSeek API Key。**一次配置，所有测试自动使用**。

```powershell
# 步骤 1: 复制模板文件
Copy-Item config/test_credentials.yaml.example config/test_credentials.yaml

# 步骤 2: 编辑文件，填入你的 API Key
# 打开 config/test_credentials.yaml，将 <YOUR_DEEPSEEK_API_KEY> 替换为真实 Key

# 步骤 3: 验证配置
python .github/skills/qa-tester/scripts/qa_config.py check
```

该文件已添加到 `.gitignore`，不会被提交到 Git，可安全存储 API Key。

#### 配置切换方式

测试脚本通过预定义的"配置 Profile"自动切换 settings.yaml，无需手动编辑：

```powershell
# 查看可用 Profile
python .github/skills/qa-tester/scripts/qa_config.py show

# 切换到 DeepSeek（自动备份 settings.yaml，注入 API Key）
python .github/skills/qa-tester/scripts/qa_config.py apply deepseek

# 执行测试...

# 测试完成后恢复原始配置
python .github/skills/qa-tester/scripts/qa_config.py restore
```

| Profile 名称 | 用途 | 对应测试 | 需要 Credentials |
|-------------|------|---------|-----------------|
| `deepseek` | LLM 切换到 DeepSeek + 关闭 Vision | K-01~K-12 | 是 |
| `rerank_llm` | 启用 LLM 重排 | L-02 | 否 |
| `no_vision` | 关闭 Vision LLM | M-04 | 否 |
| `invalid_llm_key` | 设置无效 LLM Key | M-01 | 否 |
| `invalid_embed_key` | 设置无效 Embedding Key | M-02 | 否 |

---

> **统计**: 共 **117** 条测试用例
