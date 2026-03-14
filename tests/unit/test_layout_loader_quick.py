"""Quick smoke test for LayoutPdfLoader."""
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.libs.loader.layout_pdf_loader import LayoutPdfLoader


def main() -> None:
    # Find a sample PDF in the project
    data_dir = Path(__file__).resolve().parents[2] / "data" / "documents"
    pdfs = list(data_dir.glob("*.pdf")) if data_dir.exists() else []

    if not pdfs:
        print("No PDF files found in data/documents/, testing import only")
        loader = LayoutPdfLoader(extract_images=False)
        print(f"LayoutPdfLoader created: {loader}")
        print("OCR engine resolved:", loader._resolve_ocr_engine())
        return

    pdf_path = pdfs[0]
    print(f"Testing with: {pdf_path.name}")

    loader = LayoutPdfLoader(extract_images=False)
    doc = loader.load(pdf_path)

    print(f"Doc ID: {doc.id}")
    print(f"Text length: {len(doc.text)} chars")
    print(f"Parser: {doc.metadata.get('parser')}")
    print(f"Multi-column pages: {doc.metadata.get('multi_column_pages', [])}")
    print(f"Scanned pages: {doc.metadata.get('scanned_pages', [])}")
    print(f"Preview: {doc.text[:200]}...")


if __name__ == "__main__":
    main()
