"""submodule_init - 可复用的 submodule 初始化工具

提供两个独立函数供 load / repo install / power install 共同调用：

- init_powers:             初始化 driving.power.json 中所有未就绪的 remote power
- init_repos_from_config:  从指定 driving.config.json 初始化未就绪的 remote repos，
                           并按配置切换分支

设计原则：
- verbose=True  → 通过 log_info/log_warning/log_success 输出（交互式命令）
- verbose=False → 通过 stderr 输出（load 后台静默执行）
- 所有异常均被捕获后降级处理，不中断调用方的主流程
"""

import json
import sys
from pathlib import Path

from driving_cli.utils.config_manager import CONFIG_FILE_NAME, POWER_FILE_NAME, PowerManager
from driving_cli.utils.git_helper import ensure_submodule_initialized


def _out(msg: str, *, verbose: bool, level: str = "info") -> None:
    """统一输出：verbose 模式走 log_*，静默模式走 stderr。

    level: "info" | "warning" | "error"
    静默模式（verbose=False）下，info 级别不输出，只输出 warning 和 error。
    """
    if verbose:
        from driving_cli.utils.logger import log_error, log_info, log_warning

        if level == "error":
            log_error(msg)
        elif level == "warning":
            log_warning(msg)
        else:
            log_info(msg)
    else:
        # 静默模式：info 不输出，warning/error 写 stderr
        if level == "info":
            return
        if level == "error":
            prefix = "[driving] 错误："
        else:
            prefix = "[driving] 警告："
        import click

        click.echo(f"{prefix}{msg}", file=sys.stderr)


def _rel_path(project_root: Path, git_root: Path, entry_path: str) -> str:
    """计算相对于 git_root 的 submodule 路径，统一用正斜杠"""
    try:
        rel = str((project_root / entry_path).relative_to(git_root))
    except ValueError:
        rel = entry_path
    return rel.replace("\\", "/")


# ==================== init_powers ====================


def init_powers(
    project_root: Path,
    git_root: Path,
    *,
    verbose: bool = True,
) -> int:
    """检测并初始化 driving.power.json 中所有未就绪的 remote power。

    对每个 remote power：
    - 目录为空/不存在 → ensure_submodule_initialized + _set_submodule_ignore
    - 目录已就绪      → 检查/切换分支、验证 driving.config.json 存在性

    Args:
        project_root: 项目根目录
        git_root:     git 仓库根目录
        verbose:      True 使用 log_* 输出，False 静默写 stderr

    Returns:
        成功初始化（新增）的 power 数量
    """
    power_file = project_root / POWER_FILE_NAME
    if not power_file.exists():
        return 0

    try:
        pm = PowerManager(project_root)
        power_cfg = pm.load_power_config()
    except Exception as e:
        _out(f"读取 driving.power.json 失败：{e}", verbose=verbose, level="warning")
        return 0

    initialized = 0

    for entry in power_cfg.powers:
        if entry.type != "remote":
            continue

        power_dir = project_root / entry.path

        if _needs_init(power_dir):
            _out(f"正在初始化 power '{entry.name}'...", verbose=verbose)
            submodule_path = _rel_path(project_root, git_root, entry.path)
            ok = ensure_submodule_initialized(
                project_root=project_root,
                git_root=git_root,
                rel_path=submodule_path,
                url=entry.url or "",
                branch=entry.branch or "",
                label=f"power '{entry.name}'",
            )
            if ok:
                # ignore = all：主项目忽略 submodule 内部变更
                from driving_cli.commands.repo import _set_submodule_ignore

                _set_submodule_ignore(git_root, submodule_path)
                initialized += 1
                _ensure_power_config(power_dir, entry, verbose=verbose)
        else:
            _ensure_power_config(power_dir, entry, verbose=verbose)

    return initialized


def _needs_init(path: Path) -> bool:
    """目录不存在，或存在但为空——两种情况都需要初始化"""
    if not path.exists():
        return True
    return path.is_dir() and not any(path.iterdir())


def _ensure_power_config(power_dir: Path, entry, *, verbose: bool) -> None:
    """确保 power 处于正确的分支，并验证 driving.config.json 存在性。

    分支解析优先级（通过 entry.get_load_branch() 处理）：
    1. entry.repo_config[entry.name].branch
    2. entry.branch
    3. 无配置 → 仅在 config 缺失时打印警告
    """
    import driving_cli.utils.git_helper as _gh

    config_path = power_dir / CONFIG_FILE_NAME
    label = f"power '{entry.name}'"
    effective_branch = entry.get_load_branch()

    if effective_branch:
        try:
            repo = _gh.git.Repo(power_dir)
            # 已在目标分支则跳过
            try:
                if not repo.head.is_detached and repo.active_branch.name == effective_branch:
                    if not config_path.exists():
                        _out(
                            f"{label} 缺少 driving.config.json",
                            verbose=verbose,
                            level="warning",
                        )
                    return
            except Exception:
                pass

            if repo.remotes:
                try:
                    repo.remotes.origin.fetch()
                except _gh.git.exc.GitCommandError:
                    pass
            repo.git.checkout(effective_branch)

        except _gh.git.exc.GitCommandError as e:
            err_msg = e.stderr.strip() if e.stderr else str(e)
            _out(
                f"{label} 切换到分支 '{effective_branch}' 失败：{err_msg}",
                verbose=verbose,
                level="error",
            )
            return
        except Exception as e:
            _out(
                f"{label} 切换到分支 '{effective_branch}' 失败：{e}",
                verbose=verbose,
                level="error",
            )
            return

        if not config_path.exists():
            _out(
                f"{label} 切换到分支 '{effective_branch}' 后仍缺少 driving.config.json",
                verbose=verbose,
                level="warning",
            )
    else:
        if not config_path.exists():
            _out(
                f"{label} 缺少 driving.config.json，可能位于错误的分支。"
                "建议在 driving.power.json 中为该 power 配置 branch 字段以自动切换。",
                verbose=verbose,
                level="warning",
            )


# ==================== init_repos_from_config ====================


def init_repos_from_config(
    config_path: Path,
    project_root: Path,
    git_root: Path,
    *,
    power_entry=None,
    verbose: bool = True,
) -> int:
    """从指定的 driving.config.json 检测并初始化未就绪的 remote repos，
    并对所有 remote repo 执行分支切换。

    Args:
        config_path:   driving.config.json 的绝对路径
        project_root:  项目根目录
        git_root:      git 仓库根目录
        power_entry:   对应的 PowerEntry（有值则启用 repo_config 分支覆盖，None 为传统模式）
        verbose:       True 使用 log_* 输出，False 静默写 stderr

    Returns:
        成功初始化（新增）的 repo 数量
    """
    if not config_path.exists():
        return 0

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        repos = data.get("repos", [])
    except Exception as e:
        _out(f"读取 {config_path} 失败：{e}", verbose=verbose, level="warning")
        return 0

    initialized = 0

    for repo in repos:
        repo_path_str = repo.get("path", "")
        repo_name = repo.get("name", repo_path_str)
        repo_type = repo.get("type", "remote")
        repo_url = repo.get("url", "")
        repo_branch = repo.get("branch", "")

        if repo_type != "remote" or not repo_path_str:
            continue

        repo_dir = project_root / repo_path_str
        label = f"repo '{repo_name}'"
        submodule_path = _rel_path(project_root, git_root, repo_path_str)

        if _needs_init(repo_dir):
            _out(f"正在初始化 {label}...", verbose=verbose)
            ok = ensure_submodule_initialized(
                project_root=project_root,
                git_root=git_root,
                rel_path=submodule_path,
                url=repo_url,
                branch=repo_branch,
                label=label,
            )
            if ok:
                initialized += 1
        else:
            # 目录已就绪：检查是否需要切换分支
            target_branch = (
                power_entry.get_repo_load_branch(repo_name) if power_entry is not None else None
            ) or repo_branch

            if target_branch:
                _checkout_repo_branch(repo_dir, repo_name, target_branch, verbose=verbose)

    return initialized


def _checkout_repo_branch(
    repo_dir: Path, repo_name: str, target_branch: str, *, verbose: bool
) -> None:
    """切换 repo 到目标分支（已就绪目录场景）"""
    import driving_cli.utils.git_helper as _gh

    label = f"repo '{repo_name}'"
    try:
        repo = _gh.git.Repo(repo_dir)
        try:
            if not repo.head.is_detached and repo.active_branch.name == target_branch:
                return  # 已在目标分支
        except Exception:
            pass

        if repo.remotes:
            try:
                repo.remotes.origin.fetch()
            except _gh.git.exc.GitCommandError:
                pass
        repo.git.checkout(target_branch)
    except _gh.git.exc.GitCommandError as e:
        err_msg = e.stderr.strip() if e.stderr else str(e)
        _out(
            f"{label} 切换到分支 '{target_branch}' 失败：{err_msg}",
            verbose=verbose,
            level="error",
        )
    except Exception as e:
        _out(
            f"{label} 切换到分支 '{target_branch}' 失败：{e}",
            verbose=verbose,
            level="error",
        )
