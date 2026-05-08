"""Refine 子命令组

提供 `driving refine list` 和 `driving refine load` 命令，
扫描所有已安装仓库的 refines/ 目录，管理和加载 pending 状态的优化提案。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_warning

VALID_TYPES = ("skill", "rule", "agent", "framework")


def _parse_refine_frontmatter(file_path: Path) -> Optional[Dict]:
    """解析 refine 文件的 YAML frontmatter。

    提取 date、target_type、target_name、target_file、description、operator、status 字段。
    逐行读取到第二个 --- 即停止，避免读取大文件正文。

    Returns:
        Dict 或 None（无 frontmatter / 缺少必填字段）
    """
    from driving_cli.utils.yaml_parser import parse_frontmatter

    try:
        data = parse_frontmatter(file_path, required_fields=["target_type"])
        if data is None:
            return None

        return {
            "date": str(data.get("date", "")),
            "target_type": str(data.get("target_type", "")),
            "target_name": str(data.get("target_name", "")),
            "target_file": str(data.get("target_file", "")),
            "description": str(data.get("description", "")),
            "operator": str(data.get("operator", "")),
            "status": str(data.get("status", "pending")),
        }
    except Exception as e:
        log_warning(f"解析 {file_path.name} 失败: {e}")
        return None


def _scan_refines(repo_name: str, refines_dir: Path, type_filter: Optional[str] = None) -> List[Dict]:
    """扫描单个仓库的 refines/ 目录，返回 refine 信息列表。"""
    results = []
    for f in sorted(refines_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md":
            continue
        meta = _parse_refine_frontmatter(f)
        if meta is None:
            continue
        if type_filter and meta["target_type"] != type_filter:
            continue
        results.append({
            "name": f.stem,
            "description": meta["description"],
            "path": f"ai-driving/{repo_name}/refines/{f.name}",
            "date": meta["date"],
            "target_type": meta["target_type"],
            "target_name": meta["target_name"],
            "status": meta["status"],
            "_file": f,  # 内部用，load 时读取正文
        })
    return results


def _get_all_refines_dirs(config_manager: ConfigManager) -> List[Tuple[str, Path]]:
    """返回所有仓库的 refines/ 目录（仅存在的）。"""
    result = []
    for repo in config_manager.get_all_repos():
        d = config_manager.get_repo_dir(repo.name) / "refines"
        if d.exists():
            result.append((repo.name, d))
    return result


@click.group(name="refine")
def refine_group():
    """Refine 提案管理

    - 列出所有仓库的 pending refine 提案\n
    - 加载 refine 内容供 AI 检索历史优化经验
    """
    pass


@refine_group.command(name="list")
@click.option("--type", "type_filter", type=click.Choice(VALID_TYPES), default=None,
              help="只显示指定类型的 refine（skill/rule/agent/framework）")
@click.option("--repo", "repo_name", default=None, help="只显示指定仓库的 refine")
def refine_list(type_filter: Optional[str], repo_name: Optional[str]):
    """列出所有 pending 状态的 refine 提案，按类型分组显示。

    示例：
        driving refine list
        driving refine list --type skill
        driving refine list --repo driving
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        if repo_name:
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            refines_dirs = [(repo_name, config_manager.get_repo_dir(repo_name) / "refines")]
            refines_dirs = [(n, d) for n, d in refines_dirs if d.exists()]
        else:
            refines_dirs = _get_all_refines_dirs(config_manager)

        if not refines_dirs:
            log_info("未找到任何 refines 目录")
            return

        total = 0
        for rname, rdir in refines_dirs:
            items = _scan_refines(rname, rdir, type_filter=type_filter)
            if not items:
                continue

            click.echo(f"\n仓库：{rname}")

            # 按 target_type 分组
            by_type: Dict[str, List[Dict]] = {}
            for item in items:
                by_type.setdefault(item["target_type"], []).append(item)

            type_groups = sorted(by_type.items())
            for i, (ttype, group) in enumerate(type_groups):
                click.echo(f"  [{ttype}]")
                for item in group:
                    desc = item["description"] or "-"
                    click.echo(f"    {item['date']}  {item['target_name']}  {desc}  ({item['status']})")
                    total += 1
                if i < len(type_groups) - 1:
                    click.echo("")
        if total == 0:
            log_info("没有找到符合条件的 refine 提案")
        else:
            click.echo(f"\n共 {total} 条 refine")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出 refine 失败: {e}")
        raise click.Abort()


@refine_group.command(name="load")
@click.argument("names", nargs=-1, required=False)
@click.option("--type", "type_filter", type=click.Choice(VALID_TYPES), default=None,
              help="只加载指定类型的 refine（skill/rule/agent/framework）")
def refine_load(names: tuple, type_filter: Optional[str]):
    """输出 refine 提案内容，供 AI 注入上下文检索历史优化经验。

    不传 name 时输出所有 pending 的 refine。
    传入 name 时按文件名模糊匹配（包含即命中），支持多个。

    示例：
        driving refine load
        driving refine load self-refine
        driving refine load self-refine code-style
        driving refine load --type skill
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        refines_dirs = _get_all_refines_dirs(config_manager)

        output = []
        for rname, rdir in refines_dirs:
            items = _scan_refines(rname, rdir, type_filter=type_filter)
            for item in items:
                # 名称过滤：文件名包含任意一个关键词即命中
                if names and not any(n in item["name"] for n in names):
                    continue
                output.append({
                    "name": item["name"],
                    "description": item["description"],
                    "path": item["path"],
                })

        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        log_error(f"加载 refine 失败: {e}")
        raise click.Abort()
