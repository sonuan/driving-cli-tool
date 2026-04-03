"""Agent 子命令组

提供 `driving agent` 系列命令，用于管理多 agent。
每个 agent 存放在仓库的 agents/<name>/ 目录下，包含：
  - AGENTS.md   agent 指令/系统提示（必填，含 YAML frontmatter）
  - SOUL.md     agent 人格与行为风格（可选）
  - memory/     持久化记忆目录（可选）
      ├── facts.md    长期事实记忆
      ├── context.md  当前工作状态
      └── history/    历史对话摘要（按日期归档）
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving.models.config import RepoConfig
from driving.utils.config_manager import ConfigManager, find_project_root
from driving.utils.logger import log_error, log_info, log_success, log_warning

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ---------------------------------------------------------------------------
# YAML frontmatter 解析
# ---------------------------------------------------------------------------

def _parse_frontmatter(md_path: Path) -> Optional[Dict]:
    """解析 .md 文件的 YAML frontmatter，返回字段字典。

    要求文件以 --- 开头，找到第二个 --- 后停止读取，避免加载大文件正文。
    缺少 name 字段时返回 None。
    """
    try:
        yaml_lines: List[str] = []
        with md_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f):
                if lineno == 0:
                    if line.rstrip("\n") != "---":
                        return None
                    continue
                if line.strip() == "---":
                    break
                yaml_lines.append(line)
            else:
                return None  # 未找到结束 ---

        yaml_content = "".join(yaml_lines).strip()

        if HAS_YAML:
            try:
                data = yaml.safe_load(yaml_content)
                if not data or "name" not in data:
                    return None
                return data
            except Exception:
                pass

        # 简化解析器（无 PyYAML 时降级）
        result: Dict = {}
        lines_list = yaml_content.splitlines()
        i = 0
        while i < len(lines_list):
            line = lines_list[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                if v:
                    result[k] = v
                else:
                    # 可能是块序列，向后收集 "- item"
                    items = []
                    i += 1
                    while i < len(lines_list):
                        next_stripped = lines_list[i].strip()
                        if next_stripped.startswith("- "):
                            items.append(next_stripped[2:].strip())
                            i += 1
                        else:
                            break
                    result[k] = items if items else ""
                    continue
            i += 1
        return result if "name" in result else None

    except Exception as e:
        log_warning(f"解析 {md_path} 失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 扫描 / 过滤
# ---------------------------------------------------------------------------

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
        memory_dir = agent_dir / "memory"
        has_memory = memory_dir.exists() and any(memory_dir.iterdir())

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
def agent_list(repo_name: Optional[str], edit: bool):
    """列出所有 agent，按仓库分组显示启用状态，支持编辑模式。

    示例：
        driving agent list
        driving agent list --repo driving
        driving agent list --edit
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
        for rname, adir in agents_dirs:
            all_agents_by_repo[rname] = scan_agents_from_dir(rname, adir, quiet=True)

        def _is_enabled(rc: Optional[RepoConfig], aname: str) -> bool:
            if rc is None or rc.agents is None:
                return True
            enabled = rc.agents.get("enabled") or []
            disabled = rc.agents.get("disabled") or []
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
                values = [(a["name"], a["name"]) for a in agents]
                default_checked = [a["name"] for a in agents if _is_enabled(rc, a["name"])]

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
                new_disabled = [n for n in all_names if n not in result]
                old_disabled = set((rc.agents or {}).get("disabled") or [])
                new_disabled_set = set(new_disabled)
                newly_enabled = sorted(old_disabled - new_disabled_set)
                newly_disabled = sorted(new_disabled_set - old_disabled)

                rc.agents = None if not new_disabled else {"enabled": [], "disabled": sorted(new_disabled)}
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
                click.echo(f"\n仓库：{rname}")
                for a in agents:
                    mark = "✓" if _is_enabled(rc, a["name"]) else "✗"
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

@agent_group.command(name="load")
def agent_load():
    """输出所有已启用 agent 的元数据列表（JSON），供 AI 会话注入上下文。

    输出字段：name、description、role、version、skills、path、has_soul、has_memory

    示例：
        driving agent load
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agents_dirs = config_manager.get_all_agents_dirs()
        if not agents_dirs:
            click.echo("[]")
            return

        repo_configs = config_manager.get_all_repos()
        agents = _merge_agents(agents_dirs, repo_configs=repo_configs, quiet=True)

        output = sorted(agents, key=lambda x: x["name"])
        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        log_error(f"加载 agent 列表失败: {e}")
        raise click.Abort()


# ── agent memory ─────────────────────────────────────────────────────────────

@agent_group.group(name="memory")
def agent_memory():
    """管理 agent 的持久化记忆（memory/ 目录）。"""
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
@click.argument("key", required=False, default=None)
def memory_get(agent_name: str, key: Optional[str]):
    """读取 agent 的记忆内容。

    不指定 key 时输出所有记忆文件的内容（JSON）。
    指定 key 时只输出对应文件（facts / context / history）。

    示例：
        driving agent memory get android-reviewer
        driving agent memory get android-reviewer facts
        driving agent memory get android-reviewer context
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_dir = agent_dir / "memory"
        if not memory_dir.exists():
            click.echo("" if key else "{}")
            return

        if key:
            # 读取指定文件
            target = memory_dir / f"{key}.md"
            if not target.exists():
                click.echo("")
                return
            click.echo(target.read_text(encoding="utf-8"))
        else:
            # 读取所有 .md 文件（不含 history/）
            result: Dict[str, str] = {}
            for f in sorted(memory_dir.iterdir()):
                if f.is_file() and f.suffix == ".md":
                    result[f.stem] = f.read_text(encoding="utf-8")
            # history/ 目录：列出文件名列表
            history_dir = memory_dir / "history"
            if history_dir.exists():
                result["history"] = sorted(p.name for p in history_dir.iterdir() if p.is_file())
            click.echo(json_module.dumps(result, ensure_ascii=False, indent=2))

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"读取记忆失败: {e}")
        raise click.Abort()


def _get_git_author() -> str:
    """从 git config 读取当前用户名，失败时返回 'unknown'。"""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=3,
        )
        name = result.stdout.strip()
        return name if name else "unknown"
    except Exception:
        return "unknown"


def _make_entry(content: str) -> str:
    """生成带时间戳和作者的 append-only 记录条目。

    格式：
        <!-- 2026-04-02T14:30:00+08:00 | author -->
        内容
    """
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    ts = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S%z")
    # +0800 → +08:00
    if len(ts) == 24 and ts[-5] in ("+", "-"):
        ts = ts[:-2] + ":" + ts[-2:]
    author = _get_git_author()
    return f"<!-- {ts} | {author} -->\n{content.rstrip()}\n"


@agent_memory.command(name="set")
@click.argument("agent_name")
@click.argument("key")
@click.argument("content")
@click.option("--force", is_flag=True, default=False, help="强制覆盖（跳过确认）")
def memory_set(agent_name: str, key: str, content: str, force: bool):
    """覆盖写入 agent 的记忆文件（会丢失历史，谨慎使用）。

    通常应使用 append 追加带时间戳的条目。
    set 适用于初始化或需要完全重置某个 key 的场景。

    示例：
        driving agent memory set android-reviewer facts "初始事实"
        driving agent memory set android-reviewer context "重置上下文" --force
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_dir = agent_dir / "memory"
        target = memory_dir / f"{key}.md"

        # 已有内容时提示确认
        if target.exists() and not force:
            log_warning(f"memory/{key}.md 已有内容，覆盖将丢失历史记录。")
            log_warning("建议使用 'driving agent memory append' 追加带时间戳的条目。")
            if not click.confirm("确认覆盖？"):
                log_info("已取消，使用 --force 跳过此提示")
                return

        memory_dir.mkdir(exist_ok=True)
        entry = _make_entry(content)
        target.write_text(entry, encoding="utf-8")
        log_success(f"已写入 {agent_name}/memory/{key}.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"写入记忆失败: {e}")
        raise click.Abort()


@agent_memory.command(name="append")
@click.argument("agent_name")
@click.argument("key")
@click.argument("content")
def memory_append(agent_name: str, key: str, content: str):
    """追加带时间戳和作者的记录到 agent 记忆文件（推荐写入方式）。

    每条记录自动附加当前时间和 git user.name，格式：
        <!-- 2026-04-02T14:30:00+08:00 | author -->
        内容

    多人协作时追加操作几乎不产生 git 冲突。

    示例：
        driving agent memory append android-reviewer facts "用户不喜欢过度注释"
        driving agent memory append android-reviewer context "正在审查 PR #42"
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_dir = agent_dir / "memory"
        memory_dir.mkdir(exist_ok=True)

        target = memory_dir / f"{key}.md"
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        separator = "\n" if existing and not existing.endswith("\n") else ""
        entry = _make_entry(content)
        target.write_text(existing + separator + entry, encoding="utf-8")
        log_success(f"已追加到 {agent_name}/memory/{key}.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"追加记忆失败: {e}")
        raise click.Abort()


@agent_memory.command(name="clear")
@click.argument("agent_name")
@click.argument("key", required=False, default=None)
@click.option("--yes", "-y", is_flag=True, default=False, help="跳过确认提示")
def memory_clear(agent_name: str, key: Optional[str], yes: bool):
    """清空 agent 的记忆。

    指定 key 时只清空对应文件，不指定时清空整个 memory/ 目录。

    示例：
        driving agent memory clear android-reviewer context
        driving agent memory clear android-reviewer -y
    """
    import shutil

    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        agent_dir = _resolve_agent_dir(config_manager, agent_name)
        if agent_dir is None:
            log_error(f"未找到 agent '{agent_name}'")
            raise click.Abort()

        memory_dir = agent_dir / "memory"
        if not memory_dir.exists():
            log_info("memory/ 目录不存在，无需清空")
            return

        if key:
            target = memory_dir / f"{key}.md"
            if not target.exists():
                log_info(f"文件 memory/{key}.md 不存在")
                return
            if not yes and not click.confirm(f"确认清空 {agent_name}/memory/{key}.md？"):
                return
            target.unlink()
            log_success(f"已删除 {agent_name}/memory/{key}.md")
        else:
            if not yes and not click.confirm(f"确认清空 {agent_name} 的全部记忆？"):
                return
            shutil.rmtree(memory_dir)
            log_success(f"已清空 {agent_name}/memory/")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"清空记忆失败: {e}")
        raise click.Abort()

# ---------------------------------------------------------------------------
# agent export
# ---------------------------------------------------------------------------

# 支持的导出目标工具
SUPPORTED_TOOLS = ["kiro", "claude-code", "cursor", "windsurf"]


def _read_agent_full(agent_dir: Path) -> Dict:
    """读取 agent 目录的完整内容，返回结构化字典。

    包含：
      - meta: AGENTS.md frontmatter 字段
      - instructions: AGENTS.md 正文（frontmatter 之后）
      - soul: SOUL.md 全文（如有）
      - memory_facts: memory/facts.md 内容（如有）
      - memory_context: memory/context.md 内容（如有）
    """
    agents_md = agent_dir / "AGENTS.md"

    # 读取 AGENTS.md，分离 frontmatter 和正文
    content = agents_md.read_text(encoding="utf-8")
    lines = content.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    meta = _parse_frontmatter(agents_md) or {}
    instructions = "\n".join(lines[end_idx + 1:]).strip() if end_idx else content.strip()

    # SOUL.md
    soul_md = agent_dir / "SOUL.md"
    soul = soul_md.read_text(encoding="utf-8").strip() if soul_md.exists() else ""

    # memory
    memory_dir = agent_dir / "memory"
    facts = ""
    context_mem = ""
    if memory_dir.exists():
        facts_file = memory_dir / "facts.md"
        context_file = memory_dir / "context.md"
        if facts_file.exists():
            facts = facts_file.read_text(encoding="utf-8").strip()
        if context_file.exists():
            context_mem = context_file.read_text(encoding="utf-8").strip()

    return {
        "meta": meta,
        "instructions": instructions,
        "soul": soul,
        "memory_facts": facts,
        "memory_context": context_mem,
    }


def _build_prompt(data: Dict, include_memory: bool = True) -> str:
    """将 driving agent 内容组装成完整 prompt 字符串。

    顺序：指令 → 人格 → 记忆（facts → context）
    """
    parts = []

    if data["instructions"]:
        parts.append(data["instructions"])

    if data["soul"]:
        # 去掉 SOUL.md 的 frontmatter
        soul_text = data["soul"]
        if soul_text.startswith("---"):
            soul_lines = soul_text.split("\n")
            end = next((i for i, l in enumerate(soul_lines[1:], 1) if l.strip() == "---"), None)
            if end:
                soul_text = "\n".join(soul_lines[end + 1:]).strip()
        if soul_text:
            parts.append(soul_text)

    if include_memory:
        if data["memory_facts"]:
            parts.append("## 背景知识（长期记忆）\n\n" + data["memory_facts"])
        if data["memory_context"]:
            parts.append("## 当前工作状态\n\n" + data["memory_context"])

    return "\n\n---\n\n".join(parts)


def _export_kiro(agent_name: str, data: Dict, agent_dir: Path,
                 output_dir: Path, include_memory: bool) -> Path:
    """生成 Kiro custom agent JSON 配置文件。

    输出：<output_dir>/.kiro/agents/<name>.json
    prompt 用 file:// 引用 AGENTS.md，SOUL.md 作为 resource，
    memory 通过 agentSpawn hook 注入。
    """
    # 计算从 .kiro/agents/ 到 agent_dir 的相对路径
    kiro_agents_dir = output_dir / ".kiro" / "agents"
    try:
        rel_agents_md = "file://" + str(
            (agent_dir / "AGENTS.md").relative_to(output_dir)
        )
    except ValueError:
        rel_agents_md = "file://" + str((agent_dir / "AGENTS.md").resolve())

    resources = []
    soul_md = agent_dir / "SOUL.md"
    if soul_md.exists():
        try:
            rel_soul = "file://" + str(soul_md.relative_to(output_dir))
        except ValueError:
            rel_soul = "file://" + str(soul_md.resolve())
        resources.append(rel_soul)

    # 关联技能
    meta = data["meta"]
    skills = meta.get("skills") or []
    if isinstance(skills, list) and skills:
        resources.append("skill://ai-driving/**/skills/**/SKILL.md")

    config: Dict = {
        "name": agent_name,
        "description": str(meta.get("description", "")),
        "prompt": rel_agents_md,
        "tools": ["read", "shell"],
        "allowedTools": ["read"],
        "toolsSettings": {
            "shell": {"autoAllowReadonly": True}
        },
    }
    if resources:
        config["resources"] = resources

    # agentSpawn hook：自动注入记忆（Kiro 始终通过 hook 动态注入，不嵌入记忆内容）
    config["hooks"] = {
        "agentSpawn": [
            {"command": f"python3 -m driving.cli agent memory get {agent_name}"}
        ]
    }

    welcome = f"{meta.get('description', agent_name)} 已就绪。"
    config["welcomeMessage"] = welcome

    kiro_agents_dir.mkdir(parents=True, exist_ok=True)
    out_file = kiro_agents_dir / f"{agent_name}.json"
    out_file.write_text(
        json_module.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_file


def _export_claude_code(agent_name: str, data: Dict, agent_dir: Path,
                        output_dir: Path, include_memory: bool) -> Path:
    """生成 Claude Code sub-agent 配置。

    优先创建软链接指向 AGENTS.md（保持单一来源）。
    当需要嵌入记忆（include_memory=True）或软链接创建失败时，
    降级为生成包含完整内容的独立 md 文件。

    输出：<output_dir>/.claude/agents/<name>.md
    """
    out_dir = output_dir / ".claude" / "agents"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.md"

    # 有记忆需要嵌入时，必须生成独立文件（软链接无法追加内容）
    if include_memory and (data["memory_facts"] or data["memory_context"]):
        if out_file.is_symlink():
            out_file.unlink()
        return _export_claude_code_full(agent_name, data, agent_dir, out_file)

    # 优先尝试软链接：指向 AGENTS.md 原文，保持单一来源
    agents_md = agent_dir / "AGENTS.md"
    try:
        if out_file.exists() or out_file.is_symlink():
            out_file.unlink()
        out_file.symlink_to(agents_md.resolve())
        return out_file
    except OSError:
        # 软链接失败（跨设备等情况），降级为独立文件
        return _export_claude_code_full(agent_name, data, agent_dir, out_file)


def _export_claude_code_full(agent_name: str, data: Dict, agent_dir: Path,
                              out_file: Path) -> Path:
    """生成包含完整内容的 Claude Code sub-agent md 文件（软链接降级方案）。"""
    meta = data["meta"]
    prompt = _build_prompt(data, include_memory=True)

    skills = meta.get("skills") or []
    skills_note = ""
    if isinstance(skills, list) and skills:
        skills_note = "\n\n> 关联技能：" + "、".join(skills)

    frontmatter_lines = [
        "---",
        f"name: {agent_name}",
        f"description: {meta.get('description', '')}",
    ]
    if meta.get("tools"):
        frontmatter_lines.append(f"tools: {meta['tools']}")
    frontmatter_lines.append("---")

    content = "\n".join(frontmatter_lines) + "\n\n" + prompt + skills_note + "\n"
    out_file.write_text(content, encoding="utf-8")
    return out_file


def _export_cursor(agent_name: str, data: Dict, agent_dir: Path,
                   output_dir: Path, include_memory: bool) -> Path:
    """生成 Cursor Rules 配置文件。

    AGENTS.md 包含 alwaysApply 字段时，创建软链接（单一来源）。
    否则生成独立 .mdc 文件。

    输出：<output_dir>/.cursor/rules/<name>.mdc
    """
    out_dir = output_dir / ".cursor" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.mdc"

    # AGENTS.md 包含 alwaysApply 字段时，可以直接软链接
    meta = data["meta"]
    if "alwaysApply" in meta:
        agents_md = agent_dir / "AGENTS.md"
        try:
            if out_file.exists() or out_file.is_symlink():
                out_file.unlink()
            out_file.symlink_to(agents_md.resolve())
            return out_file
        except OSError:
            pass  # 降级为独立文件

    # 降级：生成独立 .mdc 文件
    prompt = _build_prompt(data, include_memory=include_memory)
    content = (
        "---\n"
        f"description: {meta.get('description', '')}\n"
        "alwaysApply: false\n"
        "---\n\n"
        + prompt + "\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return out_file


def _export_windsurf(agent_name: str, data: Dict, agent_dir: Path,
                     output_dir: Path, include_memory: bool) -> Path:
    """生成 Windsurf Rules 配置文件。

    AGENTS.md 包含 trigger 字段时，创建软链接（单一来源）。
    否则生成独立 .md 文件。

    输出：<output_dir>/.windsurf/rules/<name>.md
    """
    out_dir = output_dir / ".windsurf" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{agent_name}.md"

    # AGENTS.md 包含 trigger 字段时，可以直接软链接
    meta = data["meta"]
    if "trigger" in meta:
        agents_md = agent_dir / "AGENTS.md"
        try:
            if out_file.exists() or out_file.is_symlink():
                out_file.unlink()
            out_file.symlink_to(agents_md.resolve())
            return out_file
        except OSError:
            pass  # 降级为独立文件

    # 降级：生成独立 .md 文件
    prompt = _build_prompt(data, include_memory=include_memory)
    content = (
        "---\n"
        f"trigger: manual\n"
        f"description: {meta.get('description', '')}\n"
        "---\n\n"
        + prompt + "\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return out_file


_EXPORTERS = {
    "kiro": _export_kiro,
    "claude-code": _export_claude_code,
    "cursor": _export_cursor,
    "windsurf": _export_windsurf,
}


@agent_group.command(name="export")
@click.argument("agent_name")
@click.option(
    "--tool", "-t",
    type=click.Choice(SUPPORTED_TOOLS, case_sensitive=False),
    required=True,
    help="目标 AI 工具",
)
@click.option(
    "--output", "-o",
    default=None,
    help="输出根目录（默认为项目根目录）",
)
@click.option(
    "--no-memory",
    is_flag=True,
    default=False,
    help="不将当前记忆内容嵌入配置（适合提交到 git 的静态配置）",
)
def agent_export(agent_name: str, tool: str, output: Optional[str], no_memory: bool):
    """将 driving agent 导出为指定 AI 工具的配置文件。

    支持的工具：kiro、claude-code、cursor、windsurf

    示例：
        driving agent export android-reviewer --tool kiro
        driving agent export android-reviewer --tool claude-code
        driving agent export android-reviewer --tool cursor --no-memory
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

        log_info(f"正在导出 agent '{agent_name}' → {tool} ...")

        data = _read_agent_full(agent_dir)
        exporter = _EXPORTERS[tool.lower()]
        out_file = exporter(
            agent_name=agent_name,
            data=data,
            agent_dir=agent_dir,
            output_dir=output_dir,
            include_memory=not no_memory,
        )

        log_success(f"已生成：{out_file.relative_to(output_dir)}")
        if out_file.is_symlink():
            log_info("软链接模式：AGENTS.md 更新后自动生效，无需重新导出")
        elif tool.lower() in ("cursor", "windsurf"):
            log_info("独立文件模式：AGENTS.md 更新后需重新运行 export 同步")

        # Kiro 通过 agentSpawn hook 动态注入记忆，不需要 warning
        if tool.lower() != "kiro" and not no_memory and (data["memory_facts"] or data["memory_context"]):
            log_warning("配置中包含当前记忆内容，建议使用 --no-memory 生成提交到 git 的静态版本")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"导出失败: {e}")
        raise click.Abort()
