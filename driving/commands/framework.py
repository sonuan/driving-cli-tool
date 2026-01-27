"""框架仓库管理命令"""

import json
from pathlib import Path

import click
import git
from rich.console import Console
from rich.table import Table

from driving.models.framework import get_framework_by_name
from driving.utils.config import (
    check_environment,
    get_all_gitlist_files,
    get_driving_dir,
    get_framework_base_dir,
    get_gitlist_file,
    is_local_mode,
)
from driving.utils.git_helper import clone_repository, find_git_root, is_local_framework
from driving.utils.logger import log_error, log_info, log_success


def load_all_frameworks() -> list[dict]:
    """加载所有 gitlist.json 文件中的框架配置

    Returns:
        list[dict]: 所有框架配置列表

    Raises:
        click.Abort: 如果没有找到任何配置文件或解析失败
    """
    gitlist_files = get_all_gitlist_files()

    if not gitlist_files:
        log_error("未找到任何 gitlist.json 配置文件")
        raise click.Abort()

    all_frameworks = []
    for gitlist_file in gitlist_files:
        try:
            with open(gitlist_file, "r", encoding="utf-8") as f:
                frameworks = json.load(f)
                # 跳过模板条目
                frameworks = [fw for fw in frameworks if fw.get("name") != "框架名称"]
                all_frameworks.extend(frameworks)
        except json.JSONDecodeError as e:
            log_error(f"解析配置文件 {gitlist_file} 失败: {e}")
            continue

    if not all_frameworks:
        log_error("未找到任何框架配置")
        raise click.Abort()

    return all_frameworks


def find_framework_by_name(framework_name: str) -> tuple[dict, Path]:
    """在所有 gitlist.json 文件中查找指定框架

    Args:
        framework_name: 框架名称

    Returns:
        tuple[dict, Path]: (框架配置, 所在的 gitlist.json 文件路径)

    Raises:
        click.Abort: 如果未找到框架
    """
    gitlist_files = get_all_gitlist_files()

    for gitlist_file in gitlist_files:
        try:
            with open(gitlist_file, "r", encoding="utf-8") as f:
                frameworks = json.load(f)
                for fw in frameworks:
                    if fw.get("name") == framework_name:
                        return fw, gitlist_file
        except json.JSONDecodeError:
            continue

    log_error(f"未找到框架 '{framework_name}'")
    raise click.Abort()


@click.command(name="git-list")
@click.argument("framework_name", required=False)
@click.option("--json", "output_json", is_flag=True, help="以 JSON 格式输出")
def git_list(framework_name: str = None, output_json: bool = False):
    """显示可用的框架仓库列表

    读取并显示所有 gitlist.json 中配置的框架仓库信息。

    标准模式：读取 .driving/ai-docs-local/gitlist.json 和 .driving/ai-docs/gitlist.json
    本地模式：读取 ai-docs-local/gitlist.json 和 ai-docs/gitlist.json

    Args:
        framework_name: 框架名称（可选），如果指定则只显示该框架的仓库（精确匹配）
        output_json: 是否以 JSON 格式输出
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        local_mode = is_local_mode()

        # 加载所有框架配置
        all_frameworks = load_all_frameworks()

        # 如果指定了框架名，进行精确匹配并处理 extends
        if framework_name:
            # 精确匹配框架
            matched_framework = None
            for fw in all_frameworks:
                if fw.get("name", "") == framework_name:
                    matched_framework = fw
                    break

            if not matched_framework:
                log_error(f"未找到框架 '{framework_name}'")
                raise click.Abort()

            # 初始化结果列表，包含主框架
            frameworks = [matched_framework]

            # 处理 extends 字段
            if "extends" in matched_framework and matched_framework["extends"]:
                for extend_name in matched_framework["extends"]:
                    # 查找扩展框架
                    for fw in all_frameworks:
                        if fw.get("name", "") == extend_name:
                            frameworks.append(fw)
                            break
        else:
            frameworks = all_frameworks

        # 如果指定了 JSON 输出
        if output_json:
            framework_base_dir = get_framework_base_dir()

            # 处理 sources 字段，拼接完整路径
            processed_frameworks = []
            for fw in frameworks:
                fw_copy = fw.copy()
                if "sources" in fw_copy and fw_copy["sources"]:
                    # 检查是否为本地项目
                    if is_local_framework(fw_copy):
                        # 本地项目：使用当前项目根目录
                        try:
                            project_root = find_git_root()
                            full_path_sources = []
                            for source in fw_copy["sources"]:
                                full_path = f"{project_root}/{source}"
                                full_path_sources.append(full_path)
                            fw_copy["sources"] = full_path_sources
                        except Exception as e:
                            log_error(f"获取本地项目路径失败: {e}")
                    else:
                        # 远程项目：使用 submodules 路径
                        project_name = fw_copy.get("project_name", "")
                        full_path_sources = []
                        for source in fw_copy["sources"]:
                            full_path = f"{framework_base_dir}/{project_name}/{source}"
                            full_path_sources.append(full_path)
                        fw_copy["sources"] = full_path_sources

                processed_frameworks.append(fw_copy)

            output_data = {
                "frameworks": processed_frameworks,
                "install_path": str(framework_base_dir),
                "mode": "local" if local_mode else "standard",
            }
            print(json.dumps(output_data, ensure_ascii=False, indent=2))
            return

        # 使用 Rich 创建表格
        title = f"框架 '{framework_name}' 的仓库列表" if framework_name else "可用框架列表"
        table = Table(title=title)
        table.add_column("框架名称", style="cyan", no_wrap=True)
        table.add_column("项目名", style="green")
        table.add_column("URL", style="blue")
        table.add_column("分支", style="magenta")
        table.add_column("描述", style="yellow")
        table.add_column("创建者", style="white")
        table.add_column("日期", style="white")

        for fw in frameworks:
            table.add_row(
                fw.get("name", ""),
                fw.get("project_name", ""),
                fw.get("url", ""),
                fw.get("branch", "-"),
                fw.get("description", ""),
                fw.get("creator", ""),
                fw.get("date", ""),
            )

        console = Console()
        console.print(table)

        # 显示存储路径信息
        framework_base_dir = get_framework_base_dir()
        if local_mode:
            log_info(f"\n框架将安装到: {framework_base_dir} (本地模式)")
        else:
            log_info(f"\n框架将安装到: {framework_base_dir}")

    except json.JSONDecodeError as e:
        log_error(f"解析配置文件失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"读取框架列表失败: {e}")
        raise click.Abort()


@click.command(name="git-install")
@click.argument("framework_name")
def git_install(framework_name: str):
    """安装指定的框架仓库

    如果本地不存在该仓库，则克隆；如果已存在，则更新。
    如果框架有 extends 字段，会自动安装所有扩展框架。

    标准模式：框架将安装到 .driving/submodules/ 目录
    本地模式：框架将安装到 submodules/ 目录

    Args:
        framework_name: 框架名称
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        gitlist_file = get_gitlist_file()
        framework_base_dir = get_framework_base_dir()
        local_mode = is_local_mode()

        if not local_mode and not driving_dir.exists():
            log_error(f"目录 {driving_dir} 不存在")
            log_error("请先执行 'driving install' 命令添加 driving submodule")
            raise click.Abort()

        # 加载所有框架配置
        all_frameworks = load_all_frameworks()

        # 精确匹配主框架
        main_framework = None
        for fw in all_frameworks:
            if fw.get("name", "") == framework_name:
                main_framework = fw
                break

        if not main_framework:
            log_error(f"框架 '{framework_name}' 不存在，请使用 'driving git-list' 查看可用框架")
            raise click.Abort()

        # 收集所有需要安装的框架（包括主框架和扩展框架）
        frameworks_to_install = [main_framework]

        # 处理 extends 字段
        if "extends" in main_framework and main_framework["extends"]:
            log_info(f"检测到扩展框架: {', '.join(main_framework['extends'])}")
            for extend_name in main_framework["extends"]:
                # 查找扩展框架
                for fw in all_frameworks:
                    if fw.get("name", "") == extend_name:
                        frameworks_to_install.append(fw)
                        break

        # 确保 submodules 目录存在
        framework_base_dir.mkdir(parents=True, exist_ok=True)

        # 逐个安装框架
        installed_count = 0
        skipped_count = 0
        for framework in frameworks_to_install:
            framework_display_name = framework.get("name", "")

            log_info(f"\n{'='*50}")
            log_info(f"正在处理框架: {framework_display_name}")
            log_info(f"{'='*50}")

            # 检查是否为本地项目
            if is_local_framework(framework):
                log_info(f"检测到本地项目配置，跳过安装")
                log_info(f"源码路径: {', '.join(framework.get('sources', []))}")
                skipped_count += 1
                continue

            repo_path = framework_base_dir / framework["project_name"]
            branch = framework.get("branch")

            if repo_path.exists():
                log_info(f"仓库已存在，正在更新...")
                repo = git.Repo(repo_path)

                # 如果配置了分支，先切换到指定分支
                if branch:
                    try:
                        repo.git.checkout(branch)
                        log_info(f"已切换到分支: {branch}")
                    except git.exc.GitCommandError:
                        log_info(f"分支 {branch} 不存在，保持当前分支")

                repo.remotes.origin.pull()
                log_success(f"✓ {framework_display_name} 更新成功！")
            else:
                if branch:
                    log_info(f"正在克隆仓库到 {repo_path} (分支: {branch})...")
                else:
                    log_info(f"正在克隆仓库到 {repo_path}...")
                clone_repository(framework["url"], repo_path, branch)
                log_success(f"✓ {framework_display_name} 安装成功！")

            log_info(f"框架路径: {repo_path}")
            if branch:
                log_info(f"分支: {branch}")

            installed_count += 1

        # 显示总结信息
        log_info(f"\n{'='*50}")
        if skipped_count > 0:
            log_success(
                f"共安装/更新了 {installed_count} 个框架，跳过了 {skipped_count} 个本地项目"
            )
        else:
            log_success(f"共安装/更新了 {installed_count} 个框架")
        log_info(f"{'='*50}")

    except git.exc.GitCommandError as e:
        log_error(f"操作失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"操作失败: {e}")
        raise click.Abort()


@click.command(name="git-checkout")
@click.argument("framework_name")
@click.argument("branch_name")
def git_checkout(framework_name: str, branch_name: str):
    """切换框架仓库的分支

    标准模式：在 .driving/submodules/ 中切换指定框架的分支
    本地模式：在 submodules/ 中切换指定框架的分支

    Args:
        framework_name: 框架名称
        branch_name: 分支名称
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        gitlist_file = get_gitlist_file()
        framework_base_dir = get_framework_base_dir()
        local_mode = is_local_mode()

        if not local_mode and not driving_dir.exists():
            log_error(f"目录 {driving_dir} 不存在")
            log_error("请先执行 'driving install' 命令添加 driving submodule")
            raise click.Abort()

        framework = get_framework_by_name(gitlist_file, framework_name)
        if not framework:
            log_error(f"框架 '{framework_name}' 不存在，请使用 'driving git-list' 查看可用框架")
            raise click.Abort()

        repo_path = framework_base_dir / framework["project_name"]
        if not repo_path.exists():
            log_error(f"仓库不存在，请先执行 'driving git-install {framework_name}'")
            raise click.Abort()

        log_info(f"正在切换到分支 {branch_name}...")
        repo = git.Repo(repo_path)
        repo.git.checkout(branch_name)
        log_success(f"已切换到分支 {branch_name}")

    except git.exc.GitCommandError as e:
        log_error(f"切换分支失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"切换分支失败: {e}")
        raise click.Abort()


@click.command(name="git-pull")
@click.argument("framework_name")
def git_pull(framework_name: str):
    """更新指定的框架仓库

    标准模式：更新 .driving/submodules/ 中的指定框架
    本地模式：更新 submodules/ 中的指定框架

    Args:
        framework_name: 框架名称
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        driving_dir = get_driving_dir()
        gitlist_file = get_gitlist_file()
        framework_base_dir = get_framework_base_dir()
        local_mode = is_local_mode()

        if not local_mode and not driving_dir.exists():
            log_error(f"目录 {driving_dir} 不存在")
            log_error("请先执行 'driving install' 命令添加 driving submodule")
            raise click.Abort()

        framework = get_framework_by_name(gitlist_file, framework_name)
        if not framework:
            log_error(f"框架 '{framework_name}' 不存在，请使用 'driving git-list' 查看可用框架")
            raise click.Abort()

        repo_path = framework_base_dir / framework["project_name"]
        if not repo_path.exists():
            log_error(f"仓库不存在，请先执行 'driving git-install {framework_name}'")
            raise click.Abort()

        log_info("正在更新仓库...")
        repo = git.Repo(repo_path)
        repo.remotes.origin.pull()
        log_success("更新成功！")

    except git.exc.GitCommandError as e:
        log_error(f"更新失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"更新失败: {e}")
        raise click.Abort()


@click.command(name="git-sources")
@click.argument("framework_name")
def git_sources(framework_name: str):
    """获取指定框架的源码路径列表

    返回框架的完整源码路径信息（JSON 格式）。
    如果框架有 extends 字段，会自动合并所有扩展框架的 sources。

    标准模式：读取 .driving/gitlist.json
    本地模式：读取当前目录的 gitlist.json

    Args:
        framework_name: 框架名称（精确匹配）

    示例:
        driving git-sources xstatic
    """
    try:
        # 检查环境配置
        is_valid, error_msg = check_environment()
        if not is_valid:
            log_error(error_msg)
            raise click.Abort()

        gitlist_file = get_gitlist_file()
        local_mode = is_local_mode()

        # 加载所有框架配置
        all_frameworks = load_all_frameworks()

        # 精确匹配框架
        matched_framework = None
        for fw in all_frameworks:
            if fw.get("name", "") == framework_name:
                matched_framework = fw
                break

        if not matched_framework:
            log_error(f"未找到框架 '{framework_name}'")
            raise click.Abort()

        # 初始化结果列表，包含主框架
        matched_frameworks = [matched_framework]

        # 处理 extends 字段
        if "extends" in matched_framework and matched_framework["extends"]:
            for extend_name in matched_framework["extends"]:
                # 查找扩展框架
                for fw in all_frameworks:
                    if fw.get("name", "") == extend_name:
                        matched_frameworks.append(fw)
                        break

        framework_base_dir = get_framework_base_dir()

        # 处理 sources 字段，拼接完整路径
        processed_frameworks = []
        for fw in matched_frameworks:
            fw_copy = fw.copy()
            if "sources" in fw_copy and fw_copy["sources"]:
                # 检查是否为本地项目
                if is_local_framework(fw_copy):
                    # 本地项目：使用当前项目根目录
                    try:
                        project_root = find_git_root()
                        full_path_sources = []
                        for source in fw_copy["sources"]:
                            full_path = f"{project_root}/{source}"
                            full_path_sources.append(full_path)
                        fw_copy["sources"] = full_path_sources
                    except Exception as e:
                        log_error(f"获取本地项目路径失败: {e}")
                        raise click.Abort()
                else:
                    # 远程项目：使用 submodules 路径
                    project_name = fw_copy.get("project_name", "")
                    full_path_sources = []
                    for source in fw_copy["sources"]:
                        full_path = f"{framework_base_dir}/{project_name}/{source}"
                        full_path_sources.append(full_path)
                    fw_copy["sources"] = full_path_sources

            processed_frameworks.append(fw_copy)

        # 如果有多个框架（包含 extends），合并所有 sources 到第一个
        if len(processed_frameworks) > 1:
            first_framework = processed_frameworks[0]
            all_sources = first_framework.get("sources", [])

            # 合并其他框架的 sources
            for fw in processed_frameworks[1:]:
                if "sources" in fw and fw["sources"]:
                    all_sources.extend(fw["sources"])

            # 去重并保持顺序
            seen = set()
            unique_sources = []
            for source in all_sources:
                if source not in seen:
                    seen.add(source)
                    unique_sources.append(source)

            first_framework["sources"] = unique_sources
            result = first_framework
        else:
            result = processed_frameworks[0]

        # 只保留核心字段，移除文档相关字段
        core_fields = [
            "name",
            "description",
            "project_name",
            "url",
            "branch",
            "module",
            "creator",
            "date",
            "sources",
        ]
        filtered_result = {k: v for k, v in result.items() if k in core_fields}

        # 输出 JSON 格式
        print(json.dumps(filtered_result, ensure_ascii=False, indent=2))

    except json.JSONDecodeError as e:
        log_error(f"解析配置文件失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"获取源码列表失败: {e}")
        raise click.Abort()
