"""Feature 子命令组

提供 `driving feature list` 命令，
扫描所有已安装仓库的 features/ 目录，支持关键词搜索，以 JSON 格式输出。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_warning

# 精简摘要字段列表（有序）
SUMMARY_FIELDS = ["name", "description", "status", "path", "feature_file", "urls"]

# 完整字段列表（有序）
ALL_FIELDS = [
    "name", "description", "status", "priority",
    "module", "assignee", "tags", "path", "feature_file", "urls",
]


def parse_feature_yaml(feature_md_path: Path) -> Optional[Dict]:
    """解析 FEATURE.md 文件的 YAML frontmatter

    提取所有字段：name、title、description、status、priority、module、assignee、tags、urls。

    Args:
        feature_md_path: FEATURE.md 文件路径

    Returns:
        Dict: 包含所有 frontmatter 字段的字典，缺少 name 字段则返回 None
    """
    from driving_cli.utils.yaml_parser import parse_frontmatter

    try:
        data = parse_frontmatter(feature_md_path, required_fields=["name"])
        if data is None:
            return None

        return {
            "name": str(data.get("name", "")),
            "description": str(data.get("description", "") or ""),
            "status": str(data.get("status", "") or ""),
            "priority": str(data.get("priority", "") or ""),
            "module": str(data.get("module", "") or ""),
            "assignee": str(data.get("assignee", "") or ""),
            "tags": list(data.get("tags") or []),
            "urls": list(data.get("urls") or []),
        }
    except Exception as e:
        log_warning(f"解析 {feature_md_path} 失败: {e}")
        return None


def _resolve_feature_md(feature_dir: Path) -> Optional[Path]:
    """在 feature 目录中按优先级查找可用的 feature 描述文件

    优先级：
    1. FEATURE.md（存在则直接返回）
    2. iOS/ios-feature.md（FEATURE.md 不存在时降级查找）

    Args:
        feature_dir: feature 子目录路径

    Returns:
        Path: 找到的文件路径；None 表示两者均不存在
    """
    feature_md = feature_dir / "FEATURE.md"
    if feature_md.exists():
        return feature_md

    ios_md = feature_dir / "iOS" / "ios-feature.md"
    if ios_md.exists():
        return ios_md

    return None


def scan_features_from_dir(repo_name: str, features_dir: Path, quiet: bool = False) -> List[Dict]:
    """扫描单个仓库的 features/ 目录，返回 feature 列表

    遍历 features_dir 下的所有子目录，每个子目录按优先级查找 feature 描述文件：
    优先 FEATURE.md，不存在时降级查找 iOS/ios-feature.md。
    解析 YAML frontmatter，设置 path 和 repo 字段。

    Args:
        repo_name: 仓库名称
        features_dir: features 目录路径
        quiet: 静默模式，不输出日志

    Returns:
        List[Dict]: feature 列表，每条包含所有 frontmatter 字段及 path、repo
    """
    features = []

    for subdir in sorted(features_dir.iterdir()):
        if not subdir.is_dir():
            continue

        feature_md = _resolve_feature_md(subdir)
        if feature_md is None:
            if not quiet:
                log_warning(f"跳过 {subdir.name}：未找到 FEATURE.md 或 iOS/ios-feature.md 文件")
            continue

        feature_info = parse_feature_yaml(feature_md)
        if feature_info is None:
            if not quiet:
                log_warning(f"跳过 {subdir.name}：{feature_md.name} 缺少 name 字段或解析失败")
            continue

        feature_info["path"] = f"ai-driving/{repo_name}/features/{subdir.name}/"
        feature_info["feature_file"] = "FEATURE.md" if feature_md.name == "FEATURE.md" else f"iOS/{feature_md.name}"
        features.append(feature_info)

        if not quiet:
            log_info(f"发现 feature: {feature_info['name']} (来自仓库 {repo_name})")

    return features


def scan_features_deep(module_name: str, module_dir: Path, repo_path: str, quiet: bool = False) -> List[Dict]:
    """深度扫描模块目录，兼容多层目录结构（如 {年度-季度}/{日期}-{feature}/FEATURE.md）

    收集策略：
    1. 递归查找所有 FEATURE.md，记录其所在目录
    2. 递归查找所有 iOS/ios-feature.md，若其父目录（feature 目录）已有 FEATURE.md 则跳过（FEATURE.md 优先）
    path 字段记录相对于项目 ai-driving 根的完整路径。

    Args:
        module_name: 业务模块名称（如 "family"）
        module_dir: 模块目录绝对路径
        repo_path: 仓库相对路径（如 "ai-driving/aidoc"）
        quiet: 静默模式，不输出日志

    Returns:
        List[Dict]: feature 列表，每条包含所有 frontmatter 字段及 path、repo、quarter
    """
    features = []

    # 收集所有候选 (feature_dir, feature_md_path) 对
    # key = feature_dir，确保同一目录只保留一个条目（FEATURE.md 优先）
    candidates: Dict[Path, Path] = {}

    for feature_md in sorted(module_dir.glob("**/FEATURE.md")):
        candidates[feature_md.parent] = feature_md

    for ios_md in sorted(module_dir.glob("**/iOS/ios-feature.md")):
        # iOS/ios-feature.md 的 feature 目录是其祖父目录（.../feature-dir/iOS/ios-feature.md）
        feature_dir = ios_md.parent.parent
        if feature_dir not in candidates:
            candidates[feature_dir] = ios_md

    for feature_dir, feature_md in sorted(candidates.items()):
        feature_info = parse_feature_yaml(feature_md)
        if feature_info is None:
            if not quiet:
                log_warning(f"跳过 {feature_dir.name}：{feature_md.name} 缺少 name 字段或解析失败")
            continue

        # 计算相对于 module_dir 的路径，提取中间层级（如 "2026-Q2"）
        try:
            rel_parts = feature_dir.relative_to(module_dir).parts
        except ValueError:
            rel_parts = (feature_dir.name,)

        # 构建完整路径：{repo_path}/{module_name}/{...中间层级...}/{feature_dir}/
        path_parts = [repo_path, module_name] + list(rel_parts)
        feature_info["path"] = "/".join(path_parts) + "/"

        # feature_file：相对于 feature 目录的文件路径
        try:
            feature_info["feature_file"] = str(feature_md.relative_to(feature_dir))
        except ValueError:
            feature_info["feature_file"] = feature_md.name

        features.append(feature_info)

        if not quiet:
            log_info(f"发现 feature: {feature_info['name']} (来自模块 {module_name})")

    return features


def filter_features(features: List[Dict], keywords: List[str]) -> List[Dict]:
    """对 feature 列表进行关键词过滤

    将每个 feature 的所有元数据字段序列化为字符串（包括 tags 列表、
    urls 列表中的 url 和 title），对每个关键词做大小写不敏感的子字符串匹配。
    多个关键词之间为 OR 关系：任意一个关键词匹配即返回该 feature。

    Args:
        features: feature 列表
        keywords: 关键词列表

    Returns:
        List[Dict]: 过滤后的 feature 列表
    """
    if not keywords:
        return features

    result = []
    for feature in features:
        if _feature_matches_any_keyword(feature, keywords):
            result.append(feature)
    return result


def _feature_matches_any_keyword(feature: Dict, keywords: List[str]) -> bool:
    """检查 feature 是否匹配任意一个关键词（大小写不敏感）"""
    # 收集所有可搜索的字符串
    searchable_parts = []

    for field in ("name", "description", "status", "priority", "module", "assignee"):
        val = feature.get(field)
        if val:
            searchable_parts.append(str(val))

    # tags 列表
    tags = feature.get("tags") or []
    for tag in tags:
        searchable_parts.append(str(tag))

    # urls 列表中的 url 和 title
    urls = feature.get("urls") or []
    for url_item in urls:
        if isinstance(url_item, dict):
            if url_item.get("url"):
                searchable_parts.append(str(url_item["url"]))
            if url_item.get("title"):
                searchable_parts.append(str(url_item["title"]))

    # 合并为一个大字符串，做大小写不敏感匹配
    combined = " ".join(searchable_parts).lower()
    for kw in keywords:
        if kw.lower() in combined:
            return True
    return False


def format_feature_output(feature: Dict, detail: bool) -> Dict:
    """格式化单条 feature 输出

    Args:
        feature: feature 字典
        detail: True 输出所有字段，False 只输出精简摘要字段

    Returns:
        Dict: 格式化后的字典
    """
    if detail:
        # 输出所有已知字段（保留原始值，缺失字段用 None）
        return {field: feature.get(field) for field in ALL_FIELDS}
    else:
        result = {field: feature.get(field) for field in SUMMARY_FIELDS}
        # urls 精简为纯字符串数组，只保留 url 字段
        raw_urls = feature.get("urls") or []
        result["urls"] = [
            u["url"] for u in raw_urls if isinstance(u, dict) and u.get("url")
        ]
        return result


@click.group(name="feature")
def feature_group():
    """需求功能管理

    - 支持扫描多个仓库的 features/ 目录\n
    - 支持关键词全字段模糊搜索\n
    - 以 JSON 格式输出供开发者和 AI 会话使用
    """
    pass


def _collect_feature_modules(config_manager: ConfigManager, project_root: Path) -> List[Dict]:
    """聚合所有仓库的 modules 列表，同时兜底追加每个仓库的 features 目录。

    规则：
    1. 若仓库有 modules，展开每个 module，path = {repo.path}/{module.name}
    2. 无论是否有 modules，始终追加 {repo.path}/features 作为兜底条目
    3. 仓库 tags 包含 "features" 时，标记 deep=True，扫描时使用深度递归模式

    Returns:
        List[Dict]: 每条包含 name、description、path、deep（bool）、repo_path（str）
    """
    try:
        repos = config_manager.get_all_repos()
    except ValueError:
        return []

    result = []
    for repo in repos:
        is_deep = bool(repo.tags and "features" in repo.tags)
        has_modules = bool(repo.modules)  # 有具体 module 条目时为 True
        if repo.modules:
            for mod in repo.modules:
                result.append({
                    "name": mod.name,
                    "description": mod.description,
                    "path": f"{repo.path}/{mod.name}",
                    "deep": is_deep,
                    "repo_path": repo.path,
                })
        # 非 deep 仓库始终追加 features 兜底；deep 仓库在无 modules 条目时也追加兜底
        if not is_deep or not has_modules:
            result.append({
                "name": repo.name,
                "description": repo.description or "",
                "path": f"{repo.path}/features",
                "deep": False,
                "repo_path": repo.path,
            })

    return result


@feature_group.command(name="modules")
@click.option("--features-only", "features_only", is_flag=True, default=False,
              help="只输出 tags 包含 'features' 的仓库的模块")
def feature_modules(features_only: bool):
    """列出所有仓库的 features 模块路径，以 JSON 数组格式输出

    聚合所有仓库的 modules 字段，同时兜底追加每个仓库的 features 目录。
    - 仓库有 modules：展开每个 module，path = {repo.path}/{module.name}
    - 所有仓库：始终追加 {repo.path}/features 作为兜底条目

    输出字段：name、description、path

    \b
    示例：
        driving feature modules
        driving feature modules --features-only
    """
    import json as _json

    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    raw = _collect_feature_modules(config_manager, project_root)

    # --features-only：只保留 deep=True（即 tags 含 features）的条目
    if features_only:
        raw = [m for m in raw if m.get("deep")]

    # 只输出对外字段，过滤内部辅助字段
    result = [{"name": m["name"], "description": m["description"], "path": m["path"]} for m in raw]
    click.echo(_json.dumps(result, ensure_ascii=False, indent=2))


@feature_group.command(name="list")
@click.option("--repo", "repo_name", default=None, help="只扫描指定仓库的 features")
@click.option("--keywords", "keywords", multiple=True, help="关键词过滤，OR 关系（可多次指定，或用逗号分割：--keywords kw1,kw2）")
@click.option("--detail", is_flag=True, default=False, help="输出完整字段（默认只输出精简摘要）")
def feature_list(repo_name: Optional[str], keywords: Tuple[str, ...], detail: bool):
    """列出所有 features，支持关键词搜索，以 JSON 数组格式输出

    从 `driving feature modules` 聚合的 modules 列表中遍历，
    扫描每个 module path 下的所有 feature 子目录，
    解析 FEATURE.md 的 YAML frontmatter，支持关键词全字段模糊搜索。

    \b
    示例：
        driving feature list
        driving feature list --repo my-local
        driving feature list --keywords game,list
        driving feature list --keywords game --keywords list
        driving feature list --detail
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        if repo_name:
            # 单仓库模式：直接扫描该仓库的 features 目录
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            features_dir = config_manager.get_repo_dir(repo_name) / "features"
            if not features_dir.exists():
                click.echo("[]")
                return
            all_features = scan_features_from_dir(repo_name, features_dir, quiet=True)
        else:
            # 从 modules 聚合结果遍历
            modules_list = _collect_feature_modules(config_manager, project_root)

            if not modules_list:
                # 回退：扫描所有仓库的 features 目录（兼容旧逻辑）
                features_dirs = config_manager.get_all_features_dirs()
                all_features = []
                for rname, fdir in features_dirs:
                    all_features.extend(scan_features_from_dir(rname, fdir, quiet=True))
            else:
                all_features = []
                for mod_entry in modules_list:
                    mod_path = project_root / mod_entry["path"]
                    if not mod_path.exists():
                        continue
                    if mod_entry.get("deep"):
                        # 深度递归模式：适用于 tags 含 "features" 的仓库
                        # 结构：{module}/{年度-季度}/{日期}-{feature}/FEATURE.md
                        mod_features = scan_features_deep(
                            module_name=mod_entry["name"],
                            module_dir=mod_path,
                            repo_path=mod_entry["repo_path"],
                            quiet=True,
                        )
                    else:
                        # 普通模式：mod_path 本身就是 features 根目录，扫描其子目录
                        mod_features = scan_features_from_dir(
                            mod_entry["name"], mod_path, quiet=True
                        )
                    all_features.extend(mod_features)

        # 关键词过滤（支持逗号分割，如 --keywords kw1,kw2,kw3）
        if keywords:
            expanded = []
            for kw in keywords:
                expanded.extend(k.strip() for k in kw.split(",") if k.strip())
            all_features = filter_features(all_features, expanded)

        # 格式化输出
        output = [format_feature_output(f, detail) for f in all_features]

        # 按 feature name 字母顺序排序
        output.sort(key=lambda x: (x.get("name") or ""))

        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出 features 失败: {e}")
        raise click.Abort()
