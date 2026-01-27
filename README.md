# Driving CLI Tool

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI Status](https://github.com/your-org/driving-cli/workflows/CI/badge.svg)](https://github.com/your-org/driving-cli/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

命令行工具，用于管理开发框架文档和代码仓库。支持两种工作模式：标准模式（Git submodule）和本地模式（直接在当前目录）。

## 核心特性

- ✅ 双模式支持 - 标准模式（Git submodule）和本地模式（当前目录）
- ✅ 多配置文件 - 支持 `ai-docs-local/gitlist.json` 和 `ai-docs/gitlist.json`
- ✅ 本地项目支持 - 本地项目和远程框架分离管理
- ✅ 自动检测 - 根据 gitlist.json 位置自动切换模式
- ✅ 子目录支持 - 可在项目的任意子目录运行命令，自动向上查找配置
- ✅ 无需 Git 仓库 - 不依赖 .git 目录，支持在任意位置装载 .driving 目录
- ✅ 项目内管理 - 框架仓库存储在 `submodules/` 或 `.driving/submodules/`
- ✅ 团队协作 - 自动同步配置和框架版本
- ✅ IDE 友好 - 可被正确识别和索引
- ✅ Context 加载 - 可在 IDE context 中正常加载

## 工作模式

### 标准模式（Git Submodule）
当前目录或父目录**不存在** `gitlist.json` 文件时，使用标准模式：
- 配置存储在 `.driving/` 目录（Git submodule）
- 框架仓库存储在 `.driving/submodules/`
- 适合多项目共享配置
- 支持在任意子目录运行命令，自动向上查找 `.driving/` 目录

### 本地模式（Direct）
当前目录或父目录**存在** `gitlist.json` 文件时，使用本地模式：
- 配置直接在当前目录
- 框架仓库存储在 `submodules/`
- 适合 driving 仓库本身或独立项目
- `install` 和 `uninstall` 命令不需要执行
- 支持在任意子目录运行命令，自动向上查找 `gitlist.json` 文件

## 快速开始

### 安装

#### 方式 1：一键安装（推荐，适合 macOS/Linux）

```bash
# 下载并安装到 /usr/local/bin/（需要管理员权限）

# github
sudo sh -c 'curl -fsSL https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/driving -o /usr/local/bin/driving && chmod +x /usr/local/bin/driving'

# 内网
sudo sh -c 'curl -fsSL http://192.168.100.90/android/ai-tools/driving -o /usr/local/bin/driving && chmod +x /usr/local/bin/driving'

# 验证安装
driving --version
```

**说明**：
- 自动下载可执行文件到 `/usr/local/bin/`
- 自动添加执行权限
- `/usr/local/bin/` 默认在 PATH 中，无需额外配置
- 使用 `sudo` 获取管理员权限

#### 方式 3：开发模式安装

```bash
# 从源码安装（适合开发者）
cd cli-tool
pip3 install -e .
```

### 基本使用

#### 标准模式（在其他项目中使用）

```bash
# 1. 在项目中添加 driving
cd your-project
driving install --url https://github.com/your-org/driving  # url为框架文档管理仓库

# 2. 提交 submodule
git add .gitmodules .driving
git commit -m "Add driving submodule"

# 3. 查看可用框架
driving git-list

# 或查看特定框架的仓库
driving git-list xstatic

# 4. 安装框架（支持自动切换到配置的分支）
driving git-install ximage
```

#### 本地模式（在 driving 仓库本身使用）

```bash
# 1. 进入 driving 仓库（已有 gitlist.json）
cd driving

# 2. 直接查看和安装框架（无需 install）
driving git-list
driving git-install ximage

# 3. 框架将安装到 submodules/ 目录
```

## 主要命令

### Driving 配置管理

```bash
driving install --url <url>  # 使用自定义框架文档管理仓库地址安装，并自动保存到 .env 文件
driving uninstall            # 从当前目录移除 driving Git submodule
driving pull                 # 更新配置（标准模式：.driving，本地模式：当前目录）
driving commit               # 提交修改（标准模式：.driving，本地模式：当前目录）
driving push                 # 推送修改（标准模式：.driving，本地模式：当前目录）
```

**参数说明：**
- `--url`: 自定义 Driving 仓库地址，会自动保存到项目根目录的 `.env` 文件，下次无需再指定

**示例：**
```bash
# 使用自定义框架文档管理仓库地址（会自动保存到 .env）
driving install --url https://github.com/your-org/driving

# 下次直接使用，会自动读取 .env 中的配置
driving pull
driving commit "update config"
```

**注意**：
- `install` 和 `uninstall` 会在**当前工作目录**创建/删除 `.driving` 目录
- 支持在 Git 仓库的任意子目录中执行 `install`，`.driving` 会创建在执行命令的目录
- 标准模式：操作 `.driving/` 目录
- 本地模式：操作当前目录
- `install` 和 `uninstall` 在本地模式下不需要执行

### 框架仓库管理

```bash
driving git-list                    # 显示所有可用框架列表
driving git-list <framework>        # 显示指定框架的仓库列表
driving git-list --json             # 以 JSON 格式输出所有框架信息
driving git-list <framework> --json # 以 JSON 格式输出指定框架信息
driving git-sources <framework>     # 获取指定框架的源码路径列表（JSON 格式）
driving git-install <framework>     # 安装框架（标准模式：.driving/submodules/，本地模式：submodules/）
driving git-checkout <framework> <branch>  # 切换框架分支
driving git-pull <framework>        # 更新框架仓库
```

**注意**：
- 标准模式：框架安装到 `.driving/submodules/`
- 本地模式：框架安装到 `submodules/`
- `git-list --json` 输出包含完整路径的 sources 字段
- `git-sources` 自动合并多个仓库的源码路径，适合文档生成工具使用

### IDE 配置管理

```bash
driving ide-list            # 列出可用的 IDE 配置
driving ide-sync <ide名称>  # 增量同步 IDE 配置到项目根目录
```

**示例**：
```bash
# 查看可用的 IDE 配置
driving ide-list

# 同步 Kiro IDE 配置到项目
driving ide-sync kiro

# 同步 Cursor IDE 配置到项目
driving ide-sync cursor
```

**说明**：
- IDE 配置存储在 `install/` 目录下
- 同步时会将配置增量复制到项目根目录（Git 仓库根目录）
- 只会覆盖同名文件，不会删除目标目录中的其他文件
- 保留用户自定义的配置文件
- **自动提取敏感信息**：
  - 自动检测 mcp.json 中的敏感字段（API Key、Token、Secret 等）
  - 将敏感值提取到项目根目录的 `.env.local` 文件
  - 在 mcp.json 中用环境变量引用替换（如 `${API_KEY}`）
  - 自动将 `.env.local` 添加到 `.gitignore`，防止敏感信息泄露
  - `.env` 文件用于非敏感的项目配置，可以提交到仓库

### Skills 管理

```bash
driving skills-sync         # 同步技能列表到 AGENTS.md 文件
```

**示例**：
```bash
# 扫描 ai-docs/skills 目录并更新 AGENTS.md
driving skills-sync
```

**说明**：
- 自动扫描 `ai-docs/skills` 目录下的所有技能
- 读取每个技能的 SKILL.md 文件的 YAML 头信息（name 和 description）
- 生成或更新 AGENTS.md 文件
- **按名称排序**：技能按名称字母顺序排列，便于查找和管理
- 标准模式：从 `.driving/ai-docs/skills` 读取，更新 `.driving/AGENTS.md`
- 本地模式：从 `ai-docs/skills` 读取，更新 `AGENTS.md`
- 跳过特殊目录（如 `other`、`__pycache__`）
- **自动过滤**：跳过 description 为空的技能，不添加到 AGENTS.md
- 对缺少 SKILL.md 或 YAML 头信息不完整的技能给出警告
- **无需额外依赖**：内置简化的 YAML 解析器，无需安装 PyYAML（推荐安装以获得更好的兼容性）

### 打包和更新

#### 构建可执行文件

```bash
# 仅构建，不上传（默认）
cd cli-tool
./scripts/build.sh

# 构建并上传到默认服务器
./scripts/build.sh --upload

# 自定义服务器地址
./scripts/build.sh --upload --server 192.168.1.100::custom/path/

# 自定义下载地址
./scripts/build.sh --upload --download-url http://192.168.1.100/custom/path/driving

# 同时自定义服务器和下载地址
./scripts/build.sh --upload \
  --server 192.168.1.100::custom/path/ \
  --download-url http://192.168.1.100/custom/path/driving

# 查看帮助
./scripts/build.sh --help
```

**构建脚本参数：**
- `--upload`: 上传到服务器（默认不上传）
- `--server <地址>`: 指定上传服务器地址（默认：`192.168.100.90::android_archive/ai-tools/`）
- `--download-url <URL>`: 指定 version.json 中的 download_url（默认：`http://192.168.100.90/android/ai-tools/driving`）
- `-h, --help`: 显示帮助信息

**说明**：
- 默认只构建，不上传到服务器
- 使用 `--upload` 参数才会上传
- 可以自定义服务器地址和下载 URL
- 构建产物在 `dist/` 目录：`driving` 可执行文件和 `version.json`
- `build.sh` 构建独立可执行文件，无需 Python，文件较大（10-20MB）

#### 版本检查和更新

```bash
driving version              # 显示当前版本
driving version --check      # 检查是否有新版本（使用默认 URL）
driving version --check --url <url>  # 使用自定义 version.json URL 检查更新
driving update               # 从服务器更新到最新版本（使用默认 URL：https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json）
driving update --url <url>   # 使用自定义 version.json URL 更新，并自动保存到 .env 文件
```

**参数说明：**
- `--url`: 自定义 version.json 文件的完整 URL，会自动保存到项目根目录的 `.env` 文件，下次无需再指定

**示例**：
```bash
# 检查更新（使用默认 URL）
driving version --check

# 使用 driving-cli-tool 的 version.json URL 检查更新
driving version --check --url https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json

# 更新到最新版本（使用默认 URL）
driving update -y

# 使用 driving-cli-tool 的 version.json URL 更新（会自动保存到 .env）
driving update --url https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json -y

# 下次直接使用，会自动读取 .env 中的配置
driving update
```

**说明**：
- `version --check` - 从服务器检查是否有新版本可用
- `update` - 自动下载并安装最新版本
- 使用 `--url` 参数时，会自动将配置保存到项目根目录的 `.env` 文件
- URL 应该是 version.json 文件的完整路径
- 默认 URL：无（需要用户配置）
- 支持从服务器分发和更新，方便团队使用

## 目录结构

### 标准模式（使用 Git submodule）

```
your-project/
├── .driving/                    # Git submodule
│   ├── ai-docs/                # 远程框架文档和配置
│   │   ├── gitlist.json       # 远程框架配置
│   │   └── frameworks/        # 远程框架文档
│   ├── ai-docs-local/          # 本地项目文档和配置
│   │   ├── gitlist.json       # 本地项目配置
│   │   └── frameworks/        # 本地项目文档
│   └── submodules/            # 框架仓库（本地，不提交）
│       ├── ximage/            # XImage 框架
│       ├── xrequest/          # XRequest 框架
│       └── ...
├── .gitmodules                 # Git submodule 配置
└── ...
```

### 本地模式（直接在当前目录）

```
driving/                        # driving 仓库本身
├── ai-docs/                   # 远程框架文档和配置
│   ├── gitlist.json          # 远程框架配置
│   └── frameworks/           # 远程框架文档
├── ai-docs-local/            # 本地项目文档和配置
│   ├── gitlist.json          # 本地项目配置
│   └── frameworks/           # 本地项目文档
│       └── driving/          # driving 自身的文档
├── gitlist.json              # 根目录配置（兼容旧版本）
├── submodules/               # 框架仓库（本地，不提交）
│   ├── ximage/               # XImage 框架
│   ├── xrequest/             # XRequest 框架
│   └── ...
└── ...
```

## 多配置文件支持

Driving CLI 支持从多个 `gitlist.json` 文件加载框架配置，实现本地项目和远程框架的分离管理。

### 配置文件优先级

按以下顺序加载（优先级从高到低）：

1. **ai-docs-local/gitlist.json** - 本地项目配置（优先级最高）
2. **ai-docs/gitlist.json** - 远程框架配置
3. **gitlist.json** - 根目录配置（兼容旧版本）

### 本地项目标识

当框架配置中 `project_name`、`url`、`branch` 都设置为 `__local__` 时，表示本地项目：

```json
{
  "name": "driving",
  "description": "Driving CLI 工具",
  "project_name": "__local__",
  "url": "__local__",
  "branch": "__local__",
  "module": "driving",
  "sources": [
    "cli-tool/driving/*",
    "cli-tool/README.md"
  ]
}
```

### 文档存储路径

- **远程框架**：`ai-docs/frameworks/{框架名称}/`
- **本地项目**：`ai-docs-local/frameworks/{框架名称}/`

### 使用示例

```bash
# 列出所有框架（自动合并所有配置文件）
driving git-list

# 查看本地项目
driving git-list driving

# 查看远程框架
driving git-list xstatic

# 获取源码路径（自动在所有配置文件中查找）
driving git-sources driving
driving git-sources xstatic

# 安装框架（本地项目自动跳过）
driving git-install driving  # 跳过
driving git-install xstatic  # 正常安装
```

详细说明请参考 [多配置文件支持文档](docs/multi-gitlist-support.md)。

## 配置说明

### 环境变量配置

Driving CLI 支持通过环境变量进行配置，详细说明请参考 [配置指南](docs/CONFIGURATION.md)。

**可配置项：**

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DRIVING_REPO_URL` | Driving 仓库的 Git 地址 | 无（需要用户指定） |
| `DRIVING_UPDATE_VERSION_URL` | version.json 文件的完整 URL | 无（需要用户指定） |
| `DRIVING_DEFAULT_COMMIT_MESSAGE` | 默认的 Git 提交信息 | `update by driving` |
| `DRIVING_SENSITIVE_KEYWORDS` | IDE 配置中敏感信息的关键词列表（逗号分隔） | `api_key,token,secret,...` |

**快速配置：**

```bash
# 方式 1: 临时设置（当前会话）
export DRIVING_REPO_URL="https://github.com/your-org/driving"
export DRIVING_UPDATE_VERSION_URL="http://your-server.com/path/version.json"
export DRIVING_DEFAULT_COMMIT_MESSAGE="chore: update driving config"

# 方式 2: 使用 .env 文件
cp .env.example .env
# 编辑 .env 文件
source .env

# 方式 3: 在命令前直接设置
DRIVING_REPO_URL=https://github.com/your-org/driving driving install

# 方式 4: 使用命令参数（推荐，会自动保存到 .env）
driving install --url https://github.com/your-org/driving
driving update --url http://your-server.com/path/version.json
```

详细配置说明和使用场景请参考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

### gitlist.json 格式

框架列表配置文件 `.driving/gitlist.json` 支持以下字段：

```json
{
  "name": "框架名称",
  "project_name": "本地仓库名称",
  "url": "远程仓库地址",
  "branch": "分支名（可选）",
  "module": "模块名",
  "sources": ["源码的包名"],
  "extends": ["扩展框架名称（可选）"],
  "description": "框架描述",
  "creator": "创建者（如果是AI，则填模型名称）",
  "date": "创建日期（YYYY-MM-DD）"
}
```

**字段说明：**
- `name`: 框架标识名称，用于命令行操作
- `project_name`: 克隆到本地的仓库目录名（设置为 `__local__` 表示本地项目）
- `url`: Git 仓库地址（设置为 `__local__` 表示本地项目）
- `branch`: （可选）指定克隆的分支，不填则使用默认分支（设置为 `__local__` 表示本地项目）
- `module`: Android 模块名
- `sources`: 源码包名列表（本地项目使用相对于项目根目录的路径）
- `extends`: （可选）扩展框架名称列表，用于关联其他框架
- `description`: 框架功能描述
- `creator`: 创建者信息，如果是 AI 生成则填写模型名称
- `date`: 创建日期，格式为 YYYY-MM-DD

**本地项目支持：**
当 `project_name`、`url`、`branch` 都设置为 `__local__` 时，表示这是当前项目本身的代码，不需要从远程仓库拉取。此时：
- `sources` 字段使用相对于当前项目根目录的路径
- `driving git-install` 会跳过该框架的安装
- `driving git-sources` 会返回当前项目的完整路径
- 文档存储在 `ai-docs-local/frameworks/{框架名称}/`

**配置文件选择：**
- 本地项目配置应添加到 `ai-docs-local/gitlist.json`
- 远程框架配置应添加到 `ai-docs/gitlist.json` 或根目录 `gitlist.json`

**示例 1：远程框架**

```json
{
  "name": "xstatic",
  "project_name": "xstatic",
  "url": "https://git.example.com/android/base.git",
  "branch": "develop",
  "module": "library_xstatic",
  "sources": [
    "library_xstatic/src/main/java/hb/xstatic/core/*", 
    "library_xstatic/src/main/java/hb/xstatic/mvvm/*"
  ],
  "extends": [
    "xstatic2"
  ],
  "description": "Activity/Fragment基础封装框架",
  "creator": "开发团队",
  "date": "2024-01-20"
}
```

当执行 `driving git-install xstatic` 时，会自动克隆 `develop` 分支，并自动安装 `xstatic2` 扩展框架。

**示例 2：本地项目**

```json
{
  "name": "driving",
  "project_name": "__local__",
  "url": "__local__",
  "branch": "__local__",
  "module": "driving",
  "sources": [
    "cli-tool/driving/*",
    "cli-tool/README.md"
  ],
  "description": "Driving CLI 工具本身",
  "creator": "开发团队",
  "date": "2024-01-25"
}
```

当执行 `driving git-install driving` 时，会跳过安装，因为这是当前项目本身。`driving git-sources driving` 会返回当前项目根目录下的完整路径。

**extends 字段说明：**
- 用于关联其他框架，实现一个框架依赖多个仓库的场景
- `driving git-install` 会自动安装所有扩展框架
- `driving git-list` 会自动显示所有扩展框架的信息
- `driving git-sources` 会自动合并所有扩展框架的源码路径

## 使用场景

### 场景 1: 新项目开始使用（标准模式）

```bash
# 1. 创建项目
mkdir my-project && cd my-project
git init

# 2. 在当前目录添加 driving submodule

# 使用自定义框架文档管理仓库地址（会自动保存到 .env）
driving install --url https://github.com/your-org/driving
# 此命令会自动创建 .env 文件并保存 DRIVING_REPO_URL=https://github.com/your-org/driving

# 3. 提交（包括 .env 文件）
git add .gitmodules .driving .env
git commit -m "Initial commit with driving"

# 4. 安装框架
driving git-list
driving git-install ximage

# 5. 查看特定框架的所有仓库
driving git-list xstatic
```

**说明**：
- `driving install` 会在当前目录创建 `.driving` 目录
- 如果在子目录执行，`.driving` 会创建在该子目录中
- 使用 `--url` 参数时，会自动将配置保存到项目根目录的 `.env` 文件
- `.env` 文件包含项目配置（非敏感信息），建议提交到 Git 仓库
- 团队成员克隆项目后，会自动使用 `.env` 中的配置

### 场景 2: 在 driving 仓库本身使用（本地模式）

```bash
# 1. 进入 driving 仓库
cd driving

# 2. 直接安装框架（无需 install，自动检测为本地模式）
driving git-list
driving git-install ximage

# 3. 框架安装到 submodules/ 目录
# 4. 提交和推送
driving commit "add new framework"
driving push
```

### 场景 3: 团队成员克隆项目（标准模式）

```bash
# 使用自定义框架文档管理仓库地址（如果 .env 已配置 DRIVING_REPO_URL=https://github.com/your-org/driving，可省略url）
driving install --url https://github.com/your-org/driving

# 安装需要的框架
driving git-install ximage
```

### 场景 4: 更新配置

```bash
# 标准模式：更新 .driving 配置
driving pull
git add .driving
git commit -m "Update driving submodule"
git push

# 本地模式：更新当前目录
driving pull
```

### 场景 5: 同步 IDE 配置到项目

```bash
# 查看可用的 IDE 配置
driving ide-list

# 同步 Kiro IDE 配置
driving ide-sync kiro

# 配置会被复制到项目根目录的 .kiro/ 目录
# 如果 mcp.json 中包含敏感信息，会自动提取到 .env.local
# 提交配置到项目（.env.local 会被自动忽略）
git add .kiro .gitignore
git commit -m "Add Kiro IDE configuration"
git push
```

**敏感信息处理示例**：

假设 `install/.kiro/settings/mcp.json` 包含：
```json
{
  "mcpServers": {
    "my-service": {
      "env": {
        "API_KEY": "sk-1234567890abcdef",
        "AUTH_TOKEN": "token_xyz"
      }
    }
  }
}
```

执行 `driving ide-sync kiro` 后：

1. 项目根目录生成 `.env.local` 文件（敏感信息）：
```bash
# IDE 配置环境变量（敏感信息）
# 此文件包含敏感信息，请勿提交到 Git 仓库
# 优先级：.env.local > .env

API_KEY=sk-1234567890abcdef
AUTH_TOKEN=token_xyz
```

2. `.kiro/settings/mcp.json` 中的敏感值被替换：
```json
{
  "mcpServers": {
    "my-service": {
      "env": {
        "API_KEY": "${API_KEY}",
        "AUTH_TOKEN": "${AUTH_TOKEN}"
      }
    }
  }
}
```

3. `.env.local` 自动添加到 `.gitignore`，防止泄露

4. `.env` 文件用于非敏感的项目配置（如 DRIVING_REPO_URL），可以提交到仓库

## 故障排除

### 问题：克隆后 .driving 为空

```bash
# 解决
# 如果 .env 已配置 DRIVING_REPO_URL=https://github.com/your-org/driving，可省略url
driving install --url https://github.com/your-org/driving
```

### 问题：框架不存在

```bash
# 查看可用框架列表
driving git-list
```

## 文档

- [QUICKSTART.md](QUICKSTART.md) - 5 分钟快速开始指南
- [CHANGELOG.md](CHANGELOG.md) - 版本变更记录

## 开发

```bash
# 运行测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=driving --cov-report=html
```

## 要求

- Python 3.7+
- Click >= 8.0.0
- GitPython >= 3.1.0
- Rich >= 10.0.0
- PyYAML >= 6.0.0（可选，用于 skills-sync 命令，内置简化解析器可替代）
- Git 2.0+（仅在使用 Git 相关命令时需要）
- 执行 `driving install` 时需要在 Git 仓库中

## 获取帮助

```bash
# 查看所有命令
driving --help

# 查看特定命令的帮助
driving install --help
driving git-install --help
```
