#!/bin/bash
# 开发环境设置脚本

set -e

echo "🚀 设置 Driving CLI 开发环境..."

# 检查 Python 版本
echo "📋 检查 Python 版本..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python 版本: $python_version"

# 检查是否满足最低版本要求 (3.8+)
required_version="3.8"
if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 错误: 需要 Python 3.8 或更高版本"
    exit 1
fi

# 升级 pip
echo "📦 升级 pip..."
python3 -m pip install --upgrade pip

# 安装开发依赖
echo "📦 安装开发依赖..."
pip3 install -e ".[dev]"

# 安装代码质量工具
echo "🔧 安装代码质量工具..."
pip3 install black flake8 isort mypy

# 运行测试
echo "🧪 运行测试..."
python3 -m pytest --cov=driving --cov-report=term

# 代码格式检查
echo "✨ 检查代码格式..."
python3 -m black --check driving || echo "⚠️  建议运行: python3 -m black driving"
python3 -m isort --check-only driving || echo "⚠️  建议运行: python3 -m isort driving"

# 代码风格检查
echo "🔍 检查代码风格..."
python3 -m flake8 driving --count --select=E9,F63,F7,F82 --show-source --statistics || true

echo ""
echo "✅ 开发环境设置完成！"
echo ""
echo "📝 下一步："
echo "  1. 运行测试: python3 -m pytest"
echo "  2. 格式化代码: python3 -m black driving"
echo "  3. 排序导入: python3 -m isort driving"
echo "  4. 运行 CLI: driving --help"
echo ""
