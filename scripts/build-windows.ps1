# Driving CLI Windows 版本构建脚本
# 用法：在 Windows 机器（PowerShell）中运行
#   .\scripts\build-windows.ps1                    # 构建 GitHub 版本（默认）
#   .\scripts\build-windows.ps1 -Upload            # 构建并上传 GitHub 版本
#   .\scripts\build-windows-internal.ps1           # 构建内网版本
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

# 2. 清理旧构建产物（只删除 Windows 产物，保留 Mac/Linux 的 driving）
Write-Blue "[STEP 2] Cleaning old build artifacts..."
if (Test-Path "$DistDir\driving.exe") { Remove-Item -Force "$DistDir\driving.exe" }
if (Test-Path "$DistDir\version.json") { Remove-Item -Force "$DistDir\version.json" }
if (Test-Path "build")   { Remove-Item -Recurse -Force "build" }
# 确保 dist 目录存在
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Force -Path $DistDir | Out-Null }

# 3. 设置默认更新地址（写入 update.py，构建后还原）
if ($VersionUrl) {
    Write-Blue "[STEP 3] Setting default update URL: $VersionUrl"
    Copy-Item "driving_cli/commands/update.py" "driving_cli/commands/update.py.bak"

    $content = Get-Content "driving_cli/commands/update.py" -Raw -Encoding UTF8
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*\(\s*\n\s*)"[^"]*"', "`$1`"$VersionUrl`""
    # 兼容单行写法
    $content = $content -replace '(_DEFAULT_UPDATE_VERSION_URL\s*=\s*)"[^"]*"', "`$1`"$VersionUrl`""
    [System.IO.File]::WriteAllText((Resolve-Path "driving_cli/commands/update.py").Path, $content, [System.Text.Encoding]::UTF8)

    # 验证修改后文件语法合法
    python -m py_compile "driving_cli/commands/update.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Red "update.py syntax error after URL replacement, restoring backup"
        Move-Item -Force "driving_cli/commands/update.py.bak" "driving_cli/commands/update.py"
        exit 1
    }
    Write-Host "  update.py syntax OK"
} else {
    Write-Blue "[STEP 3] Using default update URL from source code"
}

# 4. 构建 .exe
Write-Blue "[STEP 4] Building driving.exe (this may take a few minutes)..."
python -m PyInstaller `
    --distpath $DistDir `
    --clean `
    driving.spec

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

# 创建临时 Python 脚本文件（使用无 BOM 的 UTF-8）
$tempPyScript = Join-Path $env:TEMP "gen_version_json.py"
$pyScriptContent = @'
import json
import os
import re
import subprocess
from datetime import datetime

# 提取版本号
try:
    with open('driving_cli/__init__.py', 'r', encoding='utf-8') as f:
        content = f.read()
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", content)
    version = m.group(1) if m else 'unknown'
except Exception:
    version = 'unknown'

# 构建时间
build_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

# 获取 git changelog
try:
    result = subprocess.run(['git', 'log', '--pretty=format:%s', '-10'], capture_output=True, text=True, encoding='utf-8')
    changelog = result.stdout.strip().split('\n') if result.returncode == 0 else ['No changelog available']
except Exception:
    changelog = ['No changelog available']

# 从环境变量获取参数
arch = os.environ.get('DRIVING_ARCH', 'unknown')
download_url = os.environ.get('DRIVING_DOWNLOAD_URL', '')

# 生成 JSON（复用 download_url 字段，Windows CLI 会自动拼接 .exe 后缀）
data = {
    'version': version,
    'build_date': build_date,
    'platform': 'Windows',
    'arch': arch,
    'download_url': download_url,
    'changelog': changelog
}

print(json.dumps(data, indent=2, ensure_ascii=False))
'@
# 使用 .NET 方法写入无 BOM 的 UTF-8 文件
[System.IO.File]::WriteAllText($tempPyScript, $pyScriptContent, [System.Text.UTF8Encoding]::new($false))

# 通过环境变量传递参数给 Python
$env:DRIVING_ARCH = $env:PROCESSOR_ARCHITECTURE
$env:DRIVING_DOWNLOAD_URL = $DownloadUrl

# 执行 Python 脚本
$versionJson = python $tempPyScript | Out-String

# 清理临时文件和环境变量
Remove-Item $tempPyScript -ErrorAction SilentlyContinue
Remove-Item Env:DRIVING_ARCH -ErrorAction SilentlyContinue
Remove-Item Env:DRIVING_DOWNLOAD_URL -ErrorAction SilentlyContinue

if (-not $versionJson) {
    Write-Red "Failed to generate version.json"
    exit 1
}

# 使用无 BOM 的 UTF-8 写入 version.json
[System.IO.File]::WriteAllText("$DistDir\version.json", $versionJson, [System.Text.UTF8Encoding]::new($false))

# 从生成的 JSON 中提取版本号用于日志
$version = python -c "import json; print(json.loads(open('$DistDir/version.json', encoding='utf-8').read())['version'])"
Write-Host "  version.json generated (version: $version)"

# 7. 上传（可选）
if ($Upload) {
    if (-not $Server) {
        Write-Red "Must specify -Server when using -Upload"
        exit 1
    }
    Write-Blue "[STEP 7] Uploading to server: $Server"

    # 处理服务器地址格式
    # 支持 rsync 格式 "user@host::module" 和普通 UNC 路径 "\\server\share"
    if ($Server -match "::") {
        # rsync 格式，使用 cwRsync/WSL rsync
        Write-Host "  使用 rsync 上传..."
        $rsyncCmd = "rsync -av `"$DistDir\driving.exe`" `"$DistDir\version.json`" `"$Server`""
        Write-Host "  Command: $rsyncCmd"
        Write-Yellow "  请确保已安装 cwRsync 或使用 WSL"
        # 尝试执行 rsync（如果可用）
        try {
            $result = Invoke-Expression $rsyncCmd 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Green "  ✓ 上传成功"
            } else {
                Write-Yellow "  上传命令执行失败，请手动执行上述命令"
            }
        } catch {
            Write-Yellow "  上传命令执行失败，请手动执行上述命令"
        }
    } else {
        # UNC 路径格式，使用 robocopy
        Write-Host "  使用 robocopy 上传..."
        $uncPath = $Server.TrimEnd('/')
        try {
            # 提取服务器和共享部分
            if ($Server -match "^\\\\([^\\]+)\\(.+)") {
                $remotePath = $Server.TrimEnd('\') + "\"
                Write-Host "  Remote: $remotePath"
                robocopy $DistDir $remotePath "driving.exe" "version.json" /NP /NFL /NDL /NC /NJH /NJS
                if ($LASTEXITCODE -lt 8) {
                    Write-Green "  ✓ 上传成功"
                } else {
                    Write-Yellow "  上传可能失败，请检查网络连接"
                }
            } else {
                Write-Yellow "  服务器地址格式不支持，请手动上传"
            }
        } catch {
            Write-Yellow "  上传失败，请手动上传文件："
            Write-Host "    Source: $DistDir\driving.exe"
            Write-Host "    Source: $DistDir\version.json"
            Write-Host "    Dest: $Server"
        }
    }
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
