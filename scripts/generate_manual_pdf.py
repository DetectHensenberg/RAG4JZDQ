"""
将使用说明书 Markdown 转换为包含图片的 PDF
利用 Playwright Chromium 的打印功能，确保图片完整嵌入
"""
import base64
import re
from pathlib import Path

MANUAL_PATH = Path(r"C:\Users\51178\.gemini\antigravity\brain\7b867d83-b066-4bdb-a23b-0e4723a72237\用户使用说明书.md")
OUTPUT_PDF = Path(r"C:\Users\51178\.gemini\antigravity\brain\7b867d83-b066-4bdb-a23b-0e4723a72237\九洲RAG平台用户使用说明书.pdf")

# ── 1. 读取 Markdown 内容 ─────────────────────────────────
md_text = MANUAL_PATH.read_text(encoding="utf-8")

# ── 2. 把 Markdown 图片引用替换为 base64 内联 ────────────
IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

def embed_image(match: re.Match) -> str:
    alt = match.group(1)
    path_str = match.group(2).strip()
    img_path = Path(path_str)
    if img_path.exists():
        data = img_path.read_bytes()
        b64 = base64.b64encode(data).decode()
        suffix = img_path.suffix.lower().lstrip('.')
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}.get(suffix, "image/png")
        print(f"  ✓ 嵌入图片: {img_path.name} ({len(data)//1024}KB)")
        return f'![{alt}](data:{mime};base64,{b64})'
    else:
        print(f"  ⚠️  图片未找到: {path_str}")
        return match.group(0)

md_embedded = IMG_PATTERN.sub(embed_image, md_text)

# ── 3. 将 Markdown 转换为 HTML ────────────────────────────
import markdown as md_lib
body_html = md_lib.markdown(
    md_embedded,
    extensions=['tables', 'fenced_code', 'toc', 'nl2br']
)

# ── 4. 构建完整 HTML ──────────────────────────────────────
html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>九洲 RAG 平台用户使用说明书</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Microsoft YaHei", "SimHei", "SimSun", sans-serif;
    font-size: 13px;
    line-height: 1.85;
    color: #2d3748;
    background: white;
    padding: 0 40px;
    max-width: 860px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 24px;
    font-weight: 700;
    color: #1a365d;
    border-bottom: 3px solid #2b6cb0;
    padding-bottom: 10px;
    margin: 32px 0 16px;
    page-break-after: avoid;
  }}
  h2 {{
    font-size: 17px;
    font-weight: 700;
    color: #2b6cb0;
    margin: 28px 0 12px;
    padding-left: 10px;
    border-left: 4px solid #4299e1;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 14px;
    font-weight: 600;
    color: #2d3748;
    margin: 20px 0 10px;
    page-break-after: avoid;
  }}
  h4 {{
    font-size: 13px;
    font-weight: 600;
    color: #4a5568;
    margin: 14px 0 8px;
  }}
  p {{ margin: 8px 0; }}
  img {{
    max-width: 100%;
    height: auto;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    margin: 14px 0;
    display: block;
    page-break-inside: avoid;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 12px;
    page-break-inside: avoid;
  }}
  th {{
    background: #2b6cb0;
    color: white;
    padding: 7px 10px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 6px 10px;
    border-bottom: 1px solid #e2e8f0;
  }}
  tr:nth-child(even) td {{ background: #f7fafc; }}
  blockquote {{
    border-left: 4px solid #4299e1;
    background: #ebf8ff;
    padding: 10px 16px;
    margin: 12px 0;
    border-radius: 0 6px 6px 0;
    color: #2c5282;
    font-size: 12px;
  }}
  code {{
    background: #f0f4f8;
    padding: 2px 5px;
    border-radius: 3px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11.5px;
  }}
  pre {{
    background: #2d3748;
    color: #e2e8f0;
    padding: 14px;
    border-radius: 6px;
    margin: 12px 0;
    font-size: 11.5px;
    line-height: 1.6;
    page-break-inside: avoid;
  }}
  pre code {{ background: none; padding: 0; }}
  hr {{
    border: none;
    border-top: 2px solid #e2e8f0;
    margin: 20px 0;
  }}
  strong {{ color: #1a365d; font-weight: 600; }}
  ul, ol {{ padding-left: 22px; margin: 8px 0; }}
  li {{ margin: 4px 0; }}
  @page {{
    size: A4;
    margin: 18mm 12mm;
  }}
  @media print {{
    body {{ padding: 0 20px; }}
  }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

# ── 5. 用 Playwright 打印为 PDF ───────────────────────────
html_temp = OUTPUT_PDF.parent / "_manual_temp.html"
html_temp.write_text(html_content, encoding="utf-8")
print(f"✓ HTML 已生成 ({html_temp.stat().st_size // 1024} KB)，启动 Playwright 转 PDF...")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.goto(html_temp.as_uri(), wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.pdf(
        path=str(OUTPUT_PDF),
        format="A4",
        print_background=True,
        margin={"top": "18mm", "bottom": "18mm", "left": "12mm", "right": "12mm"},
    )
    browser.close()

html_temp.unlink()
size_kb = OUTPUT_PDF.stat().st_size // 1024
print(f"✅ PDF 已生成: {OUTPUT_PDF}")
print(f"   文件大小: {size_kb} KB")
