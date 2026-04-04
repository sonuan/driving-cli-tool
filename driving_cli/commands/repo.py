"""Repo 子命令组 - 多仓库管理命令

提供 driving repo <subcommand> 系列命令，用于安装、列出、卸载仓库，
以及对远程仓库执行 git pull/commit/push 操作。
"""

from pathlib import Path
from typing import Optional

import click
import git

from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.git_helper import find_git_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning
from driving_cli.utils.validators import (
    infer_repo_name_from_url,
    validate_git_url,
    validate_repo_name,
)


@click.group(name="repo")
def repo_group():
    """AI Coding 规范仓库管理（安装、列出、卸载、git 操作）

    支持远程仓库（git submodule）和本地仓库（软链接或普通目录）。

    示例：
        driving repo install --url https://github.com/org/repo
        driving repo install --local /path/to/local
        driving repo list
        driving repo uninstall my-repo
        driving repo pull
        driving repo push
    """
    pass


# ==================== repo install ====================

@repo_group.command(name="install")
@click.option("--url", default=None, help="远程 Git 仓库地址")
@click.option("--local", "local_path", default=None, is_flag=False, flag_value="", help="注册本地仓库（可选路径）")
@click.option("--name", "repo_name", default=None, help="自定义仓库名称")
@click.option("--description", "description", default=None, help="仓库描述，用于 AI 关键词匹配")
@click.option("--force", is_flag=True, default=False, help="强制覆盖已存在的同名仓库")
def install(url: Optional[str], local_path: Optional[str], repo_name: Optional[str], description: Optional[str], force: bool):
    """安装仓库

    无参数：读取配置初始化所有未初始化的远程仓库。\n
    --url：将远程 Git 仓库作为 submodule 安装。\n
    --local [path]：注册本地仓库（有路径则创建软链接，无路径则创建普通目录）。\n
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    # 无参数模式：初始化所有未初始化的远程仓库
    if url is None and local_path is None:
        _install_all_uninitialized(config_mgr, project_root)
        return

    # 安装远程仓库
    if url is not None:
        _install_remote(config_mgr, project_root, url, repo_name, force, description)
        return

    # 注册本地仓库（local_path 为 "" 表示 --local 无值，为具体路径表示有值）
    _install_local(config_mgr, project_root, local_path, repo_name, force, description)


def _cleanup_stale_git_modules(git_root: Path, submodule_path: str):
    """清理残留的 .git/modules 数据

    当 submodule 的工作目录不存在，但 .git/modules 中有残留数据时，
    自动清理以避免 git submodule add 报错。

    清理规则：
    - .git/modules/ai-driving 存在但 ai-driving/ 不存在 → 清理整个 modules/ai-driving
    - .git/modules/ai-driving/<name> 存在但 ai-driving/<name>/ 不存在 → 只清理该子目录
    """
    import shutil

    modules_dir = git_root / ".git" / "modules"
    parts = Path(submodule_path).parts  # e.g. ('ai-driving', 'driving')

    # 从最深层往上检查，找到需要清理的最小范围
    for depth in range(len(parts), 0, -1):
        partial_path = Path(*parts[:depth])
        modules_path = modules_dir / partial_path
        work_path = git_root / partial_path

        # 工作目录不存在，或存在但为空（视为未初始化）
        work_dir_empty = not work_path.exists() or (work_path.is_dir() and not any(work_path.iterdir()))
        if modules_path.exists() and work_dir_empty:
            log_warning(f"检测到残留 git modules 数据：{modules_path}，正在清理...")
            shutil.rmtree(modules_path)
            log_info(f"已清理：{modules_path}")
            break  # 清理最小范围后停止


def _install_all_uninitialized(config_mgr: ConfigManager, project_root: Path):
    """无参数 install：初始化所有未初始化的远程仓库"""
    try:
        repos = config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    # 过滤出 remote 类型仓库
    remote_repos = [r for r in repos if r.type == "remote"]

    if not remote_repos:
        log_info("配置中没有远程仓库，无需初始化")
        return

    # 查找 git 根目录
    try:
        git_root = find_git_root(project_root)
    except git.exc.InvalidGitRepositoryError:
        log_error("当前目录不在 Git 仓库中，请先执行 git init")
        raise click.Abort()

    git_repo = git.Repo(git_root)
    initialized_count = 0
    skipped_count = 0

    for repo_cfg in remote_repos:
        repo_dir = project_root / repo_cfg.path
        # 检查目录是否已初始化（非空目录）
        if repo_dir.exists() and any(repo_dir.iterdir()):
            log_info(f"仓库 '{repo_cfg.name}' 已初始化，跳过")
            skipped_count += 1
            continue

        log_info(f"正在初始化仓库 '{repo_cfg.name}'...")

        # 计算相对于 git 根目录的 submodule 路径
        try:
            submodule_path = str((project_root / repo_cfg.path).relative_to(git_root))
        except ValueError:
            submodule_path = repo_cfg.path

        # 优先尝试 update --init（submodule 已在 .gitmodules 中注册的情况）
        # 若失败则降级为 submodule add（首次添加）
        try:
            git_repo.git.submodule("update", "--init", submodule_path)
            log_success(f"仓库 '{repo_cfg.name}' 初始化成功")
            initialized_count += 1
        except git.exc.GitCommandError:
            # update --init 失败，说明 submodule 尚未注册，改用 add
            if not repo_cfg.url:
                log_error(f"仓库 '{repo_cfg.name}' 缺少 URL，无法添加 submodule")
                continue
            # 清理残留的 .git/modules 数据（目录不存在但 git modules 数据残留）
            _cleanup_stale_git_modules(git_root, submodule_path)
            try:
                # 确保父目录存在
                (git_root / submodule_path).parent.mkdir(parents=True, exist_ok=True)
                git_repo.git.submodule("add", repo_cfg.url, submodule_path)
                log_success(f"仓库 '{repo_cfg.name}' 添加并初始化成功")
                initialized_count += 1
            except git.exc.GitCommandError as e:
                log_error(f"添加仓库 '{repo_cfg.name}' 失败: {e}")

    log_info(f"完成：初始化 {initialized_count} 个，跳过 {skipped_count} 个")


def _install_remote(config_mgr: ConfigManager, project_root: Path, url: str, repo_name: Optional[str], force: bool, description: Optional[str] = None):
    """安装远程 Git 仓库（submodule）"""
    # 校验 Git URL 格式
    if not validate_git_url(url):
        log_error(f"Git URL 格式不合法：{url}")
        raise click.Abort()

    # 推断或校验仓库名称
    if repo_name is None:
        repo_name = infer_repo_name_from_url(url)
        log_info(f"自动推断仓库名称：{repo_name}")
    else:
        if not validate_repo_name(repo_name):
            log_error("仓库名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
            raise click.Abort()

    # 检查名称是否已存在
    existing = config_mgr.get_repo(repo_name)
    if existing is not None:
        if not force:
            log_error(f"仓库 '{repo_name}' 已存在，使用 --force 覆盖")
            raise click.Abort()
        log_warning(f"强制覆盖已存在的仓库 '{repo_name}'")
        try:
            config_mgr.remove_repo(repo_name)
        except ValueError:
            pass

    # 查找 git 根目录
    try:
        git_root = find_git_root(project_root)
    except git.exc.InvalidGitRepositoryError:
        log_error("当前目录不在 Git 仓库中，请先执行 git init")
        raise click.Abort()

    git_repo = git.Repo(git_root)
    install_path = f"ai-driving/{repo_name}"
    abs_install_path = project_root / "ai-driving" / repo_name

    # 计算相对于 git 根目录的路径（submodule 路径需相对于 git 根目录）
    try:
        rel_to_git = (project_root / "ai-driving" / repo_name).relative_to(git_root)
        submodule_path = str(rel_to_git)
    except ValueError:
        submodule_path = install_path

    log_info(f"正在添加远程仓库 '{repo_name}'...")
    log_info(f"仓库地址：{url}")

    try:
        git_repo.create_submodule(submodule_path, submodule_path, url=url)
    except git.exc.GitCommandError as e:
        log_error(f"添加 submodule 失败: {e}")
        raise click.Abort()

    # 写入配置
    repo_cfg = RepoConfig(
        name=repo_name,
        type="remote",
        url=url,
        path=install_path,
        local_path=None,
        description=description,
    )
    try:
        config_mgr.add_repo(repo_cfg)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"远程仓库 '{repo_name}' 安装成功！")
    log_info(f"安装路径：{install_path}")
    log_info("下一步：")
    log_info(f"  git add .gitmodules {submodule_path}")
    log_info(f"  git commit -m 'Add repo {repo_name}'")


def _install_local(config_mgr: ConfigManager, project_root: Path, local_path: str, repo_name: Optional[str], force: bool, description: Optional[str] = None):
    """注册本地仓库（软链接或普通目录）"""
    # 确定仓库名称
    if repo_name is None:
        if local_path:
            # 从路径推断名称
            repo_name = Path(local_path).name
            # 清理非法字符
            import re
            repo_name = re.sub(r'[^a-zA-Z0-9_-]', '-', repo_name).strip('-')
            if not repo_name or not validate_repo_name(repo_name):
                repo_name = "local"
            log_info(f"自动推断仓库名称：{repo_name}")
        else:
            log_error("注册本地仓库时，请通过 --name 指定仓库名称，或提供本地路径")
            raise click.Abort()

    if not validate_repo_name(repo_name):
        log_error("仓库名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
        raise click.Abort()

    # 检查名称是否已存在
    existing = config_mgr.get_repo(repo_name)
    if existing is not None:
        if not force:
            log_error(f"仓库 '{repo_name}' 已存在，使用 --force 覆盖")
            raise click.Abort()
        log_warning(f"强制覆盖已存在的仓库 '{repo_name}'")
        try:
            config_mgr.remove_repo(repo_name)
        except ValueError:
            pass

    install_dir = project_root / "ai-driving" / repo_name
    install_path = f"ai-driving/{repo_name}"

    if local_path:
        # 有路径：验证路径存在，创建软链接
        src_path = Path(local_path).resolve()
        if not src_path.exists():
            log_error(f"本地路径不存在：{local_path}")
            raise click.Abort()

        # 如果目标已存在，先删除
        if install_dir.exists() or install_dir.is_symlink():
            if install_dir.is_symlink():
                install_dir.unlink()
            else:
                import shutil
                shutil.rmtree(install_dir)

        # 确保父目录存在
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.symlink_to(src_path)
        log_success(f"已创建软链接：{install_path} → {src_path}")
        stored_local_path = str(src_path)
    else:
        # 无路径：创建普通目录
        install_dir.mkdir(parents=True, exist_ok=True)
        log_success(f"已创建本地仓库目录：{install_path}")
        stored_local_path = None

    # 写入配置
    repo_cfg = RepoConfig(
        name=repo_name,
        type="local",
        url=None,
        path=install_path,
        local_path=stored_local_path,
        description=description,
    )
    try:
        config_mgr.add_repo(repo_cfg)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"本地仓库 '{repo_name}' 注册成功！")


# ==================== repo list ====================

@repo_group.command(name="list")
@click.option("--check", is_flag=True, default=False, help="联网检查每个 remote 仓库是否有可用更新，输出 hasNewVersion 字段")
def repo_list(check: bool):
    """查看已安装的仓库列表（JSON 格式输出）"""
    import json as _json
    import subprocess as _sp
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    try:
        repos = config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

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
            # 读取仓库当前版本（commit hash）
            if is_init:
                try:
                    version = _sp.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=str(repo_dir),
                        stderr=_sp.DEVNULL,
                        text=True,
                    ).strip()
                    entry["version"] = version
                except Exception:
                    entry["version"] = "unknown"
                # --check: 联网对比远端
                if check:
                    try:
                        _sp.run(
                            ["git", "fetch", "--quiet"],
                            cwd=str(repo_dir),
                            stderr=_sp.DEVNULL,
                            timeout=10,
                        )
                        local = _sp.check_output(
                            ["git", "rev-parse", "HEAD"],
                            cwd=str(repo_dir), stderr=_sp.DEVNULL, text=True,
                        ).strip()
                        remote = None
                        for ref in ("@{u}", "origin/HEAD", "origin/main", "origin/master"):
                            try:
                                remote = _sp.check_output(
                                    ["git", "rev-parse", ref],
                                    cwd=str(repo_dir), stderr=_sp.DEVNULL, text=True,
                                ).strip()
                                break
                            except Exception:
                                continue
                        entry["hasNewVersion"] = (local != remote) if remote else None
                    except Exception:
                        entry["hasNewVersion"] = None
            else:
                entry["version"] = None
                if check:
                    entry["hasNewVersion"] = None
        elif repo.local_path:
            entry["local_path"] = repo.local_path
        result.append(entry)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


# ==================== repo uninstall ====================

@repo_group.command(name="uninstall")
@click.argument("repo_name")
def uninstall(repo_name: str):
    """卸载指定仓库

    移除远程仓库的 git submodule 或本地仓库的软链接/目录，并更新配置。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    # 查找仓库配置
    repo_cfg = config_mgr.get_repo(repo_name)
    if repo_cfg is None:
        log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
        raise click.Abort()

    repo_dir = project_root / repo_cfg.path

    if repo_cfg.type == "remote":
        # 移除 git submodule
        try:
            git_root = find_git_root(project_root)
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中")
            raise click.Abort()

        git_repo = git.Repo(git_root)

        # 计算相对于 git 根目录的 submodule 路径
        try:
            submodule_path = str((project_root / repo_cfg.path).relative_to(git_root))
        except ValueError:
            submodule_path = repo_cfg.path

        # 查找并移除 submodule
        submodule = None
        for sm in git_repo.submodules:
            if sm.path == submodule_path:
                submodule = sm
                break

        if submodule:
            log_info(f"正在移除 submodule '{repo_name}'...")
            try:
                submodule.remove()
                log_success(f"submodule '{repo_name}' 已移除")
            except Exception as e:
                log_warning(f"移除 submodule 时出现警告: {e}")
                # 尝试手动清理目录
                if repo_dir.exists():
                    import shutil
                    shutil.rmtree(repo_dir)
        else:
            log_warning(f"未找到 submodule '{submodule_path}'，尝试直接删除目录")
            if repo_dir.exists():
                import shutil
                shutil.rmtree(repo_dir)
                log_info(f"已删除目录：{repo_cfg.path}")

    elif repo_cfg.type == "local":
        # 移除软链接或目录
        if repo_dir.is_symlink():
            repo_dir.unlink()
            log_success(f"已移除软链接：{repo_cfg.path}")
        elif repo_dir.exists():
            import shutil
            shutil.rmtree(repo_dir)
            log_success(f"已删除目录：{repo_cfg.path}")
        else:
            log_warning(f"目录不存在，仅从配置中移除：{repo_cfg.path}")

    # 从配置中移除
    try:
        config_mgr.remove_repo(repo_name)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"仓库 '{repo_name}' 已卸载")


# ==================== repo pull ====================

@repo_group.command(name="pull")
@click.argument("repo_name", required=False, default=None)
def pull(repo_name: Optional[str]):
    """从远程拉取更新

    指定仓库名则只对该仓库执行；不指定则对所有 remote 仓库执行。
    local 类型仓库会跳过并给出提示。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    repos = _resolve_repos(config_mgr, repo_name, operation="pull")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 pull 操作")
            continue
        _git_pull(repo_cfg, project_root, config_mgr)


def _git_pull(repo_cfg: RepoConfig, project_root: Path, config_mgr: ConfigManager = None):
    """对指定远程仓库执行 git pull"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        log_info("请先执行 'driving repo install' 初始化仓库")
        return

    log_info(f"正在拉取仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if repo.is_dirty(untracked_files=True):
            log_warning(f"仓库 '{repo_cfg.name}' 存在未提交的修改，请先提交后再拉取")
            return
        if not repo.remotes:
            log_error(f"仓库 '{repo_cfg.name}' 未配置远程仓库")
            return
        # 处理 detached HEAD
        if repo.head.is_detached:
            log_warning(f"仓库 '{repo_cfg.name}' 处于 detached HEAD 状态，尝试切换到 main/master")
            for branch in ("main", "master"):
                try:
                    repo.git.checkout(branch)
                    break
                except git.exc.GitCommandError:
                    continue
            else:
                log_error(f"无法切换分支，请手动处理仓库 '{repo_cfg.name}'")
                return

        current_branch = repo.active_branch.name
        repo.remotes.origin.pull(current_branch)
        log_success(f"仓库 '{repo_cfg.name}' 拉取成功")
        # 写入最新 commit hash 到 config
        if config_mgr is not None:
            try:
                import subprocess as _sp
                new_version = _sp.check_output(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    cwd=str(repo_dir), stderr=_sp.DEVNULL, text=True,
                ).strip()
                repo_cfg.version = new_version
                config_mgr.update_repo(repo_cfg)
            except Exception:
                pass
    except git.exc.GitCommandError as e:
        log_error(f"仓库 '{repo_cfg.name}' 拉取失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 拉取失败: {e}")


# ==================== repo commit ====================

@repo_group.command(name="commit")
@click.argument("repo_name", required=False, default=None)
@click.argument("message", required=False, default=None)
def commit(repo_name: Optional[str], message: Optional[str]):
    """提交仓库修改

    指定仓库名则只对该仓库执行；不指定则对所有有未提交修改的 remote 仓库执行。
    local 类型仓库会跳过并给出提示。

    示例：
        driving repo commit my-repo "fix: update config"
        driving repo commit "fix: update all"
        driving repo commit
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    # 判断第一个参数是仓库名还是提交信息
    # 如果 repo_name 不是已知仓库名，则视为提交信息
    actual_repo_name = repo_name
    actual_message = message

    if repo_name is not None:
        existing = config_mgr.get_repo(repo_name)
        if existing is None:
            # repo_name 不是仓库名，视为提交信息
            actual_message = repo_name
            actual_repo_name = None

    # 获取默认提交信息
    if actual_message is None:
        try:
            cfg = config_mgr.load()
            actual_message = cfg.default_commit_message
        except ValueError:
            actual_message = "update by driving"

    repos = _resolve_repos(config_mgr, actual_repo_name, operation="commit")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 commit 操作")
            continue
        _git_commit(repo_cfg, project_root, actual_message)


def _git_commit(repo_cfg: RepoConfig, project_root: Path, message: str):
    """对指定远程仓库执行 git commit"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        return

    log_info(f"正在提交仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if not repo.is_dirty(untracked_files=True):
            log_info(f"仓库 '{repo_cfg.name}' 没有需要提交的修改，跳过")
            return
        repo.git.add(A=True)
        repo.index.commit(message)
        log_success(f"仓库 '{repo_cfg.name}' 提交成功：{message}")
    except git.exc.GitCommandError as e:
        log_error(f"仓库 '{repo_cfg.name}' 提交失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 提交失败: {e}")


# ==================== repo push ====================

@repo_group.command(name="push")
@click.argument("repo_name", required=False, default=None)
def push(repo_name: Optional[str]):
    """推送仓库到远程

    指定仓库名则只对该仓库执行；不指定则对所有 remote 仓库执行。
    local 类型仓库会跳过并给出提示。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    repos = _resolve_repos(config_mgr, repo_name, operation="push")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 push 操作")
            continue
        _git_push(repo_cfg, project_root)


def _git_push(repo_cfg: RepoConfig, project_root: Path):
    """对指定远程仓库执行 git push"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        return

    log_info(f"正在推送仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if not repo.remotes:
            log_error(f"仓库 '{repo_cfg.name}' 未配置远程仓库")
            return
        repo.remotes.origin.push()
        log_success(f"仓库 '{repo_cfg.name}' 推送成功")
    except git.exc.GitCommandError as e:
        if "rejected" in str(e):
            log_error(f"仓库 '{repo_cfg.name}' 推送失败：存在冲突，请先执行 pull")
        else:
            log_error(f"仓库 '{repo_cfg.name}' 推送失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 推送失败: {e}")


# ==================== 辅助函数 ====================

def _resolve_repos(config_mgr: ConfigManager, repo_name: Optional[str], operation: str):
    """解析要操作的仓库列表

    若指定了 repo_name，返回该仓库（不存在则报错返回 None）。
    若未指定，返回所有仓库（pull/push/commit 时包含 local，由调用方跳过）。

    Returns:
        list[RepoConfig] 或 None（出错时）
    """
    try:
        if repo_name is not None:
            repo_cfg = config_mgr.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
                return None
            return [repo_cfg]
        else:
            return config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        return None
