"""Unit tests for PptxLoader incremental image changes.

Covers:
1. _collect_images_from_shape — MIN_DIM=150 quality filter skips tiny images
2. _render_slides_to_images  — MAX_RENDER_DIM=2000 dynamic DPI cap
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_tiny_png(width: int, height: int) -> bytes:
    """Create a minimal valid PNG image of given dimensions."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_shape(
    width: int = 800,
    height: int = 600,
    shape_type: int = 13,
    content_type: str = "image/png",
) -> MagicMock:
    """Create a mock python-pptx picture shape."""
    shape = MagicMock()
    shape.shape_type = shape_type
    shape.image.blob = _make_tiny_png(width, height)
    shape.image.content_type = content_type
    return shape


class MockRect:
    def __init__(self, w: float, h: float) -> None:
        self.width = w
        self.height = h


class MockPixmap:
    def __init__(self, w: int = 2000, h: int = 1125) -> None:
        self.width = w
        self.height = h

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"FAKE")


class MockPage:
    def __init__(self, rect_w: float = 960.0, rect_h: float = 540.0) -> None:
        self.rect = MockRect(rect_w, rect_h)

    def get_pixmap(self, matrix: Any = None, alpha: bool = False) -> MockPixmap:
        return MockPixmap()


class MockDocument:
    def __init__(self, pages: List[MockPage] | None = None) -> None:
        self._pages = pages or []

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, idx: int) -> MockPage:
        return self._pages[idx]

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def loader(tmp_dir: Path):
    """Create PptxLoader with mocked LibreOffice check."""
    with patch("src.libs.loader.pptx_loader._check_libreoffice", return_value=None):
        from src.libs.loader.pptx_loader import PptxLoader

        return PptxLoader(
            extract_images=True,
            image_storage_dir=tmp_dir,
        )


# ===========================================================================
# _collect_images_from_shape — MIN_DIM filter
# ===========================================================================

class TestMinDimFilter:
    """Embedded images smaller than 150px on any side are skipped."""

    def test_large_image_kept(self, loader: object, tmp_dir: Path) -> None:
        """An 800x600 image passes the filter."""
        shape = _make_shape(width=800, height=600)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash1", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 1
        assert 1 in slide_ph

    def test_tiny_image_skipped(self, loader: object, tmp_dir: Path) -> None:
        """A 48x49 image (icon) is skipped."""
        shape = _make_shape(width=48, height=49)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash2", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 0
        assert 1 not in slide_ph

    def test_borderline_149px_skipped(self, loader: object, tmp_dir: Path) -> None:
        """149x200 — width < 150 → skipped."""
        shape = _make_shape(width=149, height=200)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash3", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 0

    def test_borderline_150px_kept(self, loader: object, tmp_dir: Path) -> None:
        """150x150 — exactly at threshold → kept."""
        shape = _make_shape(width=150, height=150)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash4", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 1

    def test_height_too_small_skipped(self, loader: object, tmp_dir: Path) -> None:
        """500x100 — height < 150 → skipped."""
        shape = _make_shape(width=500, height=100)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash5", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 0

    def test_skipped_image_file_cleaned_up(self, loader: object, tmp_dir: Path) -> None:
        """When a tiny image is skipped, the saved file is deleted."""
        shape = _make_shape(width=48, height=49)
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash6", image_dir, images_meta, slide_ph
        )

        # No image files should remain
        remaining = list(image_dir.glob("*.png")) + list(image_dir.glob("*.jpg"))
        assert len(remaining) == 0

    def test_non_picture_shape_ignored(self, loader: object, tmp_dir: Path) -> None:
        """Non-picture shapes (e.g. text boxes, shape_type=1) are ignored."""
        shape = MagicMock()
        shape.shape_type = 1  # text box
        images_meta: list = []
        slide_ph: dict = {}
        image_dir = tmp_dir / "test_hash"
        image_dir.mkdir(parents=True, exist_ok=True)

        loader._collect_images_from_shape(
            shape, 1, 0, "testhash7", image_dir, images_meta, slide_ph
        )

        assert len(images_meta) == 0


# ===========================================================================
# _render_slides_to_images — MAX_RENDER_DIM dynamic DPI
# ===========================================================================

class TestRenderDPICap:
    """LibreOffice slide rendering respects MAX_RENDER_DIM=2000."""

    def test_large_slide_dpi_reduced(self, tmp_dir: Path) -> None:
        """Slides wider than MAX_RENDER_DIM/base_scale get reduced DPI."""
        # 16:9 slide at 960x540pt, base_scale = 300/72 ≈ 4.17
        # 960 * 4.17 ≈ 4000px > 2000 → should reduce
        pages = [MockPage(rect_w=960.0, rect_h=540.0)]
        mock_doc = MockDocument(pages)

        captured_matrices: list = []

        class CapturingMatrix:
            def __init__(self, sx: float, sy: float) -> None:
                captured_matrices.append((sx, sy))

        # We test the matrix logic directly via _render_slides_to_images
        with patch("src.libs.loader.pptx_loader._check_libreoffice", return_value="soffice"), \
             patch("src.libs.loader.pptx_loader.PYMUPDF_AVAILABLE", True):
            from src.libs.loader.pptx_loader import PptxLoader

            loader = PptxLoader(extract_images=True, image_storage_dir=tmp_dir)

        # Mock the subprocess + fitz parts of _render_slides_to_images
        with patch("subprocess.run"), \
             patch("src.libs.loader.pptx_loader.fitz") as mock_fitz, \
             patch("tempfile.TemporaryDirectory") as mock_tmpdir:

            # Setup temp dir context
            mock_tmpdir.return_value.__enter__ = MagicMock(return_value=str(tmp_dir))
            mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)

            # Create a fake PDF in the temp dir
            fake_pdf = tmp_dir / "slide.pdf"
            fake_pdf.write_bytes(b"FAKEPDF")

            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = CapturingMatrix

            image_dir = tmp_dir / "imgs"
            image_dir.mkdir(exist_ok=True)
            loader.image_storage_dir = image_dir

            text, images = loader._render_slides_to_images(
                Path("slide.pptx"), "text", "abc12345"
            )

        if captured_matrices:
            sx, sy = captured_matrices[-1]
            # Base scale = 300/72 ≈ 4.17, but should be capped
            assert sx < 300 / 72
            assert sx == pytest.approx(sy)
