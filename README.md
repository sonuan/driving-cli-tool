# Driving CLI Tool

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

命令行工具，用于管理 AI Coding 规范仓库、框架文档、技能、规则和需求目录。

## 安装

```bash
# 一键安装（macOS/Linux）
sudo sh -c 'curl -fsSL https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/driving -o /usr/local/bin/driving && chmod +x /usr/local/bin/driving'

# 或从源码安装（开发模式）
pip3 install -e .
```

## repo — 规范仓库管理

```bash
driving repo install --url <url>     # 安装远程仓库（Git submodule）
driving repo install --local <path>  # 安装本地仓库（软链接）
driving repo uninstall <name>        # 卸载仓库
driving repo list                    # 查看已安装仓库列表
driving repo pull                    # 从远程拉取更新
driving repo commit [message]        # 提交修改
driving repo push                    # 推送到远程
```

## framework — 框架文档管理

```bash
driving framework list                        # 列出所有框架（JSON 格式）
driving framework list <name>                 # 查看指定框架
driving framework list --table                # 表格格式输出
driving framework install <name>              # 安装框架仓库
driving framework checkout <name> <branch>    # 切换框架分支
driving framework pull <name>                 # 更新框架仓库
driving framework sources <name>              # 获取框架源码路径列表
```

## skill — 技能管理

```bash
driving skill list                   # 列出所有技能（按仓库分组）
driving skill list --repo <name>     # 只显示指定仓库的技能
driving skill list --edit            # 交互模式，勾选启用/禁用技能
driving skill load                   # 输出已启用技能信息（供 AI 注入上下文）
```

## rule — 规则管理

```bash
driving rule list                    # 列出所有规则（按仓库分组）
driving rule list --edit             # 交互模式，勾选启用/禁用规则
driving rule load                    # 输出已启用规则内容（供 AI 注入上下文）
```

## feature — 需求功能管理

```bash
driving feature list                          # 列出所有 features
driving feature list --repo <name>            # 只扫描指定仓库
driving feature list --keywords game,list     # 关键词过滤（OR 关系）
driving feature list --keywords game --keywords list
driving feature list --detail                 # 输出完整字段
```

## update — 更新管理

```bash
driving update                       # 检查并安装更新
driving update --check               # 仅检查是否有新版本
driving update --force               # 强制重新安装
driving update -y                    # 跳过确认提示
driving update --url <url>           # 使用自定义 version.json URL
```

---

## 参仓库目录结构

每个通过 `driving repo install` 安装的仓库，支持以下目录结构：

```
ai-driving/
  ├── <repo>/
      ├── frameworks/            # 框架文档
      │   ├── gitlist.json       # 框架列表配置
      │   └── <framework>/       # 各框架文档目录
      │       ├── FRAMEWORK.md   # 框架说明
      │       └── references/    # 参考文档
      ├── skills/                # 技能列表
      │   └── <skill>/
      │       └── SKILL.md       # 技能说明（含 YAML frontmatter）
      ├── rules/                 # 规则列表 
      │   └── <rule>.md          # 规则文件（含 YAML frontmatter）
      └── features/              # 需求功能
          └── <feature>/
              └── FEATURE.md     # 功能说明（含 YAML frontmatter）
```

### 示例

```
ai-driving/
├── driving/               # 远程仓库（Git submodule）
│   ├── frameworks/        # 框架文档（xstatic/ximage/xtoast 等）
│   │   └── gitlist.json
│   ├── skills/            # 通用技能（android-block-page/code-reviews 等）
│   └── rules/             # 通用规则
└── my-local/              # 本地仓库（项目私有配置）
    ├── frameworks/
    │   └── gitlist.json
    ├── skills/            # 项目私有技能
    ├── rules/             # 项目私有规则
    └── features/          # 需求功能文档
```

配置文件 `driving.config.json` 位于项目根目录，管理所有已安装仓库：

```json
{
  "version": "2",
  "repos": [
    {
      "name": "driving",
      "type": "remote",
      "url": "https://github.com/your-org/driving",
      "path": "ai-driving/driving"
    },
    {
      "name": "my-local",
      "type": "local",
      "path": "ai-driving/my-local"
    }
  ]
}
```

---

## 快速上手

```bash
# 1. 在项目中安装规范仓库
driving repo install --url https://github.com/your-org/driving

# 2. 查看可用框架并安装
driving framework list
driving framework install ximage

# 3. 查看技能列表
driving skill list

# 4. 在 AI 会话中加载上下文
driving skill load
driving rule load
```