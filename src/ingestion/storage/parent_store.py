"""Parent Document Store - Persists large text chunks in SQLite for context expansion."""

import sqlite_utils
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.core.types import Chunk
from src.observability.logger import get_logger

logger = get_logger(__name__)

class ParentStore:
    """SQLite-based storage for parent document chunks.
    
    This store enables the 'Parent Document Retrieval' pattern:
    1. Child chunks are stored in vector DB for precision search.
    2. Parent chunks (the source of child chunks) are stored here.
    3. During retrieval, we find child hits and then fetch their parents 
       from here to provide broader context to the LLM.
    """
    
    def __init__(self, db_path: str):
        """Initialize ParentStore with a SQLite database.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite_utils.Database(str(self.db_path))
        
        # Initialize schema
        if "parents" not in self.db.table_names():
            self.db["parents"].create(
                {
                    "id": str,          # parent_id (e.g. {doc_id}_p_{seq})
                    "doc_id": str,      # ID of the source document
                    "text": str,        # Parent chunk text
                    "metadata": str,    # JSON string of metadata
                    "ingested_at": str, # Timestamp
                },
                pk="id"
            )
            # Create index for fast lookup by doc_id
            self.db["parents"].create_index(["doc_id"])
            logger.info(f"Initialized ParentStore at {db_path}")

    def add_parents(self, parents: List[Chunk]) -> int:
        """Store parent chunks in the database.
        
        Args:
            parents: List of Chunk objects to store as parents.
            
        Returns:
            Number of chunks successfully stored.
        """
        import json
        from datetime import datetime
        
        records = []
        for p in parents:
            records.append({
                "id": p.id,
                "doc_id": p.metadata.get("source_ref") or p.metadata.get("doc_id", "unknown"),
                "text": p.text,
                "metadata": json.dumps(p.metadata, ensure_ascii=False),
                "ingested_at": datetime.now().isoformat()
            })
            
        if records:
            # Use upsert to handle re-ingestion
            self.db["parents"].upsert_all(records, pk="id")
            logger.debug(f"Stored {len(records)} parent chunks in SQLite")
            
        return len(records)

    def get_parent_text(self, parent_id: str) -> Optional[str]:
        """Retrieve the text of a parent chunk by its ID.
        
        Args:
            parent_id: The unique ID of the parent chunk.
            
        Returns:
            The parent text if found, else None.
        """
        try:
            row = self.db["parents"].get(parent_id)
            return row["text"]
        except Exception:
            return None

    def get_parent_texts(self, parent_ids: List[str]) -> Dict[str, str]:
        """Batch retrieve parent texts.
        
        Args:
            parent_ids: List of parent chunk IDs.
            
        Returns:
            Dictionary mapping parent_id to its text.
        """
        if not parent_ids:
            return {}
            
        # Use simple select for batch retrieval
        placeholders = ", ".join(["?"] * len(parent_ids))
        query = f"SELECT id, text FROM parents WHERE id IN ({placeholders})"
        
        results = {}
        for row in self.db.query(query, parent_ids):
            results[row["id"]] = row["text"]
            
        return results

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all parent chunks associated with a document.
        
        Args:
            doc_id: The document ID to remove.
            
        Returns:
            Number of records deleted.
        """
        count = self.db["parents"].delete_where("doc_id = ?", [doc_id])
        logger.info(f"Deleted {count} parent chunks for doc_id: {doc_id}")
        return count
