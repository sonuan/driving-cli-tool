"""框架仓库管理命令

提供 `driving framework` 子命令组，支持多仓库框架管理。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import git
from rich.console import Console
from rich.table import Table

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.git_helper import clone_repository, find_git_root, is_local_framework
from driving_cli.utils.logger import log_error, log_info, log_success


def _get_config_manager() -> ConfigManager:
    """获取 ConfigManager 实例"""
    return ConfigManager(find_project_root())


def _load_all_frameworks_with_repo(config_manager: ConfigManager) -> list[dict]:
    """从所有仓库的 gitlist.json 加载框架，并附加 repo_name 字段

    Args:
        config_manager: ConfigManager 实例

    Returns:
        list[dict]: 每个框架 dict 包含额外的 _repo_name 字段

    Raises:
        click.Abort: 未找到任何配置文件或框架时
    """
    gitlist_files = config_manager.get_all_gitlist_files()

    if not gitlist_files:
        log_error("未找到任何 gitlist.json 配置文件")
        raise click.Abort()

    all_frameworks = []
    for repo_name, gitlist_path in gitlist_files:
        try:
            with open(gitlist_path, "r", encoding="utf-8") as f:
                frameworks = json.load(f)
            # 跳过模板条目
            frameworks = [fw for fw in frameworks if fw.get("name") != "框架名称"]
            # 附加来源仓库名称
            for fw in frameworks:
                fw["_repo_name"] = repo_name
            all_frameworks.extend(frameworks)
        except json.JSONDecodeError as e:
            log_error(f"解析配置文件 {gitlist_path} 失败: {e}")
            continue

    if not all_frameworks:
        log_error("未找到任何框架配置")
        raise click.Abort()

    return all_frameworks


def _resolve_framework_name(framework_name: str, all_frameworks: list[dict]) -> Tuple[dict, str]:
    """解析框架名称，支持 <repo-name>/<framework-name> 格式

    Args:
        framework_name: 框架名称，可以是 "name" 或 "repo/name" 格式
        all_frameworks: 所有框架列表（含 _repo_name 字段）

    Returns:
        Tuple[dict, str]: (框架配置, 仓库名称)

    Raises:
        click.Abort: 未找到框架或存在同名冲突时
    """
    # 解析 <repo-name>/<framework-name> 格式
    if "/" in framework_name:
        parts = framework_name.split("/", 1)
        repo_name, fw_name = parts[0], parts[1]
        for fw in all_frameworks:
            if fw.get("name") == fw_name and fw.get("_repo_name") == repo_name:
                return fw, repo_name
        log_error(f"未找到框架 '{fw_name}'（仓库：{repo_name}）")
        raise click.Abort()

    # 普通名称查找，检测同名冲突
    matched = [fw for fw in all_frameworks if fw.get("name") == framework_name]

    if not matched:
        log_error(f"未找到框架 '{framework_name}'")
        raise click.Abort()

    if len(matched) > 1:
        # 同名冲突，提示用户使用 <repo-name>/<framework-name> 格式
        repos = [fw["_repo_name"] for fw in matched]
        log_error(f"框架 '{framework_name}' 存在于多个仓库：{', '.join(repos)}")
        log_error(f"请使用 '<repo-name>/{framework_name}' 格式指定具体仓库，例如：")
        for repo in repos:
            log_error(f"  driving framework install {repo}/{framework_name}")
        raise click.Abort()

    fw = matched[0]
    return fw, fw["_repo_name"]


@click.group(name="framework")
def framework_group():
    """框架文档管理

    支持跨多个仓库查找、安装和管理框架。
    """
    pass


@framework_group.command(name="list")
@click.argument("framework_name", required=False)
@click.option("--table", "output_table", is_flag=True, help="以表格格式输出")
@click.option("--json", "output_json", is_flag=True, help="以 JSON 格式输出（默认）")
def framework_list(framework_name: Optional[str] = None, output_table: bool = False, output_json: bool = False):
    """显示可用的框架列表（默认 JSON 格式）

    合并所有已安装仓库的 gitlist.json 并展示完整框架列表，
    同时显示每个框架所属的仓库名称（repo 字段）。

    Args:
        framework_name: 框架名称（可选），如果指定则只显示该框架
        output_table: 是否以表格格式输出
    """
    try:
        config_manager = _get_config_manager()
        all_frameworks = _load_all_frameworks_with_repo(config_manager)

        # 如果指定了框架名，进行精确匹配并处理 extends
        if framework_name:
            main_fw, repo_name = _resolve_framework_name(framework_name, all_frameworks)
            frameworks = [main_fw]

            # 处理 extends 字段
            if "extends" in main_fw and main_fw["extends"]:
                for extend_name in main_fw["extends"]:
                    for fw in all_frameworks:
                        if fw.get("name") == extend_name:
                            frameworks.append(fw)
                            break
        else:
            frameworks = all_frameworks

        # JSON 格式输出（默认）
        if not output_table:
            processed = []
            for fw in frameworks:
                repo_name_for_fw = fw.get("_repo_name", "")
                if framework_name:
                    # 指定了具体框架，输出完整字段
                    fw_copy = {k: v for k, v in fw.items() if not k.startswith("_")}
                    if "sources" in fw_copy and fw_copy["sources"]:
                        if is_local_framework(fw_copy):
                            try:
                                project_root = find_git_root()
                                fw_copy["sources"] = [
                                    f"{project_root}/{s}" for s in fw_copy["sources"]
                                ]
                            except Exception as e:
                                log_error(f"获取本地项目路径失败: {e}")
                        else:
                            base_dir = config_manager.get_framework_base_dir(repo_name_for_fw)
                            project_name = fw_copy.get("project_name", "")
                            fw_copy["sources"] = [
                                f"{base_dir}/{project_name}/{s}" for s in fw_copy["sources"]
                            ]
                    fw_copy["repo"] = repo_name_for_fw
                    processed.append(fw_copy)
                else:
                    # 默认列表，只输出 3 个核心字段
                    processed.append({
                        "name": fw.get("name", ""),
                        "description": fw.get("description", ""),
                        "repo": repo_name_for_fw,
                    })

            output_data = {
                "frameworks": processed,
                "mode": "multi-repo",
            }
            print(json.dumps(output_data, ensure_ascii=False, indent=2))
            return

        # Rich 表格输出
        title = f"框架 '{framework_name}' 的仓库列表" if framework_name else "可用框架列表"
        table = Table(title=title)
        table.add_column("框架名称", style="cyan", no_wrap=True)
        table.add_column("仓库", style="bright_cyan", no_wrap=True)
        table.add_column("项目名", style="green")
        table.add_column("URL", style="blue")
        table.add_column("分支", style="magenta")
        table.add_column("描述", style="yellow")
        table.add_column("创建者", style="white")
        table.add_column("日期", style="white")

        for fw in frameworks:
            table.add_row(
                fw.get("name", ""),
                fw.get("_repo_name", ""),
                fw.get("project_name", ""),
                fw.get("url", ""),
                fw.get("branch", "-"),
                fw.get("description", ""),
                fw.get("creator", ""),
                fw.get("date", ""),
            )

        console = Console()
        console.print(table)

    except json.JSONDecodeError as e:
        log_error(f"解析配置文件失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"读取框架列表失败: {e}")
        raise click.Abort()


@framework_group.command(name="install")
@click.argument("framework_name")
def framework_install(framework_name: str):
    """安装指定的框架仓库

    支持 <repo-name>/<framework-name> 格式指定具体仓库。
    如果本地不存在该仓库，则克隆；如果已存在，则更新。
    如果框架有 extends 字段，会自动安装所有扩展框架。

    框架将安装到对应仓库的 submodules/ 目录。

    Args:
        framework_name: 框架名称，支持 <repo-name>/<framework-name> 格式
    """
    try:
        config_manager = _get_config_manager()
        all_frameworks = _load_all_frameworks_with_repo(config_manager)

        # 解析框架名称（支持 repo/name 格式，处理同名冲突）
        main_framework, repo_name = _resolve_framework_name(framework_name, all_frameworks)

        # 获取对应仓库的框架安装目录
        framework_base_dir = config_manager.get_framework_base_dir(repo_name)

        # 收集所有需要安装的框架（包括主框架和扩展框架）
        frameworks_to_install = [main_framework]

        # 处理 extends 字段
        if "extends" in main_framework and main_framework["extends"]:
            log_info(f"检测到扩展框架: {', '.join(main_framework['extends'])}")
            for extend_name in main_framework["extends"]:
                for fw in all_frameworks:
                    if fw.get("name") == extend_name:
                        frameworks_to_install.append(fw)
                        break

        # 确保 submodules 目录存在
        framework_base_dir.mkdir(parents=True, exist_ok=True)

        # 逐个安装框架
        installed_count = 0
        skipped_count = 0
        for framework in frameworks_to_install:
            fw_display_name = framework.get("name", "")
            fw_repo_name = framework.get("_repo_name", repo_name)
            fw_base_dir = config_manager.get_framework_base_dir(fw_repo_name)

            log_info(f"\n{'='*50}")
            log_info(f"正在处理框架: {fw_display_name}（仓库：{fw_repo_name}）")
            log_info(f"{'='*50}")

            # 检查是否为本地项目
            if is_local_framework(framework):
                log_info("检测到本地项目配置，跳过安装")
                log_info(f"源码路径: {', '.join(framework.get('sources', []))}")
                skipped_count += 1
                continue

            repo_path = fw_base_dir / framework["project_name"]
            branch = framework.get("branch")

            if repo_path.exists():
                log_info("仓库已存在，正在更新...")
                repo = git.Repo(repo_path)
                if branch:
                    try:
                        repo.git.checkout(branch)
                        log_info(f"已切换到分支: {branch}")
                    except git.exc.GitCommandError:
                        log_info(f"分支 {branch} 不存在，保持当前分支")
                repo.remotes.origin.pull()
                log_success(f"✓ {fw_display_name} 更新成功！")
            else:
                if branch:
                    log_info(f"正在克隆仓库到 {repo_path} (分支: {branch})...")
                else:
                    log_info(f"正在克隆仓库到 {repo_path}...")
                clone_repository(framework["url"], repo_path, branch)
                log_success(f"✓ {fw_display_name} 安装成功！")

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


@framework_group.command(name="checkout")
@click.argument("framework_name")
@click.argument("branch_name")
def framework_checkout(framework_name: str, branch_name: str):
    """切换框架仓库的分支

    在对应仓库的 submodules/ 中切换指定框架的分支。

    Args:
        framework_name: 框架名称，支持 <repo-name>/<framework-name> 格式
        branch_name: 分支名称
    """
    try:
        config_manager = _get_config_manager()
        all_frameworks = _load_all_frameworks_with_repo(config_manager)

        framework, repo_name = _resolve_framework_name(framework_name, all_frameworks)
        framework_base_dir = config_manager.get_framework_base_dir(repo_name)

        repo_path = framework_base_dir / framework["project_name"]
        if not repo_path.exists():
            log_error(f"仓库不存在，请先执行 'driving framework install {framework_name}'")
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


@framework_group.command(name="pull")
@click.argument("framework_name")
def framework_pull(framework_name: str):
    """更新指定的框架仓库

    更新对应仓库 submodules/ 中的指定框架。

    Args:
        framework_name: 框架名称，支持 <repo-name>/<framework-name> 格式
    """
    try:
        config_manager = _get_config_manager()
        all_frameworks = _load_all_frameworks_with_repo(config_manager)

        framework, repo_name = _resolve_framework_name(framework_name, all_frameworks)
        framework_base_dir = config_manager.get_framework_base_dir(repo_name)

        repo_path = framework_base_dir / framework["project_name"]
        if not repo_path.exists():
            log_error(f"仓库不存在，请先执行 'driving framework install {framework_name}'")
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


@framework_group.command(name="sources")
@click.argument("framework_name")
def framework_sources(framework_name: str):
    """获取指定框架的源码路径列表

    返回框架的完整源码路径信息（JSON 格式）。
    路径基于对应仓库的 submodules/ 目录。
    如果框架有 extends 字段，会自动合并所有扩展框架的 sources。

    Args:
        framework_name: 框架名称，支持 <repo-name>/<framework-name> 格式
    """
    try:
        config_manager = _get_config_manager()
        all_frameworks = _load_all_frameworks_with_repo(config_manager)

        main_fw, repo_name = _resolve_framework_name(framework_name, all_frameworks)

        # 收集主框架和扩展框架
        matched_frameworks = [main_fw]
        if "extends" in main_fw and main_fw["extends"]:
            for extend_name in main_fw["extends"]:
                for fw in all_frameworks:
                    if fw.get("name") == extend_name:
                        matched_frameworks.append(fw)
                        break

        # 处理 sources 字段，拼接完整路径
        processed_frameworks = []
        for fw in matched_frameworks:
            fw_copy = {k: v for k, v in fw.items() if not k.startswith("_")}
            fw_repo_name = fw.get("_repo_name", repo_name)
            fw_copy["repo"] = fw_repo_name

            if "sources" in fw_copy and fw_copy["sources"]:
                if is_local_framework(fw_copy):
                    # 本地项目：使用当前项目根目录
                    try:
                        project_root = find_git_root()
                        fw_copy["sources"] = [
                            f"{project_root}/{s}" for s in fw_copy["sources"]
                        ]
                    except Exception as e:
                        log_error(f"获取本地项目路径失败: {e}")
                        raise click.Abort()
                else:
                    # 远程项目：使用对应仓库的 submodules 路径
                    base_dir = config_manager.get_framework_base_dir(fw_repo_name)
                    project_name = fw_copy.get("project_name", "")
                    fw_copy["sources"] = [
                        f"{base_dir}/{project_name}/{s}" for s in fw_copy["sources"]
                    ]

            processed_frameworks.append(fw_copy)

        # 合并多个框架的 sources（处理 extends）
        if len(processed_frameworks) > 1:
            first = processed_frameworks[0]
            all_sources = list(first.get("sources", []))
            for fw in processed_frameworks[1:]:
                all_sources.extend(fw.get("sources", []))
            # 去重保持顺序
            seen = set()
            unique_sources = []
            for s in all_sources:
                if s not in seen:
                    seen.add(s)
                    unique_sources.append(s)
            first["sources"] = unique_sources
            result = first
        else:
            result = processed_frameworks[0]

        # 只保留核心字段
        core_fields = [
            "name", "repo", "description", "project_name", "url",
            "branch", "module", "creator", "date", "sources",
        ]
        result["repo"] = result.pop("_repo_name", repo_name)
        filtered_result = {k: v for k, v in result.items() if k in core_fields}

        print(json.dumps(filtered_result, ensure_ascii=False, indent=2))

    except json.JSONDecodeError as e:
        log_error(f"解析配置文件失败: {e}")
        raise click.Abort()
    except Exception as e:
        log_error(f"获取源码列表失败: {e}")
        raise click.Abort()




def _parse_yaml_frontmatter(file_path: Path) -> Dict[str, str]:
    """解析 Markdown 文件的 YAML front-matter

    Args:
        file_path: Markdown 文件路径

    Returns:
        Dict[str, str]: 解析出的字段字典，解析失败返回空字典
    """
    from driving_cli.utils.yaml_parser import parse_frontmatter

    data = parse_frontmatter(file_path)
    if data is None:
        return {}
    return {k: str(v) if not isinstance(v, str) else v for k, v in data.items()}


def collect_frameworks(keywords: tuple = (), category: Optional[str] = None) -> List[Dict]:
    """收集框架文档元信息，供 framework load 和 driving load 复用。

    不传关键词时，加载所有仓库的框架文档。
    传入关键词时，按 repo.name 精确匹配或 framework.name/description 模糊匹配（不区分大小写，取并集）。
    传入 category 时，按 category 字段过滤（不区分大小写）。

    Args:
        keywords: 过滤关键词，支持仓库名或框架名
        category: 按 category 字段过滤，不区分大小写

    Returns:
        List[Dict]: 框架列表，每项包含 name、description、category、path
    """
    config_manager = _get_config_manager()
    repos = config_manager.get_all_repos()

    if not repos:
        return []

    # 收集所有仓库的框架文档，按 repo_name 分组
    all_by_repo: Dict[str, List[Dict]] = {}
    for repo in repos:
        frameworks_dir = config_manager.get_repo_dir(repo.name) / "frameworks"
        if not frameworks_dir.exists():
            continue

        repo_results: List[Dict] = []
        for fw_dir in sorted(frameworks_dir.iterdir()):
            if not fw_dir.is_dir():
                continue
            framework_md = fw_dir / "FRAMEWORK.md"
            if not framework_md.exists():
                continue
            meta = _parse_yaml_frontmatter(framework_md)
            repo_results.append({
                "name": meta.get("name", fw_dir.name),
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
                "path": f"ai-driving/{repo.name}/frameworks/{fw_dir.name}",
            })
        all_by_repo[repo.name] = repo_results

    # 按关键词过滤：repo.name 命中则取整个仓库，framework.name 命中则精确匹配
    results: List[Dict] = []
    seen: set = set()

    def _add(items: List[Dict]) -> None:
        for item in items:
            if item["path"] not in seen:
                seen.add(item["path"])
                results.append(item)

    if not keywords:
        for repo_items in all_by_repo.values():
            _add(repo_items)
    else:
        from driving_cli.utils.match import fuzzy_match_any
        kw_lower = tuple(k.lower() for k in keywords)
        for repo_name, repo_items in all_by_repo.items():
            if repo_name.lower() in kw_lower:
                _add(repo_items)
                continue
            matched = [fw for fw in repo_items
                       if fuzzy_match_any((fw["name"], fw.get("description", "")), keywords)]
            _add(matched)

    if category:
        cat_lower = category.strip().lower()
        results = [fw for fw in results if (fw.get("category") or "").strip().lower() == cat_lower]

    return results


def collect_framework_categories() -> List[Dict]:
    """汇总所有框架的 category 及其描述与数量。

    - category 名称与数量：扫描所有仓库 frameworks/*/FRAMEWORK.md 的 category 字段统计。
    - category 描述：从各仓库 manifest.json 的 categories 注册表读取（[{name, description}]）。

    Returns:
        List[Dict]: [{name, description, count}]，按 name 排序。
    """
    config_manager = _get_config_manager()
    repos = config_manager.get_all_repos()

    # 1. 从框架 frontmatter 统计各 category 数量
    counts: Dict[str, int] = {}
    for fw in collect_frameworks(()):
        cat = (fw.get("category") or "").strip()
        if cat:
            counts[cat] = counts.get(cat, 0) + 1

    # 2. 从各仓库 manifest.json 的 categories 注册表读取描述
    descriptions: Dict[str, str] = {}
    for repo in repos:
        manifest_path = config_manager.get_repo_dir(repo.name) / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for c in (data.get("categories") or []):
            name = (c.get("name") or "").strip()
            if name and name not in descriptions:
                descriptions[name] = c.get("description", "")

    # 3. 合并：注册表声明的 + 框架中实际出现的
    all_names = set(counts) | set(descriptions)
    return [
        {"name": n, "description": descriptions.get(n, ""), "count": counts.get(n, 0)}
        for n in sorted(all_names)
    ]


@framework_group.command(name="load")
@click.option("--category", "category", default=None, help="按 category 过滤（如 ui-component），不区分大小写")
@click.argument("keywords", nargs=-1, required=False)
def framework_load(category: Optional[str] = None, keywords: tuple = ()):
    """加载框架文档元信息

    扫描所有已安装仓库的 frameworks/ 目录，读取每个框架的
    FRAMEWORK.md YAML front-matter，返回 name、description、path。

    不传关键词时，加载所有仓库的框架文档。
    传入关键词时，按 repo.name 或 framework.name 精确匹配（取并集）。
    支持多个关键词：driving framework load driving xstatic

    示例：
        driving framework load
        driving framework load driving
        driving framework load xstatic ximage
        driving framework load driving xstatic
    """
    from driving_cli.utils.match import normalize_keywords
    keywords = normalize_keywords(keywords)

    try:
        results = collect_frameworks(keywords, category=category)
        print(json.dumps({"frameworks": results}, ensure_ascii=False, indent=2))
    except click.Abort:
        raise
    except Exception as e:
        log_error(f"加载框架文档失败: {e}")
        raise click.Abort()


@framework_group.command(name="categories")
def framework_categories():
    """列出所有框架分类及其描述与数量。

    分类名称/数量来自扫描各仓库 frameworks/*/FRAMEWORK.md 的 category 字段；
    分类描述来自各仓库 manifest.json 的 categories 注册表（[{name, description}]）。

    示例：
        driving framework categories
    """
    try:
        results = collect_framework_categories()
        print(json.dumps({"categories": results}, ensure_ascii=False, indent=2))
    except click.Abort:
        raise
    except Exception as e:
        log_error(f"加载框架分类失败: {e}")
        raise click.Abort()
