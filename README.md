# Driving CLI Tool

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

命令行工具，用于管理 AI Coding 规范仓库、框架文档、技能、规则、需求目录和 Agent。

## 安装

```bash
# 一键安装（macOS/Linux）
sudo sh -c 'curl -fsSL https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/driving -o /usr/local/bin/driving && chmod +x /usr/local/bin/driving'

# 或从源码安装（开发模式）
pip3 install -e .
```

---

## repo — 规范仓库管理

```bash
driving repo install --url <url>     # 安装远程仓库（Git submodule）
driving repo install --local <path>  # 安装本地仓库（软链接）
driving repo uninstall <name>        # 卸载仓库
driving repo list                    # 查看已安装仓库列表
driving repo load [name...]          # 输出仓库列表（JSON，支持关键词过滤）
driving repo pull <name>             # 从远程拉取更新
driving repo commit <name> <message> # 提交修改
driving repo push <name>             # 推送到远程
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

## load — 一次性加载所有上下文

```bash
driving load                         # 输出 skills、rules、agents、repos 等，供 AI 会话注入
driving load <repo-name>             # 只加载指定仓库的 skills/rules/agents（repos 始终全量）
driving load <repo-name> <repo-name> # 同时加载多个仓库
```

## skill — 技能管理

```bash
driving skill list                   # 列出所有技能（按仓库分组）
driving skill list --repo <name>     # 只显示指定仓库的技能
driving skill list --edit            # 交互模式，勾选启用/禁用技能
driving skill load                   # 只加载 tags=base 的仓库技能（供 AI 注入上下文）
driving skill load <keywords...>     # 忽略 tags，精确匹配 repo.name 或 skill.name（取并集）
```

## rule — 规则管理

```bash
driving rule list                    # 列出所有规则（按仓库分组）
driving rule list --edit             # 交互模式，勾选启用/禁用规则
driving rule load                    # 只加载 tags=base 的仓库规则（供 AI 注入上下文）
driving rule load <keywords...>      # 忽略 tags，精确匹配 repo.name 或 rule.name（取并集）
```

## feature — 需求功能管理

```bash
driving feature list                          # 列出所有 features
driving feature list --repo <name>            # 只扫描指定仓库
driving feature list --keywords game,list     # 关键词过滤（OR 关系）
driving feature list --detail                 # 输出完整字段
```

## agent — Agent 管理

每个 agent 存放在仓库的 `agents/<name>/` 目录，包含：
- `AGENTS.md`（必填）：YAML frontmatter + agent 指令/系统提示
- `SOUL.md`（可选）：人格、价值观、沟通风格
- `MEMORY.md`（可选）：最佳实践知识沉淀，随 git 同步，团队共享

```bash
driving agent list                        # 列出所有 agent（按仓库分组）
driving agent list --repo <name>          # 只显示指定仓库的 agent
driving agent list --edit                 # 交互模式，勾选启用/禁用 agent
driving agent load                        # 只加载 tags=base 的仓库 agent（供 AI 注入上下文）
driving agent load <keywords...>          # 精确匹配 repo.name 或 agent.name（取并集）

# 记忆管理
driving agent memory get <name>                  # 读取 MEMORY.md 内容
driving agent memory append <name> <content>     # 追加知识条目
driving agent memory set <name> <content>        # 覆盖写入（会提示确认）
driving agent memory set <name> <content> --force  # 强制覆盖
driving agent memory clear <name>                # 清空 MEMORY.md

# 导出到外部 AI 工具（软链接模式，AGENTS.md 更新后自动生效；文件已存在时自动跳过）
driving agent export <name> --tool kiro              # → .kiro/agents/<name>.md（需含 tools 字段）
driving agent export <name> --tool claude-code       # → .claude/agents/<name>.md
driving agent export <name> --tool cursor            # → .cursor/rules/<name>.mdc（需含 alwaysApply 字段）
driving agent export <name> --tool windsurf          # → .windsurf/rules/<name>.md（需含 trigger 字段）
driving agent export <name> --tool kiro --force      # 强制重建软链接
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

## 仓库目录结构

每个通过 `driving repo install` 安装的仓库，支持以下目录结构：

```
ai-driving/
  └── <repo>/
      ├── frameworks/            # 框架文档
      │   ├── gitlist.json       # 框架列表配置
      │   └── <framework>/
      │       ├── FRAMEWORK.md
      │       └── references/
      ├── skills/                # 技能列表
      │   └── <skill>/
      │       └── SKILL.md       # 含 YAML frontmatter（name、description 必填）
      ├── rules/                 # 规则列表
      │   └── <rule>.md          # 含 YAML frontmatter（name 必填）
      ├── features/              # 需求功能
      │   └── <feature>/
      │       └── FEATURE.md     # 含 YAML frontmatter（name 必填）
      ├── agents/                # Agent 定义
      │   └── <agent>/
      │       ├── AGENTS.md      # 指令/系统提示（必填）
      │       ├── SOUL.md        # 人格与行为风格（可选）
      │       └── MEMORY.md      # 最佳实践知识沉淀（可选）
      ├── refines/             # 规范变更提案（由 self-refine 技能写入，需 owner 审批合并）
      │   └── YYYY-MM-DD-<type>-<name>-<brief>.md
      └── REFINE_LOG.md     # 规范进化变更日志
```

### AGENTS.md frontmatter 字段

```markdown
---
name: android-reviewer          # 唯一标识（必填）
description: Android 代码审查专家，专注于架构合规性和性能问题。  # 触发描述（必填）
role: reviewer                  # 角色类型：reviewer / architect / assistant 等（可选）
version: 1.0.0                  # 版本号（可选）
skills:                         # 激活时自动加载的技能列表（可选）
  - code-reviews
  - android-standard-page
# export 到各工具时所需字段（缺少则 export 报错）
tools: ["read", "shell"]        # Kiro 所需
alwaysApply: false              # Cursor 所需
trigger: manual                 # Windsurf 所需
# claude-code 无需额外字段
---
```

### driving.config.json 结构

```json
{
  "version": "2",
  "repos": [
    {
      "name": "driving",
      "type": "remote",
      "url": "https://github.com/your-org/driving",
      "path": "ai-driving/driving",
      "tags": ["base"],
      "skills": { "enabled": [], "disabled": [] },
      "rules":  { "enabled": [], "disabled": [] },
      "agents": { "enabled": [], "disabled": [] }
    },
    {
      "name": "f-message",
      "type": "local",
      "path": "ai-driving/f-message",
      "tags": []
    }
  ],
  "default_commit_message": "update by driving",
  "update_version_url": ""
}
```

`tags` 含 `"base"` 的仓库在无关键词时默认加载；传入关键词时忽略 tags，只按 repo.name / skill.name / rule.name 精确匹配。

`skills` / `rules` / `agents` 均支持白名单（`enabled` 非空）和黑名单（`disabled` 非空）两种模式。

### gitlist.json 配置

`project_name`、`url`、`branch` 均为 `__local__` 时，定位到本地项目源码路径，不需要拉取 git 仓库。

```json
[
  {
    "name": "框架名称",
    "description": "框架描述",
    "project_name": "仓库名称",
    "url": "远程仓库地址",
    "branch": "分支名（可选）",
    "module": "模块名",
    "creator": "创建者",
    "date": "YYYY-MM-DD",
    "sources": ["源码路径"],
    "extends": ["依赖的其他框架名"]
  }
]
```

---

## 快速上手

```bash
# 1. 安装规范仓库
driving repo install --url https://github.com/your-org/driving

# 2. 在 AI 会话中加载上下文
driving skill load                    # 只加载 tags=base 的仓库
driving skill load f-message          # 精确匹配 repo.name=f-message
driving skill load f-message f-qucall # 精确匹配多个 repo.name，取并集
driving rule load f-message
driving agent load                    # 只加载 tags=base 的仓库
driving agent load android            # 精确匹配 repo.name=android
driving agent load android-reviewer  # 精确匹配 agent.name=android-reviewer

# 3. 查看可用框架并安装
driving framework list
driving framework install ximage

# 4. 使用 agent 记忆
driving agent memory append android-reviewer "- 偏好简洁的代码风格，不喜欢过度注释"
driving agent memory get android-reviewer

# 5. 同步记忆到团队
driving repo commit driving "update agent memory: android-reviewer"
driving repo push driving
```