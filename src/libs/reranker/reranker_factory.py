"""Factory for creating Reranker provider instances.

This module implements the Factory Pattern to instantiate the appropriate
Reranker provider based on configuration, enabling configuration-driven selection
of different backends without code changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.libs.reranker.base_reranker import BaseReranker, NoneReranker

if TYPE_CHECKING:
    from src.core.settings import Settings


def _lazy_import_llm_reranker():
    """Lazy import to avoid circular dependencies."""
    from src.libs.reranker.llm_reranker import LLMReranker
    return LLMReranker


def _lazy_import_cross_encoder_reranker():
    """Lazy import to avoid circular dependencies."""
    from src.libs.reranker.cross_encoder_reranker import CrossEncoderReranker
    return CrossEncoderReranker


class RerankerFactory:
    """Factory for creating Reranker provider instances.
    
    This factory reads the rerank configuration from settings and instantiates
    the corresponding Reranker implementation. Provider implementations will be
    added in subsequent tasks (B7.7, B7.8).
    
    Design Principles Applied:
    - Factory Pattern: Centralizes object creation logic.
    - Config-Driven: Provider selection based on settings.yaml.
    - Fallback: Disabled or 'none' provider returns NoneReranker.
    - Fail-Fast: Raises clear errors for unknown providers.
    """
    
    _PROVIDERS: dict[str, type[BaseReranker]] = {}
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type[BaseReranker]) -> None:
        """Register a new Reranker provider implementation.
        
        Args:
            name: The provider identifier (e.g., 'cross_encoder', 'llm').
            provider_class: The BaseReranker subclass implementing the provider.
        
        Raises:
            ValueError: If provider_class doesn't inherit from BaseReranker.
        """
        if not issubclass(provider_class, BaseReranker):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from BaseReranker"
            )
        cls._PROVIDERS[name.lower()] = provider_class
    
    @classmethod
    def create(cls, settings: Settings, **override_kwargs: Any) -> BaseReranker:
        """Create a Reranker instance based on configuration.
        
        Args:
            settings: The application settings containing rerank configuration.
            **override_kwargs: Optional parameters to override config values.
        
        Returns:
            An instance of the configured Reranker provider.
        
        Raises:
            ValueError: If the configured provider is not supported or missing.
            RuntimeError: If provider initialization fails.
        """
        # Lazy register LLM reranker if not already registered
        if "llm" not in cls._PROVIDERS:
            LLMReranker = _lazy_import_llm_reranker()
            cls.register_provider("llm", LLMReranker)
        
        # Lazy register Cross-Encoder reranker if not already registered
        if "cross_encoder" not in cls._PROVIDERS:
            CrossEncoderReranker = _lazy_import_cross_encoder_reranker()
            cls.register_provider("cross_encoder", CrossEncoderReranker)
        
        try:
            rerank_settings = settings.rerank
            if rerank_settings is None:
                raise AttributeError("settings.rerank is None")
            provider_name = rerank_settings.provider.lower()
            enabled = bool(rerank_settings.enabled)
        except AttributeError as e:
            raise ValueError(
                "Missing required configuration: settings.rerank.provider. "
                "Please ensure 'rerank.provider' is specified in settings.yaml"
            ) from e
        
        if not enabled or provider_name == "none":
            return NoneReranker(settings=settings, **override_kwargs)
        
        provider_class = cls._PROVIDERS.get(provider_name)
        if provider_class is None:
            available = ", ".join(sorted(cls._PROVIDERS.keys())) if cls._PROVIDERS else "none"
            raise ValueError(
                f"Unsupported Reranker provider: '{provider_name}'. "
                f"Available providers: {available}."
            )
        
        try:
            return provider_class(settings=settings, **override_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to instantiate Reranker provider '{provider_name}': {e}"
            ) from e
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names.
        
        Returns:
            Sorted list of available provider identifiers.
        """
        return sorted(cls._PROVIDERS.keys())
