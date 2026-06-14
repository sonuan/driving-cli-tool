# Driving CLI Windows 安装脚本
# 用法（PowerShell）：
#   irm https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/install.ps1 | iex
#
# 或下载后本地执行：
#   .\install.ps1
#   .\install.ps1 -BinaryUrl "http://your-internal-server/driving.exe"

param(
    [string]$BinaryUrl = "https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist-windows/driving.exe"
)

$ErrorActionPreference = "Stop"

function Write-Green($msg)  { Write-Host $msg -ForegroundColor Green }
function Write-Yellow($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Red($msg)    { Write-Host $msg -ForegroundColor Red }

Write-Green "========================================"
Write-Green " Driving CLI 安装程序（Windows）"
Write-Green "========================================"
Write-Host ""

$InstallDir  = "$env:USERPROFILE\.driving-cli"
$BinaryPath  = "$InstallDir\driving.exe"

Write-Host "  安装目录：$InstallDir"
Write-Host "  下载地址：$BinaryUrl"
Write-Host ""

# 1. 创建安装目录
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 2. 下载二进制
Write-Yellow "正在下载 driving.exe..."
try {
    Invoke-WebRequest -Uri $BinaryUrl -OutFile $BinaryPath -UseBasicParsing
} catch {
    Write-Red "下载失败：$($_.Exception.Message)"
    Write-Host "请检查网络连接，或手动从以下地址下载后放置到 $BinaryPath："
    Write-Host "  $BinaryUrl"
    exit 1
}

if (-not (Test-Path $BinaryPath)) {
    Write-Red "下载后未找到文件，安装失败"
    exit 1
}

# 3. 将安装目录加入用户 PATH（永久生效，重开终端后有效）
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
    Write-Green "  ✓ 已将 $InstallDir 加入用户 PATH"
    Write-Yellow "  注意：需要重新打开终端后 driving 命令才能直接使用"
} else {
    Write-Host "  PATH 中已包含安装目录，无需修改"
}

# 4. 验证
Write-Host ""
Write-Green "✓ 安装成功！"
Write-Host ""
Write-Host "版本信息："
try {
    & $BinaryPath --version
} catch {
    Write-Yellow "无法自动验证，请重新打开终端后运行 'driving --version'"
}
Write-Host ""
Write-Host "提示："
Write-Host "  - 重新打开 PowerShell 或 cmd 后，直接运行 driving 命令"
Write-Host "  - 后续升级：driving update"
Write-Host ""
