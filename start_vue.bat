@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   九洲 RAG 管理平台 (Vue 版)
echo ============================================
echo.

REM Activate venv if present
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

REM Check if web/dist exists (production mode)
if exist "web\dist\index.html" (
    echo [生产模式] 启动 FastAPI + 静态文件...
    python -m uvicorn api.main:app --host localhost --port 8000
    goto :end
)

echo [开发模式] 同时启动前后端...
echo.

echo 正在启动 FastAPI 后端...
start "FastAPI" python -m uvicorn api.main:app --port 8001

echo 正在启动 Vue 前端...
cd web
start "Vue Dev" npm run dev
cd ..

echo.
echo 前端访问: http://localhost:5173
echo API 文档: http://localhost:8001/api/docs

:end
echo.
pause
