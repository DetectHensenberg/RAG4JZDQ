"""ChromaDB VectorStore implementation.

This module provides a concrete implementation of BaseVectorStore using ChromaDB,
a lightweight, open-source embedding database designed for local-first deployment.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from src.core.settings import resolve_path
from src.libs.vector_store.base_vector_store import BaseVectorStore

if TYPE_CHECKING:
    from src.core.settings import Settings

logger = logging.getLogger(__name__)


class ChromaStore(BaseVectorStore):
    """ChromaDB implementation of VectorStore.
    
    This class provides local-first, persistent vector storage using ChromaDB.
    It supports upsert, query, and metadata filtering operations.
    
    Design Principles Applied:
    - Pluggable: Implements BaseVectorStore interface, swappable with other providers.
    - Config-Driven: All settings (persist_directory, collection_name) from settings.yaml.
    - Idempotent: upsert operations with same ID overwrite existing records.
    - Observable: Accepts optional TraceContext (reserved for Stage F).
    - Fail-Fast: Validates dependencies and configuration on initialization.
    
    Attributes:
        client: ChromaDB client instance.
        collection: ChromaDB collection for storing vectors.
        collection_name: Name of the collection.
        persist_directory: Directory path for persistent storage.
    
    Example:
        >>> settings = Settings.load('config/settings.yaml')
        >>> store = ChromaStore(settings=settings)
        >>> records = [
        ...     {
        ...         'id': 'doc1_chunk0',
        ...         'vector': [0.1, 0.2, 0.3],
        ...         'metadata': {'source': 'doc1.pdf'}
        ...     }
        ... ]
        >>> store.upsert(records)
        >>> results = store.query([0.1, 0.2, 0.3], top_k=5)
    """
    
    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        """Initialize ChromaStore with configuration.
        
        Args:
            settings: Application settings containing vector_store configuration.
            **kwargs: Optional overrides for collection_name or persist_directory.
        
        Raises:
            ImportError: If chromadb package is not installed.
            ValueError: If required configuration is missing.
            RuntimeError: If ChromaDB client initialization fails.
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb package is required for ChromaStore. "
                "Install it with: pip install chromadb"
            )
        
        # Extract configuration
        try:
            vector_store_config = settings.vector_store
        except AttributeError as e:
            raise ValueError(
                "Missing required configuration: settings.vector_store. "
                "Please ensure 'vector_store' section exists in settings.yaml"
            ) from e
        
        # Collection name (allow override)
        raw_name = kwargs.get(
            'collection_name',
            getattr(vector_store_config, 'collection_name', 'knowledge_hub')
        )
        self.collection_name = self._sanitize_collection_name(raw_name)
        if self.collection_name != raw_name:
            logger.info(f"Collection name sanitized: '{raw_name}' -> '{self.collection_name}'")
        
        # Persist directory (allow override)
        persist_dir_str = kwargs.get(
            'persist_directory',
            getattr(vector_store_config, 'persist_directory', './data/db/chroma')
        )
        self.persist_directory = resolve_path(persist_dir_str)
        
        # ChromaDB Rust backend cannot handle non-ASCII chars in absolute
        # paths (e.g. Chinese directory names). Keep a relative path for
        # the PersistentClient and use the absolute path for file ops.
        self._chroma_path_str = persist_dir_str  # original relative string
        
        # Ensure persist directory exists
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"Initializing ChromaStore: collection='{self.collection_name}', "
            f"persist_directory='{self.persist_directory}'"
        )
        
        # ── Pre-init backup ──────────────────────────────────────────
        # Backup HNSW BEFORE creating PersistentClient, because the
        # client constructor may trigger compaction which can fail on
        # a corrupted index. Pure file copy — no ChromaDB API involved.
        from src.libs.vector_store.chroma_backup import ChromaBackupManager
        self.backup_manager = ChromaBackupManager(chroma_dir=self.persist_directory)
        
        has_hnsw = bool(self.backup_manager._find_hnsw_dirs())
        has_data = self._sqlite_has_data(self.persist_directory)
        if has_hnsw and has_data:
            self.backup_manager.backup(label="startup")
        
        # ── Initialize ChromaDB client ───────────────────────────────
        try:
            self.client = chromadb.PersistentClient(
                path=self._chroma_path_str,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                    is_persistent=True,
                )
            )
            import sqlite3
            db_path = self.persist_directory / "chroma.sqlite3"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.close()
                logger.debug("SQLite WAL mode enabled for ChromaDB")
        except (RuntimeError, OSError) as e:
            raise RuntimeError(
                f"Failed to initialize ChromaDB client at '{self.persist_directory}': {e}"
            ) from e
        
        # Get or create collection
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to get or create collection '{self.collection_name}': {e}"
            ) from e
        
        try:
            count = self.collection.count()
        except Exception:
            count = "unknown (HNSW may need restore)"
        
        logger.info(
            f"ChromaStore initialized successfully. "
            f"Collection count: {count}"
        )
        
        # Register graceful shutdown to prevent index corruption
        import atexit
        atexit.register(self.close)
    
    @staticmethod
    def _sqlite_has_data(persist_dir: Path) -> bool:
        """Check if ChromaDB SQLite has embeddings (bypasses ChromaDB API)."""
        import sqlite3
        db_path = persist_dir / "chroma.sqlite3"
        if not db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
            conn.close()
            return row[0] > 0 if row else False
        except Exception:
            return False
    
    @staticmethod
    def _sanitize_collection_name(name: str) -> str:
        """Sanitize collection name for ChromaDB compatibility.

        ChromaDB requires: 3-512 chars from [a-zA-Z0-9._-],
        starting and ending with [a-zA-Z0-9].
        Non-ASCII names (e.g. Chinese) are converted to a readable hash prefix.
        """
        # If already valid, return as-is
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]", name):
            return name

        # Replace non-ASCII / invalid chars with underscore, keep alnum and ._-
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
        # Remove leading/trailing invalid chars
        sanitized = sanitized.strip("._-")

        if len(sanitized) < 3:
            # Fallback: use hash of original name
            h = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
            sanitized = f"col_{h}"

        # Ensure start/end are alphanumeric
        if not sanitized[0].isalnum():
            sanitized = "c" + sanitized
        if not sanitized[-1].isalnum():
            sanitized = sanitized + "0"

        return sanitized[:512]

    def upsert(
        self,
        records: List[Dict[str, Any]],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Insert or update records in ChromaDB.
        
        Args:
            records: List of records to upsert. Each record must have:
                - 'id': Unique identifier (str)
                - 'vector': Embedding vector (List[float])
                - 'metadata': Optional metadata dict
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Provider-specific parameters (unused for Chroma).
        
        Raises:
            ValueError: If records list is empty or contains invalid entries.
            RuntimeError: If the upsert operation fails.
        """
        # Validate records
        self.validate_records(records)
        
        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        metadatas = []
        documents = []  # ChromaDB requires documents field
        
        for record in records:
            ids.append(str(record['id']))
            embeddings.append(record['vector'])
            
            # Metadata: extract or default to empty dict
            metadata = record.get('metadata', {})
            # Ensure all metadata values are JSON-serializable
            # ChromaDB requires string, int, float, or bool values
            sanitized_metadata = self._sanitize_metadata(metadata)
            
            # ChromaDB requires non-empty metadata dict
            if not sanitized_metadata:
                sanitized_metadata = {'_placeholder': 'true'}
            
            metadatas.append(sanitized_metadata)
            
            # Document: use metadata.text if available, otherwise use id
            document = metadata.get('text', record['id'])
            documents.append(str(document))
        
        # Perform upsert in batches with retry for compaction conflicts
        import time as _time
        UPSERT_BATCH = 50
        MAX_RETRIES = 3
        try:
            for start in range(0, len(ids), UPSERT_BATCH):
                end = min(start + UPSERT_BATCH, len(ids))
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        self.collection.upsert(
                            ids=ids[start:end],
                            embeddings=embeddings[start:end],
                            metadatas=metadatas[start:end],
                            documents=documents[start:end],
                        )
                        break  # success
                    except Exception as batch_err:
                        err_msg = str(batch_err).lower()
                        if "compaction" in err_msg and attempt < MAX_RETRIES:
                            wait = 2 ** attempt
                            logger.warning(
                                f"Compaction conflict on batch {start}-{end}, "
                                f"retry {attempt}/{MAX_RETRIES} in {wait}s..."
                            )
                            _time.sleep(wait)
                        else:
                            raise
            logger.debug(f"Successfully upserted {len(records)} records to ChromaDB")
            # Flush WAL to disk after upsert to reduce corruption risk
            self._wal_checkpoint()
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to upsert {len(records)} records to ChromaDB: {e}"
            ) from e
    
    def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Query ChromaDB for similar vectors.
        
        Args:
            vector: Query vector (embedding) to search for.
            top_k: Maximum number of results to return.
            filters: Optional metadata filters (e.g., {'source': 'doc1.pdf'}).
            trace: Optional TraceContext for observability (reserved for Stage F).
            **kwargs: Provider-specific parameters (unused for Chroma).
        
        Returns:
            List of matching records, sorted by similarity (descending).
            Each record contains:
                - 'id': Record identifier
                - 'score': Similarity score (1.0 = identical, 0.0 = orthogonal)
                - 'metadata': Associated metadata
        
        Raises:
            ValueError: If vector is empty or top_k is invalid.
            RuntimeError: If the query operation fails.
        """
        # Validate query parameters
        self.validate_query_vector(vector, top_k)
        
        # Build ChromaDB where clause from filters
        where_clause = self._build_where_clause(filters) if filters else None
        
        # Perform query with auto-restore on HNSW corruption
        try:
            results = self.collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                where=where_clause,
                include=["metadatas", "distances", "documents"]
            )
        except Exception as e:
            err_msg = str(e).lower()
            if "hnsw" in err_msg or "compaction" in err_msg or "segment" in err_msg:
                logger.warning(f"HNSW query failed: {e}. Attempting auto-restore...")
                if self._try_restore_from_backup():
                    # Retry query once after restore
                    try:
                        results = self.collection.query(
                            query_embeddings=[vector],
                            n_results=top_k,
                            where=where_clause,
                            include=["metadatas", "distances", "documents"]
                        )
                    except Exception as retry_err:
                        raise RuntimeError(
                            f"Query failed after HNSW restore: {retry_err}"
                        ) from retry_err
                else:
                    raise RuntimeError(
                        f"HNSW corrupted and no backup available: {e}"
                    ) from e
            else:
                raise RuntimeError(
                    f"Failed to query ChromaDB with top_k={top_k}: {e}"
                ) from e
        
        # Transform results to standard format
        # ChromaDB returns nested lists: [[id1, id2, ...]]
        output = []
        
        if results and results['ids'] and results['ids'][0]:
            ids = results['ids'][0]
            distances = results['distances'][0] if 'distances' in results else [0.0] * len(ids)
            metadatas = results['metadatas'][0] if 'metadatas' in results else [{}] * len(ids)
            documents = results['documents'][0] if 'documents' in results else [''] * len(ids)
            
            for i, record_id in enumerate(ids):
                # Convert distance to similarity score
                # ChromaDB returns cosine distance (0=identical, 2=opposite)
                # Convert to similarity: score = 1 - (distance / 2)
                distance = distances[i]
                score = 1.0 - (distance / 2.0)
                
                output.append({
                    'id': record_id,
                    'score': max(0.0, score),  # Clamp to [0, 1]
                    'text': documents[i] if documents[i] else '',  # Include text from documents
                    'metadata': metadatas[i] if metadatas[i] else {}
                })
        
        logger.debug(f"Query returned {len(output)} results")
        return output
    
    def delete(
        self,
        ids: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Delete records from ChromaDB by IDs.
        
        Args:
            ids: List of record IDs to delete.
            trace: Optional TraceContext for observability.
            **kwargs: Provider-specific parameters.
        
        Raises:
            ValueError: If ids list is empty.
            RuntimeError: If the delete operation fails.
        """
        if not ids:
            raise ValueError("IDs list cannot be empty")
        
        try:
            self.collection.delete(ids=[str(id_) for id_ in ids])
            logger.debug(f"Successfully deleted {len(ids)} records from ChromaDB")
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to delete {len(ids)} records from ChromaDB: {e}"
            ) from e
    
    def clear(
        self,
        collection_name: Optional[str] = None,
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Clear all records from the ChromaDB collection.
        
        Args:
            collection_name: Optional collection name to clear. If None, clears current collection.
            trace: Optional TraceContext for observability.
            **kwargs: Provider-specific parameters.
        
        Raises:
            RuntimeError: If the clear operation fails.
        """
        try:
            target_collection = collection_name or self.collection_name
            
            # Delete and recreate collection (most efficient way to clear in Chroma)
            self.client.delete_collection(name=target_collection)
            self.collection = self.client.get_or_create_collection(
                name=target_collection,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Successfully cleared collection '{target_collection}'")
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to clear collection '{collection_name or self.collection_name}': {e}"
            ) from e

    def delete_by_metadata(
        self,
        filter_dict: Dict[str, Any],
        trace: Optional[Any] = None,
    ) -> int:
        """Delete records matching a metadata filter.

        Args:
            filter_dict: Metadata key/value pairs to match
                (e.g. ``{"source_hash": "abc123"}``).
            trace: Optional TraceContext for observability.

        Returns:
            Number of records deleted.

        Raises:
            ValueError: If *filter_dict* is empty.
            RuntimeError: If the operation fails.
        """
        if not filter_dict:
            raise ValueError("filter_dict cannot be empty")

        try:
            where = self._build_where_clause(filter_dict)
            # Query matching IDs first
            results = self.collection.get(where=where, include=[])
            matching_ids = results.get("ids", [])

            if not matching_ids:
                logger.debug(f"delete_by_metadata: no records matched {filter_dict}")
                return 0

            self.collection.delete(ids=matching_ids)
            logger.info(
                f"delete_by_metadata: deleted {len(matching_ids)} records "
                f"matching {filter_dict}"
            )
            return len(matching_ids)
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to delete by metadata {filter_dict}: {e}"
            ) from e
    
    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize metadata to ensure ChromaDB compatibility.
        
        ChromaDB requires metadata values to be str, int, float, or bool.
        This method converts or filters out incompatible types.
        
        Args:
            metadata: Raw metadata dict.
        
        Returns:
            Sanitized metadata dict.
        """
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif value is None:
                # Skip None values
                continue
            elif isinstance(value, (list, tuple)):
                # Convert to comma-separated string
                sanitized[key] = ",".join(str(v) for v in value)
            else:
                # Convert to string as fallback
                sanitized[key] = str(value)
        
        return sanitized
    
    def _build_where_clause(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build ChromaDB where clause from filters.
        
        Converts standard filter dict to ChromaDB's query format.
        
        Args:
            filters: Standard filter dict (e.g., {'source': 'doc1.pdf'}).
        
        Returns:
            ChromaDB where clause dict.
        
        Note:
            ChromaDB supports operators like $eq, $ne, $gt, $lt, $in, etc.
            For simplicity, we currently support only exact equality matches.
            Future enhancement: support complex filters.
        """
        # Simple implementation: exact equality matches only
        # For complex filters (e.g., {'score': {'$gt': 0.5}}), extend this method
        where = {}
        for key, value in filters.items():
            if isinstance(value, dict):
                # Already in ChromaDB operator format (e.g., {'$eq': 'value'})
                where[key] = value
            else:
                # Simple equality
                where[key] = value
        
        return where
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the current collection.
        
        Returns:
            Dict containing collection statistics:
                - count: Number of records in collection
                - name: Collection name
                - metadata: Collection metadata
        """
        return {
            'count': self.collection.count(),
            'name': self.collection_name,
            'metadata': self.collection.metadata
        }
    
    def get_by_ids(
        self,
        ids: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve records by their IDs from ChromaDB.
        
        This method is used by SparseRetriever to fetch text and metadata
        for chunks that were matched by BM25 search.
        
        Args:
            ids: List of record IDs to retrieve.
            trace: Optional TraceContext for observability.
            **kwargs: Provider-specific parameters (unused for Chroma).
        
        Returns:
            List of records in the same order as input ids.
            Each record contains:
                - 'id': Record identifier
                - 'text': The stored text content
                - 'metadata': Associated metadata
            If an ID is not found, an empty dict is returned for that position.
        
        Raises:
            ValueError: If ids list is empty.
            RuntimeError: If the retrieval operation fails.
        """
        if not ids:
            raise ValueError("IDs list cannot be empty")
        
        # Ensure all IDs are strings
        str_ids = [str(id_) for id_ in ids]
        
        try:
            # ChromaDB's get method retrieves records by IDs
            results = self.collection.get(
                ids=str_ids,
                include=["metadatas", "documents"]
            )
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to get records by IDs from ChromaDB: {e}"
            ) from e
        
        # Build a mapping from ID to result for O(1) lookup
        id_to_result: Dict[str, Dict[str, Any]] = {}
        
        if results and results.get('ids'):
            result_ids = results['ids']
            documents = results.get('documents', [None] * len(result_ids))
            metadatas = results.get('metadatas', [{}] * len(result_ids))
            
            for i, record_id in enumerate(result_ids):
                id_to_result[record_id] = {
                    'id': record_id,
                    'text': documents[i] if documents and documents[i] else '',
                    'metadata': metadatas[i] if metadatas and metadatas[i] else {}
                }
        
        # Return results in the same order as input ids
        output = []
        for id_ in str_ids:
            if id_ in id_to_result:
                output.append(id_to_result[id_])
            else:
                # ID not found, return empty dict
                output.append({})
        
        logger.debug(f"Retrieved {len([r for r in output if r])} of {len(ids)} records by IDs")
        return output
    
    def _try_restore_from_backup(self) -> bool:
        """Attempt to restore HNSW from backup and re-initialize client.
        
        Returns:
            True if restore succeeded and collection is usable.
        """
        import gc
        import time as _time
        try:
            # Close old client completely before touching files
            del self.client
            gc.collect()
            _time.sleep(1)  # Windows file handle release delay
            
            if not self.backup_manager.restore_latest():
                return False
            
            # Re-initialize with restored files (use relative path to
            # avoid ChromaDB Rust non-ASCII path bug)
            self.client = chromadb.PersistentClient(
                path=self._chroma_path_str,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                    is_persistent=True,
                ),
            )
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            count = self.collection.count()
            logger.info(f"HNSW auto-restore succeeded! Collection count: {count}")
            return True
        except Exception as e:
            logger.error(f"HNSW auto-restore failed: {e}")
            return False
    
    def _wal_checkpoint(self) -> None:
        """Flush SQLite WAL to main database file.
        
        This reduces the risk of index corruption if the process is
        terminated unexpectedly (e.g., Ctrl+C, crash, power loss).
        Uses TRUNCATE mode for stronger persistence guarantee.
        """
        try:
            import sqlite3
            db_path = self.persist_directory / "chroma.sqlite3"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
        except Exception:
            pass  # Best-effort, don't fail the operation
    
    def close(self) -> None:
        """Gracefully close ChromaDB, flushing all pending writes.
        
        Called automatically via atexit or manually before shutdown.
        """
        try:
            import sqlite3
            db_path = self.persist_directory / "chroma.sqlite3"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
                logger.info("ChromaStore closed: WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"ChromaStore close warning: {e}")
