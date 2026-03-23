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
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
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

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
