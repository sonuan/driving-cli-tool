#!/bin/bash

echo "========== 测试 build.sh 脚本 =========="
echo ""

# 进入项目根目录
cd "$(dirname "$0")/.."

echo "1. 检查原始配置文件"
echo "原始默认值："
grep -A 2 'DRIVING_UPDATE_VERSION_URL = os.getenv' driving/utils/config.py | head -3
echo ""

echo "2. 模拟构建（仅测试配置替换，不实际构建）"
echo "测试命令: --download-url http://192.168.100.90/android/ai-tools/driving"
echo ""

# 模拟脚本的配置替换部分
DOWNLOAD_URL="http://192.168.100.90/android/ai-tools/driving"
VERSION_URL="${DOWNLOAD_URL%/driving}/version.json"

echo "推导的 VERSION_URL: $VERSION_URL"
echo ""

# 备份
cp driving/utils/config.py driving/utils/config.py.test_bak

# 替换
python3 << PYEOF
import re

with open('driving/utils/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'DRIVING_UPDATE_VERSION_URL = os\.getenv\(\s*"DRIVING_UPDATE_VERSION_URL",\s*"[^"]*"\s*\)'
replacement = f'DRIVING_UPDATE_VERSION_URL = os.getenv(\n    "DRIVING_UPDATE_VERSION_URL",\n    "${VERSION_URL}"\n)'

content = re.sub(pattern, replacement, content)

with open('driving/utils/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ 配置已替换")
PYEOF

echo ""
echo "3. 检查替换后的配置"
echo "替换后的默认值："
grep -A 2 'DRIVING_UPDATE_VERSION_URL = os.getenv' driving/utils/config.py | head -3
echo ""

echo "4. 恢复原始配置"
mv driving/utils/config.py.test_bak driving/utils/config.py
echo "✓ 已恢复"
echo ""

echo "5. 验证恢复后的配置"
echo "恢复后的默认值："
grep -A 2 'DRIVING_UPDATE_VERSION_URL = os.getenv' driving/utils/config.py | head -3
echo ""

echo "========== 测试完成 =========="
