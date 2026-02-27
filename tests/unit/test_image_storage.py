"""Unit tests for ImageStorage module."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ingestion.storage.image_storage import ImageStorage


@pytest.fixture
def temp_storage():
    """Create ImageStorage with temporary directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "image_index.db")
        images_root = str(Path(tmpdir) / "images")
        storage = ImageStorage(db_path=db_path, images_root=images_root)
        yield storage
        storage.close()


@pytest.fixture
def sample_image_data():
    """Generate sample PNG-like binary data."""
    # Simple PNG header (not a valid PNG, but sufficient for testing)
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * 100


class TestImageStorageInitialization:
    """Test ImageStorage initialization and setup."""
    
    def test_creates_database_file(self):
        """Database file should be created on initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            storage = ImageStorage(db_path=db_path)
            
            assert Path(db_path).exists()
            storage.close()
    
    def test_creates_images_directory(self):
        """Images root directory should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            images_root = str(Path(tmpdir) / "images")
            storage = ImageStorage(images_root=images_root)
            
            assert Path(images_root).exists()
            storage.close()
    
    def test_creates_nested_directories(self):
        """Should create nested parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "nested" / "path" / "db.db")
            storage = ImageStorage(db_path=db_path)
            
            assert Path(db_path).exists()
            storage.close()
    
    def test_database_schema_created(self, temp_storage):
        """Database should have correct schema."""
        conn = sqlite3.connect(temp_storage.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='image_index'"
        )
        assert cursor.fetchone() is not None
        conn.close()
    
    def test_database_indexes_created(self, temp_storage):
        """Database should have collection and doc_hash indexes."""
        conn = sqlite3.connect(temp_storage.db_path)
        
        # Check for idx_collection
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_collection'"
        )
        assert cursor.fetchone() is not None
        
        # Check for idx_doc_hash
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_doc_hash'"
        )
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_wal_mode_enabled(self, temp_storage):
        """Database should use WAL mode for concurrency."""
        conn = sqlite3.connect(temp_storage.db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()
        
        assert mode.lower() == "wal"


class TestSaveImage:
    """Test image saving functionality."""
    
    def test_save_image_from_bytes(self, temp_storage, sample_image_data):
        """Should save image from bytes data."""
        path = temp_storage.save_image(
            image_id="test_img_1",
            image_data=sample_image_data,
            collection="test_collection"
        )
        
        assert path is not None
        assert Path(path).exists()
        assert Path(path).read_bytes() == sample_image_data
    
    def test_save_image_from_file(self, temp_storage):
        """Should save image by copying from source file."""
        # Create source file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(b"test_image_data")
            source_path = tmp.name
        
        try:
            path = temp_storage.save_image(
                image_id="test_img_2",
                image_data=source_path,
                collection="test_collection"
            )
            
            assert path is not None
            assert Path(path).exists()
            assert Path(path).read_bytes() == b"test_image_data"
        finally:
            Path(source_path).unlink(missing_ok=True)
    
    def test_save_image_creates_collection_directory(self, temp_storage, sample_image_data):
        """Should create collection directory if it doesn't exist."""
        path = temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data,
            collection="new_collection"
        )
        
        assert "new_collection" in path
        collection_dir = Path(temp_storage.images_root) / "new_collection"
        assert collection_dir.exists()
    
    def test_save_image_with_custom_extension(self, temp_storage, sample_image_data):
        """Should respect custom file extension."""
        path = temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data,
            collection="test",
            extension="jpg"
        )
        
        assert path.endswith(".jpg")
    
    def test_save_image_registers_in_database(self, temp_storage, sample_image_data):
        """Should register image metadata in database."""
        temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data,
            collection="test",
            doc_hash="abc123",
            page_num=5
        )
        
        conn = sqlite3.connect(temp_storage.db_path)
        cursor = conn.execute(
            "SELECT image_id, collection, doc_hash, page_num FROM image_index WHERE image_id = ?",
            ("img1",)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == "img1"
        assert row[1] == "test"
        assert row[2] == "abc123"
        assert row[3] == 5
    
    def test_save_image_idempotent(self, temp_storage, sample_image_data):
        """Re-saving same image_id should update, not duplicate."""
        # Save first time
        temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data,
            collection="coll1"
        )
        
        # Save again with different collection
        new_data = b"updated_data"
        temp_storage.save_image(
            image_id="img1",
            image_data=new_data,
            collection="coll2"
        )
        
        # Should have only one record
        conn = sqlite3.connect(temp_storage.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM image_index WHERE image_id = ?", ("img1",))
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 1
        
        # File should be updated
        path = temp_storage.get_image_path("img1")
        assert Path(path).read_bytes() == new_data
    
    def test_save_image_empty_id_raises_error(self, temp_storage, sample_image_data):
        """Empty image_id should raise ValueError."""
        with pytest.raises(ValueError, match="image_id cannot be empty"):
            temp_storage.save_image("", sample_image_data)
        
        with pytest.raises(ValueError, match="image_id cannot be empty"):
            temp_storage.save_image("   ", sample_image_data)
    
    def test_save_image_missing_source_file_raises_error(self, temp_storage):
        """Non-existent source file should raise error."""
        with pytest.raises(IOError, match="Failed to save image"):
            temp_storage.save_image(
                image_id="img1",
                image_data="/nonexistent/path.png"
            )
    
    def test_save_image_uses_default_collection(self, temp_storage, sample_image_data):
        """Should use 'default' collection when none specified."""
        path = temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data
        )
        
        assert "default" in path


class TestGetImagePath:
    """Test image path retrieval."""
    
    def test_get_existing_image_path(self, temp_storage, sample_image_data):
        """Should return path for existing image."""
        original_path = temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data
        )
        
        retrieved_path = temp_storage.get_image_path("img1")
        
        assert retrieved_path == original_path
    
    def test_get_nonexistent_image_path_returns_none(self, temp_storage):
        """Should return None for non-existent image."""
        path = temp_storage.get_image_path("nonexistent_id")
        
        assert path is None


class TestImageExists:
    """Test image existence checking."""
    
    def test_image_exists_returns_true(self, temp_storage, sample_image_data):
        """Should return True for existing image."""
        temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data
        )
        
        assert temp_storage.image_exists("img1") is True
    
    def test_image_exists_returns_false(self, temp_storage):
        """Should return False for non-existent image."""
        assert temp_storage.image_exists("nonexistent") is False


class TestListImages:
    """Test image listing functionality."""
    
    def test_list_all_images(self, temp_storage, sample_image_data):
        """Should list all images when no filter."""
        temp_storage.save_image("img1", sample_image_data, "coll1")
        temp_storage.save_image("img2", sample_image_data, "coll2")
        temp_storage.save_image("img3", sample_image_data, "coll1")
        
        images = temp_storage.list_images()
        
        assert len(images) == 3
        image_ids = {img["image_id"] for img in images}
        assert image_ids == {"img1", "img2", "img3"}
    
    def test_list_images_by_collection(self, temp_storage, sample_image_data):
        """Should filter images by collection."""
        temp_storage.save_image("img1", sample_image_data, "coll1")
        temp_storage.save_image("img2", sample_image_data, "coll2")
        temp_storage.save_image("img3", sample_image_data, "coll1")
        
        images = temp_storage.list_images(collection="coll1")
        
        assert len(images) == 2
        image_ids = {img["image_id"] for img in images}
        assert image_ids == {"img1", "img3"}
    
    def test_list_images_by_doc_hash(self, temp_storage, sample_image_data):
        """Should filter images by document hash."""
        temp_storage.save_image("img1", sample_image_data, "coll1", doc_hash="hash1")
        temp_storage.save_image("img2", sample_image_data, "coll1", doc_hash="hash2")
        temp_storage.save_image("img3", sample_image_data, "coll1", doc_hash="hash1")
        
        images = temp_storage.list_images(doc_hash="hash1")
        
        assert len(images) == 2
        image_ids = {img["image_id"] for img in images}
        assert image_ids == {"img1", "img3"}
    
    def test_list_images_with_both_filters(self, temp_storage, sample_image_data):
        """Should combine collection and doc_hash filters."""
        temp_storage.save_image("img1", sample_image_data, "coll1", doc_hash="hash1")
        temp_storage.save_image("img2", sample_image_data, "coll2", doc_hash="hash1")
        temp_storage.save_image("img3", sample_image_data, "coll1", doc_hash="hash2")
        
        images = temp_storage.list_images(collection="coll1", doc_hash="hash1")
        
        assert len(images) == 1
        assert images[0]["image_id"] == "img1"
    
    def test_list_images_returns_complete_metadata(self, temp_storage, sample_image_data):
        """Should return complete metadata for each image."""
        temp_storage.save_image(
            image_id="img1",
            image_data=sample_image_data,
            collection="test",
            doc_hash="abc123",
            page_num=5
        )
        
        images = temp_storage.list_images()
        
        assert len(images) == 1
        img = images[0]
        assert img["image_id"] == "img1"
        assert img["collection"] == "test"
        assert img["doc_hash"] == "abc123"
        assert img["page_num"] == 5
        assert "file_path" in img
        assert "created_at" in img
    
    def test_list_images_empty_when_no_matches(self, temp_storage):
        """Should return empty list when no images match."""
        images = temp_storage.list_images(collection="nonexistent")
        
        assert images == []


class TestDeleteImage:
    """Test image deletion."""
    
    def test_delete_image_removes_from_database(self, temp_storage, sample_image_data):
        """Should remove image from database."""
        temp_storage.save_image("img1", sample_image_data)
        
        deleted = temp_storage.delete_image("img1")
        
        assert deleted is True
        assert temp_storage.image_exists("img1") is False
    
    def test_delete_image_removes_file(self, temp_storage, sample_image_data):
        """Should delete image file by default."""
        path = temp_storage.save_image("img1", sample_image_data)
        
        temp_storage.delete_image("img1", remove_file=True)
        
        assert not Path(path).exists()
    
    def test_delete_image_keeps_file_when_requested(self, temp_storage, sample_image_data):
        """Should keep file when remove_file=False."""
        path = temp_storage.save_image("img1", sample_image_data)
        
        temp_storage.delete_image("img1", remove_file=False)
        
        assert Path(path).exists()  # File still exists
        assert temp_storage.image_exists("img1") is False  # But not in database
    
    def test_delete_nonexistent_image_returns_false(self, temp_storage):
        """Should return False when deleting non-existent image."""
        deleted = temp_storage.delete_image("nonexistent")
        
        assert deleted is False


class TestGetCollectionStats:
    """Test collection statistics."""
    
    def test_get_collection_stats_counts_images(self, temp_storage, sample_image_data):
        """Should count total images in collection."""
        temp_storage.save_image("img1", sample_image_data, "coll1")
        temp_storage.save_image("img2", sample_image_data, "coll1")
        temp_storage.save_image("img3", sample_image_data, "coll2")
        
        stats = temp_storage.get_collection_stats("coll1")
        
        assert stats["total_images"] == 2
    
    def test_get_collection_stats_calculates_size(self, temp_storage, sample_image_data):
        """Should calculate total size of images."""
        temp_storage.save_image("img1", sample_image_data, "coll1")
        temp_storage.save_image("img2", sample_image_data, "coll1")
        
        stats = temp_storage.get_collection_stats("coll1")
        
        # Should be approximately 2 * len(sample_image_data)
        assert stats["total_size_bytes"] > 0
        assert stats["total_size_bytes"] == 2 * len(sample_image_data)
    
    def test_get_collection_stats_empty_collection(self, temp_storage):
        """Should handle empty collection."""
        stats = temp_storage.get_collection_stats("empty")
        
        assert stats["total_images"] == 0
        assert stats["total_size_bytes"] == 0


class TestConcurrency:
    """Test concurrent access patterns."""
    
    def test_multiple_connections_can_read(self, temp_storage, sample_image_data):
        """WAL mode should allow concurrent reads."""
        temp_storage.save_image("img1", sample_image_data)
        
        # Simulate multiple readers
        path1 = temp_storage.get_image_path("img1")
        path2 = temp_storage.get_image_path("img1")
        
        assert path1 == path2
    
    def test_can_write_while_reading(self, temp_storage, sample_image_data):
        """WAL mode should allow writes during reads."""
        temp_storage.save_image("img1", sample_image_data)
        
        # Read existing
        path1 = temp_storage.get_image_path("img1")
        
        # Write new
        temp_storage.save_image("img2", sample_image_data)
        
        # Read should still work
        path2 = temp_storage.get_image_path("img2")
        
        assert path1 is not None
        assert path2 is not None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_special_characters_in_image_id(self, temp_storage, sample_image_data):
        """Should handle special characters in image_id."""
        # Note: Some characters might be problematic for filesystems
        # Using safe special characters
        image_id = "doc_123-page_5.img_0"
        
        path = temp_storage.save_image(image_id, sample_image_data)
        
        assert temp_storage.image_exists(image_id)
        retrieved_path = temp_storage.get_image_path(image_id)
        assert retrieved_path == path
    
    def test_unicode_in_collection_name(self, temp_storage, sample_image_data):
        """Should handle Unicode in collection names."""
        collection = "文档集合"
        
        path = temp_storage.save_image(
            "img1",
            sample_image_data,
            collection=collection
        )
        
        assert collection in path
        images = temp_storage.list_images(collection=collection)
        assert len(images) == 1
    
    def test_close_and_reopen(self, sample_image_data):
        """Should persist data across close/reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            images_root = str(Path(tmpdir) / "images")
            
            # Create and save
            storage1 = ImageStorage(db_path=db_path, images_root=images_root)
            storage1.save_image("img1", sample_image_data, "coll1")
            storage1.close()
            
            # Reopen and verify
            storage2 = ImageStorage(db_path=db_path, images_root=images_root)
            assert storage2.image_exists("img1")
            images = storage2.list_images()
            assert len(images) == 1
            storage2.close()
