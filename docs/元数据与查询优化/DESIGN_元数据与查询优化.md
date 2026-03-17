# DESIGN: 元数据增强与查询优化

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingestion Pipeline                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ DocumentChunker│ → │ heading_path │ → │ content_type │  │
│  │   (#6 + #7)   │    │   file_name  │    │ ingested_at  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Query Engine                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │QueryRewriter │ → │   HyDE       │ → │ HybridSearch │  │
│  │    (#11)     │    │   (#11)      │    │   + filters  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    API + Frontend                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ /api/query   │    │ /api/system/ │    │  Dashboard   │  │
│  │  + filters   │    │ingestion-stats│   │   Stats UI   │  │
│  │    (#8)      │    │    (#10)     │    │    (#10)     │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## #6: 层级标签 heading_path

### 设计方案

在 `DocumentChunker.split_document()` 中维护标题栈：

```python
def _extract_heading_path(self, chunks: List[str]) -> List[str]:
    """为每个 chunk 计算 heading_path。"""
    heading_stack: List[Tuple[str, int]] = []
    heading_paths: List[str] = []
    
    for chunk_text in chunks:
        # 扫描 chunk 中的标题
        headings = re.findall(r'^(#{1,6})\s+(.+)$', chunk_text, re.MULTILINE)
        for level_marks, title in headings:
            level = len(level_marks)
            # 弹出同级或更低级标题
            while heading_stack and heading_stack[-1][1] >= level:
                heading_stack.pop()
            heading_stack.append((title.strip(), level))
        
        # 生成路径
        path = " > ".join(h[0] for h in heading_stack)
        heading_paths.append(path)
    
    return heading_paths
```

### 改动文件
- `src/ingestion/chunking/document_chunker.py`

---

## #7: 内容类别 + 源标签

### 设计方案

在 `_inherit_metadata()` 中增加字段：

```python
def _detect_content_type(text: str) -> str:
    """检测 chunk 内容类型。"""
    if re.search(r'^\|.+\|$', text, re.MULTILINE):
        return "table"
    if re.search(r'^```', text, re.MULTILINE):
        return "code"
    if re.search(r'^\d+\.\s|^[-*]\s', text, re.MULTILINE):
        return "list"
    return "text"

# 在 _inherit_metadata() 中：
chunk_metadata["content_type"] = _detect_content_type(chunk_text)
chunk_metadata["file_name"] = Path(source_path).stem
chunk_metadata["file_ext"] = Path(source_path).suffix.lstrip(".")
chunk_metadata["ingested_at"] = datetime.now().isoformat()
```

### 改动文件
- `src/ingestion/chunking/document_chunker.py`

---

## #8: 元数据过滤 API

### 设计方案

API 层增加 filters 参数：

```python
# api/routers/query.py
class QueryRequest(BaseModel):
    query: str
    collection: str = "default"
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None  # 新增

# 传递给 HybridSearch
results = hybrid_search.search(
    query=request.query,
    filters=request.filters,  # 新增
    ...
)
```

### 改动文件
- `api/routers/query.py`

---

## #10: 离线质量监控

### 设计方案

1. **数据收集**：Pipeline 完成后记录统计到 SQLite
2. **API 暴露**：`/api/system/ingestion-stats`
3. **前端展示**：Dashboard 增加统计卡片

```python
# src/ingestion/stats.py
@dataclass
class IngestionStats:
    total_docs: int
    total_chunks: int
    avg_chunk_size: float
    failed_count: int
    last_ingestion: str
```

### 改动文件
- `src/ingestion/stats.py` (新建)
- `api/routers/system.py`
- `web/src/views/Dashboard.vue`

---

## #11: Query Rewriting + HyDE

### 设计方案

新建 `QueryRewriter` 类，支持两种模式：

```python
# src/core/query_engine/query_rewriter.py

class QueryRewriter:
    """LLM 查询改写 + HyDE 扩展。"""
    
    def __init__(self, settings: Settings):
        self.llm = LLMFactory.create(settings)
        self.rewrite_enabled = settings.retrieval.query_rewrite
        self.hyde_enabled = settings.retrieval.hyde_enabled
    
    def rewrite(self, query: str) -> List[str]:
        """LLM 改写为多个检索友好表述。"""
        if not self.rewrite_enabled:
            return [query]
        prompt = f"将以下问题改写为2-3个语义等价但更适合知识库检索的表述，每行一个：\n{query}"
        response = self.llm.generate(prompt)
        return [q.strip() for q in response.split("\n") if q.strip()]
    
    def hyde_expand(self, query: str) -> str:
        """生成假想文档片段用于检索。"""
        if not self.hyde_enabled:
            return query
        prompt = f"请写一段可能回答以下问题的文档片段（50-100字）：\n{query}"
        return self.llm.generate(prompt)
```

### 集成到 HybridSearch

```python
# hybrid_search.py
def search(self, query: str, ...):
    # 1. Query Rewriting
    queries = self.rewriter.rewrite(query)
    
    # 2. HyDE (可选)
    hyde_doc = self.rewriter.hyde_expand(query)
    
    # 3. 多路检索 + 合并
    all_results = []
    for q in queries:
        results = self._search_single(q)
        all_results.extend(results)
    
    if hyde_doc != query:
        hyde_results = self._search_single(hyde_doc)
        all_results.extend(hyde_results)
    
    # 4. 去重 + RRF 融合
    return self._fuse_results(all_results)
```

### 配置

```yaml
retrieval:
  query_rewrite: true
  hyde_enabled: true
```

### 改动文件
- `src/core/query_engine/query_rewriter.py` (新建)
- `src/core/query_engine/hybrid_search.py`
- `src/core/settings.py`
- `config/settings.yaml`
