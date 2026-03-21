"""Watermark - 为证照文件添加水印.

Supports adding watermarks to images (JPG/PNG) and PDFs.
"""

from __future__ import annotations

import logging
import math
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def add_watermark_to_image(
    image_path: str,
    watermark_text: str,
    output_path: Optional[str] = None,
    opacity: int = 60,
    angle: int = -30,
) -> str:
    """为图片添加斜向平铺水印.
    
    Args:
        image_path: 输入图片路径
        watermark_text: 水印文字
        output_path: 输出路径，默认在原文件名后加 _watermarked
        opacity: 水印透明度 (0-255)
        angle: 水印旋转角度
    
    Returns:
        输出文件路径
    """
    from PIL import Image, ImageDraw, ImageFont
    
    input_path = Path(image_path)
    if output_path is None:
        output_path = str(input_path.parent / f"{input_path.stem}_watermarked{input_path.suffix}")
    
    img = Image.open(image_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    
    txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    font_size = max(24, min(img.width, img.height) // 15)
    font = None
    
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    
    if font:
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width = len(watermark_text) * font_size // 2
        text_height = font_size
    
    spacing_x = text_width + 80
    spacing_y = text_height * 4
    
    for y in range(-img.height, img.height * 2, spacing_y):
        for x in range(-img.width, img.width * 2, spacing_x):
            if font:
                draw.text(
                    (x, y),
                    watermark_text,
                    font=font,
                    fill=(128, 128, 128, opacity),
                )
            else:
                draw.text(
                    (x, y),
                    watermark_text,
                    fill=(128, 128, 128, opacity),
                )
    
    txt_layer = txt_layer.rotate(
        angle,
        expand=False,
        center=(img.width // 2, img.height // 2),
        resample=Image.BICUBIC,
    )
    
    result = Image.alpha_composite(img, txt_layer)
    
    if output_path.lower().endswith((".jpg", ".jpeg")):
        result = result.convert("RGB")
    
    result.save(output_path)
    logger.info(f"Watermark added to image: {output_path}")
    return output_path


def add_watermark_to_pdf(
    pdf_path: str,
    watermark_text: str,
    output_path: Optional[str] = None,
    opacity: int = 60,
    angle: int = -30,
) -> str:
    """为 PDF 添加水印.
    
    将 PDF 转为图片，添加水印后再合并为 PDF。
    
    Args:
        pdf_path: 输入 PDF 路径
        watermark_text: 水印文字
        output_path: 输出路径
        opacity: 水印透明度
        angle: 水印旋转角度
    
    Returns:
        输出文件路径
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.error("pdf2image not installed. Run: pip install pdf2image")
        raise ImportError("pdf2image is required for PDF watermarking")
    
    from PIL import Image
    
    input_path = Path(pdf_path)
    if output_path is None:
        output_path = str(input_path.parent / f"{input_path.stem}_watermarked.pdf")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            images = convert_from_path(pdf_path, dpi=150)
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            logger.info("Make sure poppler is installed and in PATH")
            raise
        
        watermarked_images = []
        
        for i, img in enumerate(images):
            page_path = temp_path / f"page_{i}.png"
            img.save(str(page_path), "PNG")
            
            wm_path = temp_path / f"page_{i}_wm.png"
            add_watermark_to_image(
                str(page_path),
                watermark_text,
                str(wm_path),
                opacity,
                angle,
            )
            
            wm_img = Image.open(wm_path).convert("RGB")
            watermarked_images.append(wm_img)
        
        if watermarked_images:
            watermarked_images[0].save(
                output_path,
                save_all=True,
                append_images=watermarked_images[1:] if len(watermarked_images) > 1 else [],
                resolution=150,
            )
        
        logger.info(f"Watermark added to PDF: {output_path}")
        return output_path


def add_watermark(
    file_path: str,
    watermark_text: str,
    output_path: Optional[str] = None,
    opacity: int = 60,
    angle: int = -30,
) -> str:
    """自动检测文件类型并添加水印.
    
    Args:
        file_path: 输入文件路径
        watermark_text: 水印文字
        output_path: 输出路径
        opacity: 水印透明度
        angle: 水印旋转角度
    
    Returns:
        输出文件路径
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix in (".jpg", ".jpeg", ".png", ".bmp", ".tiff"):
        return add_watermark_to_image(file_path, watermark_text, output_path, opacity, angle)
    elif suffix == ".pdf":
        return add_watermark_to_pdf(file_path, watermark_text, output_path, opacity, angle)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def generate_watermark_text(project_code: str) -> str:
    """生成标准水印文字.
    
    Args:
        project_code: 项目编号
    
    Returns:
        水印文字
    """
    return f"仅限于 {project_code} 项目投标使用"
