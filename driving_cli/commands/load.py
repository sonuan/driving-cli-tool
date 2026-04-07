"""load 命令 - 一次性输出所有上下文数据，供 AI 会话注入"""

import json
import subprocess
from pathlib import Path
from typing import Optional

import click

from driving_cli import __version__
from driving_cli.commands.check import _collect_updatable
from driving_cli.commands.rule import filter_rules_by_config, scan_rules_from_dir
from driving_cli.commands.skill import scan_skills_from_dir
from driving_cli.utils.config_manager import ConfigManager, find_project_root


class SystemPrompt:
    HAS_UPDATE = "以下仓库存在新版本：{repos}，请询问用户是否更新，确认前不得继续。"
    DEFAULT = ""


def _build_skills(project_root: Path, config_manager: ConfigManager) -> list:
    skills_dirs = config_manager.get_all_skills_dirs()
    if not skills_dirs:
        return []

    repo_configs = config_manager.get_all_repos()
    repo_config_map = {r.name: r for r in repo_configs}

    result = []
    seen = set()
    for repo_name, skills_dir in skills_dirs:
        rc = repo_config_map.get(repo_name)
        tags = rc.tags if rc and rc.tags else []
        if "base" not in tags:
            continue
        repo_skills = scan_skills_from_dir(repo_name, skills_dir, quiet=True)
        if rc and rc.skills:
            enabled = rc.skills.get("enabled") or []
            disabled = rc.skills.get("disabled") or []
            if enabled:
                repo_skills = [s for s in repo_skills if s["name"] in enabled]
            elif disabled:
                repo_skills = [s for s in repo_skills if s["name"] not in disabled]
        for s in repo_skills:
            if s["path"] not in seen:
                seen.add(s["path"])
                result.append({"name": s["name"], "description": s["description"], "path": s["path"]})
    return sorted(result, key=lambda x: x["name"])


def _build_rules(project_root: Path, config_manager: ConfigManager) -> list:
    rules_dirs = config_manager.get_all_rules_dirs()
    if not rules_dirs:
        return []

    repo_configs = config_manager.get_all_repos()
    repo_config_map = {r.name: r for r in repo_configs}

    result = []
    seen = set()
    for repo_name, rules_dir in rules_dirs:
        rc = repo_config_map.get(repo_name)
        tags = rc.tags if rc and rc.tags else []
        if "base" not in tags:
            continue
        repo_rules = scan_rules_from_dir(repo_name, rules_dir, quiet=True, header_only=True)
        if rc:
            repo_rules = filter_rules_by_config(repo_rules, rc)
        for r in repo_rules:
            if r["path"] not in seen:
                seen.add(r["path"])
                result.append({"name": r["name"], "description": r["description"], "path": r["path"]})
    return result


def _build_repos(project_root: Path, config_manager: ConfigManager) -> list:
    repos = config_manager.get_all_repos()
    result = []
    for repo in repos:
        repo_dir = project_root / repo.path
        if repo.type == "remote":
            is_init = repo_dir.exists() and any(repo_dir.iterdir())
            status = "initialized" if is_init else "uninitialized"
        else:
            status = "exists" if (repo_dir.exists() or repo_dir.is_symlink()) else "missing"

        entry = {
            "name": repo.name,
            "type": repo.type,
            "description": repo.description or "",
            "path": repo.path,
            "status": status,
        }
        if repo.type == "remote":
            entry["url"] = repo.url
            if repo_dir.exists() and any(repo_dir.iterdir()):
                try:
                    entry["version"] = subprocess.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True,
                    ).strip()
                except Exception:
                    entry["version"] = "unknown"
            else:
                entry["version"] = None
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
def load():
    """一次性输出所有上下文数据（skills、rules、repos、prompts），供 AI 会话注入

    示例：
        driving load
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        config = config_manager.load()

        result = {
            "cli_version": __version__,
            "skills": _build_skills(project_root, config_manager),
            "rules": _build_rules(project_root, config_manager),
            "repos": _build_repos(project_root, config_manager),
            "system_prompt": _build_system_prompt(),
            "user_prompt": config.user_prompt,
        }
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
