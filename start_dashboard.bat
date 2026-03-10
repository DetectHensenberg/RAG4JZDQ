@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Modular RAG Dashboard...
echo.
python scripts/start_dashboard.py %*
pause
