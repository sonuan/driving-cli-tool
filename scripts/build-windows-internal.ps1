# Driving CLI Windows 内网版本构建脚本
# 此脚本包含内网配置，不应提交到 Git 仓库
#
# 用法：在 Windows 机器（PowerShell）中运行
#   .\scripts\build-windows-internal.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Green
Write-Host "Driving CLI Windows 内网版本构建" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 内网配置（使用 UNC 路径格式）
$InternalServer = "\\192.168.100.90\android_archive\ai-tools\"
$InternalDownloadUrl = "http://192.168.100.90/android/ai-tools/driving"
$InternalVersionUrl = "http://192.168.100.90/android/ai-tools/version.json"

Write-Host "配置信息：" -ForegroundColor Yellow
Write-Host "  - 服务器: ${InternalServer}"
Write-Host "  - 下载地址: ${InternalDownloadUrl}"
Write-Host "  - 版本文件: ${InternalVersionUrl}"
Write-Host "  - 输出目录: dist-windows/"
Write-Host ""

# 调用主构建脚本
& "$PSScriptRoot\build-windows.ps1" `
    -Upload `
    -Server $InternalServer `
    -DownloadUrl $InternalDownloadUrl `
    -VersionUrl $InternalVersionUrl

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "内网版本构建完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "产物位置："
Write-Host "  - dist-windows/driving.exe"
Write-Host "  - dist-windows/version.json"
Write-Host ""
Write-Host "团队成员可以直接使用（已内置内网更新地址）："
Write-Host "  driving update -y"
Write-Host ""
Write-Host "首次安装（下载 driving.exe 后手动安装）："
Write-Host "  1. 下载: ${InternalDownloadUrl}.exe"
Write-Host "  2. 移动到: ~\AppData\Local\.driving-cli\"
Write-Host "  3. 添加到 PATH 或创建快捷方式"
Write-Host ""
