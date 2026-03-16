"""Unit tests for PdfLoader full-page image rendering.

Covers the rewritten ``_extract_and_process_images`` method that uses
``page.get_pixmap()`` (full-page render) instead of the old
``page.get_images()`` (xref fragment extraction).

Key verifications:
1. One image per visual page (not dozens of xref fragments)
2. Text-only pages are skipped (MIN_IMAGES_FOR_RENDER)
3. Dynamic DPI reduction when MAX_RENDER_DIM would be exceeded
4. Graceful degradation when PyMuPDF unavailable or page render fails
5. Image metadata structure and render_method tag
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock objects for fitz (PyMuPDF)
# ---------------------------------------------------------------------------

class MockPixmap:
    """Simulates fitz.Pixmap returned by page.get_pixmap()."""

    def __init__(self, width: int = 1241, height: int = 1754) -> None:
        self.width = width
        self.height = height
        self._saved_path: str | None = None

    def save(self, path: str) -> None:
        self._saved_path = path
        # Write a minimal file so Path.exists() works
        Path(path).write_bytes(b"FAKE_PNG_DATA")


class MockRect:
    """Simulates fitz.Rect (page.rect)."""

    def __init__(self, width: float = 595.0, height: float = 842.0) -> None:
        self.width = width
        self.height = height


class MockPage:
    """Simulates a fitz.Page with configurable image count."""

    def __init__(
        self,
        image_count: int = 1,
        rect_w: float = 595.0,
        rect_h: float = 842.0,
        pixmap_w: int = 1241,
        pixmap_h: int = 1754,
    ) -> None:
        self._image_count = image_count
        self.rect = MockRect(rect_w, rect_h)
        self._pixmap = MockPixmap(pixmap_w, pixmap_h)

    def get_images(self, full: bool = True) -> list:
        return [("xref",)] * self._image_count

    def get_pixmap(self, matrix: Any = None, alpha: bool = False) -> MockPixmap:
        return self._pixmap


class MockDocument:
    """Simulates fitz.Document opened via fitz.open()."""

    def __init__(self, pages: List[MockPage] | None = None) -> None:
        self._pages = pages or []

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, idx: int) -> MockPage:
        return self._pages[idx]

    def close(self) -> None:
        pass


class MockMatrix:
    """Simulates fitz.Matrix."""

    def __init__(self, sx: float, sy: float) -> None:
        self.sx = sx
        self.sy = sy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_image_dir():
    """Create and clean up a temporary image directory."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def loader(tmp_image_dir: Path):
    """Create a PdfLoader with mocked MarkItDown and image storage."""
    with patch("src.libs.loader.pdf_loader.MARKITDOWN_AVAILABLE", True), \
         patch("src.libs.loader.pdf_loader.MarkItDown"):
        from src.libs.loader.pdf_loader import PdfLoader
        return PdfLoader(extract_images=True, image_storage_dir=tmp_image_dir)


# ===========================================================================
# Core page-render behaviour
# ===========================================================================

class TestPageRender:
    """Full-page rendering via get_pixmap()."""

    def test_one_image_per_visual_page(self, loader: object, tmp_image_dir: Path) -> None:
        """Pages with images produce exactly 1 rendered image each."""
        pages = [
            MockPage(image_count=5),   # 5 xrefs → still 1 render
            MockPage(image_count=12),  # 12 xrefs → still 1 render
        ]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            text, images = loader._extract_and_process_images(
                Path("test.pdf"), "base text", "abc12345"
            )

        assert len(images) == 2
        assert all(img["render_method"] == "page_pixmap" for img in images)

    def test_text_only_pages_skipped(self, loader: object, tmp_image_dir: Path) -> None:
        """Pages with 0 images are not rendered."""
        pages = [
            MockPage(image_count=0),  # pure text → skip
            MockPage(image_count=3),  # has images → render
            MockPage(image_count=0),  # pure text → skip
        ]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            text, images = loader._extract_and_process_images(
                Path("test.pdf"), "base text", "abc12345"
            )

        assert len(images) == 1
        assert images[0]["page"] == 2  # only page 2 rendered

    def test_placeholder_inserted(self, loader: object, tmp_image_dir: Path) -> None:
        """Each rendered page inserts an [IMAGE: id] placeholder in text."""
        pages = [MockPage(image_count=1)]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            text, images = loader._extract_and_process_images(
                Path("test.pdf"), "original", "abc12345"
            )

        assert "[IMAGE:" in text
        assert images[0]["id"] in text


# ===========================================================================
# Image metadata structure
# ===========================================================================

class TestImageMetadata:
    """Rendered images carry correct metadata."""

    def test_metadata_fields(self, loader: object, tmp_image_dir: Path) -> None:
        pages = [MockPage(image_count=2, pixmap_w=1241, pixmap_h=1754)]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            _, images = loader._extract_and_process_images(
                Path("test.pdf"), "", "abc12345"
            )

        img = images[0]
        assert img["page"] == 1
        assert img["position"]["width"] == 1241
        assert img["position"]["height"] == 1754
        assert img["position"]["index"] == 1
        assert img["render_method"] == "page_pixmap"
        assert "id" in img
        assert "path" in img

    def test_image_id_format(self, loader: object, tmp_image_dir: Path) -> None:
        """Image ID format: {hash_prefix}_{page}_{sequence}."""
        pages = [MockPage(image_count=1)]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            _, images = loader._extract_and_process_images(
                Path("test.pdf"), "", "abc12345deadbeef"
            )

        assert images[0]["id"] == "abc12345_1_1"


# ===========================================================================
# Dynamic DPI cap (MAX_RENDER_DIM)
# ===========================================================================

class TestDynamicDPI:
    """DPI is reduced for large pages to stay within MAX_RENDER_DIM."""

    def test_large_page_dpi_reduced(self, loader: object, tmp_image_dir: Path) -> None:
        """Page wider than MAX_RENDER_DIM/scale gets a smaller matrix."""
        # A very wide page: 2000pt → at 150 DPI = 2000 * (150/72) ≈ 4167px
        # Should be capped to ≤ 2000px
        pages = [MockPage(image_count=1, rect_w=2000.0, rect_h=1000.0)]
        mock_doc = MockDocument(pages)

        captured_matrices: list = []

        class CapturingMatrix:
            def __init__(self, sx: float, sy: float) -> None:
                captured_matrices.append((sx, sy))
                self.sx = sx
                self.sy = sy

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = CapturingMatrix

            loader._extract_and_process_images(
                Path("test.pdf"), "", "abc12345"
            )

        # The matrix scale should be reduced from base_scale (150/72≈2.08)
        sx, sy = captured_matrices[-1]
        assert sx < 150 / 72  # less than base scale
        assert sx == pytest.approx(sy)  # uniform scaling

    def test_normal_page_uses_base_dpi(self, loader: object, tmp_image_dir: Path) -> None:
        """Standard A4 page (595x842pt) at 150 DPI is within 2000px."""
        pages = [MockPage(image_count=1, rect_w=595.0, rect_h=842.0)]
        mock_doc = MockDocument(pages)

        captured_matrices: list = []

        class CapturingMatrix:
            def __init__(self, sx: float, sy: float) -> None:
                captured_matrices.append((sx, sy))

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = CapturingMatrix

            loader._extract_and_process_images(
                Path("test.pdf"), "", "abc12345"
            )

        sx, _ = captured_matrices[-1]
        assert sx == pytest.approx(150 / 72, rel=1e-2)


# ===========================================================================
# Graceful degradation
# ===========================================================================

class TestGracefulDegradation:
    """Loader degrades gracefully on errors."""

    def test_extract_disabled(self, tmp_image_dir: Path) -> None:
        """extract_images=False returns original text and no images."""
        with patch("src.libs.loader.pdf_loader.MARKITDOWN_AVAILABLE", True), \
             patch("src.libs.loader.pdf_loader.MarkItDown"):
            from src.libs.loader.pdf_loader import PdfLoader
            loader = PdfLoader(extract_images=False, image_storage_dir=tmp_image_dir)

        text, images = loader._extract_and_process_images(Path("x.pdf"), "hi", "h")
        assert text == "hi"
        assert images == []

    def test_pymupdf_unavailable(self, loader: object) -> None:
        """When PyMuPDF is not installed, returns text unchanged."""
        with patch("src.libs.loader.pdf_loader.PYMUPDF_AVAILABLE", False):
            text, images = loader._extract_and_process_images(
                Path("x.pdf"), "hi", "h"
            )
        assert text == "hi"
        assert images == []

    def test_fitz_open_error(self, loader: object) -> None:
        """If fitz.open() fails, returns original text."""
        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.side_effect = RuntimeError("corrupt PDF")

            text, images = loader._extract_and_process_images(
                Path("test.pdf"), "base", "h"
            )

        assert text == "base"
        assert images == []

    def test_single_page_render_error(self, loader: object, tmp_image_dir: Path) -> None:
        """If one page fails to render, others still succeed."""

        class FailingPage(MockPage):
            def get_pixmap(self, **kw: Any) -> None:
                raise RuntimeError("render failed")

        pages = [
            FailingPage(image_count=1),
            MockPage(image_count=1),
        ]
        mock_doc = MockDocument(pages)

        with patch("src.libs.loader.pdf_loader.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = MockMatrix

            _, images = loader._extract_and_process_images(
                Path("test.pdf"), "", "abc12345"
            )

        # Only the second page succeeds
        assert len(images) == 1
        assert images[0]["page"] == 2
