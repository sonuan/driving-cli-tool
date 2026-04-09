"""load 命令 - 一次性输出所有上下文数据，供 AI 会话注入"""

import json
from pathlib import Path

import click

from driving_cli import __version__
from driving_cli.commands.agent import collect_agents
from driving_cli.commands.repo import collect_repos
from driving_cli.commands.check import _collect_updatable
from driving_cli.commands.rule import collect_rules
from driving_cli.commands.skill import collect_skills
from driving_cli.commands.update import (
    compare_versions,
    fetch_version_info,
    _get_update_version_url,
)
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import set_silent


class SystemPrompt:
    HAS_UPDATE = "以下仓库存在新版本：{repos}，请询问用户是否更新，确认前不得继续。当用户确认更新则需要使用 driving repo pull <repo-name> 进行更新。"
    HAS_CLI_UPDATE = "driving CLI 有新版本可用：当前 {current}，最新 {latest}。请提醒用户执行 `sudo driving update` 进行升级。"
    DEFAULT = ""


def _check_cli_update() -> str:
    """检查 CLI 是否有新版本，有则返回提示文本，否则返回空字符串"""
    try:
        version_info = fetch_version_info(_get_update_version_url())
        if not version_info:
            return ""
        latest = version_info.get("version", "")
        if latest and compare_versions(__version__, latest) < 0:
            return SystemPrompt.HAS_CLI_UPDATE.format(current=__version__, latest=latest)
    except Exception:
        pass
    return ""


def _build_system_prompt() -> str:
    parts = []

    # 检查 CLI 自身更新（优先级更高，放前面）
    cli_update_msg = _check_cli_update()
    if cli_update_msg:
        parts.append(cli_update_msg)

    # 检查仓库更新
    try:
        _, updatable, _ = _collect_updatable(fetch=False)
        if updatable:
            repos_str = "、".join(r.name for r in updatable)
            parts.append(SystemPrompt.HAS_UPDATE.format(repos=repos_str))
    except Exception:
        pass

    return "\n".join(parts)


@click.command("load")
@click.argument("keywords", nargs=-1, required=False)
@click.option("--debug", is_flag=True, default=False, help="输出调试日志")
def load(keywords: tuple, debug: bool):
    """一次性输出所有上下文数据（skills、rules、repos、prompts），供 AI 会话注入

    不传参数时加载 tags=base 的仓库内容。
    传入 repo-name 时只加载匹配仓库的 skills/rules。

    示例：
        driving load
        driving load f-message
        driving load f-message f-qucall
        driving load --debug
    """
    set_silent(not debug)
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        config = config_manager.load()

        result = {
            "cli_version": __version__,
            "skills": collect_skills(keywords),
            "rules": collect_rules(keywords),
            "repos": collect_repos(keywords),
            "system_prompt": _build_system_prompt(),
            "user_prompt": config.user_prompt,
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
