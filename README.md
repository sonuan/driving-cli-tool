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

## load — 一次性加载所有上下文

> 在 AGENTS.md 作为强制前置调用

```bash
driving load                         # 输出 skills、rules、repos 等，供 AI 会话注入
driving load <repo-name>             # 只加载指定仓库的 skills/rules（repos 始终全量）
driving load <repo-name> <repo-name> # 同时加载多个仓库（空格或逗号分隔均可）
driving load <name>,<name>           # 逗号分隔写法
driving load --with framework        # 附带框架文档（关键词同样生效）
driving load --with agent            # 附带 agent 列表（关键词同样生效）
driving load --with framework,agent  # 同时附带框架和 agent
driving load --debug                 # 同上，同时输出调试日志
```

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
driving repo checkout <name> <branch>  # 切换仓库分支
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
driving framework load                        # 加载所有框架文档元信息（name/description/path）
driving framework load <keywords...>          # 按框架名或仓库名过滤（取并集）
```

## skill — 技能管理

```bash
driving skill list                              # 列出所有技能（按仓库分组）
driving skill list --repo <name>               # 只显示指定仓库的技能
driving skill list --edit                      # 交互模式，勾选启用/禁用技能（auto：自动选最短字段）
driving skill list --edit --mode enable        # 强制写 enabled 白名单
driving skill list --edit --mode disable       # 强制写 disabled 黑名单
driving skill load                   # 只加载 tags=base 的仓库技能（供 AI 注入上下文）
driving skill load <keywords...>     # 忽略 tags，repo.name 精确匹配或 name/description 模糊匹配（不区分大小写，取并集）
```

## rule — 规则管理

```bash
driving rule list                              # 列出所有规则（按仓库分组）
driving rule list --edit                      # 交互模式，勾选启用/禁用规则（auto：自动选最短字段）
driving rule list --edit --mode enable        # 强制写 enabled 白名单
driving rule list --edit --mode disable       # 强制写 disabled 黑名单
driving rule load                    # 只加载 tags=base 的仓库规则（供 AI 注入上下文）
driving rule load <keywords...>      # 忽略 tags，repo.name 精确匹配或 name/description 模糊匹配（不区分大小写，取并集）
```

## gate — 门禁规则管理

```bash
driving gate list                          # 以表格形式列出所有 gate（列：ID/Name/Type/Location/Repo）
driving gate list --json                   # 以 JSON 数组格式输出（每条记录含 id/name/type/location/repo）
driving gate load                          # 加载所有 gate 的完整内容（JSON）
driving gate load <gate-id>                # 加载指定 gate（大小写不敏感）
driving gate load <gate-id> <gate-id> ...  # 加载多个指定 gate
driving gate request <gate-id> --path <dir>                  # 执行门禁请求（auto_pass → 交互选择）
driving gate request <gate-id> --path <dir> --context '{}'   # 附带 JSON 上下文变量
driving gate request <gate-id> --path <dir> --dry-run        # 仅预览模板，不执行交互
driving gate status --path <dir>           # 查看所有 gate 状态
driving gate status <gate-id> --path <dir> # 查看指定 gate 状态
driving gate history <gate-id> --path <dir>  # 查看指定 gate 历史记录
driving gate pass <gate-id> --path <dir>   # 手动通过门禁
driving gate pass <gate-id> --path <dir> --note "说明"  # 带说明手动通过
```

`gate load` 输出格式：
```json
{
  "system_prompt": "...",   // 来自 gates.json 顶层 system_prompt 字段，多仓库拼接；为空时不输出
  "gates": [ { ...完整 gate 对象... } ]
}
```

- 任一 ID 找不到时，`gates` 返回空数组 `[]`，不报错退出
- 多仓库存在相同 ID 时，返回 `driving.config.json` 中排在最前的仓库的 gate，并输出警告

`gate request` / `gate pass` 返回结构（pass/auto_pass 且返工次数达到阈值时，额外包含 `self_refine` 字段）：
```json
{
  "gate_id": "GATE-R1",
  "result": "pass",
  "action": "确认",
  "next": "继续下一步",
  "note": "",
  "user_prompt": "...",
  "self_refine": {               // 仅在 pass/auto_pass 且 user_amend_count >= self_refine_threshold 时出现
    "amend_count": 3,
    "history": [
      { "at": "2026-05-21T18:00:00+08:00", "action": "修改", "note": "接口命名不规范" }
    ],
    "next": "在继续执行前，请先根据 self_refine.history 中的历史返工记录进行自我反思，分析反复返工的根本原因，输出改进提案后再执行 next"
  }
}
```

**gate 配置文件：** 仓库 `manifest.json` 中通过 `"gates": "rules/gates.json"` 指向门禁定义文件。

`gates.json` 顶层支持字段：
```json
{
  "version": "1.0.0",
  "system_prompt": "...",          // 注入 AI 会话的系统提示
  "user_prompt": "...",            // 每次门禁结果的行动指引
  "self_refine_threshold": 2,      // 触发 self-refine 的最低返工次数，默认 2
  "gates": [ { ...gate 对象... } ]
}
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
driving agent list                              # 列出所有 agent（按仓库分组）
driving agent list --repo <name>               # 只显示指定仓库的 agent
driving agent list --edit                      # 交互模式，勾选启用/禁用 agent（auto：自动选最短字段）
driving agent list --edit --mode enable        # 强制写 enabled 白名单
driving agent list --edit --mode disable       # 强制写 disabled 黑名单
driving agent load                        # 只加载 tags=base 的仓库 agent（供 AI 注入上下文）
driving agent load <keywords...>          # repo.name 精确匹配或 name/description 模糊匹配（不区分大小写，取并集）

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

## refine — Refine 自我完善提案管理

```bash
driving refine list                          # 列出所有仓库的 pending refine 提案（按类型分组）
driving refine list --type skill             # 只显示指定类型（skill/rule/agent/framework）
driving refine list --repo <name>            # 只显示指定仓库的 refine
driving refine load                          # 输出所有 pending refine 内容（JSON，供 AI 检索）
driving refine load <name...>                # 按文件名模糊匹配（包含即命中），支持多个，name可以是skill-name、rule-name、agent-name、framework-name
driving refine load --type rule              # 只加载指定类型的 refine
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
      ├── manifest.json          # 仓库元信息（可选），支持 min_cli_version、system_prompt、skills、rules、agents、gates 字段
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
      "skills": { "enabled": [], "disabled": ["some-skill"] },
      "rules": { "enabled": [], "disabled": [] },
      "agents": { "enabled": [], "disabled": [] },
      "check_sample_rate": 100
    },
    {
      "name": "f-message",
      "type": "local",
      "path": "ai-driving/f-message",
      "tags": []
    }
  ],
  "default_commit_message": "update by driving",
  "update_version_url": "",
  "check_sample_rate": 100
}
```

- `check_sample_rate`（全局）：`load` 时的更新检测采样率，默认 `100`（每次都检测）
- `check_sample_rate`（仓库级）：覆盖全局配置，优先级更高
  - `0`：永不检测该仓库更新
  - `1~100`：按概率采样，每次 `load` 随机决定是否检测
  - `-1`：始终检测，检测到更新时自动执行 `repo pull`（静默，不打扰用户）
  
- `tags` 含 `"base"` 的仓库在无关键词时默认加载；传入关键词时忽略 tags，repo.name 精确匹配（不区分大小写）或 name/description 模糊匹配（子串包含即命中）。

- `skills` / `rules` / `agents` 均支持白名单（`enabled` 非空）和黑名单（`disabled` 非空）两种模式。

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
driving skill load f-message          # 精确匹配 repo.name=f-message（加载该仓库全部技能）
driving skill load message qucall     # 模糊匹配 name/description 包含 "message" 或 "qucall"
driving rule load f-message
driving agent load                    # 只加载 tags=base 的仓库
driving agent load android            # 精确匹配 repo.name=android（加载该仓库全部 agent）
driving agent load reviewer           # 模糊匹配 name/description 包含 "reviewer"

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