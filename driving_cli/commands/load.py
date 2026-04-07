"""load 命令 - 一次性输出所有上下文数据，供 AI 会话注入"""

import json
from pathlib import Path
from typing import Optional

import click

from driving_cli import __version__
from driving_cli.commands.agent import collect_agents
from driving_cli.commands.check import _collect_updatable
from driving_cli.commands.rule import collect_rules
from driving_cli.commands.skill import collect_skills
from driving_cli.utils.config_manager import ConfigManager, find_project_root


class SystemPrompt:
    HAS_UPDATE = "以下仓库存在新版本：{repos}，请询问用户是否更新，确认前不得继续。当用户确认更新则需要使用 driving repo pull <repo-name> 进行更新"
    DEFAULT = ""


def _build_repos(project_root: Path, config_manager: ConfigManager) -> list:
    repos = config_manager.get_all_repos()
    result = []
    for repo in repos:
        entry = {
            "name": repo.name,
            "type": repo.type,
            "description": repo.description or "",
            "path": repo.path,
        }
        result.append(entry)
    return result


def _build_system_prompt() -> str:
    try:
        _, updatable, _ = _collect_updatable(fetch=False)
    except Exception:
        return SystemPrompt.DEFAULT

    if updatable:
        repos_str = "、".join(r.name for r in updatable)
        return SystemPrompt.HAS_UPDATE.format(repos=repos_str)
    return SystemPrompt.DEFAULT


@click.command("load")
@click.argument("keywords", nargs=-1, required=False)
def load(keywords: tuple):
    """一次性输出所有上下文数据（skills、rules、agents、repos、prompts），供 AI 会话注入

    不传参数时加载 tags=base 的仓库内容。
    传入 repo-name 时只加载匹配仓库的 skills/rules/agents。

    示例：
        driving load
        driving load f-message
        driving load f-message f-qucall
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        config = config_manager.load()

        result = {
            "cli_version": __version__,
            "skills": collect_skills(keywords),
            "rules": collect_rules(keywords),
            "agents": collect_agents(keywords),
            "repos": _build_repos(project_root, config_manager),
            "system_prompt": _build_system_prompt(),
            "user_prompt": config.user_prompt,
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
