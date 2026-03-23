"""GraphStore - SQLite-based storage for entity relationships extracted by GraphRAG."""

import json
import sqlite_utils
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.core.storage.sqlite_manager import SQLiteManager
from src.observability.logger import get_logger

logger = get_logger(__name__)


class GraphStore:
    """SQLite-based graph database for storing entities and their relationships.
    
    Schema:
    - entities: (id, name, entity_type, description, doc_id)
    - relationships: (id, source_id, target_id, relation_type, doc_id)
    """
    
    def __init__(self, db_path: str):
        """Initialize GraphStore with a SQLite database.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        # Use SQLiteManager static helper to ensure WAL and busy_timeout
        self.db = SQLiteManager.initialize_db(self.db_path)
        self._init_schema()
        logger.info(f"GraphStore initialized at {db_path}")

    def _init_schema(self) -> None:
        """Initialize database schema if not already exists."""
        if "entities" not in self.db.table_names():
            self.db["entities"].create({
                "id": str,          # Unique entity ID (doc_id + name hash)
                "name": str,        # Entity name
                "entity_type": str, # e.g., "Person", "Organization", "Concept"
                "description": str, # Brief description
                "doc_id": str,      # Source document ID
            }, pk="id")
            self.db["entities"].create_index(["name"])
            self.db["entities"].create_index(["doc_id"])
        
        if "relationships" not in self.db.table_names():
            self.db["relationships"].create({
                "id": str,           # Unique relationship ID
                "source_id": str,    # Source entity ID
                "target_id": str,    # Target entity ID
                "relation_type": str,# e.g., "is_a", "related_to", "part_of"
                "doc_id": str,       # Source document ID
            }, pk="id")
            self.db["relationships"].create_index(["source_id"])
            self.db["relationships"].create_index(["target_id"])
            self.db["relationships"].create_index(["doc_id"])

    def add_entities(self, entities: List[Dict[str, Any]]) -> int:
        """Store extracted entities. Upserts if entity already exists.
        
        Args:
            entities: List of entity dicts with keys: id, name, entity_type, description, doc_id
            
        Returns:
            Number of entities stored.
        """
        if not entities:
            return 0
        self.db["entities"].upsert_all(entities, pk="id")
        logger.debug(f"Stored {len(entities)} entities in GraphStore")
        return len(entities)

    async def async_add_entities(self, entities: List[Dict[str, Any]]) -> int:
        """Asynchronous version of add_entities."""
        import asyncio
        return await asyncio.to_thread(self.add_entities, entities)

    def add_relationships(self, relationships: List[Dict[str, Any]]) -> int:
        """Store extracted relationships. Upserts on conflict.
        
        Args:
            relationships: List of dicts with keys: id, source_id, target_id, relation_type, doc_id
            
        Returns:
            Number of relationships stored.
        """
        if not relationships:
            return 0
        self.db["relationships"].upsert_all(relationships, pk="id")
        logger.debug(f"Stored {len(relationships)} relationships in GraphStore")
        return len(relationships)

    async def async_add_relationships(self, relationships: List[Dict[str, Any]]) -> int:
        """Asynchronous version of add_relationships."""
        import asyncio
        return await asyncio.to_thread(self.add_relationships, relationships)

    def get_neighbors(self, entity_name: str, max_hops: int = 1) -> List[Dict[str, Any]]:
        """Get neighboring entities within `max_hops` from a given entity name.
        
        Args:
            entity_name: Name of the entity to search from.
            max_hops: Number of graph hops to traverse.
            
        Returns:
            List of related entities and their relationships as context dicts.
        """
        # Find matching entities
        entity_rows = list(self.db["entities"].rows_where("name = ?", [entity_name]))
        if not entity_rows:
            # Try fuzzy match using LIKE
            entity_rows = list(self.db["entities"].rows_where(
                "name LIKE ?", [f"%{entity_name}%"]
            ))
        
        results = []
        visited = set()
        
        for entity in entity_rows[:3]:  # Limit to at most 3 starting entities
            entity_id = entity["id"]
            if entity_id in visited:
                continue
            visited.add(entity_id)
            
            # Find all 1-hop relationships
            rels = list(self.db["relationships"].rows_where(
                "source_id = ? OR target_id = ?", [entity_id, entity_id]
            ))
            
            for rel in rels:
                # Determine the "other" entity
                other_id = rel["target_id"] if rel["source_id"] == entity_id else rel["source_id"]
                
                if other_id in visited:
                    continue
                    
                try:
                    other_entity = self.db["entities"].get(other_id)
                    results.append({
                        "from": entity["name"],
                        "relation": rel["relation_type"],
                        "to": other_entity["name"],
                        "to_type": other_entity["entity_type"],
                        "to_description": other_entity.get("description", "")
                    })
                except Exception:
                    continue
                    
        return results[:20]  # Limit to top 20 relations to avoid context overflow

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all entities and relationships for a document.
        
        Args:
            doc_id: Document ID to remove from the graph.
            
        Returns:
            Total number of records deleted.
        """
        e_count = self.db["entities"].delete_where("doc_id = ?", [doc_id])
        r_count = self.db["relationships"].delete_where("doc_id = ?", [doc_id])
        logger.info(f"Deleted {e_count} entities and {r_count} relationships for doc_id: {doc_id}")
        return e_count + r_count
