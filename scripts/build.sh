#!/bin/bash

# Driving CLI 可执行文件构建脚本
# 使用 PyInstaller 将 Python 项目打包成独立可执行文件

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --upload              上传到服务器（默认不上传）"
    echo "  --server <地址>       指定上传服务器地址（默认: 192.168.100.90::android_archive/ai-tools/）"
    echo "  --download-url <URL>  指定 version.json 中的 download_url（默认: https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/driving）"
    echo "  --version-url <URL>   指定 version.json 的完整 URL，同时设置为代码中的默认更新地址"
    echo "  -h, --help            显示此帮助信息"
    echo ""
    echo "说明:"
    echo "  --download-url: 可执行文件的下载地址（写入 version.json）"
    echo "  --version-url:  version.json 文件的地址（写入 version.json 并设置为代码默认值）"
    echo "                  如果不指定，默认从 --download-url 推导"
    echo ""
    echo "使用场景:"
    echo "  1. 构建内网版本（内网默认更新）:"
    echo "     $0 --upload --download-url http://192.168.100.90/android/ai-tools/driving \\"
    echo "                 --version-url http://192.168.100.90/android/ai-tools/version.json"
    echo ""
    echo "  2. 构建外网版本（GitHub 默认更新）:"
    echo "     $0 --upload --download-url https://raw.githubusercontent.com/.../driving \\"
    echo "                 --version-url https://raw.githubusercontent.com/.../version.json"
    echo ""
    echo "示例:"
    echo "  $0                    # 仅构建，使用代码默认值"
    echo "  $0 --upload           # 构建并上传到默认服务器"
}

# 默认参数
UPLOAD=false
SERVER="192.168.100.90::android_archive/ai-tools/"
DOWNLOAD_URL="https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/driving"
VERSION_URL=""  # 如果不指定，从 DOWNLOAD_URL 推导

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --upload)
            UPLOAD=true
            shift
            ;;
        --server)
            SERVER="$2"
            shift 2
            ;;
        --download-url)
            DOWNLOAD_URL="$2"
            shift 2
            ;;
        --version-url)
            VERSION_URL="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            print_usage
            exit 1
            ;;
    esac
done

# 如果没有指定 VERSION_URL，从 DOWNLOAD_URL 推导
if [ -z "$VERSION_URL" ] && [ -n "$DOWNLOAD_URL" ]; then
    VERSION_URL="${DOWNLOAD_URL%/driving}/version.json"
    print_info "自动推导 version.json 地址: ${VERSION_URL}"
fi

# 根据 VERSION_URL 判断构建类型，决定输出目录
if [[ "$VERSION_URL" == *"github"* ]] || [[ "$VERSION_URL" == *"raw.githubusercontent"* ]]; then
    BUILD_TYPE="public"
    DIST_DIR="dist"
    print_info "构建类型: 外网版本 (GitHub)"
else
    BUILD_TYPE="internal"
    DIST_DIR="dist-internal"
    print_info "构建类型: 内网版本"
fi

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] || [ ! -d "driving" ]; then
    print_error "请在 driving-cli-tool 项目根目录中运行此脚本"
    exit 1
fi

print_info "=========================================="
print_info "Driving CLI 可执行文件构建"
print_info "=========================================="
echo ""
print_info "配置信息："
print_info "  - 上传到服务器: $([ "$UPLOAD" = true ] && echo '是' || echo '否')"
if [ "$UPLOAD" = true ]; then
    print_info "  - 服务器地址: ${SERVER}"
    print_info "  - 下载地址: ${DOWNLOAD_URL}"
    print_info "  - version.json 地址: ${VERSION_URL}"
fi
if [ -n "$VERSION_URL" ]; then
    print_info "  - 默认更新地址: ${VERSION_URL} (将写入可执行文件)"
fi
echo ""

# 1. 检查并安装 PyInstaller
print_step "1. 检查 PyInstaller..."
if ! python3 -m PyInstaller --version &> /dev/null; then
    print_warn "PyInstaller 未安装，正在安装..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        print_error "PyInstaller 安装失败"
        exit 1
    fi
    print_info "PyInstaller 安装成功"
else
    print_info "PyInstaller 已安装"
fi

# 2. 清理旧的构建文件
print_step "2. 清理旧的构建文件..."
rm -rf build ${DIST_DIR} *.spec
print_info "清理完成 (输出目录: ${DIST_DIR})"

# 3. 设置默认更新地址（如果指定了 --version-url）
if [ -n "$VERSION_URL" ]; then
    print_step "3. 设置默认更新地址..."
    print_info "将默认更新地址设置为: ${VERSION_URL}"
    
    # 备份原始文件
    cp driving/utils/config.py driving/utils/config.py.bak
    
    # 使用 Python 替换默认值（更可靠）
    python3 << PYEOF
import re

with open('driving/utils/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换 DRIVING_UPDATE_VERSION_URL 的默认值
pattern = r'DRIVING_UPDATE_VERSION_URL = os\.getenv\(\s*"DRIVING_UPDATE_VERSION_URL",\s*"[^"]*"\s*\)'
replacement = f'DRIVING_UPDATE_VERSION_URL = os.getenv(\n    "DRIVING_UPDATE_VERSION_URL",\n    "${VERSION_URL}"\n)'

content = re.sub(pattern, replacement, content)

with open('driving/utils/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("默认更新地址已替换")
PYEOF
    
    print_info "默认更新地址已设置"
else
    print_step "3. 使用代码中的默认更新地址"
    print_info "未指定 --version-url，使用代码中的默认值"
fi

# 4. 构建可执行文件
print_step "4. 构建可执行文件..."
print_info "这可能需要几分钟时间..."

python3 -m PyInstaller \
    --name driving \
    --onefile \
    --console \
    --clean \
    --distpath ${DIST_DIR} \
    driving/cli.py

BUILD_RESULT=$?

# 恢复原始配置文件（如果有备份）
if [ -f "driving/utils/config.py.bak" ]; then
    print_info "恢复原始配置文件..."
    mv driving/utils/config.py.bak driving/utils/config.py
fi

if [ $BUILD_RESULT -ne 0 ]; then
    print_error "构建失败"
    exit 1
fi

# 5. 检查构建产物
print_step "5. 检查构建产物..."
if [ ! -f "${DIST_DIR}/driving" ]; then
    print_error "构建失败：未找到可执行文件"
    exit 1
fi

# 6. 测试可执行文件
print_step "6. 测试可执行文件..."
./${DIST_DIR}/driving --version
if [ $? -ne 0 ]; then
    print_error "可执行文件测试失败"
    exit 1
fi

# 7. 显示文件信息
print_step "7. 构建完成！"
echo ""
print_info "可执行文件信息："
ls -lh ${DIST_DIR}/driving
echo ""

FILE_SIZE=$(du -h ${DIST_DIR}/driving | cut -f1)
print_info "文件大小: $FILE_SIZE"
print_info "文件位置: $(pwd)/${DIST_DIR}/driving"

# 8. 生成 version.json
print_step "8. 生成 version.json..."

# 使用 Python 提取版本号
VERSION=$(python3 << 'PYEOF'
import re
with open('driving/__init__.py', 'r') as f:
    content = f.read()
    match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        print(match.group(1))
    else:
        print("unknown")
PYEOF
)

BUILD_DATE=$(TZ='Asia/Shanghai' date +"%Y-%m-%dT%H:%M:%S+08:00")

# 获取最近的 git 提交记录作为 changelog
print_info "获取 git changelog..."
CHANGELOG_LINES=$(git log --pretty=format:"%s" -10 2>/dev/null || echo "No changelog available")

# 生成 changelog JSON 数组
CHANGELOG_JSON=$(python3 << 'PYEOF'
import sys
import json
lines = sys.stdin.read().strip().split('\n')
print(json.dumps(lines, indent=2, ensure_ascii=False))
PYEOF
)

# 读取 changelog 并格式化
echo "$CHANGELOG_LINES" | python3 -c "
import sys
import json
lines = [line.strip() for line in sys.stdin if line.strip()]
if not lines or lines == ['No changelog available']:
    lines = ['No changelog available']
changelog_json = json.dumps(lines, indent=4, ensure_ascii=False)
# 添加缩进
changelog_json = '\n'.join('  ' + line for line in changelog_json.split('\n'))
print(changelog_json)
" > /tmp/changelog.json

# 生成 version.json
cat > "${DIST_DIR}/version.json" << EOF
{
  "version": "${VERSION}",
  "build_date": "${BUILD_DATE}",
  "platform": "$(uname -s)",
  "arch": "$(uname -m)",
  "download_url": "${DOWNLOAD_URL}",
  "changelog": $(cat /tmp/changelog.json)
}
EOF

rm -f /tmp/changelog.json

print_info "version.json 已生成 (版本: ${VERSION})"

# 9. 上传到服务器（可选）
if [ "$UPLOAD" = true ]; then
    print_step "9. 上传到服务器..."
    print_info "上传可执行文件和 version.json 到服务器..."

    # 设置 rsync 用户名环境变量
    export RSYNC_USER=nginx

    rsync -av ${DIST_DIR}/driving ${DIST_DIR}/version.json "${SERVER}"

    if [ $? -eq 0 ]; then
        print_success "上传成功！"
    else
        print_error "上传失败，请检查网络连接和服务器配置"
        exit 1
    fi
else
    print_step "9. 跳过上传到服务器"
    print_info "使用 --upload 参数可以上传到服务器"
fi

# 10. 显示完成信息
echo ""
print_info "=========================================="
print_info "✓ 构建完成！"
print_info "=========================================="
echo ""
print_info "📦 构建产物："
print_info "  - 可执行文件: ${DIST_DIR}/driving"
print_info "  - 版本信息: ${DIST_DIR}/version.json"
print_info "  - 版本号: ${VERSION}"
print_info "  - 构建时间: ${BUILD_DATE}"
print_info "  - 构建类型: ${BUILD_TYPE}"

# 计算实际的 version.json URL
if [ -n "$VERSION_URL" ]; then
    ACTUAL_VERSION_URL="$VERSION_URL"
else
    ACTUAL_VERSION_URL="${DOWNLOAD_URL%/driving}/version.json"
fi

if [ -n "$VERSION_URL" ]; then
    echo ""
    print_info "� 构建配置："
    print_info "  - 默认更新地址已设置为: ${VERSION_URL}"
    print_info "  - 用户无需配置即可使用 'driving update' 更新"
fi

echo ""

if [ "$UPLOAD" = true ]; then
    print_info "🚀 已上传到服务器："
    print_info "  - 可执行文件: ${DOWNLOAD_URL}"
    print_info "  - 版本信息: ${ACTUAL_VERSION_URL}"
    echo ""
    if [ -n "$VERSION_URL" ]; then
        print_info "💡 团队成员可以直接使用（已内置更新地址）："
        print_info "  driving update -y"
    else
        print_info "💡 团队成员首次使用需要配置更新地址："
        print_info "  driving update --url ${ACTUAL_VERSION_URL}"
        echo ""
        print_info "💡 配置后可以直接更新："
        print_info "  driving update -y"
    fi
else
    print_info "💡 使用以下命令上传到服务器："
    print_info "  $0 --upload"
    echo ""
    print_info "💡 构建内网版本（内网默认更新）："
    print_info "  $0 --upload --download-url http://192.168.100.90/android/ai-tools/driving \\"
    print_info "              --version-url http://192.168.100.90/android/ai-tools/version.json"
    echo ""
    print_info "💡 构建外网版本（GitHub 默认更新）："
    print_info "  $0 --upload --download-url https://raw.githubusercontent.com/.../driving \\"
    print_info "              --version-url https://raw.githubusercontent.com/.../version.json"
fi
echo ""
