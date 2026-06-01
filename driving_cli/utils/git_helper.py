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
