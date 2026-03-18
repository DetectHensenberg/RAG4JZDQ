@echo off
chcp 65001 >nul
echo ============================================
echo   Tesseract OCR 自动安装脚本
echo ============================================
echo.

set TESSERACT_URL=https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe
set TESSERACT_INSTALLER=%TEMP%\tesseract-installer.exe

echo [1/3] 检查是否已安装...
where tesseract >nul 2>&1
if %errorlevel%==0 (
    echo Tesseract 已安装！
    tesseract --version
    goto :end
)

if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo Tesseract 已安装在默认路径！
    "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
    goto :end
)

echo [2/3] 下载 Tesseract 安装程序...
echo 下载地址: %TESSERACT_URL%
echo.

powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%TESSERACT_URL%' -OutFile '%TESSERACT_INSTALLER%'}"

if not exist "%TESSERACT_INSTALLER%" (
    echo 下载失败！请手动下载安装：
    echo https://github.com/UB-Mannheim/tesseract/wiki
    pause
    exit /b 1
)

echo [3/3] 启动安装程序...
echo.
echo ⚠️  安装时请注意：
echo    1. 勾选 "Additional language data" 
echo    2. 选择 "Chinese Simplified" 和 "Chinese Traditional"
echo    3. 使用默认安装路径
echo.
pause

start /wait "" "%TESSERACT_INSTALLER%"

echo.
echo 安装完成！验证安装...
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo ✅ Tesseract 安装成功！
    "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
) else (
    echo ❌ 安装可能未完成，请检查
)

:end
echo.
pause
