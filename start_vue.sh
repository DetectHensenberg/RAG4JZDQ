#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo "  九洲 RAG 管理平台 (Vue 版)"
echo "============================================"

if [ -f "web/dist/index.html" ]; then
    echo "[生产模式] 启动 FastAPI + 静态文件..."
    python -m uvicorn api.main:app --host localhost --port 8000
else
    echo "[开发模式] 启动前后端..."
    python -m uvicorn api.main:app --reload --port 8000 &
    cd web && npm run dev &
    echo ""
    echo "前端访问: http://localhost:5173"
    echo "API 文档: http://localhost:8000/api/docs"
    wait
fi
