"""Generate Chinese QA test PDF documents for QA_TEST_PLAN.

Creates three PDFs used by Section O (文档替换与多场景验证):
1. chinese_technical_doc.pdf  — 纯中文技术文档 (~8 页)
2. chinese_table_chart_doc.pdf — 含中文表格和流程图的文档 (~6 页, 含图片)
3. chinese_long_doc.pdf        — 30+ 页中文长文档

Usage:
    python tests/fixtures/generate_qa_test_pdfs.py
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

_CHINESE_FONT: str | None = None


def _register_chinese_font() -> str:
    """Register a Chinese TrueType font and return its name."""
    global _CHINESE_FONT
    if _CHINESE_FONT is not None:
        return _CHINESE_FONT

    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ChineseFont", path))
                _CHINESE_FONT = "ChineseFont"
                return _CHINESE_FONT
            except Exception:
                continue

    _CHINESE_FONT = "Helvetica"
    return _CHINESE_FONT


# ---------------------------------------------------------------------------
# Shared style factory
# ---------------------------------------------------------------------------


def _make_styles():
    font = _register_chinese_font()
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        "ZH_Title", parent=base["Heading1"], fontName=font, fontSize=24,
        textColor=colors.HexColor("#1a1a1a"), spaceAfter=30, alignment=TA_CENTER,
    )
    h1 = ParagraphStyle(
        "ZH_H1", parent=base["Heading2"], fontName=font, fontSize=18,
        textColor=colors.HexColor("#2c3e50"), spaceAfter=14, spaceBefore=20,
    )
    h2 = ParagraphStyle(
        "ZH_H2", parent=base["Heading3"], fontName=font, fontSize=14,
        textColor=colors.HexColor("#34495e"), spaceAfter=10, spaceBefore=14,
    )
    body = ParagraphStyle(
        "ZH_Body", parent=base["BodyText"], fontName=font, fontSize=11,
        alignment=TA_JUSTIFY, spaceAfter=12, leading=18,
    )
    code = ParagraphStyle(
        "ZH_Code", parent=base["Code"], fontName="Courier", fontSize=9,
        spaceAfter=10, leading=13, leftIndent=20, backColor=colors.HexColor("#f5f5f5"),
    )
    caption = ParagraphStyle(
        "ZH_Caption", parent=base["Normal"], fontName=font, fontSize=9,
        alignment=TA_CENTER, textColor=colors.grey, spaceAfter=12,
    )
    return {"title": title, "h1": h1, "h2": h2, "body": body, "code": code,
            "caption": caption, "normal": base["Normal"]}


def _table_style(header_color: str = "#2c3e50"):
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, -1), _register_chinese_font()),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
    ])


def _create_chart_image(width: int, height: int, title: str, chart_type: str = "bar") -> io.BytesIO:
    """Create a simple chart-like image for embedding in PDFs."""
    img = PILImage.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # border
    draw.rectangle([2, 2, width - 3, height - 3], outline="#2c3e50", width=2)

    if chart_type == "bar":
        # simple bar chart
        bar_colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6"]
        bar_w = width // 8
        base_y = height - 40
        for i, c in enumerate(bar_colors):
            h = 30 + (i * 25 + 40) % (height - 100)
            x0 = 40 + i * (bar_w + 15)
            draw.rectangle([x0, base_y - h, x0 + bar_w, base_y], fill=c)
    elif chart_type == "flow":
        # simple flow-chart boxes
        boxes = [
            (50, 30, 180, 70, "#3498db", "文档输入"),
            (50, 100, 180, 140, "#2ecc71", "文本分块"),
            (50, 170, 180, 210, "#e74c3c", "向量编码"),
            (220, 100, 350, 140, "#f39c12", "BM25索引"),
            (220, 170, 350, 210, "#9b59b6", "混合检索"),
        ]
        for x0, y0, x1, y1, c, _label in boxes:
            draw.rectangle([x0, y0, x1, y1], fill=c, outline="#2c3e50")
        # arrows (simple lines)
        draw.line([(130, 70), (130, 100)], fill="#2c3e50", width=2)
        draw.line([(130, 140), (130, 170)], fill="#2c3e50", width=2)
        draw.line([(180, 120), (220, 120)], fill="#2c3e50", width=2)
        draw.line([(285, 140), (285, 170)], fill="#2c3e50", width=2)
    elif chart_type == "pie":
        cx, cy, r = width // 2, height // 2, min(width, height) // 3
        slices = [(0, 120, "#3498db"), (120, 200, "#e74c3c"), (200, 280, "#2ecc71"), (280, 360, "#f39c12")]
        for start, end, c in slices:
            draw.pieslice([cx - r, cy - r, cx + r, cy + r], start, end, fill=c, outline="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ===================================================================
# 1. 纯中文技术文档 (~8 页)
# ===================================================================

def generate_chinese_technical_doc(output: Path) -> None:
    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=30)
    s = _make_styles()
    elems: list = []

    # 封面
    elems.append(Spacer(1, 2 * inch))
    elems.append(Paragraph("大语言模型应用开发技术指南", s["title"]))
    elems.append(Spacer(1, 0.3 * inch))
    elems.append(Paragraph("——从 RAG 到 Agent 的实战手册", s["h2"]))
    elems.append(Spacer(1, 0.5 * inch))
    cover = [
        ["作者", "Modular RAG 项目组"],
        ["版本", "v1.0 — 2026 年 2 月"],
        ["分类", "内部技术文档 / QA 测试用"],
    ]
    t = Table(cover, colWidths=[1.5 * inch, 4 * inch])
    t.setStyle(_table_style())
    elems.append(t)
    elems.append(PageBreak())

    # 目录
    elems.append(Paragraph("目录", s["h1"]))
    toc = [
        "第一章  大语言模型基础概念",
        "第二章  检索增强生成（RAG）架构设计",
        "第三章  文档分块策略详解",
        "第四章  向量检索与混合搜索",
        "第五章  重排序机制与评估方法",
        "第六章  Agent 与工具调用",
        "第七章  生产部署与性能优化",
    ]
    for item in toc:
        elems.append(Paragraph(item, s["body"]))
    elems.append(PageBreak())

    # ---- 第一章 ----
    elems.append(Paragraph("第一章  大语言模型基础概念", s["h1"]))
    elems.append(Paragraph(
        "大语言模型（Large Language Model, LLM）是基于 Transformer 架构，"
        "通过海量文本数据进行预训练而得到的深度神经网络。代表性模型包括 GPT-4、Claude、"
        "DeepSeek 等。LLM 的核心思想是将自然语言建模为 Token 序列的概率分布，通过"
        "自回归方式逐个 Token 生成文本。", s["body"]))
    elems.append(Paragraph(
        "与传统 NLP 方法相比，LLM 具有以下关键优势：", s["body"]))
    advantages = [
        "强大的上下文理解能力，能够处理长文档和复杂指令",
        "Few-shot 和 Zero-shot 学习能力，无需大量标注数据",
        "跨任务泛化能力，同一模型可完成翻译、摘要、QA 等多种任务",
        "支持多轮对话和思维链（Chain-of-Thought）推理",
    ]
    for a in advantages:
        elems.append(Paragraph(f"• {a}", s["body"]))

    elems.append(Paragraph("1.1 Transformer 架构要点", s["h2"]))
    elems.append(Paragraph(
        "Transformer 架构最初由 Vaswani 等人在 2017 年提出（Attention Is All You Need），"
        "其核心组件包括多头自注意力机制（Multi-Head Self-Attention）、前馈神经网络（FFN）、"
        "层归一化（Layer Normalization）和残差连接（Residual Connection）。在 LLM 中，"
        "通常只使用 Decoder 部分，通过因果注意力掩码实现自回归生成。", s["body"]))
    elems.append(Paragraph(
        "注意力计算的核心公式为 Attention(Q,K,V) = softmax(QK^T / √d_k) V，其中 Q、K、V "
        "分别代表查询、键和值矩阵，d_k 为键向量维度。多头注意力将输入投影到 h 个不同的子空间，"
        "并行计算注意力后拼接输出。", s["body"]))

    elems.append(Paragraph("1.2 Tokenization 与词表", s["h2"]))
    elems.append(Paragraph(
        "分词（Tokenization）是将原始文本转化为模型可处理的整数序列的关键步骤。"
        "常见的子词分词算法包括 BPE（Byte Pair Encoding）、WordPiece 和 SentencePiece。"
        "中文场景下，BPE 通常将每个汉字作为一个或多个 Token，因此中文文本的 Token 数量"
        "往往多于等长的英文文本。这对 RAG 系统的 Chunk 大小设计有直接影响。", s["body"]))
    elems.append(PageBreak())

    # ---- 第二章 ----
    elems.append(Paragraph("第二章  检索增强生成（RAG）架构设计", s["h1"]))
    elems.append(Paragraph(
        "RAG（Retrieval-Augmented Generation）将信息检索与文本生成相结合，通过"
        "在生成时引入外部知识库的相关文档片段，显著减少 LLM 的幻觉问题，同时使模型"
        "能够回答超出训练数据范围的实时性问题。", s["body"]))

    elems.append(Paragraph("2.1 Naive RAG vs Advanced RAG", s["h2"]))
    elems.append(Paragraph(
        "Naive RAG 采用最简单的「检索-拼接-生成」流程：将用户查询编码为向量，"
        "在向量数据库中检索 Top-K 相似文档，拼接到 Prompt 中交由 LLM 生成回答。"
        "其缺点包括：检索质量受限于单一向量相似度、缺乏重排序机制、"
        "无法处理多跳推理等。", s["body"]))
    elems.append(Paragraph(
        "Advanced RAG 在 Naive RAG 基础上引入多项优化：查询改写（Query Rewriting）、"
        "混合检索（Hybrid Search combining Dense + Sparse）、重排序（Reranking via "
        "Cross-Encoder 或 LLM）、以及文档分块优化（Smart Chunking + Metadata Enrichment）。"
        "本项目实现了完整的 Advanced RAG 链路。", s["body"]))

    elems.append(Paragraph("2.2 Modular RAG 设计理念", s["h2"]))
    elems.append(Paragraph(
        "Modular RAG 将 RAG 流程分解为可独立替换的模块：Loader → Splitter → Transformer → "
        "Embedder → Vector Store → Retriever → Reranker → Generator。每个模块定义抽象接口，"
        "通过工厂模式和配置文件驱动实例化，实现「乐高积木式」的灵活组合。", s["body"]))
    elems.append(Paragraph(
        "这种设计的核心优势在于：可以在不修改代码的情况下，通过 settings.yaml 一键切换"
        " LLM Provider（Azure / DeepSeek / Ollama）、Embedding 模型、Reranker 策略等，"
        "极大地方便了 A/B 测试和技术选型。", s["body"]))
    elems.append(PageBreak())

    # ---- 第三章 ----
    elems.append(Paragraph("第三章  文档分块策略详解", s["h1"]))
    elems.append(Paragraph(
        "文档分块（Chunking）是 RAG 系统中决定检索质量的关键环节。分块过大会导致检索"
        "噪声增加、LLM 上下文利用率下降；分块过小则会丢失语义上下文，影响回答连贯性。", s["body"]))

    elems.append(Paragraph("3.1 常见分块方法", s["h2"]))
    methods = [
        ["方法", "原理", "适用场景"],
        ["固定长度切分", "按字符数或 Token 数等分", "结构简单的纯文本"],
        ["递归字符切分", "按分隔符优先级递归切分", "通用文档（推荐）"],
        ["语义分块", "基于 Embedding 相似度判断边界", "长文档、主题多变"],
        ["Markdown 切分", "按标题层级切分", "Markdown / 技术文档"],
    ]
    mt = Table(methods, colWidths=[1.8 * inch, 2.5 * inch, 2 * inch])
    mt.setStyle(_table_style("#27ae60"))
    elems.append(mt)
    elems.append(Spacer(1, 0.2 * inch))

    elems.append(Paragraph("3.2 Chunk 增强：Refiner 与 Metadata Enrichment", s["h2"]))
    elems.append(Paragraph(
        "原始切分后的 Chunk 可能存在截断不自然、缺乏上下文等问题。Chunk Refiner 利用 LLM "
        "对 Chunk 文本进行改写润色，使其更加自包含、语义完整。Metadata Enricher 则为每个 "
        "Chunk 生成 title、summary 和 tags 元信息，在检索阶段可用于辅助过滤和排序。", s["body"]))
    elems.append(Paragraph(
        "图片处理方面，系统会提取 PDF 中的嵌入图片，调用 Vision LLM（如 GPT-4o）生成中文"
        "图片描述（Image Caption），并将描述文本注入对应 Chunk 的 metadata 中，从而实现"
        "跨模态检索——用户可以通过文字查询来找到相关的图表和图片内容。", s["body"]))
    elems.append(PageBreak())

    # ---- 第四章 ----
    elems.append(Paragraph("第四章  向量检索与混合搜索", s["h1"]))
    elems.append(Paragraph(
        "向量检索（Dense Retrieval）通过将文本编码为高维稠密向量，利用余弦相似度或内积"
        "计算语义相似性，是现代信息检索的核心技术。常用的 Embedding 模型包括 OpenAI "
        "text-embedding-ada-002（1536 维）、BGE 系列（768/1024 维）等。", s["body"]))

    elems.append(Paragraph("4.1 BM25 稀疏检索", s["h2"]))
    elems.append(Paragraph(
        "BM25（Best Matching 25）是经典的概率检索模型，基于词频（TF）和逆文档频率（IDF）"
        "计算文档与查询的相关性。其优势在于对精确关键词匹配的处理非常有效，特别是专有名词、"
        "错别字等场景下表现优于纯语义检索。本项目使用 jieba 分词 + rank_bm25 库实现中文 "
        "BM25 检索。", s["body"]))

    elems.append(Paragraph("4.2 RRF 融合算法", s["h2"]))
    elems.append(Paragraph(
        "Reciprocal Rank Fusion (RRF) 是一种简单高效的排名融合算法，公式为："
        "score(d) = Σ 1/(k + rank_i(d))，其中 k 为平滑常数（默认 60），rank_i(d) 为"
        "文档 d 在第 i 个排名列表中的位置。RRF 的优势在于不依赖原始分数的量纲，"
        "可以直接融合不同检索方法的排名结果。", s["body"]))

    elems.append(Paragraph("4.3 ChromaDB 向量存储", s["h2"]))
    elems.append(Paragraph(
        "ChromaDB 是一个轻量级的开源向量数据库，支持 Embedding 存储、元数据过滤和近似最近邻"
        "（ANN）搜索。本项目使用 ChromaDB 持久化存储模式，数据保存在本地 SQLite 文件中，"
        "适合个人项目和中小规模应用场景。", s["body"]))
    elems.append(PageBreak())

    # ---- 第五章 ----
    elems.append(Paragraph("第五章  重排序机制与评估方法", s["h1"]))
    elems.append(Paragraph(
        "重排序（Reranking）是 RAG 的精排阶段，在粗排召回的候选集基础上进行更精细的相关性"
        "评估。常见方案包括 Cross-Encoder Reranker 和 LLM Reranker 两种。", s["body"]))

    elems.append(Paragraph("5.1 Cross-Encoder vs Bi-Encoder", s["h2"]))
    elems.append(Paragraph(
        "Bi-Encoder（双塔模型）将查询和文档分别编码为独立向量，通过余弦相似度计算匹配度，"
        "速度快但精度有限。Cross-Encoder 将查询和文档拼接后同时输入模型，通过注意力机制"
        "捕捉细粒度交互，精度更高但速度较慢。RAG 中通常使用 Bi-Encoder 做粗排，"
        "Cross-Encoder 做精排。", s["body"]))

    elems.append(Paragraph("5.2 评估指标", s["h2"]))
    metrics_data = [
        ["指标名称", "类型", "说明"],
        ["Hit Rate", "检索指标", "Top-K 结果中是否包含正确文档"],
        ["MRR", "检索指标", "正确文档首次出现位置的倒数"],
        ["Faithfulness", "生成指标 (Ragas)", "生成答案是否忠实于检索上下文"],
        ["Answer Relevancy", "生成指标 (Ragas)", "生成答案与用户问题的相关度"],
        ["Context Precision", "生成指标 (Ragas)", "检索上下文中相关信息的占比"],
    ]
    et = Table(metrics_data, colWidths=[1.8 * inch, 1.5 * inch, 3 * inch])
    et.setStyle(_table_style("#8e44ad"))
    elems.append(et)
    elems.append(PageBreak())

    # ---- 第六章 ----
    elems.append(Paragraph("第六章  Agent 与工具调用", s["h1"]))
    elems.append(Paragraph(
        "Agent 是指能够自主规划任务、调用外部工具来完成复杂目标的 AI 系统。"
        "与简单的 RAG 查询不同，Agent 可以根据用户指令自动分解任务、选择合适的工具"
        "（如搜索引擎、计算器、代码执行器），迭代执行直到获得满意结果。", s["body"]))

    elems.append(Paragraph("6.1 MCP 协议", s["h2"]))
    elems.append(Paragraph(
        "Model Context Protocol（MCP）是 Anthropic 提出的标准化 AI 模型与外部工具交互的协议。"
        "它定义了工具发现（tools/list）、工具调用（tools/call）等 JSON-RPC 2.0 接口标准。"
        "本项目实现了一个 MCP Server，暴露了 query_knowledge_hub、list_collections 和 "
        "get_document_summary 三个工具，可被 VS Code Copilot 或 Claude Desktop 直接调用。", s["body"]))

    elems.append(Paragraph("6.2 ReAct 推理模式", s["h2"]))
    elems.append(Paragraph(
        "ReAct（Reasoning + Acting）是一种将推理与行动交替进行的 Agent 模式。"
        "LLM 先进行推理思考（Thought），然后选择一个行动（Action），观察行动结果"
        "（Observation），再继续推理，循环往复直到得出最终答案。这种模式使 Agent 的"
        "决策过程更加透明、可调试。", s["body"]))
    elems.append(PageBreak())

    # ---- 第七章 ----
    elems.append(Paragraph("第七章  生产部署与性能优化", s["h1"]))
    elems.append(Paragraph(
        "将 RAG 系统从开发环境部署到生产环境需要考虑多个维度：服务可用性、响应延迟、"
        "数据安全和成本控制。以下是关键优化策略。", s["body"]))

    elems.append(Paragraph("7.1 缓存策略", s["h2"]))
    elems.append(Paragraph(
        "对于重复或相似的查询，可以引入语义缓存（Semantic Cache）：将查询向量与缓存库中的"
        "历史查询进行相似度匹配，若超过阈值则直接返回缓存结果，避免重复的 Embedding 计算"
        "和 LLM 调用，显著降低延迟和成本。", s["body"]))

    elems.append(Paragraph("7.2 批处理与异步", s["h2"]))
    elems.append(Paragraph(
        "Embedding 计算和 LLM 调用是 RAG 链路中最耗时的环节。通过批量 Embedding "
        "（将多个 Chunk 合并为一次 API 调用）和异步并发（asyncio / ThreadPool），"
        "可以大幅提升数据摄取和查询的吞吐量。本项目的 BatchProcessor 组件实现了"
        "可配置的批量大小和并发度。", s["body"]))

    elems.append(Paragraph("7.3 可观测性", s["h2"]))
    elems.append(Paragraph(
        "生产系统必须具备完善的可观测性能力。本项目通过结构化日志（JSON Lines 格式）、"
        "全链路 Trace（记录每个阶段的输入/输出/耗时）和 Streamlit Dashboard 三位一体"
        "实现可视化监控。每次摄取和查询操作都会自动生成 Trace 记录，便于问题排查和性能分析。", s["body"]))

    # Build
    doc.build(elems)
    print(f"✅ Generated: {output}")


# ===================================================================
# 2. 含中文表格和流程图的文档 (~6 页, 含图片)
# ===================================================================

def generate_chinese_table_chart_doc(output: Path) -> None:
    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=30)
    s = _make_styles()
    elems: list = []

    # 封面
    elems.append(Spacer(1, 2 * inch))
    elems.append(Paragraph("RAG 系统性能评测报告", s["title"]))
    elems.append(Spacer(1, 0.3 * inch))
    elems.append(Paragraph("含表格与流程图 · QA 测试用", s["h2"]))
    elems.append(Spacer(1, 0.5 * inch))
    cover = [
        ["文档类型", "性能评测报告"],
        ["版本", "v1.0 — 2026 年 2 月"],
        ["用途", "QA 测试 / Section O"],
    ]
    ct = Table(cover, colWidths=[1.5 * inch, 4 * inch])
    ct.setStyle(_table_style())
    elems.append(ct)
    elems.append(PageBreak())

    # ---- 第一章：系统架构流程图 ----
    elems.append(Paragraph("第一章  RAG 系统整体架构", s["h1"]))
    elems.append(Paragraph(
        "下图展示了 Modular RAG 系统的核心处理流程。文档从输入到最终检索结果，"
        "依次经过加载、分块、增强、编码、存储五个阶段。", s["body"]))

    # 流程图
    flow_buf = _create_chart_image(400, 250, "RAG Pipeline", "flow")
    elems.append(Image(flow_buf, width=5 * inch, height=3 * inch))
    elems.append(Paragraph("图 1：RAG 数据摄取流程图", s["caption"]))
    elems.append(Spacer(1, 0.2 * inch))

    elems.append(Paragraph(
        "如图 1 所示，文档首先通过 Loader 模块进行解析（支持 PDF、Markdown、Word 等格式），"
        "提取纯文本和嵌入图片。随后进入 Splitter 模块进行智能分块，再通过 Transformer 模块"
        "进行 LLM 增强（Chunk 精炼 + 元数据生成 + 图片描述）。最后经 Embedder 编码为向量，"
        "存入 ChromaDB 和 BM25 索引。", s["body"]))
    elems.append(PageBreak())

    # ---- 第二章：Embedding 模型对比 ----
    elems.append(Paragraph("第二章  Embedding 模型性能对比", s["h1"]))
    elems.append(Paragraph(
        "不同 Embedding 模型在维度、速度、成本和质量上各有差异。下表对比了常用模型的关键参数。", s["body"]))

    embed_data = [
        ["模型名称", "维度", "延迟(ms)", "成本", "中文质量"],
        ["text-embedding-ada-002", "1536", "25", "$0.0001/1K tokens", "良好"],
        ["text-embedding-3-small", "1536", "20", "$0.00002/1K tokens", "良好"],
        ["text-embedding-3-large", "3072", "35", "$0.00013/1K tokens", "优秀"],
        ["BGE-large-zh", "1024", "15", "免费（本地）", "优秀"],
        ["GTE-large-zh", "1024", "18", "免费（本地）", "优秀"],
        ["M3E-base", "768", "12", "免费（本地）", "良好"],
    ]
    et = Table(embed_data, colWidths=[2 * inch, 0.8 * inch, 0.9 * inch, 1.8 * inch, 0.9 * inch])
    et.setStyle(_table_style("#2980b9"))
    elems.append(et)
    elems.append(Paragraph("表 1：主流 Embedding 模型参数对比", s["caption"]))
    elems.append(Spacer(1, 0.2 * inch))

    # 柱状图
    bar_buf = _create_chart_image(450, 250, "Embedding 延迟对比", "bar")
    elems.append(Image(bar_buf, width=5 * inch, height=2.8 * inch))
    elems.append(Paragraph("图 2：各 Embedding 模型延迟对比（ms）", s["caption"]))
    elems.append(PageBreak())

    # ---- 第三章：检索策略对比 ----
    elems.append(Paragraph("第三章  检索策略性能对比", s["h1"]))
    elems.append(Paragraph(
        "混合检索（Hybrid Search）结合了稠密向量和稀疏关键词两种检索方式的优势。"
        "下表展示了不同检索策略在标准测试集上的表现。", s["body"]))

    retrieval_data = [
        ["检索策略", "Precision@5", "Recall@10", "NDCG@10", "平均延迟(ms)"],
        ["纯稠密检索", "0.72", "0.65", "0.78", "45"],
        ["纯稀疏检索 (BM25)", "0.68", "0.71", "0.73", "28"],
        ["混合检索 (RRF)", "0.80", "0.78", "0.84", "65"],
        ["混合检索 + Cross-Encoder", "0.85", "0.82", "0.88", "89"],
        ["混合检索 + LLM Rerank", "0.83", "0.80", "0.87", "320"],
    ]
    rt = Table(retrieval_data, colWidths=[2.2 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch, 1.2 * inch])
    rt.setStyle(_table_style("#27ae60"))
    elems.append(rt)
    elems.append(Paragraph("表 2：检索策略性能对比", s["caption"]))
    elems.append(Spacer(1, 0.3 * inch))

    elems.append(Paragraph(
        "从表 2 可以看出，混合检索 + Cross-Encoder 重排的方案在精度指标上表现最佳，"
        "但延迟也相对较高。纯 BM25 检索延迟最低，但精度不够理想。实际部署中需要根据"
        "业务场景在精度和延迟之间做权衡。", s["body"]))
    elems.append(PageBreak())

    # ---- 第四章：分块参数实验 ----
    elems.append(Paragraph("第四章  分块参数调优实验", s["h1"]))
    elems.append(Paragraph(
        "Chunk Size 和 Chunk Overlap 是分块策略中最重要的两个超参数。下表展示了"
        "不同参数组合对检索质量的影响。", s["body"]))

    chunk_exp = [
        ["Chunk Size", "Overlap", "Chunk 数量", "Hit Rate", "MRR", "备注"],
        ["256", "50", "48", "0.65", "0.58", "分块过小，上下文丢失"],
        ["512", "100", "26", "0.78", "0.72", "较好平衡"],
        ["1000", "200", "14", "0.82", "0.76", "推荐配置"],
        ["1500", "300", "10", "0.75", "0.70", "分块偏大，噪声增加"],
        ["2000", "400", "8", "0.68", "0.62", "分块过大，检索不精确"],
    ]
    cet = Table(chunk_exp, colWidths=[0.9*inch, 0.8*inch, 0.9*inch, 0.9*inch, 0.8*inch, 2*inch])
    cet.setStyle(_table_style("#e67e22"))
    elems.append(cet)
    elems.append(Paragraph("表 3：分块参数对检索质量的影响", s["caption"]))
    elems.append(Spacer(1, 0.2 * inch))

    # 饼图
    pie_buf = _create_chart_image(350, 250, "耗时分布", "pie")
    elems.append(Image(pie_buf, width=4 * inch, height=2.8 * inch))
    elems.append(Paragraph("图 3：摄取各阶段耗时占比分布", s["caption"]))
    elems.append(Spacer(1, 0.2 * inch))

    elems.append(Paragraph(
        "根据实验结果，推荐使用 chunk_size=1000, chunk_overlap=200 的配置，在保留足够"
        "上下文的同时获得较高的检索精度。同时建议开启 LLM Chunk Refiner，进一步提升"
        "Chunk 的语义完整性。", s["body"]))
    elems.append(PageBreak())

    # ---- 第五章：配置示例 ----
    elems.append(Paragraph("第五章  配置参考", s["h1"]))
    elems.append(Paragraph(
        "以下是推荐的 settings.yaml 关键配置项汇总表：", s["body"]))

    config_data = [
        ["配置路径", "推荐值", "说明"],
        ["llm.provider", "azure", "LLM 服务商"],
        ["llm.model", "gpt-4o", "LLM 模型名"],
        ["embedding.provider", "azure", "Embedding 服务商"],
        ["embedding.model", "text-embedding-ada-002", "Embedding 模型"],
        ["ingestion.chunk_size", "1000", "分块大小（字符）"],
        ["ingestion.chunk_overlap", "200", "分块重叠（字符）"],
        ["retrieval.dense_top_k", "10", "稠密检索 Top-K"],
        ["retrieval.sparse_top_k", "10", "稀疏检索 Top-K"],
        ["retrieval.rrf_k", "60", "RRF 平滑常数"],
        ["rerank.provider", "none", "重排序方式"],
        ["rerank.top_k", "3", "最终返回条数"],
    ]
    cft = Table(config_data, colWidths=[2.2 * inch, 2 * inch, 2.5 * inch])
    cft.setStyle(_table_style("#16a085"))
    elems.append(cft)
    elems.append(Paragraph("表 4：推荐配置项汇总", s["caption"]))

    # Build
    doc.build(elems)
    print(f"✅ Generated: {output}")


# ===================================================================
# 3. 30+ 页中文长文档
# ===================================================================

def generate_chinese_long_doc(output: Path) -> None:
    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=30)
    s = _make_styles()
    elems: list = []

    # 封面
    elems.append(Spacer(1, 2 * inch))
    elems.append(Paragraph("大模型面试八股知识手册", s["title"]))
    elems.append(Spacer(1, 0.3 * inch))
    elems.append(Paragraph("RAG · Agent · 微调 · 推理部署 · 评估", s["h2"]))
    elems.append(Spacer(1, 0.5 * inch))
    cover = [
        ["作者", "Modular RAG 项目组"],
        ["版本", "v1.0 — 2026 年 2 月"],
        ["页数", "30+ 页"],
        ["用途", "QA 测试长文档 / Section O"],
    ]
    ct = Table(cover, colWidths=[1.5 * inch, 4 * inch])
    ct.setStyle(_table_style())
    elems.append(ct)
    elems.append(PageBreak())

    # 目录
    elems.append(Paragraph("目录", s["h1"]))
    chapters = [
        "第一章  Transformer 与注意力机制",
        "第二章  预训练与微调技术",
        "第三章  Prompt Engineering",
        "第四章  检索增强生成（RAG）",
        "第五章  向量数据库与 Embedding",
        "第六章  混合检索与重排序",
        "第七章  文档处理与分块策略",
        "第八章  Agent 与工具调用",
        "第九章  模型评估与基准测试",
        "第十章  推理优化与部署",
        "第十一章  多模态大模型",
        "第十二章  安全与对齐",
        "第十三章  行业应用案例",
        "第十四章  面试高频问题精选",
        "第十五章  项目实战经验总结",
    ]
    for ch in chapters:
        elems.append(Paragraph(ch, s["body"]))
    elems.append(PageBreak())

    # ---------- 内容生成（每章 ~2 页） ----------

    chapter_contents = [
        # 第一章
        ("第一章  Transformer 与注意力机制", [
            ("1.1 自注意力机制原理",
             "自注意力机制（Self-Attention）是 Transformer 的核心组件。它允许模型在处理每个 Token 时，"
             "能够关注输入序列中的所有其他 Token，从而捕获长距离依赖关系。计算过程可以描述为："
             "首先将输入向量通过三个线性变换分别映射为 Query（Q）、Key（K）和 Value（V），"
             "然后计算 Q 与 K 的点积并进行缩放和 Softmax 归一化，最后与 V 加权求和得到输出。"),
            ("1.2 多头注意力",
             "多头注意力（Multi-Head Attention）将输入空间划分为 h 个子空间，在每个子空间独立计算"
             "注意力，最后拼接所有子空间的输出。这使模型能够同时关注不同位置的不同类型的信息。"
             "例如，一个 Head 可能关注语法关系，另一个 Head 关注语义相似性。GPT-4 等现代模型通常"
             "使用 32-128 个 Head。"),
            ("1.3 位置编码",
             "由于 Self-Attention 本身不包含位置信息，需要额外添加位置编码（Positional Encoding）。"
             "原始 Transformer 使用正弦余弦函数生成固定位置编码；后续研究提出了旋转位置编码"
             "（RoPE）和 ALiBi 等方案，在支持更长上下文的同时保持良好的泛化能力。RoPE 通过"
             "旋转向量的方式将相对位置信息编码到注意力计算中，被 LLaMA、GPT-NeoX 等模型广泛采用。"),
            ("1.4 KV Cache 与推理优化",
             "在自回归生成过程中，每一步都需要计算当前 Token 对所有之前 Token 的注意力。"
             "KV Cache 技术将已计算的 Key 和 Value 向量缓存起来，避免重复计算，将推理的时间复杂度"
             "从 O(n²) 降低到 O(n)。但 KV Cache 的显存占用随序列长度线性增长，成为处理长上下文的"
             "主要瓶颈之一。常见优化方案包括 GQA（Grouped Query Attention）、MQA（Multi-Query "
             "Attention）等。"),
        ]),
        # 第二章
        ("第二章  预训练与微调技术", [
            ("2.1 预训练范式",
             "大语言模型的预训练通常采用自回归语言建模目标（Causal Language Modeling），即预测下一个 "
             "Token。训练数据来自互联网大规模文本语料（如 Common Crawl、Wikipedia、GitHub 代码等），"
             "Token 数量通常在万亿级别。预训练阶段需要数千张 GPU 运行数周甚至数月。"),
            ("2.2 SFT 监督微调",
             "预训练完成后，模型具备了基础的语言理解和生成能力，但无法很好地遵循人类指令。"
             "监督微调（Supervised Fine-Tuning, SFT）使用高质量的指令-回答对数据集对模型进行"
             "二次训练，使其学会按照指令格式回答问题。SFT 数据质量远比数量重要。"),
            ("2.3 RLHF 与 DPO",
             "人类反馈强化学习（RLHF）通过训练奖励模型（Reward Model）来评估模型输出的质量，"
             "然后使用 PPO 算法优化模型策略使其获得更高的奖励。DPO（Direct Preference Optimization）"
             "则省去了奖励模型的训练，直接从人类偏好数据中学习策略，简化了训练流程。"),
            ("2.4 LoRA 与 QLoRA",
             "全参数微调需要巨大的计算资源，LoRA（Low-Rank Adaptation）通过在原始权重矩阵旁"
             "添加低秩分解矩阵（A·B，rank << d），仅训练这些新增参数，大幅降低显存和计算需求。"
             "QLoRA 进一步将模型权重量化为 4-bit，配合 LoRA 在消费级 GPU 上也能微调大模型。"),
        ]),
        # 第三章
        ("第三章  Prompt Engineering", [
            ("3.1 Prompt 设计原则",
             "有效的 Prompt 应当清晰、具体，包含足够的上下文信息。常见的设计原则包括：提供明确的"
             "任务说明（你是一个 XX 专家）、给出输出格式要求（请用 JSON 格式输出）、提供示例"
             "（Few-shot）、以及步骤化引导（先分析…再总结…最后给出建议）。"),
            ("3.2 思维链 (Chain-of-Thought)",
             "思维链（CoT）提示通过要求模型「逐步思考」来提升推理质量。研究表明，在 Prompt 中"
             "加入「Let's think step by step」等引导语，可以显著提升数学推理、逻辑推理等任务的准确率。"
             "变种包括 Self-Consistency（多次采样取多数投票）和 Tree-of-Thought（树状分支探索）。"),
            ("3.3 RAG 场景的 Prompt",
             "在 RAG 系统中，Prompt 需要将检索到的上下文信息与用户查询结合。典型模板为：\n"
             "'你是一个知识助手。根据以下参考资料回答用户的问题。如果资料中没有相关信息，"
             "请如实告知无法回答。\n\n参考资料：{context}\n\n用户问题：{query}'\n\n"
             "需要注意上下文的排列顺序、长度控制和格式标注，以提升 LLM 的答案质量。"),
            ("3.4 Prompt 注入与安全",
             "Prompt 注入是指恶意用户通过精心构造的输入来绕过系统 Prompt 的约束，使 LLM 执行"
             "非预期的行为。防御措施包括：输入过滤与 sanitization、系统 Prompt 与用户输入的"
             "明确分隔、输出格式约束检验、以及使用 Constitutional AI 等方法训练模型的拒绝能力。"),
        ]),
        # 第四章
        ("第四章  检索增强生成（RAG）", [
            ("4.1 RAG 概述",
             "RAG 通过在 LLM 生成前引入信息检索阶段，将相关外部知识注入到生成上下文中，"
             "从而减少幻觉、提供实时知识更新、并使回答可溯源。RAG 已成为企业级 AI 应用的"
             "标准架构模式，广泛应用于知识库问答、文档分析、客服对话等场景。"),
            ("4.2 RAG 链路分解",
             "完整的 RAG 链路包含以下核心阶段：\n"
             "1. 数据摄取（Ingestion）：解析文档 → 分块 → 增强 → 向量化 → 存储\n"
             "2. 查询处理（Query Processing）：查询改写 → 关键词提取\n"
             "3. 检索（Retrieval）：稠密检索 + 稀疏检索 → 融合\n"
             "4. 重排序（Reranking）：Cross-Encoder 或 LLM 精排\n"
             "5. 生成（Generation）：Prompt 构建 → LLM 生成 → 引用标注"),
            ("4.3 RAG 常见问题",
             "常见的 RAG 失败模式包括：检索不到相关文档（召回率低）、检索到的文档不精确"
             "（精确率低）、LLM 未能正确利用上下文（忠实度低）、以及分块不合理导致关键信息"
             "被截断。针对这些问题，可以从分块策略、检索方法、重排序和 Prompt 设计等多个维度"
             "进行优化。"),
            ("4.4 面试高频问题",
             "- Q: RAG 和微调的区别？各自适用场景？\n"
             "- Q: 如何评估 RAG 系统的质量？有哪些评估指标？\n"
             "- Q: RAG 系统中如何处理多跳推理问题？\n"
             "- Q: 如何解决 RAG 中的幻觉问题？\n"
             "- Q: 混合检索相比纯向量检索有什么优势？"),
        ]),
        # 第五章
        ("第五章  向量数据库与 Embedding", [
            ("5.1 Embedding 模型选型",
             "选择 Embedding 模型时需要综合考虑以下因素：向量维度（影响存储和计算成本）、"
             "推理速度（影响摄取和查询延迟）、语义质量（尤其是中文和多语言能力）、以及部署方式"
             "（云端 API vs 本地推理）。对于中文场景，BGE-large-zh 和 GTE-large-zh 在 MTEB "
             "中文榜单上表现最佳。"),
            ("5.2 向量数据库对比",
             "主流向量数据库包括 ChromaDB（轻量级、适合快速原型）、FAISS（Facebook 开源、"
             "高性能 ANN 搜索）、Milvus（分布式、适合大规模生产环境）、Pinecone（全托管云服务）、"
             "和 Weaviate（支持混合搜索和 GraphQL）。本项目选择 ChromaDB，因其简单易用、"
             "支持持久化、且与 Python 生态集成良好。"),
            ("5.3 ANN 索引算法",
             "近似最近邻（ANN）算法是向量检索的核心。常见方案包括：\n"
             "- HNSW（Hierarchical Navigable Small World）：多层图结构，查询快但构建慢\n"
             "- IVF（Inverted File Index）：倒排索引 + 聚类，适合大规模数据\n"
             "- PQ（Product Quantization）：向量压缩，大幅降低存储\n"
             "ChromaDB 默认使用 HNSW 算法，对于本项目的数据规模是最优选择。"),
            ("5.4 Embedding 优化技巧",
             "提升 Embedding 质量的技巧：\n"
             "1. 在 Chunk 前添加 Instruction Prefix（如「为检索优化：」）\n"
             "2. 使用 Matryoshka Embedding 按需截断维度\n"
             "3. 对查询做 HyDE（Hypothetical Document Embedding）扩展\n"
             "4. 使用领域微调的 Embedding 模型提升专业领域效果"),
        ]),
        # 第六章
        ("第六章  混合检索与重排序", [
            ("6.1 稠密检索 vs 稀疏检索",
             "稠密检索基于语义向量相似度，擅长处理同义词、近义词和语义理解；稀疏检索基于关键词"
             "匹配（如 BM25），擅长处理专有名词、精确数字和低频词汇。两者具有天然的互补性："
             "稠密检索解决「语义漂移」问题，稀疏检索解决「精确匹配」问题。"),
            ("6.2 RRF 融合策略",
             "RRF（Reciprocal Rank Fusion）是最简单有效的排名融合方法。公式："
             "score(d) = Σ 1/(k + rank_i(d))，其中 k 通常取 60。RRF 的优势是与分数量纲无关，"
             "可以直接融合不同系统的排名结果。相比于 CombSUM、CombMNZ 等权重方案，"
             "RRF 不需要调参，鲁棒性更好。"),
            ("6.3 Cross-Encoder Reranker",
             "Cross-Encoder 将查询和文档拼接为一个序列输入 BERT 类模型，通过全交互注意力"
             "计算精细的相关性分数。常用模型包括 ms-marco-MiniLM-L-12-v2 和 BGE-reranker。"
             "Cross-Encoder 精度高但速度慢（O(n) 次前向传播），通常用于对粗排 Top-50 结果"
             "进行精排，最终取 Top-3~5 作为最终结果。"),
            ("6.4 LLM Reranker",
             "使用 LLM（如 GPT-4o）作为 Reranker，通过 Prompt 让模型对每个 Chunk 与 Query 的"
             "相关性打分（1-10 分），然后按分数重排。优势是精度高、可解释性强；缺点是延迟高、"
             "成本大。适合对准确率要求极高、对延迟不敏感的场景。"),
        ]),
        # 第七章
        ("第七章  文档处理与分块策略", [
            ("7.1 文档解析",
             "文档解析是 RAG 数据摄取的第一步。PDF 解析面临的挑战包括：表格识别、多栏排版、"
             "扫描件 OCR、图片提取、以及页眉页脚过滤。本项目使用 MarkItDown 库将 PDF 转换为 "
             "Markdown 格式，保留标题层级和格式信息，为后续分块提供结构化线索。"),
            ("7.2 分块策略选择",
             "不同类型的文档适合不同的分块策略：结构化技术文档适合按标题层级切分；长篇叙述性文本"
             "适合语义分块（基于 Embedding 相似度检测主题转换点）；代码文档适合按函数/类为单位"
             "切分。本项目默认使用递归字符切分（chunk_size=1000, overlap=200），并可通过配置切换。"),
            ("7.3 元数据增强",
             "为 Chunk 附加丰富的元数据可以显著提升检索效果。本项目通过 LLM 为每个 Chunk 生成："
             "- title：概括 Chunk 主题的短标题\n"
             "- summary：50-100 字的内容摘要\n"
             "- tags：3-5 个关键词标签\n"
             "这些元数据可用于检索时的辅助过滤、在搜索结果中提供快速预览。"),
            ("7.4 图片处理流程",
             "对于包含图片的 PDF，系统会：\n"
             "1. 在解析阶段提取嵌入图片，以 SHA256 哈希命名存储\n"
             "2. 调用 Vision LLM（如 GPT-4o）生成中文图片描述\n"
             "3. 将图片描述注入对应 Chunk 的 metadata\n"
             "4. 在查询时可通过文字描述匹配到相关图片\n"
             "5. MCP 工具返回结果时包含 Base64 编码的图片预览"),
        ]),
        # 第八章
        ("第八章  Agent 与工具调用", [
            ("8.1 Agent 基础概念",
             "Agent 是能够自主感知环境、规划任务、执行动作并根据反馈调整策略的 AI 系统。"
             "与简单的 Prompt → Response 模式不同，Agent 引入了工具调用、记忆管理和反思机制，"
             "使 LLM 能够处理需要多步推理和外部交互的复杂任务。"),
            ("8.2 工具调用机制",
             "工具调用（Function Calling / Tool Use）是 Agent 的核心能力。现代 LLM 支持在"
             "对话中生成结构化的工具调用请求（JSON 格式），由运行时执行对应功能后将结果返回给"
             "模型。常见工具类型包括：搜索引擎、数据库查询、计算器、代码执行器、文件操作等。"),
            ("8.3 MCP 协议详解",
             "Model Context Protocol (MCP) 标准化了 LLM 与工具之间的通信协议。核心接口包括：\n"
             "- tools/list：返回可用工具列表及其参数 Schema\n"
             "- tools/call：执行指定工具并返回结果\n"
             "- resources/list：列出可访问的资源（如文件、数据库）\n"
             "本项目的 MCP Server 通过 Stdio 传输层与 VS Code Copilot 集成。"),
            ("8.4 Agent 设计模式",
             "常见的 Agent 设计模式包括：\n"
             "- ReAct：Reasoning + Acting 交替进行\n"
             "- Plan-and-Execute：先制定完整计划再逐步执行\n"
             "- Reflection：执行后自我反思并修正\n"
             "- Multi-Agent：多个 Agent 协作完成任务，各自负责不同职能"),
        ]),
        # 第九章
        ("第九章  模型评估与基准测试", [
            ("9.1 RAG 评估框架",
             "RAG 系统的评估需要同时考虑检索质量和生成质量两个维度。检索维度关注的是能否"
             "找到正确的文档（Hit Rate、MRR、NDCG）；生成维度关注的是 LLM 输出的质量"
             "（Faithfulness、Answer Relevancy、Context Precision）。"),
            ("9.2 Ragas 评估工具",
             "Ragas 是一个专门用于 RAG 系统评估的开源框架。它提供了一系列基于 LLM-as-Judge "
             "的评估指标：Faithfulness 衡量回答是否忠实于检索上下文，Answer Relevancy 衡量"
             "回答与问题的相关度，Context Precision 衡量检索上下文中相关信息的占比。"
             "Ragas 通过调用 LLM 对回答进行自动评分，无需人工标注。"),
            ("9.3 Golden Test Set",
             "Golden Test Set 是一组预定义的查询-期望答案对，用于批量评估系统的端到端质量。"
             "构建 Golden Test Set 时应覆盖不同类型的查询：事实性问题、推理性问题、多跳问题、"
             "否定查询等。本项目在 tests/fixtures/golden_test_set.json 中维护了测试集。"),
            ("9.4 A/B 测试方法",
             "对 RAG 系统的改动（如切换 Embedding 模型、调整分块参数）需要通过 A/B 测试验证"
             "效果。方法是在相同的 Golden Test Set 上分别运行改动前后的系统，对比各项指标。"
             "Evaluation Panel 页面的 History 功能支持保存和对比历史评估记录。"),
        ]),
        # 第十章
        ("第十章  推理优化与部署", [
            ("10.1 模型量化",
             "模型量化将浮点权重转换为低精度表示（如 INT8、INT4、FP16），大幅降低模型的"
             "存储空间和推理计算量。常用方案包括：GPTQ（Post-Training Quantization）、"
             "AWQ（Activation-aware Weight Quantization）和 bitsandbytes（NF4 量化）。"
             "4-bit 量化通常可将模型大小减少 75%，性能损失在 1-3% 以内。"),
            ("10.2 推理框架",
             "主流的 LLM 推理框架包括：\n"
             "- vLLM：支持 PagedAttention，内存效率高\n"
             "- TGI（Text Generation Inference）：HuggingFace 出品\n"
             "- Ollama：本地部署一键运行\n"
             "- LM Studio：图形化本地部署工具\n"
             "- TensorRT-LLM：NVIDIA 官方优化框架\n"
             "选择框架时需综合考虑吞吐量需求、硬件条件和易用性。"),
            ("10.3 Serving 策略",
             "生产环境中的 LLM Serving 需要考虑：并发请求管理（请求队列 + 批处理）、"
             "流式输出（Server-Sent Events / WebSocket）、负载均衡（多实例 + Gateway）、"
             "以及故障恢复（健康检查 + 自动重启）。对于 RAG 应用，还需要考虑 Embedding "
             "服务和向量数据库的独立扩展。"),
            ("10.4 成本优化",
             "使用云端 API 的成本优化策略：\n"
             "1. 语义缓存减少重复调用\n"
             "2. 合理设置 max_tokens 避免浪费\n"
             "3. 使用较小模型做初筛，大模型做精排\n"
             "4. 对非关键功能使用更便宜的模型（如 Chunk Refiner 用较小模型）\n"
             "5. 批量 Embedding 减少 API 调用次数"),
        ]),
        # 第十一章
        ("第十一章  多模态大模型", [
            ("11.1 视觉语言模型 (VLM)",
             "视觉语言模型（如 GPT-4o、Claude Vision、Gemini）能够同时理解文本和图像，"
             "是实现多模态 RAG 的基础。在本项目中，VLM 用于为 PDF 中提取的图片生成中文描述"
             "（Image Captioning），使图片内容也可以通过文字检索被发现。"),
            ("11.2 多模态 RAG",
             "多模态 RAG 将检索范围从纯文本扩展到图文混合内容。实现思路有两种：\n"
             "1. 将图片转化为文本描述后统一做文本检索（本项目采用方案）\n"
             "2. 使用 CLIP 等多模态 Embedding 模型同时编码文本和图片\n"
             "方案 1 实现简单、兼容性好；方案 2 保留了更丰富的视觉信息但复杂度更高。"),
            ("11.3 图片描述生成最佳实践",
             "生成高质量 Image Caption 的关键：\n"
             "1. 使用具体的 Prompt 指导描述重点（如「请详细描述图中的流程和数据」）\n"
             "2. 为不同类型的图片使用不同的 Prompt（截图 vs 照片 vs 图表）\n"
             "3. 输出中文描述以匹配中文检索需求\n"
             "4. 限制描述长度，避免过长的 caption 干扰检索"),
            ("11.4 OCR 与文档理解",
             "对于扫描件 PDF，需要使用 OCR（光学字符识别）提取文字。现代 OCR 方案包括 "
             "Tesseract（开源）、Azure Document Intelligence（云服务）和 PaddleOCR（百度开源）。"
             "结合 Layout 分析模型可以进一步理解文档版面结构，正确识别表格、标题和段落。"),
        ]),
        # 第十二章
        ("第十二章  安全与对齐", [
            ("12.1 对齐技术",
             "模型对齐（Alignment）旨在使 LLM 的行为符合人类价值观和意图。主要手段包括 RLHF、"
             "DPO、Constitutional AI 等。对齐的目标通常概括为 HHH 原则：Helpful（有帮助）、"
             "Harmless（无害）、Honest（诚实）。"),
            ("12.2 RAG 安全注意事项",
             "RAG 系统面临的安全风险包括：\n"
             "1. 知识库投毒：恶意文档被摄入知识库，污染检索结果\n"
             "2. Prompt 注入：用户通过查询注入恶意指令\n"
             "3. 数据泄露：敏感文档内容通过检索结果暴露\n"
             "4. 引用伪造：LLM 编造不存在的引用来源"),
            ("12.3 防御措施",
             "针对上述风险的防御方案：\n"
             "1. 文档摄入时进行内容审查和分类\n"
             "2. 查询输入过滤和 sanitization\n"
             "3. 基于角色的访问控制（RBAC），不同用户只能检索授权文档\n"
             "4. 输出检验：验证引用的 chunk_id 和 source 确实存在\n"
             "5. 审计日志：记录所有查询和返回内容，便于追溯"),
            ("12.4 红队测试",
             "红队测试（Red Teaming）通过模拟攻击来发现系统安全漏洞。对 RAG 系统，"
             "红队测试应覆盖：恶意查询（尝试提取系统 Prompt）、越狱攻击（绕过安全限制）、"
             "数据提取攻击（尝试获取完整文档内容）等场景。建议定期进行红队评估。"),
        ]),
        # 第十三章
        ("第十三章  行业应用案例", [
            ("13.1 企业知识库",
             "企业内部知识库是 RAG 最典型的应用场景。核心需求包括：多格式文档支持、"
             "权限控制、实时更新和高可用性。典型架构为：文档管理系统 → 自动摄取 Pipeline → "
             "向量数据库 → RAG API → 企业聊天机器人/工单系统集成。"),
            ("13.2 智能客服",
             "基于 RAG 的智能客服系统将产品文档、FAQ、历史工单等作为知识源，用户提问时"
             "检索相关内容并生成回答。相比纯 LLM 客服，RAG 客服的优势是回答更准确、可溯源、"
             "且可以通过更新知识库快速响应新产品/新政策变更。"),
            ("13.3 代码助手",
             "代码助手（如 GitHub Copilot）可以通过 RAG 技术接入项目代码库和文档，"
             "使 LLM 在生成代码时能够参考项目的现有实现和约定。MCP 协议为此提供了标准化"
             "接口，使 AI 代码助手能够动态发现和查询项目的知识库。"),
            ("13.4 法律/医疗文档分析",
             "在法律和医疗等专业领域，RAG 系统可以帮助专业人员快速检索和分析大量文档。"
             "这些场景对准确性要求极高，通常需要：领域微调的 Embedding 模型、严格的引用追溯"
             "机制、以及人工审核环节。RAG 在此类场景中作为「辅助工具」而非「替代决策者」。"),
        ]),
        # 第十四章
        ("第十四章  面试高频问题精选", [
            ("14.1 RAG 相关问题",
             "Q1: 解释 RAG 的工作原理，以及它如何解决 LLM 的幻觉问题？\n"
             "Q2: 混合检索（Hybrid Search）的原理和优势是什么？\n"
             "Q3: Cross-Encoder 和 Bi-Encoder 的区别？在 RAG 中各自的角色？\n"
             "Q4: 你是如何设计文档分块策略的？考虑了哪些因素？\n"
             "Q5: RAG vs 微调（Fine-tuning），分别在什么场景下使用？"),
            ("14.2 Embedding 相关问题",
             "Q1: 余弦相似度和内积（Dot Product）有什么区别？什么时候用哪个？\n"
             "Q2: 什么是 ANN（近似最近邻）？常见的 ANN 算法有哪些？\n"
             "Q3: 如何评估 Embedding 模型的质量？有哪些 Benchmark？\n"
             "Q4: Embedding 维度越高越好吗？维度对检索效果和性能有什么影响？\n"
             "Q5: 如何处理「领域特定词汇」的 Embedding 效果不好的问题？"),
            ("14.3 系统设计问题",
             "Q1: 设计一个支持百万级文档的 RAG 系统，你会怎么做？\n"
             "Q2: 如何实现 RAG 系统的增量更新（新增/删除/修改文档）？\n"
             "Q3: 如何监控 RAG 系统的线上质量？有哪些关键指标？\n"
             "Q4: 如何处理 RAG 中的多语言问题？\n"
             "Q5: 你的 RAG 项目中遇到了什么技术挑战？如何解决的？"),
            ("14.4 Agent 相关问题",
             "Q1: 什么是 Agent？和普通的 LLM 对话有什么区别？\n"
             "Q2: 解释 ReAct 模式的工作流程。\n"
             "Q3: 工具调用（Function Calling）是如何实现的？\n"
             "Q4: 多 Agent 协作有哪些常见模式？\n"
             "Q5: 如何评估 Agent 的能力和可靠性？"),
        ]),
        # 第十五章
        ("第十五章  项目实战经验总结", [
            ("15.1 项目架构回顾",
             "本项目采用 Modular RAG 架构，核心模块包括：文档解析（MarkItDown）、"
             "智能分块（RecursiveCharacterTextSplitter + LLM Refiner）、双路编码"
             "（Azure Embedding + BM25/jieba）、混合检索（RRF 融合）、可选重排序"
             "（Cross-Encoder / LLM Reranker）、以及 MCP Server 对外接口。全链路采用"
             "配置驱动的工厂模式，支持一键切换 Provider。"),
            ("15.2 技术亮点与面试话术",
             "简历和面试中可以重点突出：\n"
             "1. 全链路可观测性：Streamlit Dashboard + 结构化 Trace + 评估面板\n"
             "2. 混合检索策略：Dense + Sparse + RRF 融合 + 可选 Reranking\n"
             "3. 多模态支持：PDF 图片提取 + Vision LLM Captioning\n"
             "4. 可插拔架构：工厂模式 + 配置驱动，零代码切换 Provider\n"
             "5. 数据完整性：SHA256 幂等摄取 + 跨存储级联删除"),
            ("15.3 踩坑记录",
             "开发过程中遇到的典型问题和解决方案：\n"
             "1. 中文 BM25 分词：需使用 jieba 替代默认英文分词器\n"
             "2. PDF 表格解析：MarkItDown 对复杂表格支持有限，可能丢失格式\n"
             "3. 向量维度不匹配：切换 Embedding 模型后需要重新摄取所有文档\n"
             "4. Trace 文件过大：需要定期清理或引入日志轮转\n"
             "5. Windows 编码问题：控制台输出需要显式设置 UTF-8 编码"),
            ("15.4 下一步计划",
             "可以继续迭代的方向：\n"
             "- 引入 GraphRAG，结合知识图谬提升多跳推理能力\n"
             "- 添加 Streaming Response 流式生成\n"
             "- 接入更多向量数据库（FAISS、Milvus）\n"
             "- 实现自动化 CI/CD 测试管线\n"
             "- 支持更多文档格式（HTML、代码文件、音视频转写）"),
        ]),
    ]

    for ch_title, sections in chapter_contents:
        elems.append(Paragraph(ch_title, s["h1"]))
        for sec_title, sec_body in sections:
            elems.append(Paragraph(sec_title, s["h2"]))
            # Split by \n for multi-line paragraphs
            for para in sec_body.split("\n"):
                stripped = para.strip()
                if stripped:
                    elems.append(Paragraph(stripped, s["body"]))
        # Add padding content to ensure ~2 pages per chapter
        elems.append(Spacer(1, 0.15 * inch))
        elems.append(Paragraph("本章小结", s["h2"]))
        elems.append(Paragraph(
            f"以上介绍了{ch_title[4:]}的核心概念和关键技术要点。"
            "理解这些知识对于构建高质量的 RAG 系统至关重要。在实际面试中，"
            "面试官往往会从基础概念出发，逐步深入到实现细节和工程经验。"
            "建议读者在阅读本章内容的基础上，结合项目代码进行实践验证，"
            "加深对各项技术的理解。同时，注意关注该领域的最新进展，"
            "因为大模型技术发展迅速，新的方法和工具不断涌现。", s["body"]))
        elems.append(Paragraph(
            "在准备面试时，建议将本章的知识点与实际项目经验相结合。"
            "不仅要能够清晰地解释技术原理，还要能够说明在实际项目中"
            "如何选型、如何调优、遇到了哪些问题以及如何解决。"
            "这种理论与实践结合的回答方式，能够给面试官留下深刻印象。"
            "此外，建议准备一些具体的数据和指标来支撑你的技术决策，"
            "例如选择某个 Embedding 模型后检索精度提升了多少、"
            "引入 Reranker 后 Top-3 命中率从 X 提升到 Y 等。", s["body"]))
        elems.append(Paragraph("延伸思考", s["h2"]))
        elems.append(Paragraph(
            "学习技术知识不能仅停留在表面，需要深入思考每项技术背后的设计动机和取舍。"
            "例如，为什么 RAG 系统要采用两阶段检索（粗排 + 精排）？这是因为精排模型"
            "（如 Cross-Encoder）虽然精度高，但计算成本大，无法对全库进行打分。"
            "通过粗排快速筛选候选集，再用精排做精细评估，既保证了精度又控制了延迟。"
            "这种'漏斗式'架构思想在搜索引擎、推荐系统等领域都有广泛应用。"
            "面试中如果能展示出这种跨领域的技术视野和工程直觉，会非常加分。"
            "同时，也要关注各种技术的局限性和适用边界。没有银弹，每种方案都有其"
            "最佳应用场景。能够根据具体需求选择合适的技术方案，是高级工程师的核心能力。", s["body"]))
        elems.append(PageBreak())

    # Build
    doc.build(elems)
    print(f"✅ Generated: {output}")


# ===================================================================
# Main
# ===================================================================

def main() -> None:
    output_dir = Path(__file__).parent / "sample_documents"
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_chinese_technical_doc(output_dir / "chinese_technical_doc.pdf")
    generate_chinese_table_chart_doc(output_dir / "chinese_table_chart_doc.pdf")
    generate_chinese_long_doc(output_dir / "chinese_long_doc.pdf")

    print("\n🎉 All QA test PDFs generated successfully!")


if __name__ == "__main__":
    main()
