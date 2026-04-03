#!/bin/bash
# 代码格式化脚本

set -e

echo "🎨 开始格式化代码..."

# 检查工具是否安装
echo "📋 检查工具..."

if ! command -v black &> /dev/null; then
    echo "⚠️  black 未安装，正在安装..."
    pip3 install black
fi

if ! command -v isort &> /dev/null; then
    echo "⚠️  isort 未安装，正在安装..."
    pip3 install isort
fi

# 格式化代码
echo "✨ 使用 black 格式化代码..."
python3 -m black driving_cli tests

echo "📦 使用 isort 排序导入..."
python3 -m isort driving_cli tests

# 检查结果
echo "🔍 检查格式化结果..."
python3 -m black --check driving tests && echo "✓ black 检查通过" || echo "⚠️  black 检查失败"
python3 -m isort --check-only driving tests && echo "✓ isort 检查通过" || echo "⚠️  isort 检查失败"

echo ""
echo "✅ 代码格式化完成！"
echo ""
echo "📝 下一步："
echo "  1. 查看变更: git diff"
echo "  2. 提交代码: git add . && git commit -m 'style: format code with black and isort'"
echo ""
