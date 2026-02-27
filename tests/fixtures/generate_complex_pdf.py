"""
Generate a complex PDF for testing purposes.
Contains multiple pages, text, images, tables, and various formatting.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, Image, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from PIL import Image as PILImage
import io
from pathlib import Path


def create_sample_image(width=400, height=300, color='blue'):
    """Create a simple colored image with text."""
    from PIL import ImageDraw, ImageFont
    
    img = PILImage.new('RGB', (width, height), color=color)
    draw = ImageDraw.Draw(img)
    
    # Draw some shapes
    draw.rectangle([50, 50, width-50, height-50], outline='white', width=5)
    draw.ellipse([100, 100, width-100, height-100], fill='lightblue', outline='darkblue')
    
    # Add text
    try:
        draw.text((width//2-100, height//2-10), f"Sample {color.capitalize()} Image", 
                  fill='white')
    except:
        pass
    
    return img


def generate_complex_pdf(output_path):
    """Generate a complex PDF document for testing."""
    
    # Create the PDF document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
        leading=14
    )
    
    # Title Page
    elements.append(Spacer(1, 2*inch))
    elements.append(Paragraph("Advanced RAG System", title_style))
    elements.append(Paragraph("Technical Documentation & Testing Guide", styles['Heading2']))
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph("Version 2.0 - February 2026", styles['Normal']))
    elements.append(Spacer(1, 0.5*inch))
    
    # Add author info
    author_data = [
        ['Author:', 'AI Research Team'],
        ['Department:', 'Machine Learning Division'],
        ['Document Type:', 'Technical Specification'],
        ['Classification:', 'Internal Testing']
    ]
    author_table = Table(author_data, colWidths=[2*inch, 3*inch])
    author_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(author_table)
    elements.append(PageBreak())
    
    # Table of Contents
    elements.append(Paragraph("Table of Contents", heading_style))
    toc_items = [
        "1. Introduction to Modular RAG Systems",
        "2. System Architecture Overview",
        "3. Chunking Strategies and Implementation",
        "4. Embedding Models and Vector Storage",
        "5. Retrieval Mechanisms",
        "6. Performance Benchmarks",
        "7. Visual Components Analysis",
        "8. Future Enhancements"
    ]
    for item in toc_items:
        elements.append(Paragraph(item, styles['Normal']))
    elements.append(PageBreak())
    
    # Chapter 1: Introduction
    elements.append(Paragraph("1. Introduction to Modular RAG Systems", heading_style))
    
    intro_text = """
    Retrieval-Augmented Generation (RAG) represents a paradigm shift in how we approach 
    natural language processing and information retrieval. By combining the power of 
    large language models with efficient document retrieval mechanisms, RAG systems 
    enable more accurate, contextual, and reliable responses to user queries.
    """
    elements.append(Paragraph(intro_text, body_style))
    
    intro_text2 = """
    The modular architecture of this system allows for flexible configuration and 
    easy extension. Each component—from document loading and chunking to embedding 
    generation and vector storage—can be independently configured, tested, and 
    optimized. This modularity is crucial for maintaining system quality and 
    adapting to evolving requirements.
    """
    elements.append(Paragraph(intro_text2, body_style))
    
    # Key Features List
    elements.append(Paragraph("<b>Key Features:</b>", body_style))
    features = [
        "Multiple embedding provider support (OpenAI, Azure, Ollama, Sentence Transformers)",
        "Flexible chunking strategies with metadata preservation",
        "Hybrid search combining dense and sparse retrieval",
        "Advanced reranking with cross-encoder models",
        "Comprehensive observability and evaluation framework",
        "Production-ready error handling and logging"
    ]
    
    feature_list = ListFlowable(
        [ListItem(Paragraph(f, styles['Normal']), leftIndent=20) for f in features],
        bulletType='bullet'
    )
    elements.append(feature_list)
    elements.append(Spacer(1, 0.3*inch))
    
    # Chapter 2: Architecture
    elements.append(Paragraph("2. System Architecture Overview", heading_style))
    
    arch_text = """
    The system follows a layered architecture with clear separation of concerns. 
    At the foundation, we have the data ingestion layer responsible for loading 
    various document formats (PDF, DOCX, TXT, HTML) and converting them into a 
    standardized internal representation. This layer handles document parsing, 
    text extraction, and initial metadata capture.
    """
    elements.append(Paragraph(arch_text, body_style))
    
    # Architecture Components Table
    elements.append(Paragraph("<b>Core Components:</b>", body_style))
    arch_data = [
        ['Component', 'Purpose', 'Key Technologies'],
        ['Document Loaders', 'Parse and extract content', 'PyPDF2, python-docx, BeautifulSoup'],
        ['Chunking Engine', 'Split documents intelligently', 'LangChain, custom algorithms'],
        ['Embedding Service', 'Generate vector representations', 'OpenAI, HuggingFace, Ollama'],
        ['Vector Store', 'Persist and query embeddings', 'ChromaDB, FAISS'],
        ['Reranker', 'Refine retrieval results', 'Cross-encoder models'],
        ['Query Engine', 'Orchestrate retrieval pipeline', 'Custom implementation']
    ]
    
    arch_table = Table(arch_data, colWidths=[1.8*inch, 2.2*inch, 2.2*inch])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(arch_table)
    elements.append(PageBreak())
    
    # Chapter 3: Chunking
    elements.append(Paragraph("3. Chunking Strategies and Implementation", heading_style))
    
    chunk_text = """
    Effective chunking is critical for RAG system performance. The chunking module 
    implements multiple strategies to handle different document types and use cases. 
    The recursive character text splitter is the default choice, offering a good 
    balance between semantic coherence and chunk size control.
    """
    elements.append(Paragraph(chunk_text, body_style))
    
    # Add first image
    img1 = create_sample_image(400, 250, 'steelblue')
    img_buffer1 = io.BytesIO()
    img1.save(img_buffer1, format='PNG')
    img_buffer1.seek(0)
    
    img_flowable1 = Image(img_buffer1, width=4*inch, height=2.5*inch)
    elements.append(img_flowable1)
    elements.append(Paragraph("<i>Figure 1: Chunking Strategy Visualization</i>", 
                              styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    
    chunk_text2 = """
    The chunking process preserves critical metadata including source document 
    information, page numbers, section headers, and custom attributes. This metadata 
    enables more precise retrieval and better context for the language model. 
    Additionally, the system supports chunk refinement through LLM-based 
    post-processing, which can clean noisy text, fix formatting issues, and 
    enhance readability.
    """
    elements.append(Paragraph(chunk_text2, body_style))
    
    # Chunking parameters table
    chunk_params = [
        ['Parameter', 'Default Value', 'Description'],
        ['chunk_size', '512', 'Target characters per chunk'],
        ['chunk_overlap', '128', 'Overlap between chunks'],
        ['separators', '[\\n\\n, \\n, . ]', 'Split priority sequence'],
        ['length_function', 'len()', 'Character counting method']
    ]
    
    param_table = Table(chunk_params, colWidths=[2*inch, 1.5*inch, 2.7*inch])
    param_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    elements.append(param_table)
    elements.append(PageBreak())
    
    # Chapter 4: Embeddings
    elements.append(Paragraph("4. Embedding Models and Vector Storage", heading_style))
    
    embed_text = """
    The embedding layer supports multiple providers through a factory pattern, 
    enabling seamless switching between OpenAI's text-embedding-ada-002, Azure 
    OpenAI endpoints, local Ollama models, and various Sentence Transformer models. 
    Each provider implements a common interface ensuring consistent behavior 
    across the system.
    """
    elements.append(Paragraph(embed_text, body_style))
    
    # Provider comparison
    provider_data = [
        ['Provider', 'Dimension', 'Speed', 'Cost', 'Quality'],
        ['OpenAI Ada-002', '1536', 'Fast', 'Low', 'High'],
        ['Azure OpenAI', '1536', 'Fast', 'Medium', 'High'],
        ['Ollama (local)', '384-768', 'Medium', 'Free', 'Medium'],
        ['Sentence-BERT', '384', 'Very Fast', 'Free', 'Medium-High']
    ]
    
    provider_table = Table(provider_data, colWidths=[1.8*inch, 1.2*inch, 1*inch, 1*inch, 1.2*inch])
    provider_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2980b9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.lightblue, colors.white])
    ]))
    elements.append(provider_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Add second image
    img2 = create_sample_image(400, 250, 'seagreen')
    img_buffer2 = io.BytesIO()
    img2.save(img_buffer2, format='PNG')
    img_buffer2.seek(0)
    
    img_flowable2 = Image(img_buffer2, width=4*inch, height=2.5*inch)
    elements.append(img_flowable2)
    elements.append(Paragraph("<i>Figure 2: Embedding Vector Space Representation</i>", 
                              styles['Normal']))
    elements.append(PageBreak())
    
    # Chapter 5: Retrieval
    elements.append(Paragraph("5. Retrieval Mechanisms", heading_style))
    
    retrieval_text = """
    The retrieval system implements a hybrid approach combining dense vector 
    similarity search with sparse BM25 ranking. This dual-mode retrieval strategy 
    leverages the semantic understanding of neural embeddings while preserving 
    the precision of traditional keyword matching. The results from both methods 
    are merged and reranked using a cross-encoder model for optimal relevance.
    """
    elements.append(Paragraph(retrieval_text, body_style))
    
    retrieval_text2 = """
    Query processing includes several enhancement stages: query expansion using 
    synonyms and related terms, query decomposition for complex multi-part questions, 
    and adaptive retrieval that adjusts the number of retrieved documents based on 
    query complexity. The system also maintains a query cache to improve response 
    times for frequently asked questions.
    """
    elements.append(Paragraph(retrieval_text2, body_style))
    
    # Chapter 6: Performance
    elements.append(Paragraph("6. Performance Benchmarks", heading_style))
    
    perf_text = """
    Comprehensive benchmarking has been conducted across various dimensions including 
    retrieval accuracy (measured by precision@k, recall@k, and NDCG), query latency, 
    and system throughput. The results demonstrate that the hybrid retrieval approach 
    consistently outperforms pure dense or sparse methods.
    """
    elements.append(Paragraph(perf_text, body_style))
    
    # Performance metrics table
    perf_data = [
        ['Metric', 'Pure Dense', 'Pure Sparse', 'Hybrid + Rerank'],
        ['Precision@5', '0.72', '0.68', '0.85'],
        ['Recall@10', '0.65', '0.71', '0.82'],
        ['NDCG@10', '0.78', '0.73', '0.88'],
        ['Avg Latency (ms)', '45', '28', '89'],
        ['Throughput (qps)', '120', '180', '95']
    ]
    
    perf_table = Table(perf_data, colWidths=[1.8*inch, 1.4*inch, 1.4*inch, 1.6*inch])
    perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(perf_table)
    elements.append(PageBreak())
    
    # Chapter 7: Visual Components
    elements.append(Paragraph("7. Visual Components Analysis", heading_style))
    
    visual_text = """
    The system includes specialized handling for visual content in documents. 
    Images are extracted, stored separately with content-addressed filenames 
    (SHA256 hashes), and processed through vision-language models to generate 
    descriptive captions. These captions are embedded alongside text chunks, 
    enabling multimodal retrieval capabilities.
    """
    elements.append(Paragraph(visual_text, body_style))
    
    # Add third image
    img3 = create_sample_image(400, 250, 'coral')
    img_buffer3 = io.BytesIO()
    img3.save(img_buffer3, format='PNG')
    img_buffer3.seek(0)
    
    img_flowable3 = Image(img_buffer3, width=4*inch, height=2.5*inch)
    elements.append(img_flowable3)
    elements.append(Paragraph("<i>Figure 3: Visual Content Processing Pipeline</i>", 
                              styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    visual_text2 = """
    The vision processing pipeline integrates with Azure Computer Vision and 
    GPT-4 Vision APIs to extract semantic information from diagrams, charts, 
    screenshots, and photographs. This visual understanding is crucial for 
    technical documentation where important information is often conveyed 
    through images rather than text.
    """
    elements.append(Paragraph(visual_text2, body_style))
    elements.append(PageBreak())
    
    # Chapter 8: Future Work
    elements.append(Paragraph("8. Future Enhancements", heading_style))
    
    future_text = """
    Several exciting enhancements are planned for future releases. These include 
    support for multi-hop reasoning across documents, integration with knowledge 
    graphs for structured information, and advanced citation tracking to provide 
    source attribution for generated responses. Additionally, we are exploring 
    fine-tuning custom embedding models on domain-specific corpora to improve 
    retrieval accuracy in specialized fields.
    """
    elements.append(Paragraph(future_text, body_style))
    
    # Future features
    future_features = [
        "Multi-document reasoning and cross-reference resolution",
        "Knowledge graph integration for entity-based retrieval",
        "Streaming response generation with real-time source citation",
        "Automated relevance feedback and query reformulation",
        "Support for audio and video content transcription and indexing",
        "Privacy-preserving retrieval with differential privacy guarantees"
    ]
    
    future_list = ListFlowable(
        [ListItem(Paragraph(f, styles['Normal']), leftIndent=20) for f in future_features],
        bulletType='1'
    )
    elements.append(future_list)
    elements.append(Spacer(1, 0.5*inch))
    
    # Conclusion
    conclusion_text = """
    This modular RAG system provides a robust foundation for building intelligent 
    information retrieval applications. Through careful design, comprehensive testing, 
    and continuous optimization, we have created a system that balances performance, 
    accuracy, and maintainability. The modular architecture ensures that the system 
    can evolve with changing requirements and new technological developments.
    """
    elements.append(Paragraph(conclusion_text, body_style))
    
    # Build PDF
    doc.build(elements)
    print(f"PDF generated successfully: {output_path}")


if __name__ == "__main__":
    output_dir = Path(__file__).parent / "sample_documents"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "complex_technical_doc.pdf"
    
    generate_complex_pdf(output_file)
