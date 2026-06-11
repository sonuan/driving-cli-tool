# Webhook 上报 Payload 参考

`agent_webhook` 接收所有操作事件，每次上报的 payload 结构如下：

**顶层字段（每次都有）：**
- `operation` — 操作类型标识
- `triggered_at` — 北京时间，格式 `2026/06/11 14:30`
- `cli_version` — CLI 版本号

**顶层字段（有值时才出现）：**
- `description` — 一句话描述
- `actor` — 操作者 git user.name
- `branch` — 当前 git 分支
- `extra` — 操作专属扩展字段（嵌套对象，内部空值会被过滤）

---

## List：所有 operation 类型

| operation | 触发时机 | extra 字段 |
|---|---|---|
| `load_invoked` | `driving load` 调用成功 | `platform`、`with_modules` |
| `load_auto_updated` | load 内自动更新 CLI 成功 | `from_version`、`to_version` |
| `update_completed` | `driving update` 手动更新成功 | `from_version`、`to_version` |
| `repo_pulled` | 仓库拉取成功（手动或自动初始化） | `repo_name`、`branch`、`trigger` |
| `power_pulled` | load 内 power 自动拉取成功 | `repo_name`、`branch`、`trigger` |
| `agent_started` | 子 agent 启动（`driving agent report`） | `agent_name`、`feature_path`、`trigger` |
| `refine_committed` | refine 提案提交（`driving refine commit`） | `repo_name`、`file`、`target_type`、`target_name`、`trigger` |
| `refine_merged` | refine 提案合并（`driving refine merge`） | `repo_name`、`file`、`target_type`、`target_name`、`trigger` |

**`extra.trigger` 值示例：**
- `repo_pulled` / `power_pulled`：`"pull"` / `"init"` / `"load_auto_pull"`
- `agent_started`：`"dev-review 阶段，由 dev-workflow 触发"`
- `refine_committed/merged`：`"gate"` / `"gate — 返工超过 2 次"` / `"manual — 用户主动合并"`

---

## 聚合 Item：包含所有可能字段的单条 payload

```json
{
  "operation": "refine_merged",
  "description": "skill:android-standard-page — 补充 LiveData 使用规范（合并）",
  "triggered_at": "2026/06/11 14:30",
  "cli_version": "1.3.7",
  "actor": "张三",
  "branch": "feature/my-feature",
  "agent_name": "review-agent", 
  "feature": "ai-driving/aidoc/chatroom/2026-Q2/0608-陪伴悬赏-陪伴订单推荐与房间im展示陪伴信息", 
  "source": "dev-workflow 需求拆解审查", 
  "extra": {
    "platform": "android",
    "with_modules": "framework,agent",
    "from_version": "1.3.6",
    "to_version": "1.3.7",
    "repo_name": "driving-base",
    "branch": "main",
    "trigger": "gate — 返工超过 2 次",
    "agent_name": "android-reviewer",
    "feature_path": "ai-driving/aidoc/message/features/f-message",
    "file": "2026-06-11-skill-android-standard-page-livedata.md",
    "target_type": "skill",
    "target_name": "android-standard-page"
  }
}
```

> 实际每次上报只包含该 operation 相关的 extra 字段，空值不上报。
> `extra.branch` 与顶层 `branch` 含义不同：顶层是执行者当前所在的项目分支，`extra.branch` 是被拉取仓库的目标分支。

---

## List：各 operation 类型的完整 payload 示例

```json
[
  {
    "operation": "load_invoked",
    "description": "driving load 调用成功，平台：android",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "platform": "android",
      "with_modules": "framework,agent"
    }
  },
  {
    "operation": "load_auto_updated",
    "description": "CLI 自动更新：1.3.6 → 1.3.7",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "from_version": "1.3.6",
      "to_version": "1.3.7"
    }
  },
  {
    "operation": "update_completed",
    "description": "CLI 手动更新：1.3.6 → 1.3.7",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "from_version": "1.3.6",
      "to_version": "1.3.7"
    }
  },
  {
    "operation": "repo_pulled",
    "description": "仓库 'driving-base' 拉取成功（分支：main）",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "repo_name": "driving-base",
      "branch": "main",
      "trigger": "pull"
    }
  },
  {
    "operation": "power_pulled",
    "description": "power 'driving-base' 自动拉取成功",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "repo_name": "driving-base",
      "branch": "main",
      "trigger": "load_auto_pull"
    }
  },
  {
    "operation": "agent_started",
    "description": "子 agent 'android-reviewer' 启动，来源：dev-review 阶段，由 dev-workflow 触发",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "agent_name": "android-reviewer",
      "feature_path": "ai-driving/aidoc/message/features/f-message",
      "trigger": "dev-review 阶段，由 dev-workflow 触发"
    }
  },
  {
    "operation": "refine_committed",
    "description": "skill:android-standard-page — 补充 LiveData 使用规范",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "repo_name": "driving-base",
      "file": "2026-06-11-skill-android-standard-page-livedata.md",
      "target_type": "skill",
      "target_name": "android-standard-page",
      "trigger": "gate — 返工超过 2 次"
    }
  },
  {
    "operation": "refine_merged",
    "description": "skill:android-standard-page — 补充 LiveData 使用规范（合并）",
    "triggered_at": "2026/06/11 14:30",
    "cli_version": "1.3.7",
    "actor": "张三",
    "branch": "feature/my-feature",
    "extra": {
      "repo_name": "driving-base",
      "file": "2026-06-11-skill-android-standard-page-livedata.md",
      "target_type": "skill",
      "target_name": "android-standard-page",
      "trigger": "manual — 用户主动合并"
    }
  }
]
```
