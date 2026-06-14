#!/bin/bash

# CI 构建脚本 - 用于 GitHub Actions 构建 Python 包

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info "=========================================="
print_info "CI Python 包构建"
print_info "=========================================="

# 1. 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] || [ ! -d "driving_cli" ]; then
    print_error "请在 driving-cli-tool 项目根目录中运行此脚本"
    exit 1
fi

# 2. 清理旧的构建文件
print_info "清理 dist 目录..."
rm -rf dist

# 3. 安装构建依赖
print_info "安装构建依赖..."
pip install build twine

# 4. 构建 Python 包
print_info "构建 Python 包..."
python -m build

# 5. 检查包
print_info "检查包格式..."
twine check dist/*.whl dist/*.tar.gz

print_info "=========================================="
print_info "✓ CI 构建完成！"
print_info "=========================================="