"""Azure OpenAI Embedding implementation.

This module provides the Azure OpenAI Embedding implementation, which handles
Azure-specific configuration (endpoint, api-version, deployment names) while
reusing the core OpenAI embedding logic.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from src.libs.embedding.base_embedding import BaseEmbedding


class AzureEmbeddingError(RuntimeError):
    """Raised when Azure OpenAI Embeddings API call fails."""


class AzureEmbedding(BaseEmbedding):
    """Azure OpenAI Embedding provider implementation.
    
    This class implements the BaseEmbedding interface for Azure OpenAI's Embeddings API.
    It handles Azure-specific configuration like endpoint, api-version, and deployment names.
    
    Attributes:
        api_key: The Azure API key for authentication.
        azure_endpoint: The Azure OpenAI endpoint URL.
        api_version: The API version to use.
        deployment_name: The deployment name (replaces 'model' in standard OpenAI).
        dimensions: Optional dimension reduction (only for text-embedding-3-*).
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> embedding = AzureEmbedding(settings)
        >>> vectors = embedding.embed(["hello world", "test"])
    """
    
    DEFAULT_API_VERSION = "2024-02-01"
    
    def __init__(
        self,
        settings: Any,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Azure OpenAI Embedding provider.
        
        Args:
            settings: Application settings containing Embedding configuration.
            api_key: Optional API key override (falls back to env var AZURE_OPENAI_API_KEY).
            azure_endpoint: Optional endpoint override (falls back to env var AZURE_OPENAI_ENDPOINT).
            api_version: Optional API version override.
            **kwargs: Additional configuration overrides.
        
        Raises:
            ValueError: If required Azure-specific configuration is missing.
        """
        # Azure uses 'deployment_name' instead of 'model'
        # Try settings.embedding.deployment_name first, fallback to model
        self.deployment_name = (
            getattr(settings.embedding, 'deployment_name', None) or 
            settings.embedding.model
        )
        
        # Extract optional dimensions setting
        self.dimensions = getattr(settings.embedding, 'dimensions', None)
        
        # API key: explicit parameter > settings.yaml > env var (fallback for backward compatibility)
        self.api_key = (
            api_key or 
            getattr(settings.embedding, 'api_key', None) or
            os.environ.get("AZURE_OPENAI_API_KEY") or
            os.environ.get("OPENAI_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key not provided. Configure 'api_key' in settings.yaml, "
                "set AZURE_OPENAI_API_KEY environment variable, or pass api_key parameter."
            )
        
        # Azure endpoint: explicit parameter > settings.yaml > env var (fallback)
        self.azure_endpoint = (
            azure_endpoint or
            getattr(settings.embedding, 'azure_endpoint', None) or
            os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        if not self.azure_endpoint:
            raise ValueError(
                "Azure OpenAI endpoint not provided. Configure 'azure_endpoint' in settings.yaml, "
                "set AZURE_OPENAI_ENDPOINT environment variable, or pass azure_endpoint parameter."
            )
        
        # API version: explicit > settings > default
        self.api_version = (
            api_version or
            getattr(settings.embedding, 'api_version', None) or
            self.DEFAULT_API_VERSION
        )
        
        # Store any additional kwargs for future use
        self._extra_config = kwargs
    
    def embed(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts using Azure OpenAI API.
        
        Args:
            texts: List of text strings to embed. Must not be empty.
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Override parameters (dimensions, etc.).
        
        Returns:
            List of embedding vectors, where each vector is a list of floats.
            The length of the outer list matches len(texts).
        
        Raises:
            ValueError: If texts list is empty or contains invalid entries.
            AzureEmbeddingError: If API call fails.
        """
        # Validate input
        self.validate_texts(texts)
        
        # Import Azure OpenAI client (lazy import to avoid dependency at module level)
        try:
            from openai import AzureOpenAI
        except ImportError as e:
            raise RuntimeError(
                "OpenAI Python package not installed. "
                "Install with: pip install openai"
            ) from e
        
        # Initialize Azure OpenAI client
        client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version,
        )
        
        # Prepare API call parameters
        # Azure uses 'model' parameter but expects deployment name
        api_params = {
            "input": texts,
            "model": self.deployment_name,
        }
        
        # Add dimensions if specified (only for text-embedding-3-* models)
        # text-embedding-ada-002 does NOT support dimensions parameter
        dimensions = kwargs.get("dimensions", self.dimensions)
        if dimensions is not None and "text-embedding-3" in self.deployment_name.lower():
            api_params["dimensions"] = dimensions
        
        # Call Azure OpenAI API
        try:
            response = client.embeddings.create(**api_params)
        except Exception as e:
            raise AzureEmbeddingError(
                f"Azure OpenAI Embeddings API call failed: {e}"
            ) from e
        
        # Extract embeddings from response
        # Response format is identical to OpenAI
        try:
            embeddings = [item.embedding for item in response.data]
        except (AttributeError, KeyError) as e:
            raise AzureEmbeddingError(
                f"Failed to parse Azure OpenAI Embeddings API response: {e}"
            ) from e
        
        # Verify output matches input length
        if len(embeddings) != len(texts):
            raise AzureEmbeddingError(
                f"Output length mismatch: expected {len(texts)}, got {len(embeddings)}"
            )
        
        return embeddings
    
    def get_dimension(self) -> Optional[int]:
        """Get the embedding dimension for the configured deployment.
        
        Returns:
            The embedding dimension, or None if not deterministic.
        
        Note:
            For text-embedding-3-* deployments with custom dimensions, returns
            the configured dimension. For other deployments, returns their default.
        """
        # If dimensions explicitly configured, return it
        if self.dimensions is not None:
            return self.dimensions
        
        # Common Azure deployment defaults
        # Note: deployment names are user-defined, but often follow these patterns
        deployment_dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        
        # Try exact match first
        if self.deployment_name in deployment_dimensions:
            return deployment_dimensions[self.deployment_name]
        
        # Check for partial matches (e.g., "my-embedding-3-large-prod" contains "embedding-3-large")
        # Try longer patterns first to avoid false matches
        for model_key in sorted(deployment_dimensions.keys(), key=len, reverse=True):
            if model_key in self.deployment_name:
                return deployment_dimensions[model_key]
        
        # Cannot determine dimension
        return None
