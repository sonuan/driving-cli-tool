"""load 命令 - 一次性输出所有上下文数据，供 AI 会话注入"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    HAS_UPDATE = "⬆️ 【仓库更新】以下仓库存在新版本：{repos}。仅在主 Agent 询问用户是否更新，确认后逐个执行 `driving repo pull <repo-name>` 更新，确认前不得继续任何操作（子 Agent 忽略该提醒）。"
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


def _try_auto_update(original_cmd: str = "driving load") -> Optional[str]:
    """检查并同步执行 CLI 自动更新。

    仅在满足以下全部条件时尝试更新：
    1. 已通过 ~/.driving-cli/driving 安装（用户目录，无需 sudo）
    2. 检测到有新版本

    Args:
        original_cmd: 用户原始调用的完整命令，更新成功后提示 AI 原样重新执行

    Returns:
        str: 更新成功时返回 system_prompt 提示文本，要求 AI 重新执行 driving load
        None: 无需更新、不满足条件、或更新失败时返回 None（降级，不阻断正常流程）
    """
    import subprocess as _sp
    from pathlib import Path as _Path

    user_binary = _Path.home() / ".driving-cli" / "driving"
    if not user_binary.exists():
        _dbg("跳过自动更新：未使用 ~/.driving-cli 安装方式")
        return None

    try:
        version_info = fetch_version_info(_get_update_version_url())
        if not version_info:
            return None
        latest = version_info.get("version", "")
        if not latest or compare_versions(__version__, latest) >= 0:
            _dbg(f"已是最新版本（{__version__}），跳过自动更新")
            return None

        _dbg(f"检测到新版本 {latest}，开始同步更新...")
        result = _sp.run(
            [str(user_binary), "update", "--yes"],
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
            timeout=60,
        )
        if result.returncode == 0:
            _dbg(f"CLI 更新成功：{__version__} → {latest}")
            return (
                f"🔄 【CLI已更新】driving CLI 已从 {__version__} 更新到 {latest}，"
                f"请立即重新执行 `{original_cmd}` 以加载最新版本。"
                f"当前返回数据无效，不得继续任何操作。"
            )
        else:
            _dbg(f"CLI 更新失败（returncode={result.returncode}），降级继续正常流程")
            return None
    except Exception as e:
        _dbg(f"CLI 自动更新异常，降级继续正常流程：{e}")
        return None


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


def _init_unloaded_submodules() -> None:
    """检测并自动初始化未加载的 power 和 repo（git submodule 目录存在但为空的情况）。

    执行顺序：
    1. 检查 power（driving.power.json）：发现空目录则调用 ensure_submodule_initialized
    2. power 初始化完成后，检查该 power 下的 repos（driving.config.json）是否也未初始化，
       若未初始化则继续调用 ensure_submodule_initialized
    3. 检查传统模式下的 repos（driving.config.json）

    仅在 --debug 模式下输出日志，非 debug 模式静默执行。
    """
    from driving_cli.utils.git_helper import (
        checkout_branch_after_install as _checkout_branch,
        ensure_submodule_initialized,
        find_git_root,
    )

    _dbg("开始检测未初始化的 submodule ...")
    t = time.perf_counter()

    try:
        project_root = find_project_root()
    except Exception as e:
        _dbg(f"find_project_root 失败：{e}")
        return

    # load 场景下 project_root 即 git 根目录（常见部署方式）
    try:
        git_root = find_git_root(project_root)
    except Exception as e:
        _dbg(f"find_git_root 失败：{e}")
        return

    def _needs_init(path: Path) -> bool:
        """目录不存在，或存在但为空——两种情况都需要初始化"""
        if not path.exists():
            return True
        return path.is_dir() and not any(path.iterdir())

    def _ensure_power_config(power_dir: Path, entry) -> None:
        """确保 power 处于正确的分支并检查 driving.config.json。

        分支解析优先级（通过 entry.get_load_branch() 处理）：
        1. entry.repo_config[entry.name].branch
        2. entry.branch
        3. 无配置 → 仅在 config 缺失时打印警告

        切换分支失败时报错（error），不中断其他 power 的处理。
        """
        from driving_cli.utils.config_manager import CONFIG_FILE_NAME
        import git as _git

        config_path = power_dir / CONFIG_FILE_NAME
        label = f"power '{entry.name}'"

        effective_branch = entry.get_load_branch()

        if effective_branch:
            _dbg(f"  {label} 目标分支 '{effective_branch}'，检查并切换...")
            try:
                repo = _git.Repo(power_dir)
                # 已在目标分支则跳过
                try:
                    if not repo.head.is_detached and repo.active_branch.name == effective_branch:
                        _dbg(f"  {label} 已在分支 '{effective_branch}'，跳过切换")
                        if not config_path.exists():
                            click.echo(
                                f"[driving load] 警告：{label} 缺少 driving.config.json",
                                file=sys.stderr,
                            )
                        return
                except Exception:
                    pass
                if repo.remotes:
                    try:
                        repo.remotes.origin.fetch()
                    except _git.exc.GitCommandError:
                        pass
                repo.git.checkout(effective_branch)
                _dbg(f"  {label} 已切换到分支 '{effective_branch}'")
            except _git.exc.GitCommandError as e:
                err_msg = e.stderr.strip() if e.stderr else str(e)
                click.echo(
                    f"[driving load] 错误：{label} 切换到分支 '{effective_branch}' 失败：{err_msg}",
                    file=sys.stderr,
                )
                return
            except Exception as e:
                click.echo(
                    f"[driving load] 错误：{label} 切换到分支 '{effective_branch}' 失败：{e}",
                    file=sys.stderr,
                )
                return
            if not config_path.exists():
                click.echo(
                    f"[driving load] 警告：{label} 切换到分支 '{effective_branch}' 后仍缺少 driving.config.json",
                    file=sys.stderr,
                )
        else:
            if not config_path.exists():
                hint = "建议在 driving.power.json 中为该 power 配置 branch 字段以自动切换。"
                _dbg(f"  {label} 缺少 driving.config.json，{hint}")
                click.echo(
                    f"[driving load] 警告：{label} 缺少 driving.config.json，"
                    f"可能位于错误的分支。{hint}",
                    file=sys.stderr,
                )

    def _init_repos_from_config(config_path: Path, context_label: str, power_entry=None) -> None:
        """从指定的 driving.config.json 检测并初始化未加载的 repos，
        并对所有 remote repo 执行 repo_config 指定的分支切换。

        power_entry: 对应的 PowerEntry，用于查询 repo_config 分支覆盖配置。
                     为 None 时（传统模式）不执行分支切换。
        """
        import git as _git

        if not config_path.exists():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            repos = data.get("repos", [])
        except Exception as e:
            _dbg(f"  读取 {context_label} driving.config.json 失败：{e}")
            return

        for repo in repos:
            repo_path_str = repo.get("path", "")
            repo_name = repo.get("name", repo_path_str)
            repo_type = repo.get("type", "remote")
            repo_url = repo.get("url", "")
            repo_branch = repo.get("branch", "")
            if repo_type != "remote" or not repo_path_str:
                continue

            # 计算相对于 git_root 的路径
            try:
                rel_path = str((project_root / repo_path_str).relative_to(git_root))
            except ValueError:
                rel_path = repo_path_str

            repo_dir = project_root / repo_path_str
            label = f"repo '{repo_name}'"

            if _needs_init(repo_dir):
                _dbg(f"  检测到未初始化的 repo '{repo_name}'（{repo_path_str}），正在初始化...")
                ensure_submodule_initialized(
                    project_root=project_root,
                    git_root=git_root,
                    rel_path=rel_path,
                    url=repo_url,
                    branch=repo_branch,
                    label=label,
                )
            else:
                # 目录已就绪：检查分支是否需要切换
                # Power 模式：优先取 repo_config[repo_name].branch，fallback 到 driving.config.json 里的 repo.branch
                # 传统模式：直接取 driving.config.json 里的 repo.branch
                target_branch = (
                    power_entry.get_repo_load_branch(repo_name) if power_entry is not None else None
                ) or repo_branch
                if not target_branch:
                    continue
                _dbg(f"  {label} 目标分支 '{target_branch}'，检查并切换...")
                try:
                    repo_git = _git.Repo(repo_dir)
                    try:
                        if not repo_git.head.is_detached and repo_git.active_branch.name == target_branch:
                            _dbg(f"  {label} 已在分支 '{target_branch}'，跳过切换")
                            continue
                    except Exception:
                        pass
                    if repo_git.remotes:
                        try:
                            repo_git.remotes.origin.fetch()
                        except _git.exc.GitCommandError:
                            pass
                    repo_git.git.checkout(target_branch)
                    _dbg(f"  {label} 已切换到分支 '{target_branch}'")
                except _git.exc.GitCommandError as e:
                    err_msg = e.stderr.strip() if e.stderr else str(e)
                    click.echo(
                        f"[driving load] 错误：{label} 切换到分支 '{target_branch}' 失败：{err_msg}",
                        file=sys.stderr,
                    )
                except Exception as e:
                    click.echo(
                        f"[driving load] 错误：{label} 切换到分支 '{target_branch}' 失败：{e}",
                        file=sys.stderr,
                    )

    # ---- 1. Power 模式检测 ----
    from driving_cli.utils.config_manager import PowerManager, POWER_FILE_NAME, CONFIG_FILE_NAME
    power_file = project_root / POWER_FILE_NAME

    if power_file.exists():
        _dbg("检测到 Power 模式，开始检测 power submodule ...")
        try:
            pm = PowerManager(project_root)
            power_cfg = pm.load_power_config()
        except Exception as e:
            _dbg(f"  读取 driving.power.json 失败：{e}")
            power_cfg = None

        if power_cfg:
            for entry in power_cfg.powers:
                if entry.type != "remote":
                    continue
                power_dir = project_root / entry.path

                # 计算相对于 git_root 的路径
                try:
                    rel_path = str((project_root / entry.path).relative_to(git_root))
                except ValueError:
                    rel_path = entry.path

                if _needs_init(power_dir):
                    _dbg(f"检测到未初始化的 power '{entry.name}'（{entry.path}），正在初始化...")
                    ok = ensure_submodule_initialized(
                        project_root=project_root,
                        git_root=git_root,
                        rel_path=rel_path,
                        url=entry.url or "",
                        branch=entry.branch or "",
                        label=f"power '{entry.name}'",
                    )
                    if ok:
                        _ensure_power_config(power_dir, entry)
                        _init_repos_from_config(
                            power_dir / CONFIG_FILE_NAME,
                            f"power '{entry.name}'",
                            power_entry=entry,
                        )
                else:
                    _ensure_power_config(power_dir, entry)
                    _init_repos_from_config(
                        power_dir / CONFIG_FILE_NAME,
                        f"power '{entry.name}'",
                        power_entry=entry,
                    )

    # ---- 2. 传统模式：检测根目录 driving.config.json 下的 repos ----
    from driving_cli.utils.config_manager import CONFIG_FILE_NAME as _CFG
    root_config = project_root / _CFG
    if root_config.exists():
        _dbg("检测传统模式 repos ...")
        _init_repos_from_config(root_config, "传统模式")

    _dbg(f"submodule 初始化检测完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")


def _check_and_pull_powers() -> None:
    """检查所有远程 power 是否有更新，有则自动拉取（静默执行）"""
    _dbg("检查 power 更新 ...")
    t = time.perf_counter()
    try:
        from driving_cli.utils.config_manager import PowerManager
        project_root = find_project_root()
        pm = PowerManager(project_root)
        if not pm.exists():
            _dbg("未启用 Power 模式，跳过 power 更新检查")
            return

        updatable = pm.check_power_updates()
        _dbg(f"power 更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms，有更新的 power 数={len(updatable)}")

        for entry in updatable:
            _dbg(f"自动拉取 power '{entry.name}' ...")
            try:
                ok = pm.pull_power(entry.name)
                _dbg(f"power '{entry.name}' 拉取{'成功' if ok else '跳过'}")
            except Exception as e:
                _dbg(f"power '{entry.name}' 拉取失败：{e}")
    except Exception as e:
        _dbg(f"power 更新检查异常，耗时 {(time.perf_counter()-t)*1000:.1f}ms：{e}")


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
@click.option("--platform", default="", metavar="PLATFORM",
              help="当前开发平台（android/iOS/harmony/kuikly），注入 platform 字段到返回值")
def load(keywords: tuple, debug: bool, with_modules: str, platform: str):
    """一次性输出所有上下文数据（skills、rules、repos、prompts），供 AI 会话注入

    不传参数时加载 tags=base 的仓库内容。
    传入 repo-name 时只加载匹配仓库的 skills/rules。
    使用 --with 附带额外模块（framework、agent），关键词同样生效。
    使用 --platform 指定当前开发平台，返回值中包含 platform 字段。

    示例：
        driving load
        driving load f-message
        driving load --with framework
        driving load --with framework,agent
        driving load driving --with framework,agent
        driving load xstatic --with framework
        driving load --platform android
        driving load --debug
    """
    set_silent(not debug)
    global _debug_enabled, _load_start
    _debug_enabled = debug
    _load_start = time.perf_counter()

    # 支持逗号分隔：将 ("a,b", "c") 展开为 ("a", "b", "c")
    from driving_cli.utils.match import normalize_keywords
    keywords = normalize_keywords(keywords)

    _dbg(f"driving load 开始，版本={__version__}，keywords={keywords}，with={with_modules}，platform={platform}")
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        config = config_manager.load()
        _dbg(f"配置加载完成，project_root={project_root}")

        # 解析 --with 模块列表
        modules = {m.strip().lower() for m in with_modules.split(",") if m.strip()}

        # 带关键词时不检查仓库更新；不带关键词时：
        # 0. 先同步检查并执行 CLI 自动更新，有更新时直接返回提示，要求重新执行 load
        # 1. 检查并自动拉取 power 更新（确保合并的 config 是最新的）
        # 2. 再检查各 config.json 里的 repos 是否有更新
        repo_update_msg = ""
        if not keywords:
            _dbg("检查 CLI 自动更新...")
            t = time.perf_counter()
            # 拼出原始调用命令，方便 AI 原样重新执行
            original_cmd_parts = ["driving load"]
            if with_modules:
                original_cmd_parts.append(f"--with {with_modules}")
            if platform:
                original_cmd_parts.append(f"--platform {platform}")
            original_cmd = " ".join(original_cmd_parts)
            update_msg = _try_auto_update(original_cmd)
            _dbg(f"CLI 自动更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")
            if update_msg:
                # 更新成功：只返回 system_prompt，要求 AI 重新执行 driving load
                click.echo(json.dumps(
                    {"cli_version": __version__, "system_prompt": update_msg},
                    ensure_ascii=False, indent=2
                ))
                return
            t = time.perf_counter()
            _init_unloaded_submodules()
            _dbg(f"未加载 submodule 检测完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")

            t = time.perf_counter()
            _check_and_pull_powers()
            _dbg(f"power 更新检查完成，耗时 {(time.perf_counter()-t)*1000:.1f}ms")

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
        if platform:
            result["platform"] = platform

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
