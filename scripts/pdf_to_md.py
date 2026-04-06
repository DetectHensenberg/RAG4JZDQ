"""快速 PDF 转 Markdown 预处理脚本。

用于将下载的 PDF 文件批量转换为 Markdown 文本，
供后续 RAG 系统高速且低成本地摄取，跳过多模态大模型的昂贵图片分析。
使用了项目中已存在的 PyMuPDF (fitz) 库。
"""

import argparse
import logging
from pathlib import Path

# 使用 PyMuPDF (安装于环境中)
try:
    import fitz 
except ImportError:
    raise ImportError("请先确保安装了 PyMuPDF: pip install PyMuPDF")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def convert_pdf_to_md(pdf_path: Path, out_dir: Path) -> bool:
    """将单个 PDF 转换为纯文本 Markdown 格式。"""
    try:
        doc = fitz.open(pdf_path)
        
        # 预先保留标题格式
        md_text = f"# {pdf_path.stem}\n\n"
        
        for i, page in enumerate(doc):
            # 使用 `text` 模式快速抽取，无视图片，保留文本流
            # 如果想更接近 markdown，在 fitz = 1.24.0 中也可以使用 page.get_text("markdown")
            try:
                # 尝试高级 markdown 抽取（如果 PyMuPDF 版本支持）
                text = page.get_text("markdown")
            except Exception:
                # 回退到普通纯文本
                text = page.get_text("text")

            # 简易清理掉完全空白的页
            if text.strip():
                md_text += f"\n\n<!-- Page {i+1} -->\n\n"
                md_text += text.strip() + "\n"
                
        doc.close()

        # 写入文件
        out_file = out_dir / f"{pdf_path.stem}.md"
        out_file.write_text(md_text, encoding="utf-8")
        logger.info(f"✅ 成功转换: {pdf_path.name} -> {out_file.name}")
        return True
    except Exception as e:
        logger.error(f"❌ 转换失败 {pdf_path.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="高速 PDF 转 Markdown (纯文本提取)，用以加速知识库入库。"
    )
    parser.add_argument(
        "input_dir", 
        type=str, 
        help="包含 PDF 的输入文件夹目录"
    )
    parser.add_argument(
        "--out", 
        type=str, 
        default=None, 
        help="输出文件夹目录 (默认和输入一致)"
    )

    args = parser.parse_args()
    
    input_path = Path(args.input_dir)
    if not input_path.is_dir():
        logger.error(f"输入的不是一个有效的目录: {args.input_dir}")
        return

    out_path = Path(args.out) if args.out else input_path
    out_path.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_path.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"目录 {input_path} 下未找到任何 PDF 文件。")
        return

    logger.info(f"开始批量转换 {len(pdf_files)} 个 PDF 文件到 Markdown...")
    
    success_count = 0
    for pdf in pdf_files:
        if convert_pdf_to_md(pdf, out_path):
            success_count += 1
            
    logger.info(f"\n🎉 转换完成: 成功 {success_count}/{len(pdf_files)}")

if __name__ == "__main__":
    main()
