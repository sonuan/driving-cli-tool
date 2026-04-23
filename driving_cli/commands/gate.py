"""Gate 子命令组

提供 `driving gate list` 和 `driving gate load [gate-id...]` 命令，
扫描所有已安装仓库的 gates.json，管理和读取 Android 开发工作流的门禁规则。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_warning

# Rich console（输出到 stdout）
_console = Console()


def load_gates_file(repo_name: str, repo_dir: Path) -> Optional[Dict]:
    """从单个仓库的 manifest.json 读取 gates 字段，加载并解析 gates.json。

    Args:
        repo_name: 仓库名称（用于日志）
        repo_dir: 仓库根目录路径

    Returns:
        gates.json 的完整顶层数据字典（含 version、description、system_prompt、gates 等字段），
        失败时返回 None。
        以下情况静默返回 None（不输出警告）：
          - manifest.json 不存在
          - manifest.json 中无 gates 字段
          - gates 字段指向的文件不存在
        以下情况输出 log_warning 并返回 None：
          - gates.json JSON 格式非法
          - gates.json 中 gates 字段不是数组
    """
    manifest_path = repo_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest_data = json_module.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    gates_rel_path = manifest_data.get("gates")
    if not gates_rel_path:
        return None

    gates_file = repo_dir / gates_rel_path
    if not gates_file.exists():
        return None

    try:
        gates_data = json_module.loads(gates_file.read_text(encoding="utf-8"))
    except json_module.JSONDecodeError as e:
        log_warning(f"仓库 '{repo_name}' 的 gates.json JSON 格式非法: {e}")
        return None
    except Exception as e:
        log_warning(f"仓库 '{repo_name}' 的 gates.json 读取失败: {e}")
        return None

    gates_list = gates_data.get("gates")
    if not isinstance(gates_list, list):
        log_warning(f"仓库 '{repo_name}' 的 gates.json 中 gates 字段不是数组")
        return None

    return gates_data


def load_gates_from_manifest(repo_name: str, repo_dir: Path) -> Optional[List[Dict]]:
    """从单个仓库的 manifest.json 读取 gates 字段，加载并解析 gates.json。

    向后兼容接口，只返回 gate 列表。

    Returns:
        gate 对象列表，失败时返回 None。
    """
    data = load_gates_file(repo_name, repo_dir)
    if data is None:
        return None
    return data.get("gates")


def collect_gates() -> List[Dict]:
    """扫描所有已安装仓库，收集所有 gate 的摘要信息（含 repo 字段）。

    Returns:
        包含所有 gate 摘要信息的列表，每条记录附加 repo 字段（仓库名称）。
    """
    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    all_gates = []
    for repo in config_manager.get_all_repos():
        repo_dir = config_manager.get_repo_dir(repo.name)
        gates = load_gates_from_manifest(repo.name, repo_dir)
        if gates is None:
            continue
        for gate in gates:
            gate_with_repo = dict(gate)
            gate_with_repo["repo"] = repo.name
            all_gates.append(gate_with_repo)

    return all_gates


def _collect_all_gates_data() -> Tuple[List[Dict], str]:
    """扫描所有仓库，返回 (完整 gate 列表, 拼接后的 system_prompt)。

    gate 列表中每条记录为原始字段（不含 repo）。
    system_prompt 为各仓库 gates.json 顶层 system_prompt 字段的非空值拼接。
    """
    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    all_gates: List[Dict] = []
    system_prompts: List[str] = []

    for repo in config_manager.get_all_repos():
        repo_dir = config_manager.get_repo_dir(repo.name)
        data = load_gates_file(repo.name, repo_dir)
        if data is None:
            continue
        sp = data.get("system_prompt", "")
        if sp:
            system_prompts.append(sp)
        gates = data.get("gates") or []
        all_gates.extend(gates)

    return all_gates, "\n".join(system_prompts)


@click.group(name="gate")
def gate_group():
    """门禁规则管理

    - 支持扫描多个仓库的 gates.json\n
    - 列出所有门禁规则摘要\n
    - 按 ID 读取指定门禁规则的完整内容
    """
    pass


@gate_group.command(name="list")
@click.option("--json", "output_json", is_flag=True, help="以 JSON 数组格式输出")
def gate_list(output_json: bool):
    """列出所有仓库中定义的 gate 信息

    默认以表格形式显示，列：ID、Name、Type、Location、Repo。
    使用 --json 选项输出 JSON 数组，每条记录包含 id、name、type、location、repo 字段。

    示例：
        driving gate list
        driving gate list --json
    """
    all_gates = collect_gates()

    if not all_gates:
        click.echo("未找到任何 gate 配置")
        return

    if output_json:
        output = [
            {
                "id": g.get("id", ""),
                "name": g.get("name", ""),
                "type": g.get("type", ""),
                "location": g.get("location", ""),
                "repo": g.get("repo", ""),
            }
            for g in all_gates
        ]
        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))
    else:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="bold yellow", no_wrap=True)
        table.add_column("Name")
        table.add_column("Type", no_wrap=True)
        table.add_column("Location")
        table.add_column("Repo", style="dim", no_wrap=True)

        for g in all_gates:
            table.add_row(
                g.get("id", ""),
                g.get("name", ""),
                g.get("type", ""),
                g.get("location", ""),
                g.get("repo", ""),
            )

        _console.print(table)


@gate_group.command(name="load")
@click.argument("gate_ids", nargs=-1, required=False)
def gate_load(gate_ids: tuple):
    """读取指定 gate 的完整内容

    不传 ID 时加载所有 gate；传入一个或多个 ID 时按 ID 查找（大小写不敏感）。
    任一 ID 找不到时，gates 返回空数组。
    输出格式为 JSON 对象，包含 system_prompt（来自 gates.json 顶层，多仓库拼接）和 gates 数组。

    示例：
        driving gate load                    # 加载全部
        driving gate load GATE-R1            # 加载单个
        driving gate load GATE-R1 GATE-D1   # 加载多个
    """
    all_gates, system_prompt = _collect_all_gates_data()

    if not gate_ids:
        # 不传 ID：返回全部
        result: Dict = {"gates": all_gates}
        if system_prompt:
            result = {"system_prompt": system_prompt, "gates": all_gates}
        click.echo(json_module.dumps(result, ensure_ascii=False, indent=2))
        return

    # 传了 ID：按 ID 查找
    id_lower_set = {gid.lower() for gid in gate_ids}
    found: Dict[str, Dict] = {}          # lower_id -> gate 对象（第一个匹配）
    duplicate_ids: Dict[str, List[str]] = {}  # lower_id -> 重复仓库列表

    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    for repo in config_manager.get_all_repos():
        repo_dir = config_manager.get_repo_dir(repo.name)
        gates = load_gates_from_manifest(repo.name, repo_dir)
        if gates is None:
            continue
        for gate in gates:
            lid = gate.get("id", "").lower()
            if lid in id_lower_set:
                if lid not in found:
                    found[lid] = gate
                else:
                    duplicate_ids.setdefault(lid, []).append(repo.name)

    # 警告重复 ID
    for lid, repos in duplicate_ids.items():
        log_warning(
            f"gate '{lid.upper()}' 在多个仓库中存在，"
            f"已使用第一个匹配（重复仓库：{', '.join(repos)}）"
        )

    # 任一 ID 找不到 → gates 为空数组
    missing = [gid for gid in gate_ids if gid.lower() not in found]
    if missing:
        result = {"gates": []}
        if system_prompt:
            result = {"system_prompt": system_prompt, "gates": []}
        click.echo(json_module.dumps(result, ensure_ascii=False, indent=2))
        return

    # 按传入顺序排列结果
    matched_gates = [found[gid.lower()] for gid in gate_ids]
    result = {"gates": matched_gates}
    if system_prompt:
        result = {"system_prompt": system_prompt, "gates": matched_gates}
    click.echo(json_module.dumps(result, ensure_ascii=False, indent=2))
