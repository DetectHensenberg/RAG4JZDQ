@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   九洲 RAG 管理平台 (Vue 版)
echo ============================================
echo.

REM Check if web/dist exists (production mode)
if exist "web\dist\index.html" (
    echo [生产模式] 启动 FastAPI + 静态文件...
    python -m uvicorn api.main:app --host localhost --port 8000
) else (
    echo [开发模式] 需要同时启动前后端...
    echo.
    echo 终端1: python -m uvicorn api.main:app --reload --port 8000
    echo 终端2: cd web ^&^& npm run dev
    echo.
    echo 正在启动 FastAPI 后端...
    start "FastAPI" cmd /k "python -m uvicorn api.main:app --reload --port 8000"
    echo 正在启动 Vue 前端...
    cd web
    start "Vue Dev" cmd /k "npm run dev"
    echo.
    echo 前端访问: http://localhost:5173
    echo API 文档: http://localhost:8000/api/docs
)
echo.
pause
