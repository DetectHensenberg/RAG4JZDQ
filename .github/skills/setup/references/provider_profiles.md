# Provider Profiles Reference

Quick reference for supported provider configurations.

## LLM Providers

### OpenAI
```yaml
llm:
  provider: "openai"
  model: "gpt-4o"           # or gpt-4o-mini, gpt-3.5-turbo
  api_key: "<OPENAI_API_KEY>"
  temperature: 0.0
  max_tokens: 4096
```
Required fields: `provider`, `model`, `api_key`
Remove/leave empty: `azure_endpoint`, `deployment_name`, `api_version`

### Azure OpenAI
```yaml
llm:
  provider: "azure"
  model: "gpt-4o"
  deployment_name: "<YOUR_DEPLOYMENT>"
  azure_endpoint: "https://<RESOURCE>.openai.azure.com/"
  api_version: "2024-02-15-preview"
  api_key: "<AZURE_API_KEY>"
  temperature: 0.0
  max_tokens: 4096
```
Required fields: all shown above

### DeepSeek
```yaml
llm:
  provider: "deepseek"
  model: "deepseek-chat"
  api_key: "<DEEPSEEK_API_KEY>"
  temperature: 0.0
  max_tokens: 4096
```

### Ollama (local)
```yaml
llm:
  provider: "ollama"
  model: "llama3"            # or any model pulled via `ollama pull`
  base_url: "http://localhost:11434"
  temperature: 0.0
  max_tokens: 4096
```
No API key required.

## Embedding Providers

### OpenAI
```yaml
embedding:
  provider: "openai"
  model: "text-embedding-ada-002"   # or text-embedding-3-small
  dimensions: 1536                   # 1536 for ada-002, 1536 for 3-small
  api_key: "<OPENAI_API_KEY>"
```

### Azure OpenAI
```yaml
embedding:
  provider: "azure"
  model: "text-embedding-ada-002"
  dimensions: 1536
  deployment_name: "<YOUR_EMBEDDING_DEPLOYMENT>"
  azure_endpoint: "https://<RESOURCE>.openai.azure.com/"
  api_version: "2024-02-15-preview"
  api_key: "<AZURE_API_KEY>"
```

### Ollama
```yaml
embedding:
  provider: "ollama"
  model: "nomic-embed-text"
  dimensions: 768
  base_url: "http://localhost:11434"
```

## Unimplemented Providers (auto-scaffold on selection)

> These providers use OpenAI-compatible APIs. When selected, the setup skill
> auto-scaffolds the provider code by subclassing `OpenAILLM` / `OpenAIEmbedding`.

### Qwen (Alibaba Cloud DashScope)
```yaml
llm:
  provider: "qwen"
  model: "qwen-turbo"         # or qwen-plus, qwen-max
  api_key: "<DASHSCOPE_API_KEY>"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  temperature: 0.0
  max_tokens: 4096
```
Embedding:
```yaml
embedding:
  provider: "qwen"
  model: "text-embedding-v3"
  dimensions: 1024
  api_key: "<DASHSCOPE_API_KEY>"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
```
Vision model: `qwen-vl-max`
SDK: `pip install openai` (uses OpenAI-compatible protocol)

### Gemini (Google AI Studio)
```yaml
llm:
  provider: "gemini"
  model: "gemini-2.0-flash"   # or gemini-1.5-pro, gemini-2.0-flash-lite
  api_key: "<GEMINI_API_KEY>"
  base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
  temperature: 0.0
  max_tokens: 4096
```
Embedding:
```yaml
embedding:
  provider: "gemini"
  model: "text-embedding-004"
  dimensions: 768
  api_key: "<GEMINI_API_KEY>"
  base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
```
Vision model: `gemini-2.0-flash`
SDK: `pip install openai` (uses OpenAI-compatible protocol)

## Model → Dimensions Lookup

| Model                           | Dimensions |
|---------------------------------|------------|
| text-embedding-ada-002          | 1536       |
| text-embedding-3-small          | 1536       |
| text-embedding-3-large          | 3072       |
| nomic-embed-text (Ollama)       | 768        |
| mxbai-embed-large (Ollama)      | 1024       |
| text-embedding-v3 (Qwen)        | 1024       |
| text-embedding-004 (Gemini)     | 768        |

## Vision LLM Providers

Vision uses a **separate config section** (`vision_llm`) with its own `provider`, `api_key`, etc.

### Vision Model Reference Table

| Provider | Model | Quality | Speed | Cost | Notes |
|----------|-------|---------|-------|------|-------|
| OpenAI | `gpt-4o` | ⭐⭐⭐⭐⭐ | Fast | $$ | 推荐，综合最优 |
| OpenAI | `gpt-4o-mini` | ⭐⭐⭐⭐ | Very Fast | $ | 性价比高，适合简单图片 |
| OpenAI | `gpt-4-turbo` | ⭐⭐⭐⭐⭐ | Medium | $$$ | 老牌高质量，成本较高 |
| Azure | `gpt-4o` | ⭐⭐⭐⭐⭐ | Fast | $$ | 同 OpenAI，需 Azure 部署 |
| Azure | `gpt-4o-mini` | ⭐⭐⭐⭐ | Very Fast | $ | 同上，轻量版 |
| Ollama | `llava` (7B) | ⭐⭐⭐ | Medium | Free | 本地部署，无需 API Key |
| Ollama | `llava:13b` | ⭐⭐⭐⭐ | Slow | Free | 质量更好，需更多显存 |
| Ollama | `llava:34b` | ⭐⭐⭐⭐⭐ | Very Slow | Free | 本地最高质量，需 24GB+ 显存 |
| Ollama | `llava-llama3` | ⭐⭐⭐⭐ | Medium | Free | 基于 LLaMA3，综合较好 |
| Ollama | `bakllava` | ⭐⭐⭐ | Medium | Free | BakLLaVA，轻量替代 |
| Ollama | `moondream` | ⭐⭐ | Very Fast | Free | 最轻量（1.6B），资源占用极少 |
| Qwen | `qwen-vl-max` | ⭐⭐⭐⭐⭐ | Medium | $$ | 通义千问视觉旗舰 |
| Qwen | `qwen-vl-plus` | ⭐⭐⭐⭐ | Fast | $ | 性价比高 |
| Qwen | `qwen2.5-vl-72b-instruct` | ⭐⭐⭐⭐⭐ | Slow | $$ | 最新高质量模型 |
| Qwen | `qwen2.5-vl-7b-instruct` | ⭐⭐⭐ | Fast | $ | 轻量版 |
| Gemini | `gemini-2.0-flash` | ⭐⭐⭐⭐⭐ | Very Fast | $ | 推荐，速度快质量高 |
| Gemini | `gemini-1.5-pro` | ⭐⭐⭐⭐⭐ | Slow | $$$ | 最高质量，适合复杂图片 |
| Gemini | `gemini-2.0-flash-lite` | ⭐⭐⭐ | Very Fast | ¢ | 极低成本 |
| Gemini | `gemini-1.5-flash` | ⭐⭐⭐⭐ | Fast | $ | 均衡之选 |
| DeepSeek | — | — | — | — | ❌ 不支持 Vision，需选其他 provider |

### OpenAI Vision
```yaml
vision_llm:
  enabled: true
  provider: "openai"
  model: "gpt-4o"  # or: gpt-4o-mini, gpt-4-turbo
  api_key: "<OPENAI_API_KEY>"
  max_image_size: 2048
```

### Azure Vision
```yaml
vision_llm:
  enabled: true
  provider: "azure"
  model: "gpt-4o"  # or: gpt-4o-mini, gpt-4-turbo
  deployment_name: "<YOUR_VISION_DEPLOYMENT>"
  azure_endpoint: "https://<RESOURCE>.openai.azure.com/"
  api_version: "2024-02-15-preview"
  api_key: "<AZURE_API_KEY>"
  max_image_size: 2048
```

### Ollama Vision
```yaml
vision_llm:
  enabled: true
  provider: "ollama"
  model: "llava"  # or: llava:13b, llava:34b, llava-llama3, bakllava, moondream
  base_url: "http://localhost:11434"
  max_image_size: 2048
```

### Qwen Vision
```yaml
vision_llm:
  enabled: true
  provider: "qwen"
  model: "qwen-vl-max"  # or: qwen-vl-plus, qwen2.5-vl-72b-instruct, qwen2.5-vl-7b-instruct
  api_key: "<DASHSCOPE_API_KEY>"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  max_image_size: 2048
```

### Gemini Vision
```yaml
vision_llm:
  enabled: true
  provider: "gemini"
  model: "gemini-2.0-flash"  # or: gemini-1.5-pro, gemini-2.0-flash-lite, gemini-1.5-flash
  api_key: "<GEMINI_API_KEY>"
  base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
  max_image_size: 2048
```

### Vision Disabled
```yaml
vision_llm:
  enabled: false
  provider: "openai"
  model: "gpt-4o"
  max_image_size: 2048
```

## Rerank Providers

### None (disabled)
```yaml
rerank:
  enabled: false
  provider: "none"
  model: ""
  top_k: 5
```

### Cross-Encoder

> ⚠️ **Note**: Cross-Encoder 仅完成了本地代码实现，尚未经过充分测试，可能存在兼容性问题。建议优先选择「No (disabled)」或「LLM-based」。

```yaml
rerank:
  enabled: true
  provider: "cross_encoder"
  model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
  top_k: 5
```

### LLM-based
```yaml
rerank:
  enabled: true
  provider: "llm"
  model: ""  # uses the configured LLM
  top_k: 5
```
