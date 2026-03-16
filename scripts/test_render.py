"""Test LibreOffice slide rendering."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.libs.loader.pptx_loader import PptxLoader

loader = PptxLoader(extract_images=True, image_storage_dir="data/images/test_render")
pptx_files = list(Path("tests/fixtures/sample_documents").rglob("*.pptx"))[:1]
if pptx_files:
    p = pptx_files[0]
    print(f"Testing with: {p.name}")
    doc = loader.load(str(p))
    imgs = doc.metadata.get("images", [])
    print(f"Images extracted: {len(imgs)}")
    for img in imgs[:5]:
        ip = Path(img["path"])
        size = ip.stat().st_size if ip.exists() else 0
        w = img["position"]["width"]
        h = img["position"]["height"]
        method = img.get("render_method", "embedded")
        print(f"  {img['id']}: {size:>8}B {w}x{h} [{method}]")
else:
    print("No PPTX files found")
