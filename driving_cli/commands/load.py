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


class UpdatePrompt:
    HAS_UPDATE = "⬆️ 【仓库更新】以下仓库存在新版本：{repos}。请询问用户是否更新，确认后逐个执行 `driving repo pull <repo-name>` 更新，确认前不得继续任何操作。"
    HAS_CLI_UPDATE = "⬆️ 【CLI更新】driving CLI 有新版本可用（当前 {current}，最新 {latest}），请提醒用户执行 `sudo driving update` 升级。"
    CLI_VERSION_REQUIRED = "🚨 【版本不满足】当前 driving CLI 版本 {current} 不满足要求（需要 >= {required}），必须先执行 `sudo driving update` 升级后才能继续，请立即提醒用户。"
    DEFAULT = ""


def _check_min_cli_version() -> str:
    """扫描所有仓库的 manifest.json，取 min_cli_version 最大值，与当前版本对比"""
    try:
        project_root = find_project_root()
        ai_driving_dir = project_root / "ai-driving"
        if not ai_driving_dir.exists():
            return ""

        max_required = ""
        for manifest in ai_driving_dir.glob("*/manifest.json"):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                ver = data.get("min_cli_version", "").strip()
                if ver and (not max_required or compare_versions(ver, max_required) > 0):
                    max_required = ver
            except Exception:
                continue

        if max_required and compare_versions(__version__, max_required) < 0:
            return UpdatePrompt.CLI_VERSION_REQUIRED.format(
                current=__version__, required=max_required
            )
    except Exception:
        pass
    return ""


def _check_cli_update() -> str:
    """检查 CLI 是否有新版本，有则返回提示文本，否则返回空字符串"""
    try:
        version_info = fetch_version_info(_get_update_version_url())
        if not version_info:
            return ""
        latest = version_info.get("version", "")
        if latest and compare_versions(__version__, latest) < 0:
            return UpdatePrompt.HAS_CLI_UPDATE.format(current=__version__, latest=latest)
    except Exception:
        pass
    return ""


def _collect_repo_system_prompts() -> str:
    """扫描所有仓库的 manifest.json，读取 system_prompt 字段指向的文件内容并拼接"""
    try:
        project_root = find_project_root()
        ai_driving_dir = project_root / "ai-driving"
        if not ai_driving_dir.exists():
            return ""

        parts = []
        for manifest in sorted(ai_driving_dir.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                prompt_path = data.get("system_prompt", "").strip()
                if not prompt_path:
                    continue
                full_path = manifest.parent / prompt_path
                if full_path.exists():
                    content = full_path.read_text(encoding="utf-8").strip()
                    if content:
                        parts.append(content)
            except Exception:
                continue

        return "\n\n".join(parts)
    except Exception:
        return ""


def _build_notifications() -> str:
    """构建通知类内容（更新提醒、版本不满足）"""
    parts = []

    # 检查 min_cli_version 要求（最高优先级，硬性阻断）
    version_required_msg = _check_min_cli_version()
    if version_required_msg:
        parts.append(version_required_msg)

    # 检查 CLI 自身更新
    cli_update_msg = _check_cli_update()
    if cli_update_msg:
        parts.append(cli_update_msg)

    # 检查仓库更新
    try:
        _, updatable, _ = _collect_updatable(fetch=False)
        if updatable:
            repos_str = "、".join(r.name for r in updatable)
            parts.append(UpdatePrompt.HAS_UPDATE.format(repos=repos_str))
    except Exception:
        pass

    return "\n\n".join(parts)


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
            "system_prompt": _collect_repo_system_prompts(),
            "user_prompt": config.user_prompt,
            "notifications": _build_notifications(),
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
