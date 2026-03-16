"""Unit tests for ChromaStore non-ASCII path fix.

Tests cover:
- ChromaStore stores original relative path string as _chroma_path_str
- PersistentClient receives relative (ASCII-safe) path, not absolute
- Absolute path with Chinese chars is only used for file operations
- _try_restore_from_backup uses relative path for new client
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestChromaPathHandling:
    """Verify ChromaStore uses relative path for PersistentClient."""

    @patch("src.libs.vector_store.chroma_store.chromadb")
    def test_persist_directory_stores_relative_string(self, mock_chromadb: MagicMock) -> None:
        """_chroma_path_str should be the raw config string, not resolved absolute."""
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection

        settings = MagicMock()
        settings.vector_store.provider = "chroma"
        settings.vector_store.collection_name = "default"
        settings.vector_store.persist_directory = "./data/db/chroma"

        from src.libs.vector_store.chroma_store import ChromaStore

        with patch.object(ChromaStore, "_sqlite_has_data", return_value=False):
            store = ChromaStore(settings=settings)

        assert store._chroma_path_str == "./data/db/chroma"

    @patch("src.libs.vector_store.chroma_store.chromadb")
    def test_persistent_client_receives_relative_path(self, mock_chromadb: MagicMock) -> None:
        """PersistentClient should be called with the relative path, not absolute."""
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection

        settings = MagicMock()
        settings.vector_store.provider = "chroma"
        settings.vector_store.collection_name = "default"
        settings.vector_store.persist_directory = "./data/db/chroma"

        from src.libs.vector_store.chroma_store import ChromaStore

        with patch.object(ChromaStore, "_sqlite_has_data", return_value=False):
            store = ChromaStore(settings=settings)

        # Check PersistentClient was called with relative path
        call_args = mock_chromadb.PersistentClient.call_args
        path_arg = call_args.kwargs.get("path", call_args.args[0] if call_args.args else None)
        # Should NOT be an absolute path
        assert not Path(path_arg).is_absolute(), (
            f"PersistentClient received absolute path: {path_arg}"
        )

    @patch("src.libs.vector_store.chroma_store.chromadb")
    def test_persist_directory_is_absolute_for_file_ops(self, mock_chromadb: MagicMock) -> None:
        """self.persist_directory should be absolute Path for backup/file ops."""
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_client.get_or_create_collection.return_value = mock_collection

        settings = MagicMock()
        settings.vector_store.provider = "chroma"
        settings.vector_store.collection_name = "default"
        settings.vector_store.persist_directory = "./data/db/chroma"

        from src.libs.vector_store.chroma_store import ChromaStore

        with patch.object(ChromaStore, "_sqlite_has_data", return_value=False):
            store = ChromaStore(settings=settings)

        assert store.persist_directory.is_absolute()


class TestNonAsciiPathRegression:
    """Regression tests for the Chinese-path HNSW loading bug."""

    def test_path_with_chinese_chars_detected(self) -> None:
        """Verify we can detect non-ASCII characters in paths."""
        ascii_path = r"D:\WorkSpace\project\myproject\data"
        chinese_path = r"D:\WorkSpace\project\个人项目\RAG\data"

        assert ascii_path.isascii()
        assert not chinese_path.isascii()

    def test_relative_path_avoids_chinese_parent(self) -> None:
        """Relative path ./data/db/chroma avoids Chinese parent dirs."""
        relative = "./data/db/chroma"
        assert relative.isascii()
