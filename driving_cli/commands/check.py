"""check 命令 - 打印 CLI 版本并检查各 remote 仓库是否有可用更新"""

import json
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """纯本地对比 HEAD 与上次 fetch 的远端引用，不联网。
    只有远端有本地没有的提交（behind > 0）才返回 True，
    仅本地超前（只有 ahead）返回 False，无法判断返回 None。
    """
    for ref in ("@{u}", "origin/HEAD", "origin/main", "origin/master"):
        try:
            output = subprocess.check_output(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...{ref}"],
                cwd=str(repo_dir), stderr=subprocess.DEVNULL, text=True,
            ).strip()
            _ahead, behind = map(int, output.split())
            return behind > 0
        except Exception:
            continue
    return None


def _has_new_version(repo_dir: Path) -> Optional[bool]:
    """fetch 后对比本地与远端，返回 True/False/None（None 表示网络失败）。
    只有远端有新提交（behind > 0）才返回 True。
    """
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
    """收集可更新仓库列表，返回 (project_root, updatable, warnings, auto_pull)

    fetch=True 时先 git fetch 再对比（check 命令用），
    fetch=False 时纯本地对比（load 命令用）。

    采样率规则（仅 fetch=False 即 load 场景生效）：
      - 仓库级 check_sample_rate 优先，未设置则取全局值
      - 0：跳过检测
      - 1~100：随机采样，命中才检测
      - -1：始终检测，检测到更新时加入 auto_pull 列表（由调用方自动拉取）
      - check 命令（fetch=True）不受采样率影响，始终全量检测
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)
    config = config_mgr.load()
    repos = config.repos
    remote_repos = [r for r in repos if r.type == "remote"]

    # load 场景：按采样率过滤参与检测的仓库，并记录 -1 仓库
    auto_pull_names: set = set()
    sample_log: list = []  # [(repo_name, rate, hit)]
    if not fetch:
        sampled = []
        for repo in remote_repos:
            rate = repo.check_sample_rate if repo.check_sample_rate is not None else (config.check_sample_rate if config.check_sample_rate is not None else -1)
            if rate == 0:
                sample_log.append((repo.name, 0, False, None))
                continue  # 永不检测
            elif rate == -1:
                auto_pull_names.add(repo.name)
                sampled.append(repo)  # 始终参与检测
                sample_log.append((repo.name, -1, True, None))
            else:
                # 1~100 采样
                rate = max(1, min(100, rate))
                roll = random.randint(1, 100)
                hit = roll <= rate
                sample_log.append((repo.name, rate, hit, roll))
                if hit:
                    sampled.append(repo)
        remote_repos = sampled

    compare = _has_new_version if fetch else _compare_local_remote

    # 过滤未初始化的仓库
    init_repos = []
    warnings = []
    for repo in remote_repos:
        repo_dir = project_root / repo.path
        if not (repo_dir / ".git").exists():
            warnings.append(f"仓库 '{repo.name}' 未初始化，跳过")
        else:
            init_repos.append((repo, repo_dir))

    # 并发检查各仓库更新状态
    updatable = []
    if init_repos:
        with ThreadPoolExecutor(max_workers=min(len(init_repos), 8)) as executor:
            future_to_repo = {
                executor.submit(compare, repo_dir): repo
                for repo, repo_dir in init_repos
            }
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result is True:
                    updatable.append(repo)
                elif result is None:
                    warnings.append(f"仓库 '{repo.name}' 检查失败，跳过")

    # 保持原始顺序
    order = {repo.name: i for i, (repo, _) in enumerate(init_repos)}
    updatable.sort(key=lambda r: order.get(r.name, 0))

    # 区分需要自动拉取的仓库
    auto_pull = [r for r in updatable if r.name in auto_pull_names]

    return project_root, updatable, warnings, auto_pull, sample_log


def _check_json():
    """JSON 模式：输出结构化检测结果，不做交互"""
    try:
        _, updatable, warnings, _, _ = _collect_updatable()
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
        project_root, updatable, warnings, _, _ = _collect_updatable()
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
