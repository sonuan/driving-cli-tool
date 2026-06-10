#!/bin/sh
# Driving CLI 安装脚本（内网版本）
# 用法：curl -fsSL http://192.168.100.90/android/ai-tools/install.sh | sudo bash

set -e

BINARY_URL="http://192.168.100.90/android/ai-tools/driving"

# sudo bash 执行时 $HOME 指向 /root，需要用 $SUDO_USER 还原真实用户 home
if [ -n "$SUDO_USER" ]; then
    REAL_HOME=$(eval echo "~$SUDO_USER")
else
    REAL_HOME="$HOME"
fi

INSTALL_DIR="$REAL_HOME/.driving-cli"
BINARY_PATH="$INSTALL_DIR/driving"
SYMLINK_PATH="/usr/local/bin/driving"

# 颜色输出（兼容 sh）
green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$1"; }
red() { printf '\033[0;31m%s\033[0m\n' "$1"; }
info() { printf '  %s\n' "$1"; }

green "========================================"
green " Driving CLI 安装程序（内网版本）"
green "========================================"
echo ""
info "下载地址：$BINARY_URL"
info "二进制路径：$BINARY_PATH"
info "符号链接：  $SYMLINK_PATH -> $BINARY_PATH"
echo ""

# 1. 创建安装目录
mkdir -p "$INSTALL_DIR"

# 检测旧安装方式（/usr/local/bin/driving 是真实文件而非符号链接）
if [ -f "$SYMLINK_PATH" ] && [ ! -L "$SYMLINK_PATH" ]; then
    yellow "检测到旧版安装（$SYMLINK_PATH 是真实文件），将迁移到新方式..."
    rm -f "$SYMLINK_PATH"
fi

# 2. 下载二进制
yellow "正在下载..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$BINARY_URL" -o "$BINARY_PATH"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$BINARY_PATH" "$BINARY_URL"
else
    red "错误：未找到 curl 或 wget，请先安装其中一个"
    exit 1
fi

# 3. 设置执行权限，并将所有权归还真实用户（sudo bash 下文件默认属于 root）
chmod +x "$BINARY_PATH"
if [ -n "$SUDO_USER" ]; then
    chown -R "$SUDO_USER" "$INSTALL_DIR"
fi

# 4. 创建 /usr/local/bin 符号链接（需要权限）
mkdir -p /usr/local/bin
ln -sf "$BINARY_PATH" "$SYMLINK_PATH"

echo ""
green "✓ 安装成功！"
echo ""
info "版本信息："
"$BINARY_PATH" --version 2>/dev/null || true
echo ""
info "运行以下命令验证安装："
info "  driving --version"
info ""
info "后续升级无需 sudo，直接运行："
info "  driving update"
echo ""
