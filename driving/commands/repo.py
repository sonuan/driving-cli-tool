"""Driving 仓库管理命令"""

from pathlib import Path

import click
import git

from driving.utils.config import (
    DEFAULT_COMMIT_MESSAGE,
    check_environment,
    get_driving_dir,
    is_local_mode,
)
from driving.utils.logger import log_error, log_info, log_success, log_warning


@click.command()
def pull():
    """更新 Driving 配置

    标准模式：从远程仓库拉取 .driving 目录的最新更新
    本地模式：从远程仓库拉取当前目录的最新更新
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        local_mode = is_local_mode()

        if not driving_dir.exists():
            if local_mode:
                log_error(f"当前目录不存在")
            else:
                log_error(f"目录 {driving_dir} 不存在，请先执行 'driving install' 命令")
            raise click.Abort()

        if local_mode:
            log_info("正在更新当前仓库...")
        else:
            log_info("正在更新 .driving 仓库...")

        repo = git.Repo(driving_dir)

        # 检查是否有未提交的修改
        if repo.is_dirty(untracked_files=True):
            log_warning("检测到未提交的修改：")
            # 显示修改的文件
            if repo.untracked_files:
                log_info("  未跟踪的文件：")
                for file in repo.untracked_files:
                    log_info(f"    - {file}")

            changed_files = [item.a_path for item in repo.index.diff(None)]
            if changed_files:
                log_info("  已修改的文件：")
                for file in changed_files:
                    log_info(f"    - {file}")

            log_info("")
            log_info("请先处理这些修改：")
            log_info("  1. 提交修改: driving commit '提交信息'")
            log_info("  2. 或者放弃修改: cd .driving && git reset --hard && git clean -fd")
            raise click.Abort()

        # 检查是否有远程仓库
        if not repo.remotes:
            log_error("未配置远程仓库")
            raise click.Abort()

        # 检查当前是否在分支上（处理 detached HEAD 状态）
        if repo.head.is_detached:
            log_warning("检测到 detached HEAD 状态，正在切换到 main 分支...")
            try:
                # 尝试切换到 main 分支
                repo.git.checkout("main")
                log_success("已切换到 main 分支")
            except git.exc.GitCommandError:
                # 如果 main 分支不存在，尝试 master 分支
                try:
                    repo.git.checkout("master")
                    log_success("已切换到 master 分支")
                except git.exc.GitCommandError:
                    log_error("无法切换到 main 或 master 分支")
                    log_info("提示：请手动切换到正确的分支：")
                    log_info(f"  cd {driving_dir}")
                    log_info("  git branch -a  # 查看所有分支")
                    log_info("  driving checkout <branch-name>  # 切换到目标分支")
                    raise click.Abort()

        # 获取当前分支名
        current_branch = repo.active_branch.name
        log_info(f"当前分支: {current_branch}")

        # 拉取更新
        repo.remotes.origin.pull(current_branch)
        log_success("更新成功！")

        if not local_mode:
            log_info("提示：如需提交更新，请在项目根目录执行：")
            log_info("  driving commit 'Update by driving'")
    except git.exc.GitCommandError as e:
        error_msg = str(e)
        log_error(f"更新失败: {e}")

        # 提供更详细的错误提示
        if "fatal: couldn't find remote ref" in error_msg:
            log_info("提示：远程分支不存在，请检查 .driving 目录的 git 配置")
        elif "fatal: refusing to merge unrelated histories" in error_msg:
            log_info("提示：尝试使用 --allow-unrelated-histories 选项")
            log_info("  cd .driving && git pull --allow-unrelated-histories")
        elif "error: Your local changes" in error_msg:
            log_info("提示：存在本地修改，请先提交或放弃修改")
        elif "You are not currently on a branch" in error_msg:
            log_info("提示：当前处于 detached HEAD 状态")
            log_info(f"  cd {driving_dir}")
            log_info("  git checkout main  # 或 git checkout master")
        else:
            log_info("提示：可以尝试手动更新：")
            log_info(f"  cd {driving_dir}")
            log_info("  git status  # 查看状态")
            log_info("  git pull    # 手动拉取")

        raise click.Abort()
    except Exception as e:
        log_error(f"更新失败: {e}")
        raise click.Abort()


@click.command()
@click.argument("message", default=DEFAULT_COMMIT_MESSAGE)
def commit(message: str):
    """提交 Driving 配置的修改

    标准模式：将 .driving 目录中的修改提交到本地仓库
    本地模式：将当前目录中的修改提交到本地仓库

    Args:
        message: 提交信息，默认为 'update by driving'
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        local_mode = is_local_mode()

        if not driving_dir.exists():
            if local_mode:
                log_error(f"当前目录不存在")
            else:
                log_error(f"目录 {driving_dir} 不存在，请先执行 'driving install' 命令")
            raise click.Abort()

        if local_mode:
            log_info("正在提交当前目录的修改...")
        else:
            log_info("正在提交 .driving 的修改...")

        repo = git.Repo(driving_dir)
        repo.git.add(A=True)
        repo.index.commit(message)
        log_success(f"提交成功: {message}")
        log_info("提示：如需推送到远程，请执行 'driving push'")
    except git.exc.GitCommandError as e:
        log_error(f"提交失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"提交失败: {e}")
        raise click.Abort()


@click.command()
def push():
    """推送 Driving 配置到远程仓库

    标准模式：将 .driving 目录的本地提交推送到远程仓库
    本地模式：将当前目录的本地提交推送到远程仓库
    如果遇到冲突，需要先执行 'driving pull' 并解决冲突
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        local_mode = is_local_mode()

        if not driving_dir.exists():
            if local_mode:
                log_error(f"当前目录不存在")
            else:
                log_error(f"目录 {driving_dir} 不存在，请先执行 'driving install' 命令")
            raise click.Abort()

        if local_mode:
            log_info("正在推送到远程仓库...")
        else:
            log_info("正在推送到远程仓库...")

        repo = git.Repo(driving_dir)
        repo.remotes.origin.push()
        log_success("推送成功！")

        if not local_mode:
            log_info("提示：别忘了在项目根目录提交 submodule 的更新：")
            log_info("  driving commit 'Update by driving'")
    except git.exc.GitCommandError as e:
        if "rejected" in str(e):
            log_error("推送失败：存在冲突，请先执行 'driving pull' 并解决冲突")
        else:
            log_error(f"推送失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"推送失败: {e}")
        raise click.Abort()
