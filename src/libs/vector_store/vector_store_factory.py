"""Factory for creating VectorStore provider instances.

This module implements the Factory Pattern to instantiate the appropriate
VectorStore provider based on configuration, enabling configuration-driven selection
of different backends without code changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.libs.vector_store.base_vector_store import BaseVectorStore

if TYPE_CHECKING:
    from src.core.settings import Settings


class VectorStoreFactory:
    """Factory for creating VectorStore provider instances.
    
    This factory reads the provider configuration from settings and instantiates
    the corresponding VectorStore implementation. Supported providers will be added
    in subsequent tasks (B7.6 and beyond).
    
    Design Principles Applied:
    - Factory Pattern: Centralizes object creation logic.
    - Config-Driven: Provider selection based on settings.yaml.
    - Fail-Fast: Raises clear errors for unknown providers.
    """
    
    # Registry of supported providers (to be populated in B7.x tasks)
    _PROVIDERS: dict[str, type[BaseVectorStore]] = {}
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type[BaseVectorStore]) -> None:
        """Register a new VectorStore provider implementation.
        
        This method allows provider implementations to register themselves
        with the factory, supporting extensibility.
        
        Args:
            name: The provider identifier (e.g., 'chroma', 'qdrant', 'milvus').
            provider_class: The BaseVectorStore subclass implementing the provider.
        
        Raises:
            ValueError: If provider_class doesn't inherit from BaseVectorStore.
        """
        if not issubclass(provider_class, BaseVectorStore):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from BaseVectorStore"
            )
        cls._PROVIDERS[name.lower()] = provider_class
    
    @classmethod
    def create(cls, settings: Settings, **override_kwargs: Any) -> BaseVectorStore:
        """Create a VectorStore instance based on configuration.
        
        Args:
            settings: The application settings containing VectorStore configuration.
            **override_kwargs: Optional parameters to override config values.
        
        Returns:
            An instance of the configured VectorStore provider.
        
        Raises:
            ValueError: If the configured provider is not supported.
            AttributeError: If required configuration fields are missing.
        
        Example:
            >>> settings = Settings.load('config/settings.yaml')
            >>> vector_store = VectorStoreFactory.create(settings)
            >>> vector_store.upsert([{'id': 'doc1', 'vector': [0.1, 0.2]}])
        """
        # Extract provider name from settings
        try:
            provider_name = settings.vector_store.provider.lower()
        except AttributeError as e:
            raise ValueError(
                "Missing required configuration: settings.vector_store.provider. "
                "Please ensure 'vector_store.provider' is specified in settings.yaml"
            ) from e
        
        # Look up provider class in registry
        provider_class = cls._PROVIDERS.get(provider_name)
        
        if provider_class is None:
            available = ", ".join(sorted(cls._PROVIDERS.keys())) if cls._PROVIDERS else "none"
            raise ValueError(
                f"Unsupported VectorStore provider: '{provider_name}'. "
                f"Available providers: {available}. "
                f"Provider implementations will be added in task B7.6 and beyond."
            )
        
        # Instantiate the provider
        # Provider classes should accept settings and optional kwargs
        try:
            return provider_class(settings=settings, **override_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to instantiate VectorStore provider '{provider_name}': {e}"
            ) from e
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names.
        
        Returns:
            Sorted list of provider names.
        
        Example:
            >>> VectorStoreFactory.list_providers()
            ['chroma', 'milvus', 'qdrant']
        """
        return sorted(cls._PROVIDERS.keys())
