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
driving load --platform <platform>   # 指定开发平台（android/iOS/harmony/kuikly），返回值中包含 platform 字段
driving load --debug                 # 同上，同时输出调试日志
```

`--platform` 可用值：`android`、`iOS`、`harmony`、`kuikly`


## repo — 规范仓库管理

```bash
driving repo install --url <url>              # 安装远程仓库（Git submodule）
driving repo install --url <url> --branch main              # 安装时指定分支（推荐）
driving repo install --url <url> --tag base --tag features  # 安装时指定标签（可多次指定）
driving repo install --url <url> --desc "描述"              # 安装时指定描述（--description 的简写）
driving repo install --url <url> --module "order:订单模块" --module "pay:支付模块"  # 安装时指定业务模块
driving repo install --local <path>           # 安装本地仓库（软链接）
driving repo install --local --name <name> --tag features --module "chat:聊天"  # 本地仓库 + 标签 + 模块
driving repo install --url <url> --power <power-name>  # Power 模式下指定写入哪个 power 的配置
driving repo uninstall <name>                 # 卸载仓库
driving repo list                             # 查看已安装仓库列表
driving repo load [name...]                   # 输出仓库列表（JSON，支持关键词过滤）
driving repo pull <name>                      # 从远程拉取更新
driving repo commit <name> <message>          # 提交修改
driving repo push <name>                      # 推送到远程
driving repo checkout <name> <branch>         # 切换仓库分支
```

`repo install` 新增参数说明：
- `--branch <branch>`：指定仓库分支，安装后自动 checkout；`driving repo install`（无参数）初始化时也会自动切换已配置的分支
- `--tag <tag>`：新增仓库标签，可多次指定，如 `--tag base --tag features`
- `--desc <desc>`：仓库描述，`--description` 的简写
- `--module <name:description>`：新增业务模块（格式 `name:description`），可多次指定

## power — Power 配置管理

Power 模式允许将多个目录下的 `driving.config.json` 合并使用，解决多分支场景下配置文件需要跨分支合并的问题。

**工作原理：** 在项目根目录创建 `driving.power.json`，列出多个包含 `driving.config.json` 的目录（本地或远程 git 仓库），driving-cli 运行时自动合并所有配置。不创建该文件则完全走传统模式，零感知。

```bash
# 远程模式：将远程仓库作为 git submodule 安装并注册为 power
# 幂等安装：根据本地状态自动判断执行路径
driving power install --url https://git.xxx.com/config.git
driving power install --url https://git.xxx.com/config.git --name feature
driving power install --url https://git.xxx.com/config.git --branch master  # 指定分支（推荐）
driving power install --url https://git.xxx.com/config.git --force  # 强制重新安装

# 本地模式：注册已存在的本地目录（须包含 driving.config.json）
driving power install --name main --path ai-driving/my-local

# 无参数：初始化 driving.power.json 中所有未就绪的 power（clone 缺失的远程 power）
driving power install

# 拉取远程 power 更新
driving power pull              # 更新所有远程 power
driving power pull feature      # 更新指定 power

# 管理
driving power list              # 列出所有已配置的 power
driving power uninstall feature # 卸载一个 power 条目
```

**合并规则：**
- `repos`：按 `name` 去重，先出现的 power 优先
- 单值字段（`gate_webhook`、`update_version_url` 等）：多个 power 中非空值必须相同，否则报错
- 某个 power 的 `driving.config.json` 不存在时自动跳过该 power
- 所有 power 均无有效配置时，降级读取项目根目录的 `driving.config.json`

**`driving power install --url` 安装逻辑（幂等）：**
1. 本地目录不存在 → clone + 注册
2. 本地目录存在但未注册 → 直接注册到 `driving.power.json`
3. 已注册但无 `driving.config.json` → 提示运行 `driving repo install --power <name>` 生成配置
4. 已完整安装 → 提示已存在，加 `--force` 可重新安装

**`driving power install`（无参数）初始化逻辑：**
- remote power，目录不存在 → `submodule update --init` 或 `submodule add`
- remote power，目录已初始化 → 跳过
- local power，目录存在 → 跳过
- local power，目录不存在 → warning 提示，跳过（本地目录需手动准备）

**`driving load` 自动更新：** 每次执行 `driving load` 时，会先自动检测并初始化未加载的 power 和 repo（git submodule 目录存在但为空的情况，切换分支后无需手动 `git submodule update --init`），再检查所有远程 power 是否有更新并自动拉取，最后检查各 `driving.config.json` 里的 repos 更新。

**`branch` 字段（安装时切换分支）：** power 初始化完成后，若目录下缺少 `driving.config.json`：
- 配置了 `branch` → 自动执行 `git checkout <branch>`，切换到指定分支
- 未配置 `branch` → 输出警告，提示用户手动检查或在 `driving.power.json` 中配置 `branch` 字段

适用场景：power 仓库的默认分支（如 feature 分支）不含 `driving.config.json`，而 master 分支才有。

**`repo_config` 字段（`driving load` 运行时分支切换）：** 与 `branch` 同级，放在每个 power entry 内部，控制 `driving load` 时该 power 自身及其下各 repo 应切换到哪个分支，与 `branch`（仅在安装时生效）相互独立。

- key 为 power name（控制该 power 目录自身的分支）或 power 下的 repo name（控制该 repo 的分支）
- 分支优先级：
  - power 自身：`repo_config[power_name].branch` > `PowerEntry.branch` > 不切换
  - 各 repo：`repo_config[repo_name].branch` > `driving.config.json` 里 `repo.branch` > 不切换
- 切换失败时输出**错误**，不中断其他 power/repo 的处理
- 只影响 `driving load`，`power install` / `repo install` 不受影响

适用场景：开发阶段在 power 或 repo 打了功能分支，不希望每次 `driving load` 把分支强制切回主分支，通过 `repo_config` 精确指定各 repo 在 load 时应使用的分支。


```bash
# 1. 从远程安装 power（作为 submodule，跟随主项目 git），指定 master 分支
driving power install --url https://git.xxx.com/branch-config.git --name feature --branch master

# 2. 安装新仓库时指定写入哪个 power 的配置
driving repo install --url https://... --power feature
```

### driving.power.json 结构

```json
{
  "powers": [
    {
      "name": "main",
      "type": "local",
      "path": "ai-driving/main-config",
      "url": null,
      "description": ""
    },
    {
      "name": "feature",
      "type": "remote",
      "path": "ai-driving/feature-config",
      "url": "https://git.xxx.com/feature-config.git",
      "description": "feature 分支配置",
      "branch": "master",
      "repo_config": {
        "feature": { "branch": "feature/my-work" },
        "driving-base": { "branch": "develop" }
      }
    }
  ]
}
```

- `url` 有值 → remote 类型（git submodule，支持 `power pull` 更新）
- `url` 无值 → local 类型（本地目录）
- `branch`：安装（`power install`）时自动切换的分支
- `repo_config`：与 `branch` 同级，`driving load` 时各 repo/power 的分支覆盖配置
  - key 为 repo name 或 power name（同名视为同一实体）
  - `repo_config[name].branch` 优先级高于 `branch`；不配置则使用 `branch`，都不配置则不切换

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
driving gate request <gate-id> --path <dir>                                       # 执行门禁请求（auto_pass → 交互选择）
driving gate request <gate-id> --path <dir> --platform <platform>                 # 指定平台，gate-state.json 写入 {dir}/docs/{platform}/
driving gate request <gate-id> --path <dir> --platform <platform> --owner <owner> # 指定负责人（main/owner-main/apple），激活 $vars.owner_dir
driving gate request <gate-id> --path <dir> --context '{}'                        # 附带 JSON 上下文变量
driving gate request <gate-id> --path <dir> --dry-run                             # 仅预览模板，不执行交互
driving gate respond <gate-id> --path <dir> --action <操作名>                      # 非交互式提交门禁选择（配合非终端环境使用）
driving gate respond <gate-id> --path <dir> --action <操作名> --note ""            # 修改类操作附带说明
driving gate respond <gate-id> --path <dir> --platform <platform> --owner <owner> --action <操作名>  # 指定平台和负责人
driving gate status --path <dir>                                                   # 查看所有 gate 状态
driving gate status --path <dir> --platform <platform>                            # 查看指定平台的 gate 状态
driving gate status --path <dir> --platform <platform> --owner <owner>            # 同时指定负责人
driving gate status <gate-id> --path <dir> --platform <platform>                  # 查看指定平台的指定 gate 状态
driving gate history <gate-id> --path <dir> --platform <platform>                 # 查看指定 gate 历史记录
driving gate history <gate-id> --path <dir> --platform <platform> --owner <owner> # 同时指定负责人
driving gate pass <gate-id> --path <dir> --platform <platform>                    # 手动通过门禁
driving gate pass <gate-id> --path <dir> --platform <platform> --note "说明"      # 带说明手动通过
```

`gate load` 输出格式：
```json
{
  "system_prompt": "...",   // 来自 gates.json 顶层 system_prompt 字段，多仓库拼接；为空时不输出
  "vars": [                 // CLI 内部预计算常量说明，始终输出
    { "name": "$vars.platform_dir", "description": "...", "example": "..." }
  ],
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
    ]
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

**gate 模板变量：** `gates.json` 的 `template`、`actions.next`、`auto_pass.conditions` 等字段支持以下变量：

| 变量 | 来源 | 说明 |
|------|------|------|
| `{{path}}` | `--path` 参数 | feature 目录绝对路径 |
| `{{context.xxx}}` | `--context` JSON | 用户传入的上下文字段 |
| `{{state.xxx}}` | gate-state.json | 当前 gate 的历史状态 |
| `{{$vars.platform_dir}}` | CLI 内部计算 | `{path}/docs/{platform}`（无 platform 时为 `{path}/docs`） |
| `{{$vars.owner_dir}}` | CLI 内部计算 | 传 `--owner` 时为 `{platform_dir}/owner-{owner}`（已含 `owner-` 前缀则直接使用）；未传时等于 `{platform_dir}` |

`{{$vars.xxx}}` 变量由 CLI 在执行 `gate request` 时自动注入，**路径结构变更只需修改 CLI，无需改动 gates.json**。完整变量列表可通过 `driving gate load` 输出的 `vars` 字段查看。

## feature — 需求功能管理

```bash
driving feature modules                       # 列出所有 features 仓库的业务模块（JSON）
driving feature modules --features-only       # 只输出 tags 含 features 的仓库模块
driving feature list                          # 列出所有 features（从 modules 聚合路径遍历）
driving feature list --repo <name>            # 只扫描指定仓库
driving feature list --keywords game,list     # 关键词过滤（OR 关系）
driving feature list --detail                 # 输出完整字段
```

`feature modules` 输出规则：
- 仓库有 `modules`：每个 module 输出 `name`、`description`、`path`（`{repo.path}/{module.name}`）
- `tags` 含 `"features"` 且 `modules` 非空的仓库：只输出 module 条目，**不追加** `features` 兜底
- 其余仓库（含 `tags=features` 但 `modules` 为空）：追加 `{repo.path}/features` 兜底条目

`feature list` 扫描规则：
- 普通仓库（无 `features` tag）：扫描 `{module_path}/` 下各子目录，查找 `FEATURE.md`（单层）
- `tags` 含 `"features"` 的仓库：使用**深度递归扫描**，兼容多层目录结构（如 `{module}/{年度-季度}/{日期}-{feature}/FEATURE.md`），并自动提取 `quarter` 字段（如 `2026-Q2`）

`feature list` 输出字段（精简模式）：`name`、`title`、`description`、`status`、`path`、`repo`、`quarter`、`urls`

`driving.config.json` 配置示例（多层目录仓库）：
```json
{
  "name": "aidoc",
  "type": "remote",
  "path": "ai-driving/aidoc",
  "tags": ["features"],
  "modules": [
    {"name": "family",  "description": "家族项目"},
    {"name": "message", "description": "私信项目"}
  ]
}
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

# 导出到外部 AI 工具（kiro 使用硬链接，其他工具使用软链接；文件已存在时自动跳过）
driving agent export <name> --tool kiro              # → .kiro/agents/<name>.md（硬链接，需含 tools 字段）
driving agent export <name> --tool claude-code       # → .claude/agents/<name>.md（软链接）
driving agent export <name> --tool cursor            # → .cursor/rules/<name>.mdc（软链接，需含 alwaysApply 字段）
driving agent export <name> --tool windsurf          # → .windsurf/rules/<name>.md（软链接，需含 trigger 字段）
driving agent export <name> --tool codex             # → .codex/agents/<name>.toml（TOML 文件，内容从 AGENTS.md 转换生成）
driving agent export <name> --tool kiro --force      # 强制重建硬链接

# 上报子 agent 启动事件（由子 agent 在加载步骤第 0 步调用）
driving agent report <name> --path <feature-dir> --source "<触发来源描述>"
```

## refine — Refine 自我完善提案管理

```bash
driving refine list                          # 列出所有仓库的 pending refine 提案（按类型分组）
driving refine list --type skill             # 只显示指定类型（skill/rule/agent/framework）
driving refine list --repo <name>            # 只显示指定仓库的 refine
driving refine load                          # 输出所有 pending refine 内容（JSON，供 AI 检索）
driving refine load <name...>                # 按文件名模糊匹配（包含即命中），支持多个，name可以是skill-name、rule-name、agent-name、framework-name
driving refine load --type rule              # 只加载指定类型的 refine
driving refine commit <repo>                 # 提交 pending refine 到 git（add + commit + push）
driving refine commit <repo> --no-push       # 只 commit，不 push（离线场景）
driving refine commit <repo> --file <path>   # 提交指定文件（相对于仓库根目录的路径，必填，可多次指定）

# 合并收尾：追加 REFINE_LOG → 上报 webhook → 删除 refine 文件 → commit/push
driving refine merge <repo> --file <path>                          # 完成 refine 合并收尾（--file 必填，可多次指定）
driving refine merge <repo> --file <path> --changed-file <path>    # 指定实际修改的正式文件（可多次指定）
driving refine merge <repo> --file <path> --trigger-source manual  # 指定本次合并操作的触发来源（gate/self/manual），用于 webhook 上报
driving refine merge <repo> --file <path> --trigger-reason "..."   # 指定本次合并操作的触发原因，用于 webhook 上报
driving refine merge <repo> --file <path> --no-push                # 只 commit，不 push

# REFINE_LOG.md 变更记录管理
driving refine log append <repo> "<entry>"   # 追加一条已生效的变更记录（文件不存在时自动创建）
driving refine log get <repo>                # 读取当前变更记录内容
```

`refine log append` 条目格式：
```
[YYYY-MM-DD] [即时|合并] <target_type>:<target_name> — <描述> (operator: <触发者>)
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
# codex 无需额外字段；可选：codex_model、codex_reasoning_effort、codex_sandbox_mode（read-only / workspace-write）
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
      "check_sample_rate": -1
      "type": "local",
      "path": "ai-driving/f-message",
      "tags": ["features"],
      "modules": [
        {"name": "chat", "description": "聊天模块"},
        {"name": "live", "description": "直播模块"}
      ]
    }
  ],
  "default_commit_message": "update by driving",
  "update_version_url": "",
  "check_sample_rate": -1,
  "gate_webhook": "https://...",
  "agent_webhook": "https://..."
}
```

- `check_sample_rate`（全局）：`load` 时的更新检测采样率，未配置时默认 `-1`（每次自动检测并拉取）
- `check_sample_rate`（仓库级）：覆盖全局配置，优先级更高
  - `0`：永不检测该仓库更新
  - `1~100`：按概率采样，每次 `load` 随机决定是否检测
  - `-1`：始终检测，检测到更新时自动执行 `repo pull`（静默，不打扰用户）
  
- `tags` 含 `"base"` 的仓库在无关键词时默认加载；传入关键词时忽略 tags，repo.name 精确匹配（不区分大小写）或 name/description 模糊匹配（子串包含即命中）。

- `modules`：业务模块列表，每项包含 `name` 和 `description`。`tags` 含 `"features"` 的仓库设置 modules 后，`driving feature modules` 会展开每个 module，`driving feature list` 从各 module 目录扫描需求（支持多层目录结构，如 `{module}/{年度-季度}/{feature}/FEATURE.md`）。

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