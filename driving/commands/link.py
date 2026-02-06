"""Git Submodule 管理命令"""

import os
from pathlib import Path

import click
import git

from driving.utils.config import DRIVING_REPO_URL, is_local_mode, update_env_file
from driving.utils.git_helper import find_git_root
from driving.utils.logger import log_error, log_info, log_success, log_warning


def create_symlinks(current_dir: Path, submodule_path: Path):
    """创建软链接

    Args:
        current_dir: 当前工作目录
        submodule_path: .driving 目录路径
    """
    # 定义需要创建的软链接
    symlinks = [
        ("ai-docs", submodule_path / "ai-docs"),  # 文件夹
    ]

    log_info("正在创建软链接...")

    for link_name, target_path in symlinks:
        link_path = current_dir / link_name

        # 检查目标是否存在
        if not target_path.exists():
            log_warning(f"目标不存在，跳过: {target_path}")
            continue

        # 如果软链接已存在
        if link_path.exists() or link_path.is_symlink():
            # 检查是否已经是正确的软链接
            if link_path.is_symlink() and link_path.resolve() == target_path.resolve():
                log_info(f"软链接已存在: {link_name} -> {target_path.relative_to(current_dir)}")
                continue
            else:
                # 如果是文件/目录或错误的软链接，先删除
                log_warning(f"检测到已存在的 {link_name}，将被替换为软链接")
                if link_path.is_symlink():
                    link_path.unlink()
                elif link_path.is_dir():
                    import shutil

                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()

        # 创建软链接（使用相对路径）
        try:
            relative_target = os.path.relpath(target_path, current_dir)
            os.symlink(relative_target, link_path)
            log_success(f"创建软链接: {link_name} -> {relative_target}")
        except Exception as e:
            log_error(f"创建软链接失败 {link_name}: {e}")


@click.command()
@click.option("--url", default=None, help="自定义 Driving 仓库地址（自动保存到 .env 文件）")
def install(url: str = None):
    """在当前目录添加 driving 作为 Git submodule

    将 driving 仓库作为 Git submodule 添加到当前目录的 .driving 目录。
    这样可以在项目中访问配置和文档，并且可以被 Git 追踪。

    框架仓库将安装到 .driving/submodules/ 目录中。

    参数：
        --url: 自定义 Driving 仓库地址，会自动保存到项目根目录的 .env 文件

    注意：
    - 当前目录必须在 Git 仓库中
    - 如果当前目录存在 gitlist.json 文件，则为本地模式，不需要执行此命令
    - 使用 --url 参数时，会自动将 DRIVING_REPO_URL 保存到 .env 文件，下次无需再指定

    示例：
        driving install
        driving install --url https://github.com/your-org/driving
    """
    try:
        # 确定使用的仓库地址（优先级：命令行参数 > 环境变量）
        repo_url = url if url else DRIVING_REPO_URL

        # 检查是否提供了仓库地址
        if not repo_url:
            log_error("未指定 Driving 仓库地址")
            log_info("请使用以下方式之一指定仓库地址：")
            log_info("  1. 使用 --url 参数：")
            log_info("     driving install --url https://github.com/your-org/driving")
            log_info("  2. 设置环境变量 DRIVING_REPO_URL：")
            log_info("     export DRIVING_REPO_URL=https://github.com/your-org/driving")
            log_info("  3. 在项目根目录创建 .env 文件并添加：")
            log_info("     DRIVING_REPO_URL=https://github.com/your-org/driving")
            raise click.Abort()

        # 检查当前目录是否存在 gitlist.json（本地模式）
        current_dir = Path.cwd()
        if (current_dir / "gitlist.json").exists():
            log_info("检测到当前目录存在 gitlist.json 文件（本地模式）")
            log_info("本地模式下不需要执行 install 命令")
            log_info("可以直接使用 driving git-list、driving git-install 等命令")
            return

        # 检查当前目录是否在 Git 仓库中
        try:
            git_root = find_git_root()
            log_info(f"检测到 Git 仓库根目录: {git_root}")
            log_info(f"将在当前目录安装: {current_dir}")
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中，请先执行 git init")
            raise click.Abort()

        repo = git.Repo(git_root)
        submodule_path = current_dir / ".driving"

        # 计算相对于 Git 仓库根目录的相对路径
        try:
            relative_path = current_dir.relative_to(git_root)
            submodule_relative_path = (
                str(relative_path / ".driving") if str(relative_path) != "." else ".driving"
            )
        except ValueError:
            # 如果当前目录不在 Git 根目录下（理论上不会发生）
            submodule_relative_path = ".driving"

        # 检查 .gitmodules 中是否已配置 .driving submodule
        gitmodules_path = git_root / ".gitmodules"
        submodule_exists_in_config = False

        if gitmodules_path.exists():
            gitmodules_content = gitmodules_path.read_text(encoding="utf-8")
            # 检查是否包含当前路径的 .driving 配置
            if f'[submodule "{submodule_relative_path}"]' in gitmodules_content:
                submodule_exists_in_config = True

        # 检查 .driving 是否已存在
        if submodule_path.exists():
            # 检查是否包含必要的文件（gitlist.json 或 ai-docs 等）
            contents = list(submodule_path.iterdir())
            # 过滤掉 .git、submodules 和 .gitignore
            essential_contents = [
                item
                for item in contents
                if item.name not in [".git", ".DS_Store", "submodules", ".gitignore"]
            ]

            if len(essential_contents) == 0 and submodule_exists_in_config:
                # 目录缺少必要文件且 .gitmodules 中已配置，尝试通过 git submodule update 拉取内容
                log_warning("检测到 .driving 目录缺少必要文件，但 .gitmodules 中已配置")
                log_info("尝试拉取 submodule 内容...")
                try:
                    # 使用 git submodule update --init 拉取内容
                    repo.git.submodule("update", "--init", submodule_relative_path)
                    log_success("成功拉取 .driving submodule 内容！")

                    # 如果使用了自定义 URL，保存到 .env 文件
                    if url:
                        log_info(f"保存自定义仓库地址到 {current_dir}/.env")
                        update_env_file(current_dir, "DRIVING_REPO_URL", url)
                        log_success(f"已将 DRIVING_REPO_URL={url} 保存到 .env 文件")

                    # 创建软链接
                    create_symlinks(current_dir, submodule_path)

                    return
                except git.exc.GitCommandError as e:
                    log_error(f"拉取 submodule 内容失败: {e}")
                    log_info("提示：请检查 .gitmodules 文件中的 URL 配置是否正确")
                    raise click.Abort()
            elif len(essential_contents) == 0 and not submodule_exists_in_config:
                # 目录缺少必要文件但 .gitmodules 中未配置，可能是手动创建的目录
                log_error("当前目录存在 .driving 目录，但缺少必要文件且 .gitmodules 中未配置")
                log_info("请先删除该目录后重试：rm -rf .driving")
                raise click.Abort()
            else:
                # 目录包含必要文件，说明已经正确安装
                # 但仍需检查并创建软链接（处理之前已创建好 .driving 的情况）
                log_info("检测到 .driving 目录已存在")
                
                # 如果使用了自定义 URL，保存到 .env 文件
                if url:
                    log_info(f"保存自定义仓库地址到 {current_dir}/.env")
                    update_env_file(current_dir, "DRIVING_REPO_URL", url)
                    log_success(f"已将 DRIVING_REPO_URL={url} 保存到 .env 文件")
                
                create_symlinks(current_dir, submodule_path)
                log_success(".driving 已就绪！")
                return

        # .driving 目录不存在，检查是否在 .gitmodules 中已配置
        if submodule_exists_in_config:
            log_error(f".gitmodules 中已存在 {submodule_relative_path} 的配置")
            log_info("请先执行以下命令初始化 submodule：")
            log_info(f"  git submodule update --init {submodule_relative_path}")
            raise click.Abort()

        log_info(f"正在添加 driving 作为 Git submodule...")
        log_info(f"仓库地址: {repo_url}")

        # 计算相对于 Git 仓库根目录的相对路径
        try:
            relative_path = current_dir.relative_to(git_root)
            submodule_relative_path = (
                str(relative_path / ".driving") if str(relative_path) != "." else ".driving"
            )
        except ValueError:
            # 如果当前目录不在 Git 根目录下（理论上不会发生）
            submodule_relative_path = ".driving"

        # 添加 submodule
        repo.create_submodule(submodule_relative_path, submodule_relative_path, url=repo_url)

        # 如果使用了自定义 URL，保存到 .env 文件
        if url:
            log_info(f"保存自定义仓库地址到 {current_dir}/.env")
            update_env_file(current_dir, "DRIVING_REPO_URL", url)
            log_success(f"已将 DRIVING_REPO_URL={url} 保存到 .env 文件")

        # 创建 .driving/.gitignore 文件，忽略 submodules 目录
        gitignore_path = submodule_path / ".gitignore"
        gitignore_content = """# 框架仓库目录（本地开发使用，不提交到仓库）
submodules/
"""
        gitignore_path.write_text(gitignore_content, encoding="utf-8")

        log_success("Git submodule 添加成功！")

        # 创建软链接
        create_symlinks(current_dir, submodule_path)

        log_info("")
        log_info("📁 目录结构：")
        log_info(f"  {submodule_relative_path}/              # Driving 配置（Git submodule）")
        log_info(f"  {submodule_relative_path}/submodules/   # 框架仓库（本地，不提交）")
        log_info(f"  ai-docs -> {submodule_relative_path}/ai-docs  # 软链接")
        log_info("")
        log_info("📝 下一步：")
        log_info(f"  1. git add .gitmodules {submodule_relative_path}")
        log_info("  2. git commit -m 'Add driving submodule'")
        log_info("  3. driving git-list  # 查看可用框架")
        log_info("  4. driving git-install <framework-name>  # 安装框架")

    except git.exc.GitCommandError as e:
        log_error(f"添加 Git submodule 失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"添加 Git submodule 失败: {e}")
        raise click.Abort()


@click.command()
def uninstall():
    """从当前目录移除 driving Git submodule

    移除当前目录的 .driving submodule 并清理相关配置。
    注意：这也会删除 .driving/submodules/ 中的所有框架仓库。

    如果当前目录存在 gitlist.json 文件（本地模式），则不需要执行此命令。
    """
    try:
        # 检查当前目录是否存在 gitlist.json（本地模式）
        current_dir = Path.cwd()
        if (current_dir / "gitlist.json").exists():
            log_info("检测到当前目录存在 gitlist.json 文件（本地模式）")
            log_info("本地模式下不需要执行 uninstall 命令")
            return

        # 查找 Git 仓库根目录
        try:
            git_root = find_git_root()
            log_info(f"检测到 Git 仓库根目录: {git_root}")
            log_info(f"将从当前目录移除: {current_dir}")
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中")
            raise click.Abort()

        repo = git.Repo(git_root)
        submodule_path = current_dir / ".driving"

        # 计算相对于 Git 仓库根目录的相对路径
        try:
            relative_path = current_dir.relative_to(git_root)
            submodule_relative_path = (
                str(relative_path / ".driving") if str(relative_path) != "." else ".driving"
            )
        except ValueError:
            submodule_relative_path = ".driving"

        # 检查 .driving submodule 是否存在
        submodule = None
        for sm in repo.submodules:
            if sm.path == submodule_relative_path:
                submodule = sm
                break

        if not submodule:
            log_error(f"当前目录不存在 .driving submodule")
            log_info(f"查找路径: {submodule_relative_path}")
            raise click.Abort()

        log_warning("⚠️  警告：这将删除 .driving 目录及其中的所有框架仓库！")
        log_info("正在移除 driving Git submodule...")

        # 移除 submodule
        submodule.remove()

        log_success("Git submodule 移除成功！")
        log_info("提示：请执行以下命令提交更改：")
        log_info("  git add .gitmodules")
        log_info("  git commit -m 'Remove driving submodule'")

    except git.exc.GitCommandError as e:
        log_error(f"移除 Git submodule 失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"移除 Git submodule 失败: {e}")
        raise click.Abort()
