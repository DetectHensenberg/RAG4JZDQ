@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   九洲 RAG 管理平台 - 一键安装
echo ============================================
echo.

REM ── Step 1: Check Python ──────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [✓] Python 已就绪

REM ── Step 2: Create venv ───────────────────────
if not exist ".venv" (
    echo [2/6] 正在创建虚拟环境...
    python -m venv .venv
    echo [✓] 虚拟环境创建完成
) else (
    echo [✓] 虚拟环境已存在
)

call .venv\Scripts\activate.bat

REM ── Step 3: Install dependencies ──────────────
echo [3/6] 正在安装 Python 依赖（可能需要几分钟）...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
if errorlevel 1 (
    echo [警告] 清华源安装失败，尝试默认源...
    pip install -r requirements.txt --quiet
)
echo [✓] Python 依赖安装完成

REM ── Step 4: Config files ──────────────────────
if not exist "config\settings.yaml" (
    echo [4/6] 正在生成配置文件...
    copy "config\settings.yaml.example" "config\settings.yaml" >nul
    echo [✓] 已从模板生成 config\settings.yaml
) else (
    echo [✓] config\settings.yaml 已存在，跳过
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [!] 已从模板生成 .env，请打开 .env 填入你的 API Key！
) else (
    echo [✓] .env 已存在，跳过
)

REM ── Step 5: Build frontend ────────────────────
if exist "web\package.json" (
    if not exist "web\dist\index.html" (
        echo [5/6] 正在构建前端...
        cd web
        call npm install --silent 2>nul
        call npm run build --silent 2>nul
        cd ..
        if exist "web\dist\index.html" (
            echo [✓] 前端构建完成
        ) else (
            echo [警告] 前端构建失败，请检查 Node.js 是否已安装
        )
    ) else (
        echo [✓] 前端已构建，跳过
    )
) else (
    echo [跳过] 未找到前端源码
)

REM ── Step 6: Create data dirs ──────────────────
echo [6/6] 正在创建数据目录...
if not exist "data\db" mkdir "data\db"
if not exist "data\images" mkdir "data\images"
if not exist "logs" mkdir "logs"
echo [✓] 数据目录就绪

echo.
echo ============================================
echo   安装完成！
echo ============================================
echo.
echo 下一步操作：
echo   1. 编辑 .env 文件，填入你的 DASHSCOPE_API_KEY
echo   2. 运行 start_vue.bat 启动平台
echo   3. 浏览器打开 http://localhost:8000
echo.
pause
