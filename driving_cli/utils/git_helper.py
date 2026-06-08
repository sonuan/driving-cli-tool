"""Git 辅助模块 - 使用 GitPython 封装 Git 操作"""

from pathlib import Path
from typing import Optional, Tuple, Union

import git


def clone_repository(url: str, target_path: Union[str, Path], branch: str = None) -> git.Repo:
    """克隆 Git 仓库

    Args:
        url: 仓库 URL
        target_path: 目标路径
        branch: 分支名（可选）

    Returns:
        git.Repo: 仓库对象

    Raises:
        git.exc.GitCommandError: Git 命令执行失败
    """
    try:
        if branch:
            return git.Repo.clone_from(url, target_path, branch=branch)
        else:
            return git.Repo.clone_from(url, target_path)
    except git.exc.GitCommandError as e:
        raise git.exc.GitCommandError(f"克隆仓库失败: {e}", 1)


def is_git_repo(path: Union[str, Path]) -> bool:
    """检查路径是否是 Git 仓库

    Args:
        path: 路径

    Returns:
        bool: 是否是 Git 仓库
    """
    try:
        git.Repo(path)
        return True
    except git.exc.InvalidGitRepositoryError:
        return False


def find_git_root(path: Union[str, Path] = None) -> Path:
    """查找 Git 仓库根目录

    从指定路径（默认为当前目录）向上查找，直到找到 Git 仓库根目录。

    Args:
        path: 起始路径，默认为当前目录

    Returns:
        Path: Git 仓库根目录

    Raises:
        git.exc.InvalidGitRepositoryError: 未找到 Git 仓库
    """
    if path is None:
        path = Path.cwd()
    else:
        path = Path(path)

    try:
        repo = git.Repo(path, search_parent_directories=True)
        return Path(repo.working_dir)
    except git.exc.InvalidGitRepositoryError:
        raise git.exc.InvalidGitRepositoryError(f"未找到 Git 仓库: {path}")


def get_git_user() -> dict:
    """获取当前 Git 用户信息（name 和 email）

    从当前工作目录的 Git 配置中读取 user.name 和 user.email。
    读取失败时对应字段返回空字符串，不抛出异常。

    Returns:
        dict: {"name": "...", "email": "..."}
    """
    name = ""
    email = ""
    try:
        repo = git.Repo(Path.cwd(), search_parent_directories=True)
        with repo.config_reader() as cfg:
            try:
                name = cfg.get_value("user", "name", default="")
            except Exception:
                pass
            try:
                email = cfg.get_value("user", "email", default="")
            except Exception:
                pass
    except Exception:
        pass
    return {"name": str(name), "email": str(email)}


def is_local_framework(framework: dict) -> bool:
    """检查框架是否为本地项目

    当 project_name、url、branch 都设置为 __local__ 时，表示是本地项目。

    Args:
        framework: 框架配置字典

    Returns:
        bool: 是否为本地项目
    """
    return (
        framework.get("project_name") == "__local__"
        and framework.get("url") == "__local__"
        and framework.get("branch") == "__local__"
    )


def ensure_submodule_initialized(
    project_root: Path,
    git_root: Path,
    rel_path: str,
    url: str = "",
    branch: str = "",
    label: str = "",
) -> bool:
    """确保一个 git submodule 已完成初始化，供 power install、repo install、load 三处共用。

    执行顺序：
    1. git submodule update --init <rel_path>（优先，适用于 .gitmodules 已注册的情况）
    2. 若失败且提供了 url，降级为 git submodule add --force <url> <rel_path>，
       并在 add 前清理可能残留的 .git/modules 数据
    3. 若初始化成功且提供了 branch，调用 checkout_branch_after_install 切换分支

    Args:
        project_root: 项目根目录（用于解析 rel_path 的绝对路径）
        git_root:     git 仓库根目录（submodule 路径相对于此）
        rel_path:     submodule 相对于 git_root 的路径（如 "ai-driving/myrepo"）
        url:          远程仓库地址；为空时跳过降级 add 步骤
        branch:       初始化后自动切换的分支；为空时不切换
        label:        日志标签，如 "power 'feat'" / "仓库 'driving'"

    Returns:
        True  — 初始化成功（含降级路径）
        False — 初始化失败
    """
    import shutil as _shutil

    from driving_cli.utils.logger import log_error, log_info, log_success, log_warning

    if not label:
        label = rel_path

    git_repo = git.Repo(git_root)

    # ---- 尝试 submodule update --init ----
    try:
        git_repo.git.submodule("update", "--init", rel_path)
        log_success(f"{label} 初始化成功")
        if branch:
            checkout_branch_after_install(project_root / rel_path, label, branch)
        return True
    except git.exc.GitCommandError as update_err:
        stderr_msg = update_err.stderr.strip() if update_err.stderr else str(update_err)
        log_info(f"{label} submodule update --init 失败，尝试重新添加（原因：{stderr_msg}）")

    # ---- 降级：submodule add ----
    if not url:
        log_error(f"{label} 缺少 URL，无法重新添加 submodule")
        return False

    # 清理可能残留的 .git/modules 数据
    modules_dir = git_root / ".git" / "modules"
    parts = Path(rel_path).parts
    for depth in range(len(parts), 0, -1):
        partial = Path(*parts[:depth])
        modules_path = modules_dir / partial
        work_path = git_root / partial
        work_empty = not work_path.exists() or (work_path.is_dir() and not any(work_path.iterdir()))
        if modules_path.exists() and work_empty:
            log_warning(f"检测到残留 git modules 数据：{modules_path}，正在清理...")
            _shutil.rmtree(modules_path)
            log_info(f"已清理：{modules_path}")
            break

    try:
        (git_root / rel_path).parent.mkdir(parents=True, exist_ok=True)
        git_repo.git.submodule("add", "--force", url, rel_path)
        log_success(f"{label} 添加并初始化成功")
        if branch:
            checkout_branch_after_install(project_root / rel_path, label, branch)
        return True
    except git.exc.GitCommandError as add_err:
        stderr_msg = add_err.stderr.strip() if add_err.stderr else str(add_err)
        log_error(f"{label} 初始化失败：{stderr_msg}")
        return False


def checkout_branch_after_install(repo_dir: Path, repo_name: str, branch: str) -> None:
    """submodule 安装/初始化后切换到指定分支（供 repo、power、git_helper 内部共用）。

    若当前分支已是目标分支则跳过，否则先 fetch 再 checkout。
    切换失败只给出警告，不中断整体流程。
    """
    from driving_cli.utils.logger import log_info, log_success, log_warning

    if not repo_dir.exists():
        log_warning(f"'{repo_name}' 目录不存在，跳过分支切换")
        return
    try:
        repo = git.Repo(repo_dir)
        try:
            if not repo.head.is_detached and repo.active_branch.name == branch:
                log_info(f"'{repo_name}' 已在分支 '{branch}'，跳过切换")
                return
        except Exception:
            pass
        if repo.remotes:
            try:
                repo.remotes.origin.fetch()
            except git.exc.GitCommandError as e:
                log_warning(
                    f"'{repo_name}' fetch 失败，将使用本地分支信息"
                    f"（{e.stderr.strip() if e.stderr else str(e)}）"
                )
        repo.git.checkout(branch)
        log_success(f"'{repo_name}' 已切换到分支 '{branch}'")
    except git.exc.GitCommandError as e:
        if "did not match any" in str(e) or "pathspec" in str(e):
            log_warning(f"'{repo_name}' 分支 '{branch}' 不存在，请检查分支名称")
        else:
            log_warning(f"'{repo_name}' 切换分支 '{branch}' 失败：{e}")
    except Exception as e:
        log_warning(f"'{repo_name}' 切换分支 '{branch}' 失败：{e}")


def push_with_upstream(repo: git.Repo) -> Tuple[bool, str]:
    """执行 git push，自动处理无 upstream 分支的情况。

    当当前分支在远端不存在（no upstream branch）时，自动加 --set-upstream
    推送并建立追踪关系，等价于 `git push -u origin <branch>`。

    Args:
        repo: GitPython Repo 对象，必须已配置 origin remote

    Returns:
        Tuple[bool, str]: (是否成功, 错误信息或空字符串)
    """
    if repo.head.is_detached:
        return False, "当前处于 detached HEAD 状态，无法推送"

    branch = repo.active_branch.name

    # 检查当前分支是否已有 upstream tracking
    has_upstream = False
    try:
        tracking = repo.active_branch.tracking_branch()
        has_upstream = tracking is not None
    except Exception:
        has_upstream = False

    try:
        if has_upstream:
            # 已有 upstream，直接 push
            push_infos = repo.remotes.origin.push()
        else:
            # 无 upstream，推送并建立追踪关系（git push -u origin <branch>）
            push_infos = repo.remotes.origin.push(
                refspec=f"{branch}:{branch}",
                set_upstream=True,
            )

        # GitPython 在某些错误下不抛异常，需检查 flags
        errors = []
        for info in push_infos:
            if info.flags & info.ERROR:
                errors.append(info.summary.strip())
        if errors:
            return False, "; ".join(errors)

        return True, ""

    except git.exc.GitCommandError as e:
        err = str(e)
        if "rejected" in err:
            return False, "存在冲突，请先执行 pull"
        if "no upstream" in err or "has no upstream" in err:
            # 理论上已被上面的 set_upstream 处理，保底兜底
            return False, f"分支 '{branch}' 无远端追踪分支，且自动设置 upstream 失败: {e}"
        return False, str(e)
