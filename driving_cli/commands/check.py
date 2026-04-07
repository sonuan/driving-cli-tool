"""check 命令 - 打印 CLI 版本并检查各 remote 仓库是否有可用更新"""

import json
import subprocess
from pathlib import Path
from typing import Optional

import click

from driving_cli import __version__
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning


def _get_repo_version(repo_dir: Path) -> str:
    """获取仓库当前 commit hash"""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "unknown"


def _compare_local_remote(repo_dir: Path) -> Optional[bool]:
    """纯本地对比 HEAD 与上次 fetch 的远端引用，不联网"""
    try:
        local = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True,
        ).strip()
        for ref in ("@{u}", "origin/HEAD", "origin/main", "origin/master"):
            try:
                remote = subprocess.check_output(
                    ["git", "rev-parse", ref],
                    cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True,
                ).strip()
                return local != remote
            except Exception:
                continue
        return None
    except Exception:
        return None


def _has_new_version(repo_dir: Path) -> Optional[bool]:
    """fetch 后对比本地与远端，返回 True/False/None（None 表示网络失败）"""
    try:
        subprocess.run(
            ["git", "fetch", "--quiet"],
            cwd=str(repo_dir), stderr=subprocess.DEVNULL, timeout=10,
        )
    except Exception:
        return None
    return _compare_local_remote(repo_dir)


@click.command("check")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="JSON 输出模式：仅检测并输出结果，不交互。供 AI 会话使用。")
def check(as_json: bool):
    """检查 CLI 版本及各 remote 仓库的可用更新

    示例：
        driving check
        driving check --json
    """
    if as_json:
        _check_json()
    else:
        _check_interactive()


def _collect_updatable(fetch: bool = True):
    """收集可更新仓库列表，返回 (project_root, updatable, warnings)

    fetch=True 时先 git fetch 再对比（check 命令用），
    fetch=False 时纯本地对比（load 命令用）。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)
    repos = config_mgr.get_all_repos()
    remote_repos = [r for r in repos if r.type == "remote"]

    compare = _has_new_version if fetch else _compare_local_remote
    updatable = []
    warnings = []
    for repo in remote_repos:
        repo_dir = project_root / repo.path
        is_init = repo_dir.exists() and any(repo_dir.iterdir())
        if not is_init:
            warnings.append(f"仓库 '{repo.name}' 未初始化，跳过")
            continue
        result = compare(repo_dir)
        if result is True:
            updatable.append(repo)
        elif result is None:
            warnings.append(f"仓库 '{repo.name}' 检查失败，跳过")

    return project_root, updatable, warnings


def _check_json():
    """JSON 模式：输出结构化检测结果，不做交互"""
    try:
        _, updatable, warnings = _collect_updatable()
    except ValueError as e:
        click.echo(json.dumps({"version": __version__, "error": str(e)}))
        raise SystemExit(1)

    result = {
        "version": __version__,
        "updatable": [r.name for r in updatable],
        "warnings": warnings,
    }
    click.echo(json.dumps(result, ensure_ascii=False))


def _check_interactive():
    """交互模式：原有行为"""
    log_info(f"driving CLI 版本: {__version__}")

    try:
        project_root, updatable, warnings = _collect_updatable()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    for w in warnings:
        log_warning(w)

    if not updatable:
        log_success("所有仓库均为最新版本 ✓")
        return

    names = "、".join(r.name for r in updatable)
    click.echo(f"\n以下仓库有可用更新：{names}")
    click.echo("是否执行更新？（可逐个确认）")

    for repo in updatable:
        if click.confirm(f"  更新仓库 '{repo.name}'？", default=True):
            click.echo(f"  正在更新 '{repo.name}'...")
            ret = subprocess.run(
                ["driving", "repo", "pull", repo.name],
            )
            if ret.returncode == 0:
                log_success(f"  '{repo.name}' 更新成功 ✓")
            else:
                log_error(f"  '{repo.name}' 更新失败")
        else:
            log_info(f"  跳过 '{repo.name}'")
