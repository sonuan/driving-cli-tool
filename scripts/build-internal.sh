#!/bin/bash

# 快速构建内网版本脚本
# 此脚本包含内网配置，不应提交到 Git 仓库

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Driving CLI 内网版本快速构建${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 内网配置
INTERNAL_SERVER="192.168.100.90::android_archive/ai-tools/"
INTERNAL_DOWNLOAD_URL="http://192.168.100.90/android/ai-tools/driving"

echo -e "${YELLOW}配置信息：${NC}"
echo "  - 服务器: ${INTERNAL_SERVER}"
echo "  - 下载地址: ${INTERNAL_DOWNLOAD_URL}"
echo "  - 输出目录: dist-internal/"
echo ""

# 调用主构建脚本
./scripts/build.sh \
    --upload \
    --server "${INTERNAL_SERVER}" \
    --download-url "${INTERNAL_DOWNLOAD_URL}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ 内网版本构建完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "产物位置："
echo "  - dist-internal/driving"
echo "  - dist-internal/version.json"
echo ""

# 上传安装脚本
echo -e "${YELLOW}上传安装脚本...${NC}"
export RSYNC_USER=nginx
rsync -av ./scripts/install-internal.sh "${INTERNAL_SERVER}install.sh"
echo -e "${GREEN}✓ 安装脚本已上传${NC}"
echo ""
echo "团队成员可以直接使用（已内置内网更新地址）："
echo "  driving update -y"
echo ""
echo "首次安装："
echo "  curl -fsSL http://192.168.100.90/android/ai-tools/install.sh | sudo bash"
echo ""
