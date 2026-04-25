# RAG 项目环境安装脚本 - Windows PowerShell
# 使用 Gitee 源

param(
    [string]$RepoUrl = "https://gitee.com/你的用户名/RAG.git",
    [string]$InstallDir = "D:\Workspace\project\RAG"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Msg)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host $Msg -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
}

# 检查 Python
Write-Step "1. 检查 Python"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Python 未安装，请先从 https://www.python.org/downloads/ 下载安装" -ForegroundColor Red
    Write-Host "安装后请重新运行此脚本" -ForegroundColor Yellow
    exit 1
}
$pythonVersion = python --version
Write-Host "已安装: $pythonVersion" -ForegroundColor Green

# 检查 pip
Write-Step "2. 检查 pip"
$pipVersion = pip --version
Write-Host "已安装: $pipVersion" -ForegroundColor Green

# 检查/安装 Git
Write-Step "3. 检查 Git"
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    Write-Host "Git 未安装，正在下载安装..." -ForegroundColor Yellow
    $gitInstaller = "$env:TEMP\git-installer.exe"
    Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe" -OutFile $gitInstaller
    Start-Process -FilePath $gitInstaller -Args "/SILENT" -Wait
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "Git 安装完成" -ForegroundColor Green
}

$gitVersion = git --version
Write-Host "已安装: $gitVersion" -ForegroundColor Green

# 配置 Git 用户信息
Write-Step "4. 配置 Git"
if (-not (git config --global user.name)) {
    $name = Read-Host "请输入你的 Git 用户名"
    git config --global user.name $name
}
if (-not (git config --global user.email)) {
    $email = Read-Host "请输入你的 Git 邮箱"
    git config --global user.email $email
}
Write-Host "Git 配置完成" -ForegroundColor Green

# 设置 Gitee 加速（可选）
git config --global url."https://gitee.com/".insteadOf "https://github.com/"

# 克隆或更新仓库
Write-Step "5. 克隆/更新项目"
if (Test-Path $InstallDir) {
    Write-Host "项目已存在，更新代码..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
} else {
    Write-Host "正在克隆仓库..." -ForegroundColor Yellow
    git clone $RepoUrl $InstallDir
    Set-Location $InstallDir
}
Write-Host "项目目录: $(Get-Location)" -ForegroundColor Green

# 安装项目依赖
Write-Step "6. 安装项目依赖"
pip install -r requirements.txt --quiet
Write-Host "依赖安装完成" -ForegroundColor Green

# 复制环境变量文件
Write-Step "7. 配置环境变量"
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "已创建 .env 文件，请编辑填入你的 API Key" -ForegroundColor Yellow
    }
} else {
    Write-Host ".env 文件已存在" -ForegroundColor Green
}

Write-Step "安装完成!"
Write-Host "运行以下命令启动项目:" -ForegroundColor Cyan
Write-Host "  python main.py" -ForegroundColor White
