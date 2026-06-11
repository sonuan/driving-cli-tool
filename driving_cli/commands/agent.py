"""Agent 子命令组

提供 `driving agent` 系列命令，用于管理多 agent。
每个 agent 存放在仓库的 agents/<name>/ 目录下，包含：
  - AGENTS.md   agent 指令/系统提示（必填，含 YAML frontmatter）
  - SOUL.md     agent 人格与行为风格（可选）
  - MEMORY.md   最佳实践知识沉淀（可选，团队共享，随 git 同步）
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning


# ---------------------------------------------------------------------------
# YAML frontmatter 解析
# ---------------------------------------------------------------------------

def _parse_frontmatter(md_path: Path) -> Optional[Dict]:
    """解析 .md 文件的 YAML frontmatter，返回字段字典。

    要求文件以 --- 开头，找到第二个 --- 后停止读取，避免加载大文件正文。
    缺少 name 字段时返回 None。
    """
    from driving_cli.utils.yaml_parser import parse_frontmatter
    return parse_frontmatter(md_path, required_fields=["name"])


# ---------------------------------------------------------------------------
# 扫描 / 过滤
# ---------------------------------------------------------------------------

def _load_manifest_agents(repo_dir: Path) -> Optional[dict]:
    """读取仓库 manifest.json 中的 agents 配置，作为仓库级默认值"""
    manifest_path = repo_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = json_module.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("agents") or None
    except Exception:
        return None


def scan_agents_from_dir(repo_name: str, agents_dir: Path, quiet: bool = False) -> List[Dict]:
    """扫描单个仓库的 agents/ 目录，返回 agent 元数据列表。

    每个 agent 目录必须包含 AGENTS.md（含 YAML frontmatter 和 name 字段）。
    """
    agents: List[Dict] = []

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        if agent_dir.name.startswith((".", "__")):
            continue

        agents_md = agent_dir / "AGENTS.md"
        if not agents_md.exists():
            if not quiet:
                log_warning(f"跳过 {agent_dir.name}：未找到 AGENTS.md")
            continue

        meta = _parse_frontmatter(agents_md)
        if not meta:
            if not quiet:
                log_warning(f"跳过 {agent_dir.name}：AGENTS.md 缺少 YAML frontmatter 或 name 字段")
            continue

        description = str(meta.get("description", "") or "")
        if not description.strip():
            if not quiet:
                log_warning(f"跳过 agent {meta['name']}：description 为空")
            continue

        # 检测可选文件
        has_soul = (agent_dir / "SOUL.md").exists()
        has_memory = (agent_dir / "MEMORY.md").exists()

        # skills 字段支持列表或逗号分隔字符串
        raw_skills = meta.get("skills") or []
        if isinstance(raw_skills, str):
            raw_skills = [s.strip() for s in raw_skills.split(",") if s.strip()]

        agents.append({
            "name": str(meta["name"]),
            "description": description,
            "role": str(meta.get("role", "") or ""),
            "version": str(meta.get("version", "") or ""),
            "skills": raw_skills,
            "path": f"ai-driving/{repo_name}/agents/{agent_dir.name}/",
            "has_soul": has_soul,
            "has_memory": has_memory,
        })

        if not quiet:
            log_info(f"发现 agent: {meta['name']} (来自仓库 {repo_name})")

    return agents


def _filter_agents(agents: List[Dict], repo_config: RepoConfig) -> List[Dict]:
    """根据仓库 agents 配置过滤（白名单/黑名单）。"""
    if repo_config.agents is None:
        return agents
    enabled = repo_config.agents.get("enabled") or []
    disabled = repo_config.agents.get("disabled") or []
    if enabled:
        return [a for a in agents if a["name"] in enabled]
    if disabled:
        return [a for a in agents if a["name"] not in disabled]
    return agents


def _merge_agents(agents_dirs: List[Tuple[str, Path]],
                  repo_configs: Optional[List[RepoConfig]] = None,
                  quiet: bool = False) -> List[Dict]:
    """合并所有仓库的 agent 列表，同名 agent 按仓库顺序去重。"""
    repo_config_map: Dict[str, RepoConfig] = {}
    if repo_configs:
        for rc in repo_configs:
            repo_config_map[rc.name] = rc

    merged: Dict[str, Dict] = {}
    result: List[Dict] = []

    for repo_name, agents_dir in agents_dirs:
        repo_agents = scan_agents_from_dir(repo_name, agents_dir, quiet=quiet)
        rc = repo_config_map.get(repo_name)
        if rc is not None:
            repo_agents = _filter_agents(repo_agents, rc)

        for agent in repo_agents:
            aname = agent["name"]
            if aname in merged:
                if not quiet:
                    log_warning(
                        f"agent '{aname}' 在多个仓库中存在，"
                        f"使用 {merged[aname]['path']}（跳过 {agent['path']}）"
                    )
            else:
                merged[aname] = agent
                result.append(agent)

    return result


# ---------------------------------------------------------------------------
# 命令组
# ---------------------------------------------------------------------------

@click.group(name="agent")
def agent_group():
    """Agent 管理

    - 支持扫描多个仓库的 agents/ 目录\n
    - 管理多个仓库 agent 的启用和禁用\n
    - 读写 agent 的持久化记忆（memory/）
    """
    pass


# ── agent list ──────────────────────────────────────────────────────────────

@agent_group.command(name="list")
@click.option("--repo", "repo_name", default=None, help="只显示指定仓库的 agent")
@click.option("--edit", is_flag=True, default=False, help="进入交互模式，勾选启用/禁用 agent")
@click.option("--mode", type=click.Choice(["auto", "enable", "disable"]), default="auto",
              help="保存模式：auto 自动选择（默认），enable 强制写 enabled，disable 强制写 disabled")
def agent_list(repo_name: Optional[str], edit: bool, mode: str):
    """列出所有 agent，按仓库分组显示启用状态，支持编辑模式。

    示例：
        driving agent list
        driving agent list --repo driving
        driving agent list --edit
        driving agent list --edit --mode enable
        driving agent list --edit --mode disable
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        if repo_name:
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            agents_dir = config_manager.get_repo_dir(repo_name) / "agents"
            agents_dirs = [(repo_name, agents_dir)] if agents_dir.exists() else []
            target_repos = [repo_cfg]
        else:
            agents_dirs = config_manager.get_all_agents_dirs()
            target_repos = config_manager.get_all_repos()

        if not agents_dirs:
            log_info("未找到任何 agents 目录")
            return

        repo_config_map = {r.name: r for r in target_repos}

        all_agents_by_repo: Dict[str, List[Dict]] = {}
        repo_dir_map: Dict[str, Path] = {}
        for rname, adir in agents_dirs:
            all_agents_by_repo[rname] = scan_agents_from_dir(rname, adir, quiet=True)
            repo_dir_map[rname] = adir.parent

        def _is_enabled(rc: Optional[RepoConfig], aname: str, repo_dir: Path) -> bool:
            agents_cfg = (rc.agents if rc and rc.agents is not None
                          else _load_manifest_agents(repo_dir))
            if agents_cfg is None:
                return True
            enabled = agents_cfg.get("enabled") or []
            disabled = agents_cfg.get("disabled") or []
            if enabled:
                return aname in enabled
            return aname not in disabled

        if edit:
            from prompt_toolkit.shortcuts import checkboxlist_dialog
            from prompt_toolkit.styles import Style as PTStyle

            clean_style = PTStyle.from_dict({
                "dialog":                        "bg:#1e1e1e",
                "dialog.body":                   "bg:#1e1e1e fg:#ffffff",
                "dialog.body checkbox":          "fg:#888888",
                "dialog.body checkbox-selected": "fg:#00cc00 bold",
                "dialog.body checkbox-checked":  "fg:#00cc00",
                "button":                        "bg:#333333 fg:#ffffff",
                "button.focused":                "bg:#00cc00 fg:#000000",
            })

            for rname, agents in all_agents_by_repo.items():
                if not agents:
                    continue
                rc = repo_config_map.get(rname)
                repo_dir = repo_dir_map.get(rname, Path("."))
                values = [(a["name"], a["name"]) for a in agents]
                default_checked = [a["name"] for a in agents if _is_enabled(rc, a["name"], repo_dir)]

                result = checkboxlist_dialog(
                    title=f"仓库：{rname}",
                    text="空格勾选/取消，Tab 切换到 OK，回车确认",
                    values=values,
                    default_values=default_checked,
                    style=clean_style,
                ).run()

                if result is None or rc is None:
                    continue

                all_names = [a["name"] for a in agents]
                checked = set(result)
                unchecked = set(all_names) - checked

                # 计算变更内容：对比有效状态（config 或 manifest）
                prev_agents = rc.agents if rc.agents is not None else _load_manifest_agents(repo_dir)
                old_disabled = set((prev_agents or {}).get("disabled") or [])
                if prev_agents and (prev_agents.get("enabled") or []):
                    old_enabled_set = set(prev_agents["enabled"])
                    old_disabled = {n for n in all_names if n not in old_enabled_set}

                newly_enabled = sorted(old_disabled - unchecked)
                newly_disabled = sorted(unchecked - old_disabled)

                if not unchecked:
                    rc.agents = None
                elif not checked:
                    rc.agents = {"enabled": [], "disabled": []}
                elif mode == "enable":
                    rc.agents = {"enabled": sorted(checked), "disabled": []}
                elif mode == "disable":
                    rc.agents = {"enabled": [], "disabled": sorted(unchecked)}
                else:
                    if len(checked) <= len(unchecked):
                        rc.agents = {"enabled": sorted(checked), "disabled": []}
                    else:
                        rc.agents = {"enabled": [], "disabled": sorted(unchecked)}
                config_manager.update_repo(rc)

                if not newly_enabled and not newly_disabled:
                    log_info(f"仓库 '{rname}' 无变更")
                else:
                    log_success(f"仓库 '{rname}' agent 配置已保存")
                    for n in newly_enabled:
                        click.echo(f"  + {n}  （已启用）")
                    for n in newly_disabled:
                        click.echo(f"  - {n}  （已禁用）")
        else:
            total = 0
            for rname, agents in all_agents_by_repo.items():
                rc = repo_config_map.get(rname)
                repo_dir = repo_dir_map.get(rname, Path("."))
                click.echo(f"\n仓库：{rname}")
                for a in agents:
                    mark = "✓" if _is_enabled(rc, a["name"], repo_dir) else "✗"
                    soul_tag = " [soul]" if a["has_soul"] else ""
                    mem_tag = " [memory]" if a["has_memory"] else ""
                    click.echo(f"  [{mark}] {a['name']}{soul_tag}{mem_tag}")
                    total += 1
            click.echo(f"\n共 {total} 个 agent  （使用 --edit 进入编辑模式）")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出 agent 失败: {e}")
        raise click.Abort()


# ── agent load ───────────────────────────────────────────────────────────────

def collect_agents(keywords: tuple = ()) -> list:
    """收集可用 agent 列表，供 agent load 和 driving load 复用。"""

    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    agents_dirs = config_manager.get_all_agents_dirs()
    if not agents_dirs:
        return []

    repo_configs = config_manager.get_all_repos()
    repo_config_map = {r.name: r for r in repo_configs}

    # 优化 1：无关键词时只扫描 base 仓库
    if not keywords:
        agents_dirs = [
            (n, d) for n, d in agents_dirs
            if "base" in ((repo_config_map.get(n) and repo_config_map[n].tags) or [])
        ]

    all_agents_by_repo: Dict[str, List[Dict]] = {}
    for repo_name, agents_dir in agents_dirs:
        rc = repo_config_map.get(repo_name)
        repo_agents = scan_agents_from_dir(repo_name, agents_dir, quiet=True)
        if not keywords:
            # 优先级：driving.config.json > manifest.json > 全量加载
            effective_agents = (rc.agents if rc and rc.agents is not None
                                else _load_manifest_agents(agents_dir.parent))
            if effective_agents is not None:
                enabled = effective_agents.get("enabled") or []
                disabled = effective_agents.get("disabled") or []
                if enabled:
                    repo_agents = [a for a in repo_agents if a["name"] in enabled]
                elif disabled:
                    repo_agents = [a for a in repo_agents if a["name"] not in disabled]
        all_agents_by_repo[repo_name] = repo_agents

    result: List[Dict] = []
    seen: set = set()

    def _add(agents: List[Dict]):
        for a in agents:
            if a["name"] not in seen:
                seen.add(a["name"])
                result.append(a)

    if not keywords:
        for repo_name, repo_agents in all_agents_by_repo.items():
            _add(repo_agents)
    else:
        from driving_cli.utils.match import fuzzy_match_any
        kw_lower = tuple(k.lower() for k in keywords)
        for repo_name, repo_agents in all_agents_by_repo.items():
            if repo_name.lower() in kw_lower:
                _add(repo_agents)
                continue
            matched = [a for a in repo_agents
                       if fuzzy_match_any((a["name"], a.get("description", "")), keywords)]
            _add(matched)

    return [
        {"name": a["name"], "description": a["description"], "path": a["path"]}
        for a in sorted(result, key=lambda x: x["name"])
    ]


@agent_group.command(name="load")
@click.argument("keywords", nargs=-1, required=False)
def agent_load(keywords: tuple):
    """输出已启用 agent 的元数据列表（JSON），供 AI 会话注入上下文。

    输出字段：name、description、path

    不传关键词时，只加载 tags 含 "base" 的仓库的 agent。
    传入关键词时，在 base 仓库基础上，额外匹配 repo.name 或 agent.name 的 agent（取并集）。
    支持多个关键词：driving agent load android ios

    示例：
        driving agent load
        driving agent load android
        driving agent load android ios
    """
    from driving_cli.utils.match import normalize_keywords
    keywords = normalize_keywords(keywords)

    try:
        output = collect_agents(keywords)
        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        log_error(f"加载 agent 列表失败: {e}")
        raise click.Abort()


# ── agent memory ─────────────────────────────────────────────────────────────

@agent_group.group(name="memory")
def agent_memory():
    """管理 agent 的最佳实践知识沉淀（MEMORY.md）。"""
    pass


def _resolve_agent_dir(config_manager: ConfigManager, agent_name: str) -> Optional[Path]:
    """在所有仓库中查找指定 agent 的目录，返回绝对路径。"""
    project_root = config_manager._project_root
    for repo in config_manager.get_all_repos():
        agent_dir = project_root / repo.path / "agents" / agent_name
        if agent_dir.exists() and (agent_dir / "AGENTS.md").exists():
            return agent_dir
    return None


@agent_memory.command(name="get")
@click.argument("agent_name")
def memory_get(agent_name: str):
    """读取 agent 的 MEMORY.md 内容。

    示例：
        driving agent memory get android-reviewer
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_file = agent_dir / "MEMORY.md"
        if not memory_file.exists():
            click.echo("")
            return

        click.echo(memory_file.read_text(encoding="utf-8"))

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"读取记忆失败: {e}")
        raise click.Abort()


@agent_memory.command(name="set")
@click.argument("agent_name")
@click.argument("content")
@click.option("--force", is_flag=True, default=False, help="强制覆盖（跳过确认）")
def memory_set(agent_name: str, content: str, force: bool):
    """覆盖写入 agent 的 MEMORY.md（适合初始化或完全重置）。

    示例：
        driving agent memory set android-reviewer "## 审查偏好\n\n- 不喜欢过度注释"
        driving agent memory set android-reviewer "内容" --force
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_file = agent_dir / "MEMORY.md"

        if memory_file.exists() and not force:
            log_warning("MEMORY.md 已有内容，覆盖将丢失现有知识。")
            log_warning("建议使用 'driving agent memory append' 追加新条目。")
            if not click.confirm("确认覆盖？"):
                log_info("已取消，使用 --force 跳过此提示")
                return

        memory_file.write_text(content.rstrip() + "\n", encoding="utf-8")
        log_success(f"已写入 {agent_name}/MEMORY.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"写入记忆失败: {e}")
        raise click.Abort()


@agent_memory.command(name="append")
@click.argument("agent_name")
@click.argument("content")
def memory_append(agent_name: str, content: str):
    """追加知识条目到 agent 的 MEMORY.md（推荐写入方式）。

    示例：
        driving agent memory append android-reviewer "- 不喜欢过度注释"
        driving agent memory append android-reviewer "## 有效策略\\n\\n- 先指出架构问题"
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_file = agent_dir / "MEMORY.md"
        existing = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        memory_file.write_text(existing + separator + content.rstrip() + "\n", encoding="utf-8")
        log_success(f"已追加到 {agent_name}/MEMORY.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"追加记忆失败: {e}")
        raise click.Abort()


@agent_memory.command(name="clear")
@click.argument("agent_name")
@click.option("--yes", "-y", is_flag=True, default=False, help="跳过确认提示")
def memory_clear(agent_name: str, yes: bool):
    """清空 agent 的 MEMORY.md。

    示例：
        driving agent memory clear android-reviewer
        driving agent memory clear android-reviewer -y
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_file = agent_dir / "MEMORY.md"
        if not memory_file.exists():
            log_info("MEMORY.md 不存在，无需清空")
            return

        if not yes and not click.confirm(f"确认清空 {agent_name}/MEMORY.md？"):
            return

        memory_file.unlink()
        log_success(f"已删除 {agent_name}/MEMORY.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"清空记忆失败: {e}")
        raise click.Abort()

# ---------------------------------------------------------------------------
# agent export
# ---------------------------------------------------------------------------

# 支持的导出目标工具
SUPPORTED_TOOLS = ["kiro", "claude-code", "cursor", "windsurf", "codex"]



def _export_kiro(agent_name: str, data: Dict, agent_dir: Path,
                 output_dir: Path) -> Path:
    """生成 Kiro custom agent 硬链接。

    AGENTS.md frontmatter 需包含 tools 字段，Kiro 才能正确识别。
    参考：https://kiro.dev/docs/chat/subagents/
    """
    meta = data["meta"]
    if "tools" not in meta:
        raise click.ClickException(
            f"AGENTS.md 缺少 tools 字段，无法导出到 kiro。\n"
            f"请在 {agent_dir}/AGENTS.md frontmatter 中添加：tools: [\"read\", \"shell\"]"
        )

    kiro_agents_dir = output_dir / ".kiro" / "agents"
    kiro_agents_dir.mkdir(parents=True, exist_ok=True)
    out_file = kiro_agents_dir / f"{agent_name}.md"

    agents_md = agent_dir / "AGENTS.md"
    if out_file.exists() or out_file.is_symlink():
        out_file.unlink()
    
    import os
    os.link(agents_md.resolve(), out_file)
    return out_file


def _export_claude_code(agent_name: str, data: Dict, agent_dir: Path,
                        output_dir: Path) -> Path:
    """生成 Claude Code sub-agent 软链接。输出：<output_dir>/.claude/agents/<name>.md"""
    out_dir = output_dir / ".claude" / "agents"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.md"

    agents_md = agent_dir / "AGENTS.md"
    if out_file.exists() or out_file.is_symlink():
        out_file.unlink()
    out_file.symlink_to(agents_md.resolve())
    return out_file


def _export_cursor(agent_name: str, data: Dict, agent_dir: Path,
                   output_dir: Path) -> Path:
    """生成 Cursor Rules 软链接。AGENTS.md 需含 alwaysApply 字段。

    输出：<output_dir>/.cursor/rules/<name>.mdc
    """
    meta = data["meta"]
    if "alwaysApply" not in meta:
        raise click.ClickException(
            f"AGENTS.md 缺少 alwaysApply 字段，无法导出到 cursor。\n"
            f"请在 {agent_dir}/AGENTS.md frontmatter 中添加：alwaysApply: false"
        )

    out_dir = output_dir / ".cursor" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.mdc"

    agents_md = agent_dir / "AGENTS.md"
    if out_file.exists() or out_file.is_symlink():
        out_file.unlink()
    out_file.symlink_to(agents_md.resolve())
    return out_file


def _export_windsurf(agent_name: str, data: Dict, agent_dir: Path,
                     output_dir: Path) -> Path:
    """生成 Windsurf Rules 软链接。AGENTS.md 需含 trigger 字段。

    输出：<output_dir>/.windsurf/rules/<name>.md
    """
    meta = data["meta"]
    if "trigger" not in meta:
        raise click.ClickException(
            f"AGENTS.md 缺少 trigger 字段，无法导出到 windsurf。\n"
            f"请在 {agent_dir}/AGENTS.md frontmatter 中添加：trigger: manual"
        )

    out_dir = output_dir / ".windsurf" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.md"

    agents_md = agent_dir / "AGENTS.md"
    if out_file.exists() or out_file.is_symlink():
        out_file.unlink()
    out_file.symlink_to(agents_md.resolve())
    return out_file


def _read_agents_md_body(agents_md: Path) -> str:
    """提取 AGENTS.md frontmatter 之后的正文内容。

    跳过开头的 --- ... --- frontmatter 块，返回剩余正文。
    若无 frontmatter，返回完整文件内容。
    """
    content = agents_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return content
    # 找第二个 ---
    second = content.find("\n---", 3)
    if second == -1:
        return content
    # 跳过 \n--- 以及紧随的换行
    body_start = second + 4  # len("\n---") == 4
    if body_start < len(content) and content[body_start] == "\n":
        body_start += 1
    return content[body_start:]


def _export_codex(agent_name: str, data: Dict, agent_dir: Path,
                  output_dir: Path) -> Path:
    """生成 OpenAI Codex sub-agent TOML 配置文件。

    输出：<output_dir>/.codex/agents/<name>.toml
    Codex CLI 支持项目级 .codex/agents/ 目录下的 TOML 自定义 agent。
    格式：name / description / model / model_reasoning_effort / sandbox_mode / developer_instructions

    AGENTS.md 正文内容会写入 developer_instructions 字段。
    frontmatter 中可选字段：
      - codex_model（映射到 TOML model）
      - codex_reasoning_effort（映射到 TOML model_reasoning_effort）
      - codex_sandbox_mode（映射到 TOML sandbox_mode，可选值：read-only、workspace-write）
    """
    meta = data["meta"]
    out_dir = output_dir / ".codex" / "agents"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.toml"

    agents_md = agent_dir / "AGENTS.md"
    body = _read_agents_md_body(agents_md).strip()

    # 构建 TOML 内容
    lines = []
    lines.append(f'name = "{meta.get("name", agent_name)}"')
    if meta.get("description"):
        desc = str(meta["description"]).strip()
        if "\n" in desc:
            # 多行 description 使用 TOML 多行字符串，转义内部的 """
            escaped_desc = desc.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
            lines.append(f'description = """\n{escaped_desc}\n"""')
        else:
            lines.append(f'description = "{desc.replace(chr(34), chr(92) + chr(34))}"')
    if meta.get("codex_model"):
        lines.append(f'model = "{meta["codex_model"]}"')
    if meta.get("codex_reasoning_effort"):
        lines.append(f'model_reasoning_effort = "{meta["codex_reasoning_effort"]}"')
    if meta.get("codex_sandbox_mode"):
        lines.append(f'sandbox_mode = "{meta["codex_sandbox_mode"]}"')
    # developer_instructions 使用多行字符串
    escaped_body = body.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
    lines.append(f'developer_instructions = """\n{escaped_body}\n"""')

    if out_file.exists() or out_file.is_symlink():
        out_file.unlink()
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_file


_EXPORTERS = {
    "kiro": _export_kiro,
    "claude-code": _export_claude_code,
    "cursor": _export_cursor,
    "windsurf": _export_windsurf,
    "codex": _export_codex,
}


# 各工具对应的输出文件路径（相对于 output_dir）
_TOOL_OUTPUT_PATHS = {
    "kiro":        lambda name: Path(".kiro") / "agents" / f"{name}.md",
    "claude-code": lambda name: Path(".claude") / "agents" / f"{name}.md",
    "cursor":      lambda name: Path(".cursor") / "rules" / f"{name}.mdc",
    "windsurf":    lambda name: Path(".windsurf") / "rules" / f"{name}.md",
    "codex":       lambda name: Path(".codex") / "agents" / f"{name}.toml",
}


@agent_group.command(name="export")
@click.argument("agent_name")
@click.option(
    "--tool", "-t",
    type=click.Choice(SUPPORTED_TOOLS, case_sensitive=False),
    required=True,
    help="目标 AI 工具（kiro、claude-code、cursor、windsurf、codex）",
)
@click.option(
    "--output", "-o",
    default=None,
    help="输出根目录（默认为项目根目录）",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="强制重建软链接（默认：文件已存在则跳过）",
)
def agent_export(agent_name: str, tool: str, output: Optional[str], force: bool):
    """将 driving agent 导出为指定 AI 工具的软链接配置。

    文件已存在时默认跳过，使用 --force 强制重建。
    支持的工具：kiro、claude-code、cursor、windsurf、codex

    示例：
        driving agent export android-reviewer --tool kiro
        driving agent export android-reviewer --tool claude-code
        driving agent export android-reviewer --tool codex
        driving agent export android-reviewer --tool kiro --force
        driving agent export android-reviewer --tool kiro --output /path/to/project
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        output_dir = Path(output).resolve() if output else project_root

        # 文件已存在且非强制模式 → 跳过
        out_path = output_dir / _TOOL_OUTPUT_PATHS[tool.lower()](agent_name)
        if not force and (out_path.exists() or out_path.is_symlink()):
            log_info(f"已存在：{out_path.relative_to(output_dir)}（使用 --force 强制重建）")
            return

        log_info(f"正在导出 agent '{agent_name}' → {tool} ...")

        data = _parse_frontmatter(agent_dir / "AGENTS.md") or {}
        exporter = _EXPORTERS[tool.lower()]
        out_file = exporter(
            agent_name=agent_name,
            data={"meta": data},
            agent_dir=agent_dir,
            output_dir=output_dir,
        )

        log_success(f"已生成：{out_file.relative_to(output_dir)}")
        if tool.lower() == "kiro":
            log_info("硬链接模式：AGENTS.md 更新后自动生效，无需重新导出")
        elif tool.lower() == "codex":
            log_info("TOML 文件模式：AGENTS.md 更新后需重新执行 export（使用 --force）才能同步")
        else:
            log_info("软链接模式：AGENTS.md 更新后自动生效，无需重新导出")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"导出失败: {e}")
        raise click.Abort()


# ---------------------------------------------------------------------------
# agent report
# ---------------------------------------------------------------------------

@agent_group.command(name="report")
@click.argument("agent_name")
@click.option("--path", "feature_path", required=True, help="需求目录路径")
@click.option("--source", default="", help="触发来源（来自 agent-dispatcher 构建 prompt 时的触发来源描述）")
def agent_report(agent_name: str, feature_path: str, source: str):
    """上报子 agent 启动事件（由子 agent 在加载步骤第 0 步调用）。

    上报内容：agent 名称、需求目录、触发来源、触发时间、执行者（git user.name）。
    agent 找不到时打印提示但不影响后续执行。
    上报失败静默处理，不阻塞主流程。

    示例：
        driving agent report android-reviewer --path features/login --source "dev-review 阶段，由 dev-workflow 触发"
    """
    from driving_cli.utils.op_reporter import report_op_event

    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_warning(f"未找到 agent '{agent_name}'，跳过上报")
    except Exception:
        log_warning(f"查找 agent '{agent_name}' 时出错，跳过上报")

    desc = f"子 agent '{agent_name}' 启动"
    if source:
        desc += f"，来源：{source}"

    report_op_event(
        operation="agent_started",
        description=desc,
        extra={
            "agent_name": agent_name,
            "feature_path": feature_path or None,
            "source": source or None,
        },
        silent=True,
    )
