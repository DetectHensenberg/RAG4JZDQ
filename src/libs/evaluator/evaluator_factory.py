"""Factory for creating Evaluator provider instances.

This module implements the Factory Pattern to instantiate the appropriate
Evaluator provider based on configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.libs.evaluator.base_evaluator import BaseEvaluator, NoneEvaluator
from src.libs.evaluator.custom_evaluator import CustomEvaluator

if TYPE_CHECKING:
    from src.core.settings import Settings


def _get_ragas_evaluator() -> type[BaseEvaluator]:
    """Lazy import RagasEvaluator to avoid hard dependency on ragas."""
    from src.observability.evaluation.ragas_evaluator import RagasEvaluator
    return RagasEvaluator


def _get_composite_evaluator() -> type[BaseEvaluator]:
    """Lazy import CompositeEvaluator."""
    from src.observability.evaluation.composite_evaluator import CompositeEvaluator
    return CompositeEvaluator


class EvaluatorFactory:
    """Factory for creating Evaluator provider instances.

    Design Principles Applied:
    - Factory Pattern: Centralizes object creation logic.
    - Config-Driven: Provider selection based on settings.yaml.
    - Fallback: Disabled evaluation returns NoneEvaluator.
    - Fail-Fast: Raises clear errors for unknown providers.
    """

    _PROVIDERS: dict[str, type[BaseEvaluator]] = {
        "custom": CustomEvaluator,
    }

    # Lazy-loaded providers (import on demand to avoid hard dependencies)
    _LAZY_PROVIDERS: dict[str, Any] = {
        "ragas": _get_ragas_evaluator,
        "composite": _get_composite_evaluator,
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: type[BaseEvaluator]) -> None:
        """Register a new Evaluator provider implementation.

        Args:
            name: The provider identifier (e.g., 'ragas', 'custom').
            provider_class: The BaseEvaluator subclass implementing the provider.

        Raises:
            ValueError: If provider_class doesn't inherit from BaseEvaluator.
        """
        if not issubclass(provider_class, BaseEvaluator):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from BaseEvaluator"
            )
        cls._PROVIDERS[name.lower()] = provider_class

    @classmethod
    def create(cls, settings: Settings, **override_kwargs: Any) -> BaseEvaluator:
        """Create an Evaluator instance based on configuration.

        Args:
            settings: The application settings containing evaluation config.
            **override_kwargs: Optional parameters to override config values.

        Returns:
            An instance of the configured Evaluator provider.

        Raises:
            ValueError: If the configured provider is not supported or missing.
            RuntimeError: If provider initialization fails.
        """
        try:
            # Accept either full Settings (with .evaluation attr) or
            # a bare EvaluationSettings object directly.
            if hasattr(settings, "evaluation"):
                evaluation_settings = settings.evaluation
            elif hasattr(settings, "provider") and hasattr(settings, "enabled"):
                evaluation_settings = settings
            else:
                raise AttributeError("settings has no 'evaluation' attribute")
            if evaluation_settings is None:
                raise AttributeError("settings.evaluation is None")
            provider_name = evaluation_settings.provider.lower()
            enabled = bool(evaluation_settings.enabled)
        except AttributeError as e:
            raise ValueError(
                "Missing required configuration: settings.evaluation.provider. "
                "Please ensure 'evaluation.provider' is specified in settings.yaml"
            ) from e

        if not enabled or provider_name in {"none", "disabled"}:
            return NoneEvaluator(settings=settings, **override_kwargs)

        provider_class = cls._PROVIDERS.get(provider_name)
        if provider_class is None and provider_name in cls._LAZY_PROVIDERS:
            try:
                provider_class = cls._LAZY_PROVIDERS[provider_name]()
                cls._PROVIDERS[provider_name] = provider_class  # cache for next call
            except ImportError as e:
                raise ValueError(
                    f"Provider '{provider_name}' requires additional dependencies: {e}"
                ) from e
        if provider_class is None:
            all_providers = sorted(set(cls._PROVIDERS.keys()) | set(cls._LAZY_PROVIDERS.keys()))
            available = ", ".join(all_providers) if all_providers else "none"
            raise ValueError(
                f"Unsupported Evaluator provider: '{provider_name}'. "
                f"Available providers: {available}."
            )

        try:
            return provider_class(settings=settings, **override_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to instantiate Evaluator provider '{provider_name}': {e}"
            ) from e

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names.

        Returns:
            Sorted list of available provider identifiers.
        """
        return sorted(cls._PROVIDERS.keys())