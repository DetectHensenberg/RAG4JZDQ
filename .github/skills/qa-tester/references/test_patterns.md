# Dashboard & MCP Test Patterns Reference

> Read this file when executing Dashboard (A–F) or MCP (J) tests.

---

## Dashboard Tests — Streamlit AppTest

Streamlit `AppTest` renders pages in headless mode (no browser). For each test, write and execute an inline Python script.

### Basic Template

```python
from streamlit.testing.v1 import AppTest

def page_script():
    from src.observability.dashboard.pages.<PAGE_MODULE> import render
    render()

at = AppTest.from_function(page_script, default_timeout=30)
at.run()
assert not at.exception, f"Exception: {at.exception}"

# Print elements for verification
for attr in ("header", "subheader", "info", "error", "warning", "markdown"):
    for el in getattr(at, attr, []):
        print(f"{attr}: {getattr(el, 'value', '')}")
for m in at.metric:
    print(f"metric: label={m.label}, value={m.value}")
for s in at.selectbox:
    print(f"selectbox: options={s.options}, value={s.value}")
print(f"button count: {len(at.button)}")
print(f"expander count: {len(at.expander)}")
```

Page modules: `overview`, `data_browser`, `ingestion_manager`, `ingestion_traces`, `query_traces`, `evaluation_panel`

### Interaction Patterns

**Select dropdown + re-render:**
```python
at.selectbox[0].select("test_col")
at.run()
```

**Click button + re-render:**
```python
at.button[0].click()
at.run()
```

**Text input:**
```python
at.text_input[0].input("search term")
at.run()
```

### File Upload Workaround

`AppTest` cannot simulate `st.file_uploader`. Use two-step approach:
1. Ingest via CLI: `python scripts/ingest.py --path <file> [--collection <name>]`
2. Verify via AppTest: render page, check document counts / chunk lists

### Data Mutations (Clear All / Delete Document)

Call the service directly, then verify via AppTest or CLI:
```python
from src.observability.dashboard.services.data_service import DataService
svc = DataService()
svc.delete_document(source_path, collection, source_hash)  # or svc.reset_all()
```

### Reference Smoke Tests

```
pytest tests/e2e/test_dashboard_smoke.py -v
```

---

## MCP Tests — Subprocess JSON-RPC

### Method 1: Existing pytest tests (covers most J-* cases)

```
pytest tests/e2e/test_mcp_client.py -v         # 7 E2E tests
pytest tests/integration/test_mcp_server.py -v  # 4 protocol tests
```

### Method 2: Inline JSON-RPC script

```python
import json, subprocess, sys, threading, time

proc = subprocess.Popen(
    [sys.executable, "-m", "src.mcp_server.server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8",
)

messages = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18",
                "clientInfo": {"name": "qa-test", "version": "1.0"},
                "capabilities": {}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "query_knowledge_hub",
                "arguments": {"query": "What is hybrid search?", "top_k": 5}}},
]

for msg in messages:
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()

responses = []
def reader():
    while True:
        line = proc.stdout.readline()
        if not line: break
        stripped = line.strip()
        if not stripped: continue
        try:
            data = json.loads(stripped)
            if "id" in data and ("result" in data or "error" in data):
                responses.append(data)
        except json.JSONDecodeError: pass

t = threading.Thread(target=reader, daemon=True)
t.start()
time.sleep(30)
proc.terminate()

for r in responses:
    print(json.dumps(r, indent=2, ensure_ascii=False)[:500])
```

### MCP Test Assertions

| Test ID | What to Verify | Key Assertions |
|---------|---------------|----------------|
| J-01 | Server startup | `initialize` response has `serverInfo`, `capabilities` |
| J-02 | tools/list | 3 tools: `query_knowledge_hub`, `list_collections`, `get_document_summary` |
| J-03 | query_knowledge_hub | `content` array with text blocks |
| J-04 | list_collections | Response contains collection names |
| J-05 | get_document_summary | Response has title/summary |
| J-06 | Multimodal | Response has `type: "image"` blocks |
| J-07 | Bad collection | Graceful error, no crash |
| J-08 | Invalid params | JSON-RPC error or `isError: true` |
| J-09 | Stability | 5 sequential calls all succeed |
| J-10 | Citations | Response has `source_file`, `page`, `score` |
