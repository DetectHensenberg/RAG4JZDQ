# New Provider Scaffolding Guide

When a user selects a provider that is not yet implemented, follow this procedure to auto-scaffold the code. The project uses a plugin architecture — adding a new provider is mechanical.

## Quick Check: Is the Provider Built-in?

Built-in LLM providers: `openai`, `azure`, `deepseek`, `ollama`
Built-in Embedding providers: `openai`, `azure`, `ollama`
Built-in Vision providers: `openai`, `azure`

If the provider is NOT in these lists, proceed with scaffolding below.

## Key Insight: OpenAI-Compatible Providers

Many modern providers (Qwen/DashScope, Gemini, Groq, Mistral, Together AI, etc.) expose an **OpenAI-compatible API**. For these, the implementation is trivial — subclass the existing `OpenAILLM` / `OpenAIEmbedding` and override the base URL + auth.

## Step 1: Create LLM Provider

Create `src/libs/llm/{name}_llm.py`:

```python
"""<ProviderName> LLM implementation (OpenAI-compatible)."""
from __future__ import annotations
import os
from typing import Any, Optional
from src.libs.llm.openai_llm import OpenAILLM


class <ProviderName>LLMError(RuntimeError):
    """Raised when <ProviderName> API call fails."""


class <ProviderName>LLM(OpenAILLM):
    """<ProviderName> LLM provider — OpenAI-compatible endpoint.

    Inherits all chat logic from OpenAILLM; overrides base URL and
    API key resolution.
    """

    DEFAULT_BASE_URL = "<PROVIDER_BASE_URL>"

    def __init__(self, settings: Any, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, **kwargs: Any) -> None:
        # Allow base_url from settings.llm.base_url
        resolved_base = (
            base_url
            or getattr(settings.llm, 'base_url', None)
            or self.DEFAULT_BASE_URL
        )
        # Allow api_key from settings or env
        resolved_key = (
            api_key
            or getattr(settings.llm, 'api_key', None)
            or os.environ.get("<ENV_VAR_NAME>")
        )
        if not resolved_key:
            raise ValueError(
                "<ProviderName> API key not provided. Set in settings.yaml "
                "(llm.api_key) or <ENV_VAR_NAME> environment variable."
            )
        super().__init__(settings, api_key=resolved_key, base_url=resolved_base, **kwargs)
```

For providers that are NOT OpenAI-compatible, subclass `BaseLLM` directly and implement `chat()` — refer to `deepseek_llm.py` or `ollama_llm.py` as examples.

## Step 2: Create Embedding Provider (if needed)

Create `src/libs/embedding/{name}_embedding.py`:

```python
"""<ProviderName> Embedding implementation (OpenAI-compatible)."""
from __future__ import annotations
import os
from typing import Any, Optional
from src.libs.embedding.openai_embedding import OpenAIEmbedding


class <ProviderName>EmbeddingError(RuntimeError):
    """Raised when <ProviderName> Embedding API call fails."""


class <ProviderName>Embedding(OpenAIEmbedding):
    """<ProviderName> Embedding provider — OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "<PROVIDER_BASE_URL>"

    def __init__(self, settings: Any, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, **kwargs: Any) -> None:
        resolved_base = (
            base_url
            or getattr(settings.embedding, 'base_url', None)
            or self.DEFAULT_BASE_URL
        )
        resolved_key = (
            api_key
            or getattr(settings.embedding, 'api_key', None)
            or os.environ.get("<ENV_VAR_NAME>")
        )
        if not resolved_key:
            raise ValueError(
                "<ProviderName> API key not provided. Set in settings.yaml "
                "(embedding.api_key) or <ENV_VAR_NAME> environment variable."
            )
        super().__init__(settings, api_key=resolved_key, base_url=resolved_base, **kwargs)
```

## Step 3: Create Vision LLM Provider (if needed)

Create `src/libs/llm/{name}_vision_llm.py` — subclass `OpenAIVisionLLM` with same pattern as Step 1.

## Step 4: Register Providers

### LLM — append to `src/libs/llm/__init__.py`:

```python
from src.libs.llm.{name}_llm import <ProviderName>LLM, <ProviderName>LLMError
LLMFactory.register_provider("{name}", <ProviderName>LLM)
```

### Embedding — append to `src/libs/embedding/embedding_factory.py` inside `_register_builtin_providers()`:

```python
try:
    from src.libs.embedding.{name}_embedding import <ProviderName>Embedding
    EmbeddingFactory.register_provider("{name}", <ProviderName>Embedding)
except ImportError:
    pass
```

Also update `src/libs/embedding/__init__.py` imports and `__all__`.

### Vision — append to `src/libs/llm/llm_factory.py` inside `_register_vision_providers()`:

```python
try:
    from src.libs.llm.{name}_vision_llm import <ProviderName>VisionLLM
    LLMFactory.register_vision_provider("{name}", <ProviderName>VisionLLM)
except ImportError:
    pass
```

## Step 5: Verify `base_url` Field Exists in Settings

Check `src/core/settings.py` — `LLMSettings` and `EmbeddingSettings` already have `base_url: Optional[str] = None`. No change needed.

## Step 6: Install SDK (if any)

Most OpenAI-compatible providers only need `pip install openai` (already installed).
Provider-specific SDKs if NOT OpenAI-compatible:
- Qwen: `pip install dashscope` (alternative, but OpenAI-compat mode recommended)
- Gemini: `pip install google-generativeai` (only if NOT using OpenAI-compat mode)

## Provider-Specific Reference

| Provider | Base URL (LLM) | Base URL (Embedding) | API Key Env Var | OpenAI-compat |
|----------|----------------|----------------------|-----------------|---------------|
| Qwen     | `https://dashscope.aliyuncs.com/compatible-mode/v1` | same | `DASHSCOPE_API_KEY` | Yes |
| Gemini   | `https://generativelanguage.googleapis.com/v1beta/openai/` | same | `GEMINI_API_KEY` | Yes |
| Groq     | `https://api.groq.com/openai/v1` | N/A (no embedding) | `GROQ_API_KEY` | Yes |
| Mistral  | `https://api.mistral.ai/v1` | same | `MISTRAL_API_KEY` | Yes |
| Together | `https://api.together.xyz/v1` | same | `TOGETHER_API_KEY` | Yes |

## Validation

After scaffolding, run quick validation:

```python
python -c "
from src.libs.llm import LLMFactory
from src.libs.embedding import EmbeddingFactory
print('LLM providers:', LLMFactory.list_providers())
print('Embedding providers:', EmbeddingFactory.list_providers())
print('Vision providers:', LLMFactory.list_vision_providers())
"
```

The new provider should appear in the list. Then proceed with setup Step 3 (Generate Config).
