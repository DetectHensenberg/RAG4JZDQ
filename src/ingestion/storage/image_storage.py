"""Image storage with SQLite indexing for multimodal RAG.

This module provides persistent image storage with SQLite-backed indexing,
enabling efficient image retrieval and management across collections.

Design Principles:
- Persistent: Images stored on filesystem, metadata in SQLite
- Concurrent: WAL mode enables concurrent read/write operations
- Idempotent: Re-saving same image_id updates metadata safely
- Organized: Images grouped by collection for namespace isolation
"""

import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Union


class ImageStorage:
    """SQLite-backed image storage manager.
    
    Stores image files in organized directory structure and maintains
    a SQLite index for efficient lookup and querying.
    
    Directory Structure:
        data/images/{collection}/{image_id}.png
    
    Database Schema:
        image_index (
            image_id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            collection TEXT,
            doc_hash TEXT,
            page_num INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        
        INDEX idx_collection ON image_index(collection)
        INDEX idx_doc_hash ON image_index(doc_hash)
    
    Args:
        db_path: Path to SQLite database file (default: data/db/image_index.db).
        images_root: Root directory for image storage (default: data/images).
    
    Example:
        >>> storage = ImageStorage()
        >>> 
        >>> # Save an image
        >>> with open("sample.png", "rb") as f:
        >>>     image_data = f.read()
        >>> path = storage.save_image(
        ...     image_id="doc123_p1_img0",
        ...     image_data=image_data,
        ...     collection="contracts",
        ...     doc_hash="abc123",
        ...     page_num=1
        ... )
        >>> print(path)  # data/images/contracts/doc123_p1_img0.png
        >>> 
        >>> # Retrieve image path
        >>> path = storage.get_image_path("doc123_p1_img0")
        >>> print(path)  # data/images/contracts/doc123_p1_img0.png
        >>> 
        >>> # List images in collection
        >>> images = storage.list_images("contracts")
        >>> print(len(images))  # 1
    """
    
    def __init__(
        self,
        db_path: str = "data/db/image_index.db",
        images_root: str = "data/images"
    ):
        """Initialize image storage and create database if needed.
        
        Args:
            db_path: Path to SQLite database file.
            images_root: Root directory for storing image files.
        """
        self.db_path = db_path
        self.images_root = Path(images_root)
        self._conn = None
        self._ensure_database()
    
    def close(self) -> None:
        """Close database connection if open."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __del__(self):
        """Cleanup: close connection on deletion."""
        self.close()
    
    def _ensure_database(self) -> None:
        """Create database file and schema if they don't exist."""
        # Create parent directories
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create images root directory
        self.images_root.mkdir(parents=True, exist_ok=True)
        
        # Connect and initialize schema
        conn = sqlite3.connect(self.db_path)
        try:
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Create table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_index (
                    image_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    collection TEXT,
                    doc_hash TEXT,
                    page_num INTEGER,
                    created_at TEXT NOT NULL
                )
            """)
            
            # Create indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collection 
                ON image_index(collection)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_hash 
                ON image_index(doc_hash)
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def save_image(
        self,
        image_id: str,
        image_data: Union[bytes, Path, str],
        collection: Optional[str] = None,
        doc_hash: Optional[str] = None,
        page_num: Optional[int] = None,
        extension: str = "png"
    ) -> str:
        """Save image to filesystem and register in database.
        
        This operation is idempotent - re-saving with same image_id
        will update the metadata and overwrite the file.
        
        Args:
            image_id: Unique identifier for the image.
            image_data: Image data as bytes, or path to source image file.
            collection: Optional collection/namespace for organization.
            doc_hash: Optional document hash for traceability.
            page_num: Optional page number if from paginated document.
            extension: File extension without dot (default: "png").
        
        Returns:
            Relative path where image was saved.
            
        Raises:
            ValueError: If image_id is empty or invalid.
            IOError: If image file cannot be saved.
            RuntimeError: If database operation fails.
            
        Example:
            >>> # Save from bytes
            >>> path = storage.save_image("img1", b"PNG_DATA", "docs")
            >>> 
            >>> # Save from file
            >>> path = storage.save_image("img2", Path("source.png"), "docs")
        """
        if not image_id or not image_id.strip():
            raise ValueError("image_id cannot be empty")
        
        # Determine collection directory
        if collection:
            collection_dir = self.images_root / collection
        else:
            collection_dir = self.images_root / "default"
        
        collection_dir.mkdir(parents=True, exist_ok=True)
        
        # Build image file path
        image_filename = f"{image_id}.{extension}"
        image_path = collection_dir / image_filename
        
        # Save image file
        try:
            if isinstance(image_data, bytes):
                # Write bytes directly
                image_path.write_bytes(image_data)
            elif isinstance(image_data, (Path, str)):
                # Copy from source file
                source_path = Path(image_data)
                if not source_path.exists():
                    raise FileNotFoundError(f"Source image not found: {source_path}")
                shutil.copy2(source_path, image_path)
            else:
                raise ValueError(f"Unsupported image_data type: {type(image_data)}")
        except Exception as e:
            raise IOError(f"Failed to save image {image_id}: {e}")
        
        # Store absolute path for reliable retrieval
        # (relative paths would fail with temp directories in tests)
        stored_path = str(image_path.resolve())
        
        # Register in database
        now = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            # Use INSERT OR REPLACE for idempotent operation
            conn.execute("""
                INSERT OR REPLACE INTO image_index 
                (image_id, file_path, collection, doc_hash, page_num, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (image_id, stored_path, collection, doc_hash, page_num, now))
            
            conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to register image {image_id}: {e}")
        finally:
            conn.close()
        
        return stored_path
    
    def register_image(
        self,
        image_id: str,
        file_path: Union[Path, str],
        collection: Optional[str] = None,
        doc_hash: Optional[str] = None,
        page_num: Optional[int] = None
    ) -> str:
        """Register an existing image file in the database index.
        
        Unlike save_image(), this method does NOT copy or move the file.
        It only creates a database entry pointing to the existing file.
        Use this when the image has already been saved by another component
        (e.g., PdfLoader) and you just need to index it.
        
        Args:
            image_id: Unique identifier for the image.
            file_path: Path to the existing image file.
            collection: Optional collection/namespace for organization.
            doc_hash: Optional document hash for traceability.
            page_num: Optional page number if from paginated document.
        
        Returns:
            Absolute path to the registered image.
            
        Raises:
            ValueError: If image_id is empty or invalid.
            FileNotFoundError: If the image file does not exist.
            RuntimeError: If database operation fails.
            
        Example:
            >>> # Register an image that was saved by PdfLoader
            >>> path = storage.register_image(
            ...     image_id="doc123_p1_img0",
            ...     file_path="data/images/tech_docs/abc123/doc123_p1_img0.png",
            ...     collection="tech_docs",
            ...     doc_hash="abc123",
            ...     page_num=1
            ... )
        """
        if not image_id or not image_id.strip():
            raise ValueError("image_id cannot be empty")
        
        # Verify file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")
        
        # Store absolute path for reliable retrieval
        stored_path = str(path.resolve())
        
        # Register in database
        now = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            # Use INSERT OR REPLACE for idempotent operation
            conn.execute("""
                INSERT OR REPLACE INTO image_index 
                (image_id, file_path, collection, doc_hash, page_num, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (image_id, stored_path, collection, doc_hash, page_num, now))
            
            conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to register image {image_id}: {e}")
        finally:
            conn.close()
        
        return stored_path
    
    def get_image_path(self, image_id: str) -> Optional[str]:
        """Get filesystem path for an image by ID.
        
        Args:
            image_id: Unique identifier for the image.
            
        Returns:
            Relative file path if image exists, None otherwise.
            
        Example:
            >>> path = storage.get_image_path("img1")
            >>> if path:
            ...     with open(path, "rb") as f:
            ...         image_data = f.read()
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT file_path FROM image_index WHERE image_id = ?",
                (image_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()
    
    def image_exists(self, image_id: str) -> bool:
        """Check if image exists in database.
        
        Args:
            image_id: Unique identifier for the image.
            
        Returns:
            True if image is registered, False otherwise.
        """
        return self.get_image_path(image_id) is not None
    
    def list_images(
        self,
        collection: Optional[str] = None,
        doc_hash: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """List images with optional filtering.
        
        Args:
            collection: Optional collection filter.
            doc_hash: Optional document hash filter.
            
        Returns:
            List of image metadata dictionaries with keys:
            - image_id: Image identifier
            - file_path: Filesystem path
            - collection: Collection name
            - doc_hash: Document hash
            - page_num: Page number (if applicable)
            - created_at: Creation timestamp
            
        Example:
            >>> # List all images in a collection
            >>> images = storage.list_images(collection="contracts")
            >>> for img in images:
            ...     print(img["image_id"], img["file_path"])
            
            >>> # List images from a specific document
            >>> images = storage.list_images(doc_hash="abc123")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        
        try:
            # Build query with optional filters
            query = "SELECT * FROM image_index WHERE 1=1"
            params = []
            
            if collection is not None:
                query += " AND collection = ?"
                params.append(collection)
            
            if doc_hash is not None:
                query += " AND doc_hash = ?"
                params.append(doc_hash)
            
            query += " ORDER BY created_at ASC"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def delete_image(self, image_id: str, remove_file: bool = True) -> bool:
        """Delete image from database and optionally from filesystem.
        
        Args:
            image_id: Unique identifier for the image.
            remove_file: If True, also delete the image file (default: True).
            
        Returns:
            True if image was deleted, False if not found.
            
        Example:
            >>> # Delete image and file
            >>> deleted = storage.delete_image("img1")
            >>> 
            >>> # Remove from database only, keep file
            >>> deleted = storage.delete_image("img2", remove_file=False)
        """
        # Get file path before deleting from database
        file_path = self.get_image_path(image_id)
        
        if file_path is None:
            return False
        
        # Delete from database
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM image_index WHERE image_id = ?",
                (image_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        except sqlite3.Error:
            return False
        finally:
            conn.close()
        
        # Optionally delete file
        if remove_file and deleted:
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                # Log but don't fail if file deletion fails
                pass
        
        return deleted
    
    def get_collection_stats(self, collection: str) -> Dict[str, any]:
        """Get statistics for a collection.
        
        Args:
            collection: Collection name.
            
        Returns:
            Dictionary with statistics:
            - total_images: Number of images in collection
            - total_size_bytes: Total file size (if files exist)
            
        Example:
            >>> stats = storage.get_collection_stats("contracts")
            >>> print(f"Total images: {stats['total_images']}")
        """
        images = self.list_images(collection=collection)
        
        total_size = 0
        for img in images:
            try:
                file_path = Path(img["file_path"])
                if file_path.exists():
                    total_size += file_path.stat().st_size
            except Exception:
                pass
        
        return {
            "total_images": len(images),
            "total_size_bytes": total_size
        }
