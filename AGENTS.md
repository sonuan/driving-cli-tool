# AGENTS

## ⚠️ 强制前置步骤

**每次新会话的第一步，必须执行以下命令，否则不得回答任何问题：**

```bash
driving load
```

解析返回的 JSON：
- `system_prompt` 非空 → 作为系统指令执行
- `user_prompt` 非空 → 作为用户约束执行
- `skills` → 当前所有可用技能列表，每项包含 `name`、`description`、`path`
- `rules` → 当前所有可用规则列表，每项包含 `name`、`description`、`path`
- `repos` → 当前所有已安装AI工程基建的仓库列表，包含 `name`、`description`、`path`
- `agents` → 当前所有子代理列表，包含 `name`、`description`、`path`

未完成以上步骤前，不得响应任何用户请求。

## Repos 使用规则
收到用户请求后，对比 `repos` 仓库列表中每个仓库的 `description`：
- 若请求与某仓库相关，必须先调用 `driving load <repo-name>` 加载指定仓库内容，再作答
- 可同时匹配多个仓库，按需依次加载

## Skills 使用规则

1. 收到用户请求后，对比 `skills` 技能列表中每个技能的 `description`：
    - 若请求与某技能相关，必须先读取该技能路径下的 `SKILL.md`，再作答
    - 可同时匹配多个技能，按需依次加载
2. 调用 `driving skill load <skill-name>` 命令行进行动态加载指定技能

## Rules 使用规则

1. 收到用户请求后，对比 `rules` 规则列表中每个规则的 `description`：
    - 若请求与某规则相关，必须先读取该规则路径下的文件内容，再作答
    - 可同时匹配多个规则，按需依次加载
    - 若无法判断相关性，默认加载所有规则
2. 调用 `driving rule load <rule-name>` 命令行进行动态加载指定规则

## Agents 使用规则

1. 收到用户请求后，对比 `agents` 子代理列表中每个代理的 `description`：
    - 若请求与某子代理相关，调用子代理启动任务
    - 可同时匹配多个子代理，按需依次加载
2. 调用 `driving agent load <agent-name>` 命令行进行动态加载指定子代理


## 沟通指南

- 使用中文输出
- 前端页面内容使用英文

## 维护守则

**每次会话的任务执行完成，必须执行以下检查：**
- 检测测试用例是否要更新或执行
- 检查README.md文件是否要更新
- 检查driving-cli技能是否要更新
