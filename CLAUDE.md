# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

九洲 RAG 管理平台 (Jiuzhou RAG Management Platform) — a modular Retrieval-Augmented Generation knowledge management system. It features a FastAPI backend, Vue 3 frontend, and MCP server, supporting multi-format document ingestion, hybrid search (Dense + Sparse + RRF fusion), and intelligent Q&A with streaming output.

**Language**: The codebase uses Chinese for comments, documentation, and UI. Respond in the language the user uses.

## Common Commands

### Backend
```bash
# Install Python dependencies (editable mode)
pip install -e .

# Start backend server (port 8001)
python -m uvicorn api.main:app --port 8001

# Start MCP server (stdio transport)
python main.py
```

### Frontend
```bash
# Install frontend dependencies
cd web && npm install

# Start dev server (port 5173, proxies /api to :8001)
cd web && npm run dev

# Build for production
cd web && npm run build
```

### Windows one-click start (both frontend + backend)
```bash
start_vue.bat
```

### Tests
```bash
# Run all tests
pytest tests/ -v

# Run only unit tests
pytest tests/unit/ -v

# Run a single test file
pytest tests/unit/test_query_processor.py -v

# Skip tests requiring real LLM API calls
pytest tests/ -v -m "not llm"

# Run only integration tests
pytest tests/integration/ -v

# Run E2E tests
pytest tests/e2e/ -v
```

### Linting
```bash
ruff check src/ api/ tests/
ruff format src/ api/ tests/
mypy src/
```

## Architecture

### Four-Layer Design

The system follows a strict layered architecture:

1. **API Layer** (`api/`) — FastAPI application with routers for chat, ingest, knowledge, config, data, evaluation, bid processing, and system management. `api/deps.py` provides singleton dependency injection (Settings, HybridSearch, IngestionPipeline, DocumentManager, etc.) via `lru_cache` and lazy initialization.

2. **Core Layer** (`src/core/`) — Business logic:
   - `types.py` — Central data contracts: `Document`, `Chunk`, `ChunkRecord`, `ProcessedQuery`, `RetrievalResult`. All pipeline stages share these types.
   - `settings.py` — YAML config loading from `config/settings.yaml` with `.env` fallback for API keys.
   - `query_engine/` — `QueryProcessor` → `DenseRetriever` + `SparseRetriever` (parallel) → `RRFFusion` → `CoreReranker` (optional, with fallback).
   - `trace/` — `TraceContext` for full-pipeline observability (record_stage / finish / to_dict).

3. **Ingestion Pipeline** (`src/ingestion/`) — Six-stage pipeline orchestrated by `pipeline.py`:
   - `FileIntegrityChecker` (SHA256 dedup) → `Loader` (PDF→Markdown + image extraction) → `DocumentChunker` (recursive splitting) → `Transform` (ChunkRefiner + MetadataEnricher + ImageCaptioner) → `Embedding` (Dense + Sparse dual encoding) → `Storage` (ChromaDB upsert + BM25 index + image storage)
   - `document_manager.py` — Cross-storage lifecycle management (coordinated delete across Chroma, BM25, ImageStorage, FileIntegrity).

4. **Libs Layer** (`src/libs/`) — Pluggable provider abstractions using Factory Pattern:
   - `llm/` — `BaseLLM` → OpenAI / Azure / Ollama / DeepSeek (all OpenAI-compatible). `BaseVisionLLM` for image captioning.
   - `embedding/` — `BaseEmbedding` → OpenAI / Azure / Ollama.
   - `vector_store/` — `BaseVectorStore` → ChromaDB (local persistent, WAL mode).
   - `reranker/` — `BaseReranker` → None / CrossEncoder / LLM Rerank.
   - `loader/` — `BaseLoader` → PDF (MarkItDown + PyMuPDF for images), PPTX, DOCX, MD, TXT.
   - `splitter/` — `BaseSplitter` → RecursiveCharacterTextSplitter (LangChain).

### Frontend (`web/`)

Vue 3 + TypeScript + Vite + Element Plus + TailwindCSS. Dark glassmorphism theme.

Key directories:
- `web/src/views/` — Page components (ChatView, KnowledgeBase, DataBrowser, SystemConfig, etc.)
- `web/src/composables/` — Composition functions (useSSE for streaming, useApi)
- `web/src/stores/` — Pinia state management

The Vite dev server proxies `/api` requests to `localhost:8001`.

### MCP Server (`src/mcp_server/`)

Exposes 3 tools via stdio transport (JSON-RPC 2.0): `query_knowledge_hub`, `list_collections`, `get_document_summary`. Entry point: `main.py`.

### Key Design Patterns

- **Config-Driven**: All components configured via `config/settings.yaml`. Zero-code provider switching.
- **Factory Pattern**: Every pluggable component (LLM, Embedding, VectorStore, Reranker, Splitter) uses a factory that reads settings and instantiates the correct implementation.
- **Graceful Degradation**: LLM calls fail → fallback to rule-based processing. Reranker fails → fallback to RRF fusion results. Vision LLM unavailable → skip image captioning.
- **Singleton DI**: `api/deps.py` manages heavy objects (HybridSearch, IngestionPipeline) as lazy singletons with collection-aware cache invalidation.

## Configuration

All runtime config lives in `config/settings.yaml` (see `config/settings.yaml.example` for template).

API Key priority: `settings.yaml` explicit value > `.env` file `DASHSCOPE_API_KEY` > system env `OPENAI_API_KEY`.

Default provider setup uses DashScope (Qwen models) via OpenAI-compatible API.

## Data Storage

- `data/db/chroma/` — ChromaDB vector store (persistent, WAL mode)
- `data/db/bm25/` — BM25 inverted index (pickle serialized)
- `data/db/ingestion_history.db` — SQLite: file hash dedup for incremental ingestion
- `data/db/image_index.db` — SQLite: image_id → file path mapping
- `data/images/` — Extracted document images
- `logs/traces.jsonl` — Structured trace logs (JSON Lines)

## Test Markers

Defined in `pyproject.toml`:
- `unit` — Fast, no external dependencies
- `integration` — May require external services
- `e2e` — Full system tests
- `llm` — Requires real LLM API calls (skip with `-m "not llm"`)
- `slow` — Slow tests

## Code Style

- **Ruff**: line-length=100, target Python 3.10, rules: E, F, I, N, W, UP (E501 ignored)
- **mypy**: Python 3.10, ignore_missing_imports=true
- All functions should have docstrings (Chinese or English)
- Use `src/core/types.py` data contracts across all pipeline stages — do not define duplicate types
- SQLite databases use WAL mode for concurrent safety

## Adding a New Provider

Example: adding a new LLM provider:
1. Inherit from `src/libs/llm/base_llm.py::BaseLLM`
2. Implement `chat()` and optionally `chat_stream()` methods
3. Register in `src/libs/llm/llm_factory.py`
4. Configure in `config/settings.yaml` under `llm.provider`
