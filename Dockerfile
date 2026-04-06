# ============================================================
# 九洲 RAG 管理平台 — 多阶段 Docker 构建
#
# Stage 1: Node.js 构建 Vue 前端
# Stage 2: Python 运行后端 + 托管静态文件
# ============================================================

# ── Stage 1: Build frontend ─────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --registry https://registry.npmmirror.com
COPY web/ ./
RUN npm run build


# ── Stage 2: Python runtime ─────────────────────────────────
FROM python:3.11-slim AS runtime

# 系统依赖：Tesseract OCR + 中文语言包 + 构建工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先拷贝 pyproject.toml 和 src/ 用于 pip install（利用缓存层）
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 使用 pyproject.toml 声明式依赖安装（自动解析平台匹配版本）
RUN pip install --no-cache-dir \
    --default-timeout=120 \
    --retries=3 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    ".[ml]" \
    python-dotenv \
    python-multipart \
    tantivy \
    redis

# 拷贝后端源码
COPY api/ ./api/
COPY config/ ./config/

# 拷贝前端构建产物
COPY --from=frontend-builder /build/web/dist ./web/dist

# 创建数据目录（运行时通过 volume 挂载）
RUN mkdir -p data/db data/images data/exports data/solution_files logs

# ── 源码隐藏：编译 Python 字节码，删除 .py 源文件 ────────────
# 将 src/ 和 api/ 下所有 .py 文件编译为 .pyc 字节码
# 仅发布 .pyc 文件，保护源代码不被查看
RUN python -m compileall -b -q src/ api/ && \
    find src/ api/ -name "*.py" -not -name "__init__.py" -delete && \
    find src/ api/ -name "__pycache__" -exec sh -c 'mv "$1"/*.pyc "$(dirname "$1")/" 2>/dev/null; rm -rf "$1"' _ {} \; 2>/dev/null || true

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
