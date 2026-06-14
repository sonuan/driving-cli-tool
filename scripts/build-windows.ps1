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
    Write-Host "Usage: .\scripts\build-windows.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Upload                Upload to server (disabled by default)"
    Write-Host "  -Server ADDR           Specify upload server address"
    Write-Host "  -DownloadUrl URL       Specify download_url_windows in version.json"
    Write-Host "  -VersionUrl URL        Specify full URL for version.json"
    Write-Host "  -Help                  Show this help"
    exit 0
}

# 检查是否在项目根目录
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "driving_cli")) {
    Write-Red "Error: Please run this script from the driving-cli-tool project root"
    exit 1
}

# 自动推导 VersionUrl
if (-not $VersionUrl -and $DownloadUrl) {
    $VersionUrl = $DownloadUrl -replace "/driving\.exe$", "/version.json"
    Write-Yellow "Auto-derived version.json URL: $VersionUrl"
}

$DistDir = "dist-windows"

Write-Green "========================================"
Write-Green " Driving CLI Windows Build"
Write-Green "========================================"
Write-Host ""
Write-Host "  Output dir  : $DistDir"
Write-Host "  Download URL: $DownloadUrl"
Write-Host ""

# 1. 安装 PyInstaller
Write-Blue "[STEP 1] Checking PyInstaller..."
$pyiVersion = python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Yellow "PyInstaller not found, installing..."
    pip install pyinstaller
}
Write-Host "  PyInstaller ready"

# 2. 清理旧构建产物
Write-Blue "[STEP 2] Cleaning old build artifacts..."
if (Test-Path $DistDir)  { Remove-Item -Recurse -Force $DistDir }
if (Test-Path "build")   { Remove-Item -Recurse -Force "build" }

# 3. 设置默认更新地址（写入 update.py，构建后还原）
if ($VersionUrl) {
    Write-Blue "[STEP 3] Setting default update URL: $VersionUrl"
    Copy-Item "driving_cli/commands/update.py" "driving_cli/commands/update.py.bak"

    $content = Get-Content "driving_cli/commands/update.py" -Raw
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*\(\s*\n\s*)"[^"]*"', "`$1`"$VersionUrl`""
    # 兼容单行写法
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*)"[^"]*"', "`$1`"$VersionUrl`""
    Set-Content "driving_cli/commands/update.py" $content -Encoding UTF8
} else {
    Write-Blue "[STEP 3] Using default update URL from source code"
}

# 4. 构建 .exe
Write-Blue "[STEP 4] Building driving.exe (this may take a few minutes)..."
python -m PyInstaller `
    --name driving `
    --onefile `
    --console `
    --clean `
    --distpath $DistDir `
    --hidden-import driving_cli.commands.agent `
    --hidden-import driving_cli.commands.check `
    --hidden-import driving_cli.commands.feature `
    --hidden-import driving_cli.commands.framework `
    --hidden-import driving_cli.commands.gate `
    --hidden-import driving_cli.commands.ide `
    --hidden-import driving_cli.commands.load `
    --hidden-import driving_cli.commands.power `
    --hidden-import driving_cli.commands.refine `
    --hidden-import driving_cli.commands.repo `
    --hidden-import driving_cli.commands.rule `
    --hidden-import driving_cli.commands.skill `
    --hidden-import driving_cli.commands.update `
    driving_cli/cli.py

$buildResult = $LASTEXITCODE

# 还原 update.py
if (Test-Path "driving_cli/commands/update.py.bak") {
    Move-Item -Force "driving_cli/commands/update.py.bak" "driving_cli/commands/update.py"
}

if ($buildResult -ne 0) {
    Write-Red "Build failed"
    exit 1
}

# 5. 验证
Write-Blue "[STEP 5] Verifying build artifacts..."
if (-not (Test-Path "$DistDir\driving.exe")) {
    Write-Red "Build failed: driving.exe not found"
    exit 1
}
& ".\$DistDir\driving.exe" --version
if ($LASTEXITCODE -ne 0) { Write-Red "Executable test failed"; exit 1 }

# 6. 生成 version.json
Write-Blue "[STEP 6] Generating version.json..."

# 用独立 Python 脚本提取版本号，避免内联引号转义问题
$version = python -c "
import re, sys
try:
    c = open('driving_cli/__init__.py').read()
    m = re.search(r\"__version__\s*=\s*['\\\"]([^'\\\"]+)['\\\"]\", c)
    print(m.group(1) if m else 'unknown')
except Exception as e:
    print('unknown')
"

$buildDate = Get-Date -Format "yyyy-MM-ddTHH:mm:ss+08:00"

# 读取最近 10 条 git log
$changelog = git log --pretty=format:"%s" -10 2>&1
if ($LASTEXITCODE -ne 0) { $changelog = @("No changelog available") }
$changelogJson = $changelog | ConvertTo-Json

# 构建 JSON 内容（避免 here-string 编码问题）
$versionObj = [ordered]@{
    version              = $version
    build_date           = $buildDate
    platform             = "Windows"
    arch                 = $env:PROCESSOR_ARCHITECTURE
    download_url         = $DownloadUrl
    download_url_windows = $DownloadUrl
    changelog            = $changelog
}
$versionJson = $versionObj | ConvertTo-Json -Depth 3
Set-Content "$DistDir\version.json" $versionJson -Encoding UTF8
Write-Host "  version.json generated (version: $version)"

# 7. 上传（可选）
if ($Upload) {
    if (-not $Server) {
        Write-Red "Must specify -Server when using -Upload"
        exit 1
    }
    Write-Blue "[STEP 7] Uploading to server: $Server"
    # 根据服务器类型选择上传方式（rsync / scp / robocopy）
    # 示例：rsync（需安装 cwRsync 或使用 WSL）
    # rsync -av $DistDir/driving.exe $DistDir/version.json $Server
    Write-Yellow "Please run the upload command manually based on your server type"
    Write-Host "  File: $DistDir\driving.exe"
    Write-Host "  File: $DistDir\version.json"
} else {
    Write-Blue "[STEP 7] Skipping upload (use -Upload flag to enable)"
}

Write-Host ""
Write-Green "========================================"
Write-Green " Build complete!"
Write-Green "========================================"
Write-Host ""
Write-Host "  Executable : $DistDir\driving.exe"
Write-Host "  Version    : $DistDir\version.json"
Write-Host "  Version No : $version"
Write-Host ""
