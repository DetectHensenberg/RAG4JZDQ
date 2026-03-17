"""BGE-M3 Embedding implementation.

This module provides the BGE-M3 Embedding implementation that produces both
dense and learned sparse (lexical) vectors in a single forward pass.

BGE-M3 is a state-of-the-art embedding model from BAAI that supports:
- Dense embeddings (1024 dimensions)
- Learned sparse embeddings (similar to SPLADE)
- Multi-lingual support (100+ languages)

Requires: pip install FlagEmbedding
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from src.libs.embedding.base_embedding import BaseEmbedding
from src.observability.logger import get_logger

if TYPE_CHECKING:
    from FlagEmbedding import BGEM3FlagModel

logger = get_logger(__name__)


class BGEM3EmbeddingError(RuntimeError):
    """Raised when BGE-M3 embedding operation fails."""


class BGEM3Embedding(BaseEmbedding):
    """BGE-M3 Embedding provider - Dense + Learned Sparse dual output.
    
    This class implements the BaseEmbedding interface for BAAI's BGE-M3 model,
    which can produce both dense and sparse embeddings in a single inference.
    
    Attributes:
        model_name: The HuggingFace model identifier.
        use_fp16: Whether to use FP16 precision (recommended for GPU).
        device: Device to run inference on (auto/cpu/cuda).
    
    Example:
        >>> from src.core.settings import load_settings
        >>> settings = load_settings('config/settings.yaml')
        >>> embedding = BGEM3Embedding(settings)
        >>> vectors = embedding.embed(["hello world", "test"])
        >>> dense, sparse = embedding.embed_with_sparse(["hello"])
    """
    
    DEFAULT_MODEL = "BAAI/bge-m3"
    DEFAULT_DIMENSION = 1024
    
    def __init__(
        self,
        settings: Any,
        model_name: Optional[str] = None,
        use_fp16: Optional[bool] = None,
        device: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the BGE-M3 Embedding provider.
        
        Args:
            settings: Application settings containing Embedding configuration.
            model_name: Optional model name override.
            use_fp16: Optional FP16 flag override.
            device: Optional device override (auto/cpu/cuda).
            **kwargs: Additional configuration overrides.
        
        Note:
            Model is lazily loaded on first embed() call to avoid startup delay.
        """
        bge_m3_config = getattr(
            getattr(settings, 'embedding', None), 'bge_m3', None
        )
        
        self.model_name = (
            model_name
            or (getattr(bge_m3_config, 'model', None) if bge_m3_config else None)
            or self.DEFAULT_MODEL
        )
        
        self.use_fp16 = (
            use_fp16 if use_fp16 is not None
            else (getattr(bge_m3_config, 'use_fp16', True) if bge_m3_config else True)
        )
        
        self.device = (
            device
            or (getattr(bge_m3_config, 'device', 'auto') if bge_m3_config else 'auto')
        )
        
        self._model: Optional[BGEM3FlagModel] = None
        self._extra_config = kwargs
        
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        
        logger.info(
            f"BGEM3Embedding initialized: model={self.model_name}, "
            f"use_fp16={self.use_fp16}, device={self.device}"
        )
    
    def _get_model(self) -> "BGEM3FlagModel":
        """Lazily load the BGE-M3 model.
        
        Returns:
            The loaded BGEM3FlagModel instance.
        
        Raises:
            BGEM3EmbeddingError: If model loading fails.
        """
        if self._model is not None:
            return self._model
        
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as e:
            raise BGEM3EmbeddingError(
                "FlagEmbedding package not installed. "
                "Install with: pip install FlagEmbedding"
            ) from e
        
        try:
            logger.info(f"Loading BGE-M3 model: {self.model_name}")
            
            device = self.device
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16 if device != "cpu" else False,
                device=device,
            )
            
            logger.info(f"BGE-M3 model loaded successfully on {device}")
            return self._model
            
        except Exception as e:
            raise BGEM3EmbeddingError(
                f"Failed to load BGE-M3 model '{self.model_name}': {e}"
            ) from e
    
    def embed(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[List[float]]:
        """Generate dense embeddings for a batch of texts.
        
        Args:
            texts: List of text strings to embed. Must not be empty.
            trace: Optional TraceContext for observability.
            **kwargs: Additional parameters (ignored).
        
        Returns:
            List of dense embedding vectors (1024 dimensions each).
        
        Raises:
            ValueError: If texts list is empty or contains invalid entries.
            BGEM3EmbeddingError: If embedding operation fails.
        """
        self.validate_texts(texts)
        
        try:
            model = self._get_model()
            output = model.encode(
                texts,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            
            dense_vecs = output["dense_vecs"]
            
            if hasattr(dense_vecs, "tolist"):
                return dense_vecs.tolist()
            return [list(v) for v in dense_vecs]
            
        except BGEM3EmbeddingError:
            raise
        except Exception as e:
            raise BGEM3EmbeddingError(
                f"BGE-M3 embedding failed: {type(e).__name__}: {e}"
            ) from e
    
    def embed_with_sparse(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> Tuple[List[List[float]], List[Dict[int, float]]]:
        """Generate both dense and sparse embeddings for a batch of texts.
        
        This method produces both dense vectors and learned sparse (lexical)
        weights in a single forward pass, which is more efficient than
        calling embed() and a separate sparse encoder.
        
        Args:
            texts: List of text strings to embed. Must not be empty.
            trace: Optional TraceContext for observability.
            **kwargs: Additional parameters (ignored).
        
        Returns:
            Tuple of:
                - dense: List of dense embedding vectors (1024 dimensions)
                - sparse: List of sparse weight dicts {token_id: weight}
        
        Raises:
            ValueError: If texts list is empty or contains invalid entries.
            BGEM3EmbeddingError: If embedding operation fails.
        """
        self.validate_texts(texts)
        
        try:
            model = self._get_model()
            output = model.encode(
                texts,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
            
            dense_vecs = output["dense_vecs"]
            lexical_weights = output["lexical_weights"]
            
            if hasattr(dense_vecs, "tolist"):
                dense_list = dense_vecs.tolist()
            else:
                dense_list = [list(v) for v in dense_vecs]
            
            sparse_list = []
            for weights in lexical_weights:
                if isinstance(weights, dict):
                    sparse_list.append(weights)
                else:
                    sparse_list.append(dict(weights))
            
            return dense_list, sparse_list
            
        except BGEM3EmbeddingError:
            raise
        except Exception as e:
            raise BGEM3EmbeddingError(
                f"BGE-M3 embedding with sparse failed: {type(e).__name__}: {e}"
            ) from e
    
    def get_dimension(self) -> int:
        """Get the embedding dimension for BGE-M3.
        
        Returns:
            1024 (fixed dimension for BGE-M3 dense embeddings).
        """
        return self.DEFAULT_DIMENSION
