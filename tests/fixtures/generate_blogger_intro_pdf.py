"""
Generate a PDF for blogger introduction and notes overview.
Contains personal introduction, notes description, and sample images.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, Image, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
import io
from pathlib import Path
import os


def register_chinese_font():
    """Register a Chinese font for PDF generation."""
    # Try to find a Chinese font on the system
    font_paths = [
        # Windows fonts
        "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
        "C:/Windows/Fonts/simsun.ttc",  # 宋体
        "C:/Windows/Fonts/simhei.ttf",  # 黑体
        # Mac fonts
        "/System/Library/Fonts/PingFang.ttc",
        # Linux fonts
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                return 'ChineseFont'
            except:
                continue
    
    # Fallback to Helvetica if no Chinese font found
    return 'Helvetica'


def get_image_paths():
    """Get paths for the external images."""
    script_dir = Path(__file__).parent
    sample_docs_dir = script_dir / "sample_documents"
    
    return {
        'design_thinking': sample_docs_dir / "design_thinking.png",
        'project_intro': sample_docs_dir / "project_intro.png"
    }


def generate_blogger_intro_pdf(output_path):
    """Generate a PDF document with blogger introduction."""
    
    # Register Chinese font
    chinese_font = register_chinese_font()
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=30,
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles with Chinese font
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=chinese_font,
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=chinese_font,
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=20,
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontName=chinese_font,
        fontSize=14,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=10,
        spaceBefore=12,
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontName=chinese_font,
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
        leading=18
    )
    
    list_style = ParagraphStyle(
        'ListStyle',
        parent=styles['BodyText'],
        fontName=chinese_font,
        fontSize=11,
        leftIndent=20,
        spaceAfter=8,
        leading=16
    )
    
    # ==================== 封面页 ====================
    elements.append(Spacer(1, 1.5*inch))
    elements.append(Paragraph("不转到大模型不改名", title_style))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("博主介绍 & 笔记说明", heading_style))
    elements.append(Spacer(1, 0.5*inch))
    
    # 封面信息表格
    cover_data = [
        ['作者:', '不转到大模型不改名'],
        ['平台:', '小红书 + B站'],
        ['方向:', '大模型开发'],
        ['文档版本:', '2026年2月'],
    ]
    cover_table = Table(cover_data, colWidths=[1.5*inch, 3.5*inch])
    cover_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), chinese_font),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
    ]))
    elements.append(cover_table)
    elements.append(PageBreak())
    
    # ==================== 第一部分：个人介绍 ====================
    elements.append(Paragraph("1. 个人介绍", heading_style))
    
    intro_text = """
    小红书 + B站博主，双985学历，校招毕业后进入国内一线大厂，目前就职于外企一线大厂。主要开发语言是C++。
    """
    elements.append(Paragraph(intro_text.strip(), body_style))
    
    achievement_text = """
    通过自学，从0AI基础出发，自学掌握了Agent、RAG等技术，成功拿到了6个大模型的offer，其中包括：
    """
    elements.append(Paragraph(achievement_text.strip(), body_style))
    
    # Offer列表
    offers = [
        "京东（算法岗）",
        "千问C端",
        "网龙",
        "SAP（世界500强外企）",
        "平安证券",
        "华林证券"
    ]
    for offer in offers:
        elements.append(Paragraph(f"• {offer}", list_style))
    
    elements.append(Spacer(1, 0.3*inch))
    
    # ==================== 第二部分：笔记介绍 ====================
    elements.append(Paragraph("2. 笔记介绍", heading_style))
    
    notes_intro = """
    不转到大模型不改名在自学的过程中，把所有自学过程中遇到的问题，总结在了文档中。目前文档已经有12万字。
    """
    elements.append(Paragraph(notes_intro.strip(), body_style))
    
    design_concept = """
    文档设计的理念是：针对于0基础学员，以应用方向为主，算法方向为辅助，帮助0基础的同学快速转行到大模型。
    笔记设计的最大的理念是：<b>突出重点，讲清楚每个知识点为什么要考，怎么复习，要复习多深入。</b>
    """
    elements.append(Paragraph(design_concept.strip(), body_style))
    
    elements.append(Spacer(1, 0.2*inch))
    
    # ==================== 笔记内容详解 ====================
    elements.append(Paragraph("笔记内容包括：", subheading_style))
    
    # 2.1 面试真题
    elements.append(Paragraph("<b>2.1 面试真题（20+公司）</b>", body_style))
    interview_content = """
    包含完整的岗位JD（帮助大家有针对性复习）、问题解析、参考资料、个人反思、视频讲解。
    """
    elements.append(Paragraph(interview_content.strip(), list_style))
    
    # 2.2 八股内容
    elements.append(Paragraph("<b>2.2 八股内容</b>", body_style))
    bagu_content = """
    涵盖Agent、RAG、模型基础、微调、推理部署等内容。最重要的思想是完全根据面试内容，
    针对性总结八股——面试常考的就总结的深入，不常考的就总结的少，突出重点和思路，
    不想让转行的人陷入"感觉什么都要学，不知道学多深"的困境。
    """
    elements.append(Paragraph(bagu_content.strip(), list_style))
    
    # 2.3 项目
    elements.append(Paragraph("<b>2.3 自研RAG项目</b>", body_style))
    project_content = """
    自研了一个RAG项目，包含完整的项目技术开发文档和代码。项目不光总结该项目常见的面试问题和解析、
    简历如何写、项目设计的代码和技术详解。更重要的是总结讲解自己写项目的思路，不光提供项目，
    更重要提供写项目的思路，学会以后也能轻松扩展。同样该内容包含视频讲解。
    """
    elements.append(Paragraph(project_content.strip(), list_style))
    
    # 2.4 参考资料
    elements.append(Paragraph("<b>2.4 参考资料</b>", body_style))
    reference_content = """
    将自学过程中遇到的好的参考资料、视频，总结在文档中。让大家做到只管照着笔记学就可以。
    """
    elements.append(Paragraph(reference_content.strip(), list_style))
    
    # 2.5 持续更新
    elements.append(Paragraph("<b>2.5 持续更新</b>", body_style))
    update_content = """
    从文档上线目前已经更新了2个多月了。博主每天下班就在整理笔记，做到和大家一起学习。
    过完年也会更新更多面经、算法相关内容，持续更新，共同进步，但从未涨价。
    """
    elements.append(Paragraph(update_content.strip(), list_style))
    
    elements.append(Spacer(1, 0.2*inch))
    
    # 价格信息
    price_info = """
    <b>笔记目前在小红书链接售卖，价格199元。</b>
    """
    elements.append(Paragraph(price_info, body_style))
    
    elements.append(PageBreak())
    
    # ==================== 图片1：设计思路 ====================
    elements.append(Paragraph("图片1：设计思路", heading_style))
    
    # Get image paths
    image_paths = get_image_paths()
    
    # Add design thinking image (use external image)
    design_img_path = image_paths['design_thinking']
    if design_img_path.exists():
        # Calculate appropriate size while maintaining aspect ratio
        with PILImage.open(design_img_path) as pil_img:
            orig_width, orig_height = pil_img.size
            # Max width is 6 inches, calculate height to maintain ratio
            max_width = 6 * inch
            aspect_ratio = orig_height / orig_width
            img_width = min(max_width, orig_width * 0.8)  # Scale down if needed
            img_height = img_width * aspect_ratio
            # Cap max height
            if img_height > 7 * inch:
                img_height = 7 * inch
                img_width = img_height / aspect_ratio
        
        img_flowable1 = Image(str(design_img_path), width=img_width, height=img_height)
        elements.append(img_flowable1)
    else:
        elements.append(Paragraph(f"[图片未找到: {design_img_path}]", body_style))
    
    elements.append(PageBreak())
    
    # ==================== 图片2：项目介绍 ====================
    elements.append(Paragraph("图片2：项目介绍", heading_style))
    
    # Add project intro image (use external image)
    project_img_path = image_paths['project_intro']
    if project_img_path.exists():
        # Calculate appropriate size while maintaining aspect ratio
        with PILImage.open(project_img_path) as pil_img:
            orig_width, orig_height = pil_img.size
            # Max width is 6 inches, calculate height to maintain ratio
            max_width = 6 * inch
            aspect_ratio = orig_height / orig_width
            img_width = min(max_width, orig_width * 0.8)  # Scale down if needed
            img_height = img_width * aspect_ratio
            # Cap max height
            if img_height > 7 * inch:
                img_height = 7 * inch
                img_width = img_height / aspect_ratio
        
        img_flowable2 = Image(str(project_img_path), width=img_width, height=img_height)
        elements.append(img_flowable2)
    else:
        elements.append(Paragraph(f"[图片未找到: {project_img_path}]", body_style))

    # Build the PDF
    doc.build(elements)
    print(f"PDF generated successfully: {output_path}")


def main():
    """Main function to generate the blogger intro PDF."""
    # Get the output path
    output_dir = Path(__file__).parent / "sample_documents"
    output_dir.mkdir(exist_ok=True)
    
    output_path = output_dir / "blogger_intro.pdf"
    
    # Generate the PDF
    generate_blogger_intro_pdf(output_path)


if __name__ == "__main__":
    main()
