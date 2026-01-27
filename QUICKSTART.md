# Driving CLI Tool 快速开始

## 5 分钟上手指南

### 1. 安装 Driving CLI Tool

```bash
cd /path/to/driving/cli-tool
pip3 install -e .
```

验证安装：
```bash
driving --help
```

### 2. 在项目中使用 Driving

#### 标准模式（在其他项目中使用）

```bash
# 进入你的项目目录
cd /path/to/your/project

# 确保是 Git 仓库
git status  # 如果不是，执行 git init

# 添加 driving 作为 Git submodule
driving install

# 提交 submodule 配置
git add .gitmodules .driving
git commit -m "Add driving submodule"
git push
```

现在你可以在项目中访问 `.driving/` 目录下的所有配置和文档！

#### 本地模式（在 driving 仓库本身使用）

```bash
# 进入 driving 仓库（已有 gitlist.json）
cd /path/to/driving

# 无需 install，直接使用
# 工具会自动检测到 gitlist.json 并切换到本地模式
driving git-list
```

### 3. 安装框架仓库

#### 标准模式

```bash
# 查看所有可用框架
driving git-list

# 查看特定框架的仓库
driving git-list xstatic

# 安装框架到 .driving/submodules/（支持自动切换到配置的分支）
driving git-install ximage
driving git-install xrequest

# 框架将安装到：
# .driving/submodules/ximage/
# .driving/submodules/xrequest/
```

#### 本地模式

```bash
# 查看所有可用框架
driving git-list

# 安装框架到 submodules/
driving git-install ximage
driving git-install xrequest

# 框架将安装到：
# submodules/ximage/
# submodules/xrequest/
```

### 4. 团队成员克隆项目

如果项目已经包含了 driving submodule：

```bash
# 克隆项目并初始化 submodule
git clone --recurse-submodules <project-url>

# 或者克隆后初始化
git clone <project-url>
cd project
git submodule update --init --recursive

# 安装框架（如果需要）
driving git-install ximage
```

### 5. 常用命令

#### 标准模式

```bash
# 更新 driving 配置
driving pull
git add .driving
git commit -m "Update driving"

# 查看可用框架
driving git-list

# 查看特定框架的仓库
driving git-list xstatic

# 以 JSON 格式查看框架信息（包含完整源码路径）
driving git-list xstatic --json

# 获取框架的源码路径列表（适合文档生成工具）
driving git-sources xstatic

# 安装框架仓库
driving git-install ximage

# 切换框架分支
driving git-checkout ximage dev

# 更新框架仓库
driving git-pull ximage

# 提交 driving 配置的修改
driving commit "update config"
driving push

# 查看可用的 IDE 配置
driving ide-list

# 同步 IDE 配置到项目
driving ide-sync kiro
```

#### 本地模式

```bash
# 更新当前仓库
driving pull

# 查看和安装框架（同标准模式）
driving git-list
driving git-sources xstatic
driving git-install ximage

# 提交当前目录的修改
driving commit "update config"
driving push

# IDE 配置管理（同标准模式）
driving ide-list
driving ide-sync kiro
```

## 工作流示例

### 场景 1: 新项目开始使用 Driving（标准模式）

```bash
# 1. 创建项目
mkdir my-project
cd my-project
git init

# 2. 添加 driving submodule
driving install

# 3. 提交
git add .gitmodules .driving
git commit -m "Initial commit with driving"

# 4. 查看和安装框架
driving git-list
driving git-install ximage
```

### 场景 2: 在 driving 仓库本身使用（本地模式）

```bash
# 1. 进入 driving 仓库
cd driving

# 2. 直接安装框架（无需 install）
driving git-list
driving git-install ximage

# 3. 框架安装到 submodules/ 目录
# 4. 提交和推送
driving commit "add new framework"
driving push
```

### 场景 3: 现有项目添加 Driving（标准模式）

```bash
# 1. 进入项目
cd existing-project

# 2. 添加 driving submodule
driving install

# 3. 提交
git add .gitmodules .driving
git commit -m "Add driving submodule"
git push
```

### 场景 4: 更新 Driving 配置

```bash
# 标准模式：更新 .driving 配置
driving pull
git add .driving
git commit -m "Update driving submodule"
git push

# 本地模式：更新当前目录
driving pull
```

### 场景 5: 管理框架仓库

```bash
# 查看所有可用框架
driving git-list

# 查看特定框架的所有仓库
driving git-list xstatic

# 安装多个框架
driving git-install ximage
driving git-install xrequest
driving git-install xdialog

# 切换到开发分支
driving git-checkout ximage dev

# 更新所有框架
driving git-pull ximage
driving git-pull xrequest
driving git-pull xdialog
```

### 场景 6: 同步 IDE 配置

```bash
# 查看可用的 IDE 配置
driving ide-list

# 增量同步 Kiro IDE 配置到项目根目录
# 只会覆盖同名文件，保留自定义配置
# 自动提取 mcp.json 中的敏感信息到 .env
driving ide-sync kiro

# 同步 Cursor IDE 配置
driving ide-sync cursor

# 检查并填写 .env 文件中的敏感信息
cat .env

# 提交 IDE 配置到项目（.env 会被自动忽略）
git add .kiro .gitignore
git commit -m "Add Kiro IDE configuration"
git push
```

## 目录结构说明

### 标准模式（使用 Git submodule）

```
your-project/           # 你的项目
├── .driving/           # Git submodule
│   ├── gitlist.json   # 框架列表配置
│   ├── ai-doc/        # AI 文档
│   ├── frameworks/    # 框架文档
│   └── submodules/    # 框架仓库（本地，不提交）
│       ├── ximage/    # XImage 框架
│       ├── xrequest/  # XRequest 框架
│       └── ...
├── .gitmodules        # Submodule 配置
└── ...
```

**重要说明**：
- `.driving/` 是 Git submodule，会被 Git 追踪
- `.driving/submodules/` 目录被 `.driving/.gitignore` 忽略，不会提交到仓库
- 每个开发者需要自己安装需要的框架

### 本地模式（直接在当前目录）

```
driving/               # driving 仓库本身
├── gitlist.json      # 框架列表配置（存在此文件即为本地模式）
├── ai-doc/           # AI 文档
├── frameworks/       # 框架文档
├── submodules/       # 框架仓库（本地，不提交）
│   ├── ximage/       # XImage 框架
│   ├── xrequest/     # XRequest 框架
│   └── ...
└── ...
```

**重要说明**：
- 当前目录存在 `gitlist.json` 时自动切换到本地模式
- 框架安装到 `submodules/` 目录
- 不需要执行 `install` 和 `uninstall` 命令

## 常见问题

**Q: 什么是标准模式和本地模式？**

A: 
- 标准模式：当前目录不存在 `gitlist.json`，使用 `.driving/` 目录（Git submodule）
- 本地模式：当前目录存在 `gitlist.json`，直接在当前目录操作
- 工具会自动检测并切换模式

**Q: 框架仓库存储在哪里？**

A: 
- 标准模式：`.driving/submodules/` 目录
- 本地模式：`submodules/` 目录

**Q: 为什么框架仓库不提交到 Git？**

A: 
- 框架仓库可能很大，不适合提交到项目仓库
- 每个开发者可以根据需要安装不同的框架
- `.gitignore` 已配置忽略 `submodules/` 目录

**Q: 如何更新 driving？**

A: 
```bash
# 标准模式：更新 .driving 配置
driving pull
git add .driving
git commit -m "Update driving"

# 本地模式：更新当前目录
driving pull
```

**Q: 团队成员需要安装 driving CLI 吗？**

A: 
- 推荐安装，可以方便地管理框架
- 如果只是使用 `.driving` 中的配置，不需要安装 CLI
- 如果需要安装框架仓库，必须安装 CLI

**Q: 在 driving 仓库本身如何使用？**

A:
- 直接使用，无需 `install`
- 工具会自动检测到 `gitlist.json` 并切换到本地模式
- 框架安装到 `submodules/` 目录

## 下一步

- 查看 [USAGE.md](USAGE.md) 了解详细使用说明
- 查看 [README.md](README.md) 了解项目架构

## 获取帮助

```bash
# 查看所有命令
driving --help

# 查看特定命令帮助
driving install --help
driving git-install --help
```
