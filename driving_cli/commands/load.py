"""load 命令 - 一次性输出所有上下文数据，供 AI 会话注入"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import click

from driving_cli import __version__

# 模块级调试开关，由 load() 设置后供内部函数使用
_debug_enabled = False
_load_start: float = 0.0


def _dbg(msg: str) -> None:
    """输出带时间戳和相对耗时的调试日志到 stderr"""
    if not _debug_enabled:
        return
    elapsed = time.perf_counter() - _load_start
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    click.echo(f"[DEBUG {ts}] (+{elapsed*1000:.1f}ms) {msg}", file=sys.stderr)


from driving_cli.commands.agent import collect_agents
from driving_cli.commands.framework import collect_frameworks
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
    HAS_CLI_UPDATE = "⬆️ 【CLI更新】driving CLI 有新版本可用（当前 {current}，最新 {latest}），请询问用户是否执行 `sudo driving update` 升级。"
    CLI_VERSION_REQUIRED = "🚨 【版本不满足】当前 driving CLI 版本 {current} 不满足要求（需要 >= {required}），必须先执行 `sudo driving update` 升级后才能继续，请询问用户是否执行升级。"
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


def _check_and_pull_repos() -> str:
    """检查仓库更新，自动拉取 check_sample_rate=-1 的仓库，返回需通知的提示文本"""
    _dbg("检查仓库更新 ...")
    t = time.perf_counter()
    try:
        _, updatable, _, auto_pull, sample_log = _collect_updatable(fetch=False)

        # 打印采样结果
        for repo_name, rate, hit, roll in sample_log:
            if rate == 0:
                _dbg(f"  仓库 '{repo_name}'：采样率=0，跳过检测")
            elif rate == -1:
                _dbg(f"  仓库 '{repo_name}'：采样率=-1（auto_pull），始终检测")
            else:
                _dbg(f"  仓库 '{repo_name}'：采样率={rate}，随机值={roll}，{'命中' if hit else '未命中'}")

        _dbg(f"仓库更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，可更新仓库数={len(updatable)}，自动拉取数={len(auto_pull)}")

        # 自动拉取 check_sample_rate=-1 的仓库
        if auto_pull:
            import subprocess as _sp
            auto_pull_names = {r.name for r in auto_pull}
            for repo in auto_pull:
                _dbg(f"自动拉取仓库 '{repo.name}' ...")
                try:
                    _sp.run(
                        ["driving", "repo", "pull", repo.name],
                        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=30,
                    )
                except Exception as e:
                    _dbg(f"自动拉取 '{repo.name}' 失败：{e}")
            # 需要通知的仓库 = 有更新但不在自动拉取列表中的
            notify_repos = [r for r in updatable if r.name not in auto_pull_names]
        else:
            notify_repos = updatable

        if notify_repos:
            repos_str = "、".join(r.name for r in notify_repos)
            return UpdatePrompt.HAS_UPDATE.format(repos=repos_str)
    except Exception:
        _dbg(f"仓库更新检查异常，耗时 {(time.perf_counter()-t)*1000:.1f}ms")
    return ""


def _build_notifications(repo_update_msg: str = "") -> str:
    """构建通知类内容（更新提醒、版本不满足）

    repo_update_msg: 仓库更新提示，由外部提前检查后传入
    """
    parts = []

    # 检查 min_cli_version 要求（最高优先级，硬性阻断）
    _dbg("检查 min_cli_version ...")
    t = time.perf_counter()
    version_required_msg = _check_min_cli_version()
    _dbg(f"min_cli_version 检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")
    if version_required_msg:
        parts.append(version_required_msg)

    # 检查 CLI 自身更新
    _dbg("检查 CLI 自身更新 ...")
    t = time.perf_counter()
    cli_update_msg = _check_cli_update()
    _dbg(f"CLI 更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")
    if cli_update_msg:
        parts.append(cli_update_msg)

    if repo_update_msg:
        parts.append(repo_update_msg)

    return "\n\n".join(parts)


@click.command("load")
@click.argument("keywords", nargs=-1, required=False)
@click.option("--debug", is_flag=True, default=False, help="输出调试日志")
@click.option("--with", "with_modules", default="", metavar="MODULES",
              help="附带额外模块，逗号分隔，可选值：framework, agent")
def load(keywords: tuple, debug: bool, with_modules: str):
    """一次性输出所有上下文数据（skills、rules、repos、prompts），供 AI 会话注入

    不传参数时加载 tags=base 的仓库内容。
    传入 repo-name 时只加载匹配仓库的 skills/rules。
    使用 --with 附带额外模块（framework、agent），关键词同样生效。

    示例：
        driving load
        driving load f-message
        driving load --with framework
        driving load --with framework,agent
        driving load driving --with framework,agent
        driving load xstatic --with framework
        driving load --debug
    """
    set_silent(not debug)
    global _debug_enabled, _load_start
    _debug_enabled = debug
    _load_start = time.perf_counter()
    _dbg(f"driving load 开始，版本={__version__}，keywords={keywords}，with={with_modules}")
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        config = config_manager.load()
        _dbg(f"配置加载完成，project_root={project_root}")

        # 解析 --with 模块列表
        modules = {m.strip().lower() for m in with_modules.split(",") if m.strip()}

        # 带关键词时不检查仓库更新；不带关键词时提前检查并 auto_pull，
        # 确保后续 collect 读到的是最新内容
        repo_update_msg = ""
        if not keywords:
            t = time.perf_counter()
            repo_update_msg = _check_and_pull_repos()
            _dbg(f"仓库更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")

        t = time.perf_counter()
        skills = collect_skills(keywords)
        _dbg(f"collect_skills 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，数量={len(skills)}")

        t = time.perf_counter()
        rules = collect_rules(keywords)
        _dbg(f"collect_rules 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，数量={len(rules)}")

        # 带关键词时不收集 repos（关键词即 repo-name，无需重复返回仓库信息）
        repos = []
        if not keywords:
            t = time.perf_counter()
            repos = collect_repos(keywords)
            _dbg(f"collect_repos 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，数量={len(repos)}")

        frameworks = None
        if "framework" in modules:
            t = time.perf_counter()
            frameworks = collect_frameworks(keywords)
            _dbg(f"collect_frameworks 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，数量={len(frameworks)}")

        agents_data = None
        if "agent" in modules:
            t = time.perf_counter()
            agents_data = collect_agents(keywords)
            _dbg(f"collect_agents 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，数量={len(agents_data)}")

        result = {"cli_version": __version__}

        # 空列表不输出，避免给 AI 造成误解
        if skills:
            result["skills"] = skills
        if rules:
            result["rules"] = rules
        if repos:
            result["repos"] = repos
        if frameworks:
            result["frameworks"] = frameworks
        if agents_data:
            result["agents"] = agents_data

        # 带关键词时不输出 system_prompt / user_prompt / notifications
        if not keywords:
            t = time.perf_counter()
            system_prompt = _collect_repo_system_prompts()
            _dbg(f"collect_repo_system_prompts 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，长度={len(system_prompt)}")

            t = time.perf_counter()
            notifications = _build_notifications(repo_update_msg)
            _dbg(f"build_notifications 完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")

            if system_prompt:
                result["system_prompt"] = system_prompt
            if config.user_prompt:
                result["user_prompt"] = config.user_prompt
            if notifications:
                result["notifications"] = notifications
        else:
            _dbg("带关键词，跳过 system_prompt / user_prompt / notifications")

        _dbg(f"load 全部完成，总耗时 {(time.perf_counter()-_load_start)*1000:.1f}ms")
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}, ensure_ascii=False))
        raise SystemExit(1)
