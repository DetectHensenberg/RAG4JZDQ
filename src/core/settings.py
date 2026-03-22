"""Configuration loading and validation for the Modular RAG MCP Server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# ---------------------------------------------------------------------------
# Repo root & path resolution
# ---------------------------------------------------------------------------
# Anchored to this file's location: <repo>/src/core/settings.py → parents[2]
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Default absolute path to settings.yaml
DEFAULT_SETTINGS_PATH: Path = REPO_ROOT / "config" / "settings.yaml"


def resolve_path(relative: Union[str, Path]) -> Path:
    """Resolve a repo-relative path to an absolute path.

    If *relative* is already absolute it is returned as-is.  Otherwise
    it is resolved against :data:`REPO_ROOT`.

    >>> resolve_path("config/settings.yaml")  # doctest: +SKIP
    PosixPath('/home/user/Modular-RAG-MCP-Server/config/settings.yaml')
    """
    p = Path(relative)
    if p.is_absolute():
        return p
    return (REPO_ROOT / p).resolve()


class SettingsError(ValueError):
    """Raised when settings validation fails."""


VALID_RETRIEVAL_MODES = {"auto", "always", "never"}


def _require_mapping(data: Dict[str, Any], key: str, path: str) -> Dict[str, Any]:
    value = data.get(key)
    if value is None:
        raise SettingsError(f"Missing required field: {path}.{key}")
    if not isinstance(value, dict):
        raise SettingsError(f"Expected mapping for field: {path}.{key}")
    return value


def _require_value(data: Dict[str, Any], key: str, path: str) -> Any:
    if key not in data or data.get(key) is None:
        raise SettingsError(f"Missing required field: {path}.{key}")
    return data[key]


def _require_str(data: Dict[str, Any], key: str, path: str) -> str:
    value = _require_value(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"Expected non-empty string for field: {path}.{key}")
    return value


def _require_int(data: Dict[str, Any], key: str, path: str) -> int:
    value = _require_value(data, key, path)
    if not isinstance(value, int):
        raise SettingsError(f"Expected integer for field: {path}.{key}")
    return value


def _require_number(data: Dict[str, Any], key: str, path: str) -> float:
    value = _require_value(data, key, path)
    if not isinstance(value, (int, float)):
        raise SettingsError(f"Expected number for field: {path}.{key}")
    return float(value)


def _require_bool(data: Dict[str, Any], key: str, path: str) -> bool:
    value = _require_value(data, key, path)
    if not isinstance(value, bool):
        raise SettingsError(f"Expected boolean for field: {path}.{key}")
    return value


def _require_list(data: Dict[str, Any], key: str, path: str) -> List[Any]:
    value = _require_value(data, key, path)
    if not isinstance(value, list):
        raise SettingsError(f"Expected list for field: {path}.{key}")
    return value


def _parse_retrieval_mode(
    retrieval: Dict[str, Any],
    key: str,
    legacy_key: str,
) -> str:
    """Parse tri-state retrieval mode with legacy bool compatibility."""
    if key in retrieval:
        value = retrieval[key]
    elif legacy_key in retrieval:
        value = retrieval[legacy_key]
    else:
        return "never"

    if isinstance(value, bool):
        return "always" if value else "never"

    if isinstance(value, str):
        mode = value.strip().lower()
        if mode in VALID_RETRIEVAL_MODES:
            return mode

    raise SettingsError(
        f"Expected {key} to be one of {sorted(VALID_RETRIEVAL_MODES)} "
        f"or a legacy boolean {legacy_key}"
    )


def _parse_embedding_settings(embedding: Dict[str, Any]) -> "EmbeddingSettings":
    """Parse embedding settings including optional BGE-M3 config."""
    bge_m3_config = None
    if "bge_m3" in embedding:
        bge_m3_data = embedding["bge_m3"]
        if isinstance(bge_m3_data, dict):
            bge_m3_config = BGEM3Config(
                model=bge_m3_data.get("model", "BAAI/bge-m3"),
                use_fp16=bge_m3_data.get("use_fp16", True),
                device=bge_m3_data.get("device", "auto"),
            )
    
    return EmbeddingSettings(
        provider=_require_str(embedding, "provider", "embedding"),
        model=_require_str(embedding, "model", "embedding"),
        dimensions=_require_int(embedding, "dimensions", "embedding"),
        api_key=_resolve_api_key(embedding.get("api_key")),
        api_version=embedding.get("api_version"),
        azure_endpoint=embedding.get("azure_endpoint"),
        deployment_name=embedding.get("deployment_name"),
        base_url=embedding.get("base_url"),
        bge_m3=bge_m3_config,
    )


def _parse_ingestion_settings(ingestion: Dict[str, Any]) -> "IngestionSettings":
    """Parse ingestion settings including optional context_enricher config."""
    context_enricher_config = None
    if "context_enricher" in ingestion:
        ce_data = ingestion["context_enricher"]
        if isinstance(ce_data, dict):
            context_enricher_config = ContextEnricherConfig(
                enabled=ce_data.get("enabled", True),
            )
    
    parent_retrieval_config = None
    if "parent_retrieval" in ingestion:
        pr_data = ingestion["parent_retrieval"]
        if isinstance(pr_data, dict):
            parent_retrieval_config = ParentRetrievalConfig(
                enabled=pr_data.get("enabled", False),
                parent_chunk_size=pr_data.get("parent_chunk_size", 2000),
                child_chunk_size=pr_data.get("child_chunk_size", 400),
                child_chunk_overlap=pr_data.get("child_chunk_overlap", 50),
            )
    
    graph_rag_config = None
    if "graph_rag" in ingestion:
        gr_data = ingestion["graph_rag"]
        if isinstance(gr_data, dict):
            graph_rag_config = GraphRAGConfig(
                enabled=gr_data.get("enabled", False),
                extraction_model=gr_data.get("extraction_model"),
                max_hops=gr_data.get("max_hops", 1),
            )
    
    return IngestionSettings(
        chunk_size=_require_int(ingestion, "chunk_size", "ingestion"),
        chunk_overlap=_require_int(ingestion, "chunk_overlap", "ingestion"),
        splitter=_require_str(ingestion, "splitter", "ingestion"),
        batch_size=_require_int(ingestion, "batch_size", "ingestion"),
        pdf_parser=ingestion.get("pdf_parser", "markitdown"),
        chunk_refiner=ingestion.get("chunk_refiner"),
        metadata_enricher=ingestion.get("metadata_enricher"),
        context_enricher=context_enricher_config,
        parent_retrieval=parent_retrieval_config,
        graph_rag=graph_rag_config,
    )


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    # Azure/OpenAI-specific optional fields
    api_key: Optional[str] = None
    api_version: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    # Ollama-specific optional fields
    base_url: Optional[str] = None


@dataclass(frozen=True)
class BGEM3Config:
    """BGE-M3 specific configuration."""
    model: str = "BAAI/bge-m3"
    use_fp16: bool = True
    device: str = "auto"  # auto/cpu/cuda


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    dimensions: int
    # Azure-specific optional fields
    api_key: Optional[str] = None
    api_version: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    # Ollama-specific optional fields
    base_url: Optional[str] = None
    # BGE-M3 specific config
    bge_m3: Optional[BGEM3Config] = None


@dataclass(frozen=True)
class VectorStoreSettings:
    provider: str
    persist_directory: str
    collection_name: str


@dataclass(frozen=True)
class RetrievalSettings:
    dense_top_k: int
    sparse_top_k: int
    fusion_top_k: int
    rrf_k: int
    query_rewrite: bool = False  # LLM query rewriting
    hyde_enabled: bool = False   # HyDE (Hypothetical Document Embedding)
    parent_retrieval_mode: str = "never"
    graph_rag_mode: str = "never"

    @property
    def parent_retrieval_enabled(self) -> bool:
        """Backward-compatible legacy flag view."""
        return self.parent_retrieval_mode == "always"

    @property
    def graph_rag_enabled(self) -> bool:
        """Backward-compatible legacy flag view."""
        return self.graph_rag_mode == "always"


@dataclass(frozen=True)
class RerankSettings:
    enabled: bool
    provider: str
    model: str
    top_k: int


@dataclass(frozen=True)
class EvaluationSettings:
    enabled: bool
    provider: str
    metrics: List[str]


@dataclass(frozen=True)
class ObservabilitySettings:
    log_level: str
    trace_enabled: bool
    trace_file: str
    structured_logging: bool


@dataclass(frozen=True)
class VisionLLMSettings:
    enabled: bool
    provider: str
    model: str
    max_image_size: int
    api_key: Optional[str] = None
    api_version: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    base_url: Optional[str] = None


@dataclass(frozen=True)
class ContextEnricherConfig:
    """Context Enricher configuration."""
    enabled: bool = True


@dataclass(frozen=True)
class ParentRetrievalConfig:
    """Parent Document Retrieval configuration."""
    enabled: bool = False
    parent_chunk_size: int = 2000
    child_chunk_size: int = 400
    child_chunk_overlap: int = 50


@dataclass(frozen=True)
class GraphRAGConfig:
    """GraphRAG configuration."""
    enabled: bool = False
    extraction_model: Optional[str] = None
    max_hops: int = 1


@dataclass(frozen=True)
class IngestionSettings:
    chunk_size: int
    chunk_overlap: int
    splitter: str
    batch_size: int
    pdf_parser: str = "markitdown"  # Options: markitdown, layout
    chunk_refiner: Optional[Dict[str, Any]] = None  # 动态配置
    metadata_enricher: Optional[Dict[str, Any]] = None  # 动态配置
    context_enricher: Optional[ContextEnricherConfig] = None  # 上下文注入配置
    parent_retrieval: Optional[ParentRetrievalConfig] = None
    graph_rag: Optional[GraphRAGConfig] = None


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings
    embedding: EmbeddingSettings
    vector_store: VectorStoreSettings
    retrieval: RetrievalSettings
    rerank: RerankSettings
    evaluation: EvaluationSettings
    observability: ObservabilitySettings
    ingestion: Optional[IngestionSettings] = None
    vision_llm: Optional[VisionLLMSettings] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        if not isinstance(data, dict):
            raise SettingsError("Settings root must be a mapping")

        llm = _require_mapping(data, "llm", "settings")
        embedding = _require_mapping(data, "embedding", "settings")
        vector_store = _require_mapping(data, "vector_store", "settings")
        retrieval = _require_mapping(data, "retrieval", "settings")
        rerank = _require_mapping(data, "rerank", "settings")
        evaluation = _require_mapping(data, "evaluation", "settings")
        observability = _require_mapping(data, "observability", "settings")

        ingestion_settings = None
        if "ingestion" in data:
            ingestion = _require_mapping(data, "ingestion", "settings")
            ingestion_settings = _parse_ingestion_settings(ingestion)

        vision_llm_settings = None
        if "vision_llm" in data:
            vision_llm = _require_mapping(data, "vision_llm", "settings")
            vision_llm_settings = VisionLLMSettings(
                enabled=_require_bool(vision_llm, "enabled", "vision_llm"),
                provider=_require_str(vision_llm, "provider", "vision_llm"),
                model=_require_str(vision_llm, "model", "vision_llm"),
                max_image_size=_require_int(vision_llm, "max_image_size", "vision_llm"),
                api_key=_resolve_api_key(vision_llm.get("api_key")),
                api_version=vision_llm.get("api_version"),
                azure_endpoint=vision_llm.get("azure_endpoint"),
                deployment_name=vision_llm.get("deployment_name"),
                base_url=vision_llm.get("base_url"),
            )

        settings = cls(
            llm=LLMSettings(
                provider=_require_str(llm, "provider", "llm"),
                model=_require_str(llm, "model", "llm"),
                temperature=_require_number(llm, "temperature", "llm"),
                max_tokens=_require_int(llm, "max_tokens", "llm"),
                api_key=_resolve_api_key(llm.get("api_key")),
                api_version=llm.get("api_version"),
                azure_endpoint=llm.get("azure_endpoint"),
                deployment_name=llm.get("deployment_name"),
                base_url=llm.get("base_url"),
            ),
            embedding=_parse_embedding_settings(embedding),
            vector_store=VectorStoreSettings(
                provider=_require_str(vector_store, "provider", "vector_store"),
                persist_directory=_require_str(vector_store, "persist_directory", "vector_store"),
                collection_name=_require_str(vector_store, "collection_name", "vector_store"),
            ),
            retrieval=RetrievalSettings(
                dense_top_k=_require_int(retrieval, "dense_top_k", "retrieval"),
                sparse_top_k=_require_int(retrieval, "sparse_top_k", "retrieval"),
                fusion_top_k=_require_int(retrieval, "fusion_top_k", "retrieval"),
                rrf_k=_require_int(retrieval, "rrf_k", "retrieval"),
                query_rewrite=retrieval.get("query_rewrite", False),
                hyde_enabled=retrieval.get("hyde_enabled", False),
                parent_retrieval_mode=_parse_retrieval_mode(
                    retrieval,
                    "parent_retrieval_mode",
                    "parent_retrieval_enabled",
                ),
                graph_rag_mode=_parse_retrieval_mode(
                    retrieval,
                    "graph_rag_mode",
                    "graph_rag_enabled",
                ),
            ),
            rerank=RerankSettings(
                enabled=_require_bool(rerank, "enabled", "rerank"),
                provider=_require_str(rerank, "provider", "rerank"),
                model=_require_str(rerank, "model", "rerank"),
                top_k=_require_int(rerank, "top_k", "rerank"),
            ),
            evaluation=EvaluationSettings(
                enabled=_require_bool(evaluation, "enabled", "evaluation"),
                provider=_require_str(evaluation, "provider", "evaluation"),
                metrics=[str(item) for item in _require_list(evaluation, "metrics", "evaluation")],
            ),
            observability=ObservabilitySettings(
                log_level=_require_str(observability, "log_level", "observability"),
                trace_enabled=_require_bool(observability, "trace_enabled", "observability"),
                trace_file=_require_str(observability, "trace_file", "observability"),
                structured_logging=_require_bool(observability, "structured_logging", "observability"),
            ),
            ingestion=ingestion_settings,
            vision_llm=vision_llm_settings,
        )

        return settings


def _load_dotenv() -> None:
    """Load .env file from repo root if it exists."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Don't override existing env vars
                if key and key not in os.environ:
                    os.environ[key] = value


def _resolve_api_key(config_value: Optional[str]) -> Optional[str]:
    """Resolve API key: use config value if non-empty, else fall back to env var.
    
    Priority:
    1. Explicit value in settings.yaml (non-empty)
    2. DASHSCOPE_API_KEY environment variable
    3. OPENAI_API_KEY environment variable
    """
    if config_value and config_value.strip():
        return config_value.strip()
    return os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY")


def validate_settings(settings: Settings) -> None:
    """Validate settings and raise SettingsError if invalid."""

    if not settings.llm.provider:
        raise SettingsError("Missing required field: llm.provider")
    if not settings.embedding.provider:
        raise SettingsError("Missing required field: embedding.provider")
    if not settings.vector_store.provider:
        raise SettingsError("Missing required field: vector_store.provider")
    if not settings.retrieval.rrf_k:
        raise SettingsError("Missing required field: retrieval.rrf_k")
    if not settings.rerank.provider:
        raise SettingsError("Missing required field: rerank.provider")
    if not settings.evaluation.provider:
        raise SettingsError("Missing required field: evaluation.provider")
    if not settings.observability.log_level:
        raise SettingsError("Missing required field: observability.log_level")


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file and validate required fields.

    Args:
        path: Path to settings YAML.  Defaults to
            ``<repo>/config/settings.yaml`` (absolute, CWD-independent).
    """
    # Load .env file first so env vars are available
    _load_dotenv()
    
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.is_absolute():
        settings_path = resolve_path(settings_path)
    if not settings_path.exists():
        raise SettingsError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    settings = Settings.from_dict(data or {})
    validate_settings(settings)
    return settings
