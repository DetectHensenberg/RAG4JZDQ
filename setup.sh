#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================"
echo "  九洲 RAG 管理平台 - 一键安装"
echo "============================================"
echo ""

# ── Step 1: Check Python ──────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.10+"
    exit 1
fi
echo "[✓] Python 已就绪"

# ── Step 2: Create venv ───────────────────────
if [ ! -d ".venv" ]; then
    echo "[2/6] 正在创建虚拟环境..."
    python3 -m venv .venv
    echo "[✓] 虚拟环境创建完成"
else
    echo "[✓] 虚拟环境已存在"
fi

source .venv/bin/activate

# ── Step 3: Install dependencies ──────────────
echo "[3/6] 正在安装 Python 依赖（可能需要几分钟）..."
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet 2>/dev/null \
    || pip install -r requirements.txt --quiet
echo "[✓] Python 依赖安装完成"

# ── Step 4: Config files ──────────────────────
if [ ! -f "config/settings.yaml" ]; then
    echo "[4/6] 正在生成配置文件..."
    cp config/settings.yaml.example config/settings.yaml
    echo "[✓] 已从模板生成 config/settings.yaml"
else
    echo "[✓] config/settings.yaml 已存在，跳过"
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[!] 已从模板生成 .env，请打开 .env 填入你的 API Key！"
else
    echo "[✓] .env 已存在，跳过"
fi

# ── Step 5: Build frontend ────────────────────
if [ -f "web/package.json" ] && [ ! -f "web/dist/index.html" ]; then
    echo "[5/6] 正在构建前端..."
    cd web
    npm install --silent 2>/dev/null
    npm run build --silent 2>/dev/null
    cd ..
    if [ -f "web/dist/index.html" ]; then
        echo "[✓] 前端构建完成"
    else
        echo "[警告] 前端构建失败，请检查 Node.js 是否已安装"
    fi
elif [ -f "web/dist/index.html" ]; then
    echo "[✓] 前端已构建，跳过"
fi

# ── Step 6: Create data dirs ──────────────────
echo "[6/6] 正在创建数据目录..."
mkdir -p data/db data/images logs
echo "[✓] 数据目录就绪"

echo ""
echo "============================================"
echo "  安装完成！"
echo "============================================"
echo ""
echo "下一步操作："
echo "  1. 编辑 .env 文件，填入你的 DASHSCOPE_API_KEY"
echo "  2. 运行 ./start_vue.sh 启动平台"
echo "  3. 浏览器打开 http://localhost:8000"
echo ""
