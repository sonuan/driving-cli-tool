# Driving CLI Windows 版本构建脚本
# 用法：在 Windows 机器（PowerShell）中运行
#   .\scripts\build-windows.ps1
#   .\scripts\build-windows.ps1 -Upload -DownloadUrl "http://your-server/driving.exe"
#
# 前提：Python 3.8+（python.org）、pip

param(
    [switch]$Upload,
    [string]$Server = "",
    [string]$DownloadUrl = "https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist-windows/driving.exe",
    [string]$VersionUrl = "",
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Write-Green($msg)  { Write-Host $msg -ForegroundColor Green }
function Write-Yellow($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Red($msg)    { Write-Host $msg -ForegroundColor Red }
function Write-Blue($msg)   { Write-Host $msg -ForegroundColor Cyan }

if ($Help) {
    Write-Host "用法: .\scripts\build-windows.ps1 [选项]"
    Write-Host ""
    Write-Host "选项:"
    Write-Host "  -Upload                上传到服务器（默认不上传）"
    Write-Host "  -Server <地址>         指定上传服务器地址"
    Write-Host "  -DownloadUrl <URL>     指定 version.json 中的 download_url_windows"
    Write-Host "  -VersionUrl <URL>      指定 version.json 的完整 URL"
    Write-Host "  -Help                  显示此帮助"
    exit 0
}

# 检查是否在项目根目录
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "driving_cli")) {
    Write-Red "错误：请在 driving-cli-tool 项目根目录中运行此脚本"
    exit 1
}

# 自动推导 VersionUrl
if (-not $VersionUrl -and $DownloadUrl) {
    $VersionUrl = $DownloadUrl -replace "/driving\.exe$", "/version.json"
    Write-Yellow "自动推导 version.json 地址: $VersionUrl"
}

$DistDir = "dist-windows"

Write-Green "========================================"
Write-Green " Driving CLI Windows 版本构建"
Write-Green "========================================"
Write-Host ""
Write-Host "  输出目录 : $DistDir"
Write-Host "  下载地址 : $DownloadUrl"
Write-Host ""

# 1. 安装 PyInstaller
Write-Blue "[STEP 1] 检查 PyInstaller..."
$pyiVersion = python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Yellow "PyInstaller 未安装，正在安装..."
    pip install pyinstaller
}
Write-Host "  PyInstaller 已就绪"

# 2. 清理旧构建产物
Write-Blue "[STEP 2] 清理旧构建..."
if (Test-Path $DistDir)  { Remove-Item -Recurse -Force $DistDir }
if (Test-Path "build")   { Remove-Item -Recurse -Force "build" }

# 3. 设置默认更新地址（写入 update.py，构建后还原）
if ($VersionUrl) {
    Write-Blue "[STEP 3] 设置默认更新地址: $VersionUrl"
    Copy-Item "driving_cli/commands/update.py" "driving_cli/commands/update.py.bak"

    $content = Get-Content "driving_cli/commands/update.py" -Raw
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*\(\s*\n\s*)"[^"]*"', "`$1`"$VersionUrl`""
    # 兼容单行写法
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*)"[^"]*"', "`$1`"$VersionUrl`""
    Set-Content "driving_cli/commands/update.py" $content -Encoding UTF8
} else {
    Write-Blue "[STEP 3] 使用代码中的默认更新地址"
}

# 4. 构建 .exe
Write-Blue "[STEP 4] 构建 driving.exe（可能需要几分钟）..."
python -m PyInstaller `
    --name driving `
    --onefile `
    --console `
    --clean `
    --distpath $DistDir `
    driving_cli/cli.py

$buildResult = $LASTEXITCODE

# 还原 update.py
if (Test-Path "driving_cli/commands/update.py.bak") {
    Move-Item -Force "driving_cli/commands/update.py.bak" "driving_cli/commands/update.py"
}

if ($buildResult -ne 0) {
    Write-Red "构建失败"
    exit 1
}

# 5. 验证
Write-Blue "[STEP 5] 验证构建产物..."
if (-not (Test-Path "$DistDir\driving.exe")) {
    Write-Red "构建失败：未找到 driving.exe"
    exit 1
}
& ".\$DistDir\driving.exe" --version
if ($LASTEXITCODE -ne 0) { Write-Red "可执行文件测试失败"; exit 1 }

# 6. 生成 version.json
Write-Blue "[STEP 6] 生成 version.json..."
$version = python -c "import re; c=open('driving_cli/__init__.py').read(); print(re.search(r\"__version__\s*=\s*['\\\"]([^'\\\"]+)['\\\"]\", c).group(1))"
$buildDate = Get-Date -Format "yyyy-MM-ddTHH:mm:ss+08:00"

# 读取最近 10 条 git log
$changelog = git log --pretty=format:"%s" -10 2>&1
if ($LASTEXITCODE -ne 0) { $changelog = @("No changelog available") }
$changelogJson = $changelog | ConvertTo-Json

$versionJson = @"
{
  "version": "$version",
  "build_date": "$buildDate",
  "platform": "Windows",
  "arch": "$env:PROCESSOR_ARCHITECTURE",
  "download_url": "$DownloadUrl",
  "download_url_windows": "$DownloadUrl",
  "changelog": $changelogJson
}
"@
Set-Content "$DistDir\version.json" $versionJson -Encoding UTF8
Write-Host "  version.json 已生成（版本: $version）"

# 7. 上传（可选）
if ($Upload) {
    if (-not $Server) {
        Write-Red "使用 -Upload 时必须指定 -Server 参数"
        exit 1
    }
    Write-Blue "[STEP 7] 上传到服务器: $Server"
    # 根据服务器类型选择上传方式（rsync / scp / robocopy）
    # 示例：rsync（需安装 cwRsync 或使用 WSL）
    # rsync -av $DistDir/driving.exe $DistDir/version.json $Server
    Write-Yellow "请根据实际服务器类型手动执行上传命令"
    Write-Host "  文件位置: $DistDir\driving.exe"
    Write-Host "  文件位置: $DistDir\version.json"
} else {
    Write-Blue "[STEP 7] 跳过上传（使用 -Upload 参数可上传）"
}

Write-Host ""
Write-Green "========================================"
Write-Green " ✓ 构建完成！"
Write-Green "========================================"
Write-Host ""
Write-Host "  可执行文件 : $DistDir\driving.exe"
Write-Host "  版本信息   : $DistDir\version.json"
Write-Host "  版本号     : $version"
Write-Host ""
