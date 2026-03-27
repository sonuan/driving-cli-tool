"""Feature 子命令组

提供 `driving feature list` 命令，
扫描所有已安装仓库的 features/ 目录，支持关键词搜索，以 JSON 格式输出。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving.utils.config_manager import ConfigManager, find_project_root
from driving.utils.logger import log_error, log_info, log_warning

# 尝试导入 yaml，如果失败则使用简单解析器
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# 精简摘要字段集合
SUMMARY_FIELDS = {"name", "title", "description", "status", "urls", "path", "repo"}

# 完整字段集合（含计算字段）
ALL_FIELDS = {
    "name", "title", "description", "status", "priority",
    "module", "assignee", "tags", "urls", "path", "repo",
}


def _parse_frontmatter_simple(yaml_content: str) -> Optional[Dict]:
    """简化的 YAML 解析器，支持 FEATURE.md 中的所有字段

    Args:
        yaml_content: YAML 内容字符串

    Returns:
        Dict: 包含解析字段的字典，缺少 name 则返回 None
    """
    result: Dict = {}
    lines = yaml_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # 解析简单 key: value 字段
        for field in ("name", "title", "description", "status", "priority", "module", "assignee"):
            if stripped.startswith(f"{field}:"):
                value = stripped[len(field) + 1:].strip()
                result[field] = value
                i += 1
                break
        else:
            # 解析 tags 列表（YAML 块序列）
            if stripped.startswith("tags:"):
                tags = []
                i += 1
                while i < len(lines):
                    tag_line = lines[i]
                    tag_stripped = tag_line.strip()
                    if tag_stripped.startswith("- "):
                        tags.append(tag_stripped[2:].strip())
                        i += 1
                    else:
                        break
                result["tags"] = tags
                continue

            # 解析 urls 列表（YAML 块序列，每项含 type/url/title）
            if stripped.startswith("urls:"):
                urls = []
                i += 1
                current_url: Optional[Dict] = None
                while i < len(lines):
                    url_line = lines[i]
                    url_stripped = url_line.strip()
                    if url_stripped.startswith("- "):
                        if current_url is not None:
                            urls.append(current_url)
                        # 新的 url 条目，可能包含第一个字段
                        rest = url_stripped[2:].strip()
                        current_url = {}
                        if ":" in rest:
                            k, v = rest.split(":", 1)
                            current_url[k.strip()] = v.strip()
                        i += 1
                    elif url_stripped and current_url is not None and ":" in url_stripped:
                        k, v = url_stripped.split(":", 1)
                        current_url[k.strip()] = v.strip()
                        i += 1
                    else:
                        break
                if current_url is not None:
                    urls.append(current_url)
                result["urls"] = urls
                continue

            i += 1

    if "name" not in result:
        return None
    return result


def parse_feature_yaml(feature_md_path: Path) -> Optional[Dict]:
    """解析 FEATURE.md 文件的 YAML frontmatter

    提取所有字段：name、title、description、status、priority、module、assignee、tags、urls。
    优先使用 PyYAML，降级到简单解析器。

    Args:
        feature_md_path: FEATURE.md 文件路径

    Returns:
        Dict: 包含所有 frontmatter 字段的字典，缺少 name 字段则返回 None
    """
    try:
        content = feature_md_path.read_text(encoding="utf-8")

        # 检查是否有 YAML frontmatter
        if not content.startswith("---"):
            return None

        # 按独立行的 --- 分割
        lines = content.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return None

        yaml_content = "\n".join(lines[1:end_idx]).strip()

        # 优先使用 PyYAML 解析
        if HAS_YAML:
            try:
                yaml_data = yaml.safe_load(yaml_content)
                if not yaml_data or "name" not in yaml_data:
                    return None
                return {
                    "name": str(yaml_data.get("name", "")),
                    "title": str(yaml_data.get("title", "") or ""),
                    "description": str(yaml_data.get("description", "") or ""),
                    "status": str(yaml_data.get("status", "") or ""),
                    "priority": str(yaml_data.get("priority", "") or ""),
                    "module": str(yaml_data.get("module", "") or ""),
                    "assignee": str(yaml_data.get("assignee", "") or ""),
                    "tags": list(yaml_data.get("tags") or []),
                    "urls": list(yaml_data.get("urls") or []),
                }
            except Exception as e:
                log_warning(f"PyYAML 解析失败，尝试使用简化解析器: {e}")
                parsed = _parse_frontmatter_simple(yaml_content)
        else:
            parsed = _parse_frontmatter_simple(yaml_content)

        if parsed is None:
            return None

        return {
            "name": str(parsed.get("name", "")),
            "title": str(parsed.get("title", "") or ""),
            "description": str(parsed.get("description", "") or ""),
            "status": str(parsed.get("status", "") or ""),
            "priority": str(parsed.get("priority", "") or ""),
            "module": str(parsed.get("module", "") or ""),
            "assignee": str(parsed.get("assignee", "") or ""),
            "tags": list(parsed.get("tags") or []),
            "urls": list(parsed.get("urls") or []),
        }

    except Exception as e:
        log_warning(f"解析 {feature_md_path} 失败: {e}")
        return None


def scan_features_from_dir(repo_name: str, features_dir: Path, quiet: bool = False) -> List[Dict]:
    """扫描单个仓库的 features/ 目录，返回 feature 列表

    遍历 features_dir 下的所有子目录，每个子目录查找 FEATURE.md 文件，
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

        feature_md = subdir / "FEATURE.md"
        if not feature_md.exists():
            if not quiet:
                log_warning(f"跳过 {subdir.name}：未找到 FEATURE.md 文件")
            continue

        feature_info = parse_feature_yaml(feature_md)
        if feature_info is None:
            if not quiet:
                log_warning(f"跳过 {subdir.name}：FEATURE.md 缺少 name 字段或解析失败")
            continue

        feature_info["path"] = f"ai-driving/{repo_name}/features/{subdir.name}/"
        feature_info["repo"] = repo_name
        features.append(feature_info)

        if not quiet:
            log_info(f"发现 feature: {feature_info['name']} (来自仓库 {repo_name})")

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

    for field in ("name", "title", "description", "status", "priority", "module", "assignee"):
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
        return {field: feature.get(field) for field in sorted(ALL_FIELDS)}
    else:
        result = {field: feature.get(field) for field in sorted(SUMMARY_FIELDS)}
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


@feature_group.command(name="list")
@click.option("--repo", "repo_name", default=None, help="只扫描指定仓库的 features")
@click.option("--keywords", "keywords", multiple=True, help="关键词过滤，OR 关系（可多次指定，或用逗号分割：--keywords kw1,kw2）")
@click.option("--detail", is_flag=True, default=False, help="输出完整字段（默认只输出精简摘要）")
def feature_list(repo_name: Optional[str], keywords: Tuple[str, ...], detail: bool):
    """列出所有 features，支持关键词搜索，以 JSON 数组格式输出

    扫描所有已安装仓库（或指定仓库）的 features/ 目录，
    解析每个 FEATURE.md 的 YAML frontmatter，支持关键词全字段模糊搜索。

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

        # 确定要扫描的仓库范围
        if repo_name:
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            features_dirs: List[Tuple[str, Path]] = []
            features_dir = config_manager.get_repo_dir(repo_name) / "features"
            if features_dir.exists():
                features_dirs = [(repo_name, features_dir)]
        else:
            features_dirs = config_manager.get_all_features_dirs()

        if not features_dirs:
            click.echo("[]")
            return

        # 扫描所有 features
        all_features: List[Dict] = []
        for rname, fdir in features_dirs:
            repo_features = scan_features_from_dir(rname, fdir, quiet=True)
            all_features.extend(repo_features)

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
