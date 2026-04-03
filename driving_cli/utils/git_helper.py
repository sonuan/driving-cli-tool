"""Git 辅助模块 - 使用 GitPython 封装 Git 操作"""

from pathlib import Path
from typing import Union

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
