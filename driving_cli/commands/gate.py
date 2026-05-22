"""Gate 子命令组

提供 `driving gate list` 和 `driving gate load [gate-id...]` 命令，
扫描所有已安装仓库的 gates.json，管理和读取 Android 开发工作流的门禁规则。
"""

import json as json_module
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

from driving_cli.gate import (
    AutoPassEngine,
    ConditionChecker,
    GateStateManager,
    InteractiveRunner,
    RequiresChecker,
    TemplateRenderer,
    build_result_json,
)
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_warning
from driving_cli.utils.gate_reporter import report_gate_event

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


def _get_user_prompt() -> str:
    """从 gates.json 顶层读取 user_prompt 字段。

    多仓库时取第一个非空值。未配置时返回默认值。
    """
    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    for repo in config_manager.get_all_repos():
        repo_dir = config_manager.get_repo_dir(repo.name)
        data = load_gates_file(repo.name, repo_dir)
        if data is None:
            continue
        up = data.get("user_prompt", "")
        if up:
            return up

    return "按 next 字段执行后续动作"


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


@gate_group.command(name="request")
@click.argument("gate_id")
@click.option("--path", required=True, help="feature 目录路径")
@click.option("--context", default=None, help="JSON 字符串，用于模板变量渲染")
@click.option("--dry-run", is_flag=True, default=False, help="仅展示模板，不执行交互")
def gate_request(gate_id: str, path: str, context: str, dry_run: bool):
    """执行门禁请求"""
    # 1. 解析 --context JSON
    context_dict = {}
    if context is not None:
        try:
            context_dict = json_module.loads(context)
        except (json_module.JSONDecodeError, ValueError):
            click.echo("错误：--context 参数不是有效的 JSON 格式", err=True)
            sys.exit(1)

    # 2. 加载 gate 定义
    all_gates, _system_prompt = _collect_all_gates_data()
    user_prompt = _get_user_prompt()
    gate = None
    for g in all_gates:
        if g.get("id", "").lower() == gate_id.lower():
            gate = g
            break

    if gate is None:
        click.echo(f"错误：未找到门禁 {gate_id}", err=True)
        sys.exit(1)

    # 4. 初始化组件
    state_manager = GateStateManager(path)
    gate_state = state_manager.get_gate_state(gate_id)

    gate_state_dict = {
        "request_count": gate_state.request_count,
        "auto_pass_count": gate_state.auto_pass_count,
        "user_pass_count": gate_state.user_pass_count,
        "user_amend_count": gate_state.user_amend_count,
        "pass_rate": gate_state.pass_rate,
        "last_result": gate_state.last_result,
    }

    renderer = TemplateRenderer(path, context_dict, gate_state_dict)
    checker = ConditionChecker(renderer)
    auto_pass_engine = AutoPassEngine(checker)
    requires_checker = RequiresChecker(state_manager, all_gates)
    interactive_runner = InteractiveRunner(renderer)

    # 5. Dry-run 模式
    if dry_run:
        # 渲染并展示 template
        template_lines = gate.get("template", [])
        if template_lines:
            rendered = renderer.render_lines(template_lines)
            click.echo(rendered)
            click.echo("")

        # 展示 actions（不选择）
        actions = gate.get("actions", {})
        if actions:
            click.echo("可用操作：")
            for key, action_def in actions.items():
                # 兼容 actions 值为字符串的旧格式
                if isinstance(action_def, str):
                    next_desc = action_def
                else:
                    next_desc = action_def.get("next", "")
                click.echo(f"  - {key} — {next_desc}")
        return

    # 6. 正常模式
    # 6a. Requires 校验
    requires_result = requires_checker.check(
        gate.get("requires", []), gate.get("level", "blocking")
    )
    if not requires_result.passed:
        result_json = build_result_json(
            gate_id=gate_id,
            result="blocked",
            action="requires_not_met",
            next_text=requires_result.message,
            user_prompt=user_prompt,
        )
        click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))
        # 上报：blocked
        report_gate_event(
            gate_id=gate_id,
            gate_name=gate.get("name", ""),
            gate_level=gate.get("level", "blocking"),
            result="blocked",
            action="requires_not_met",
            note=requires_result.message,
            feature_path=path,
            context=context_dict or None,
        )
        return

    # 6b. Auto_pass 检查
    auto_pass_config = gate.get("auto_pass", {"mode": "human_only"})
    auto_pass_result = auto_pass_engine.evaluate(
        auto_pass_config, gate_state.user_amend_count
    )

    if auto_pass_result.passed:
        # auto_pass 成功
        on_pass = auto_pass_config.get("on_pass", {})
        actions = gate.get("actions", {})

        # 兼容 on_pass 为字符串的旧格式
        if isinstance(on_pass, str):
            on_pass_next = renderer.render(on_pass)
            action_key = next(iter(actions), "")
        else:
            # 确定 action key
            action_key = on_pass.get("action", "")
            if not action_key:
                action_key = next(iter(actions), "")
            on_pass_next = renderer.render(on_pass.get("next", ""))

        # 构建 next_text: on_pass.next + "。" + actions[action_key].next
        action_next = ""
        if action_key and action_key in actions:
            action_def = actions[action_key]
            # 兼容 actions 值为字符串的旧格式
            if isinstance(action_def, str):
                action_next = renderer.render(action_def)
            else:
                action_next = renderer.render(action_def.get("next", ""))

        if on_pass_next and action_next:
            next_text = f"{on_pass_next}。{action_next}"
        elif on_pass_next:
            next_text = on_pass_next
        else:
            next_text = action_next

        # 记录状态
        state_manager.record_result(gate_id, "auto_pass", action_key, gate_name=gate.get("name", ""))

        # 构建 Result_JSON
        result_json = build_result_json(
            gate_id=gate_id,
            result="auto_pass",
            action=action_key,
            next_text=next_text,
            user_prompt=user_prompt,
        )

        # 根据 mode 决定输出格式
        mode = auto_pass_config.get("mode", "human_only")
        if mode == "full_auto":
            click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))
        else:
            # notify_pass
            click.echo(f"✅ {on_pass_next}")
            click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))

        # 上报：auto_pass（record_result 之后读取最新 stats）
        updated_state = state_manager.get_gate_state(gate_id)
        report_gate_event(
            gate_id=gate_id,
            gate_name=gate.get("name", ""),
            gate_level=gate.get("level", "blocking"),
            result="auto_pass",
            action=action_key,
            feature_path=path,
            context=context_dict or None,
            gate_state=updated_state,
        )
        return

    # 6c. 交互模式（auto_pass 失败或跳过）
    action_key, note = interactive_runner.run(
        gate,
        auto_pass_result.condition_results,
        gate_state.user_amend_count,
        auto_pass_result.forced_interactive,
    )

    # 确定 result_type
    actions = gate.get("actions", {})
    selected_action = actions.get(action_key, {})
    # 兼容 actions 值为字符串的旧格式
    if isinstance(selected_action, str):
        # 字符串格式无 requires_note 字段，根据是否有 note 判断
        result_type = "amend" if note else "pass"
        next_text = renderer.render(selected_action)
    else:
        if selected_action.get("requires_note", False):
            result_type = "amend"
        else:
            result_type = "pass"
        next_text = renderer.render(selected_action.get("next", ""))

    # 记录状态
    state_manager.record_result(gate_id, result_type, action_key, note, gate_name=gate.get("name", ""))

    # 构建 next_text 已在上面完成

    # 输出 Result_JSON
    result_json = build_result_json(
        gate_id=gate_id,
        result=result_type,
        action=action_key,
        next_text=next_text,
        note=note,
        user_prompt=user_prompt,
    )
    click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))

    # 上报：pass / amend（record_result 之后读取最新 stats）
    updated_state = state_manager.get_gate_state(gate_id)
    report_gate_event(
        gate_id=gate_id,
        gate_name=gate.get("name", ""),
        gate_level=gate.get("level", "blocking"),
        result=result_type,
        action=action_key,
        note=note,
        feature_path=path,
        context=context_dict or None,
        gate_state=updated_state,
    )


@gate_group.command(name="status")
@click.argument("gate_id", required=False, default=None)
@click.option("--path", required=True, help="feature 目录路径")
def gate_status(gate_id: Optional[str], path: str):
    """查看门禁状态"""
    state_manager = GateStateManager(path)

    # state 文件不存在时输出提示信息
    if not state_manager.state_file.exists():
        click.echo("尚未记录任何门禁状态")
        return

    data = state_manager.load()

    if gate_id is not None:
        # 输出指定 gate 的状态
        gates = data.get("gates", {})
        gate_data = gates.get(gate_id, {})
        click.echo(json_module.dumps(gate_data, ensure_ascii=False, indent=2))
    else:
        # 输出所有 gate 状态
        gates = data.get("gates", {})
        click.echo(json_module.dumps(gates, ensure_ascii=False, indent=2))


@gate_group.command(name="history")
@click.argument("gate_id")
@click.option("--path", required=True, help="feature 目录路径")
def gate_history(gate_id: str, path: str):
    """查看门禁历史"""
    state_manager = GateStateManager(path)
    gate_state = state_manager.get_gate_state(gate_id)

    if not gate_state.history:
        click.echo(f"门禁 {gate_id} 暂无历史记录")
        return

    for entry in gate_state.history:
        click.echo(f"{entry.at}  {entry.action}  {entry.note}")


@gate_group.command(name="pass")
@click.argument("gate_id")
@click.option("--path", required=True, help="feature 目录路径")
@click.option("--note", default="", help="通过说明")
def gate_pass(gate_id: str, path: str, note: str):
    """手动通过门禁"""
    # 1. 加载所有 gate 定义
    all_gates, _system_prompt = _collect_all_gates_data()
    user_prompt = _get_user_prompt()

    # 2. 查找 gate 定义（大小写不敏感）
    gate = None
    for g in all_gates:
        if g.get("id", "").lower() == gate_id.lower():
            gate = g
            break

    if gate is None:
        click.echo(f"错误：未找到门禁 {gate_id}", err=True)
        sys.exit(1)

    # 3. 初始化状态管理器和前置依赖校验器
    state_manager = GateStateManager(path)
    requires_checker = RequiresChecker(state_manager, all_gates)

    # 5. 前置依赖校验
    requires_result = requires_checker.check(
        gate.get("requires", []), gate.get("level", "blocking")
    )

    if not requires_result.passed:
        # 阻断时输出 blocked Result_JSON
        result_json = build_result_json(
            gate_id=gate_id,
            result="blocked",
            action="requires_not_met",
            next_text=requires_result.message,
            user_prompt=user_prompt,
        )
        click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))
        # 上报：blocked
        report_gate_event(
            gate_id=gate_id,
            gate_name=gate.get("name", ""),
            gate_level=gate.get("level", "blocking"),
            result="blocked",
            action="requires_not_met",
            note=requires_result.message,
            feature_path=path,
        )
        return

    # 6. 通过：确定 action_key（actions 的第一个 key）
    actions = gate.get("actions", {})
    action_key = next(iter(actions), "")

    # 7. 记录状态（user_pass）
    state_manager.record_result(gate_id, "pass", action_key, note, gate_name=gate.get("name", ""))

    # 8. 构建 next_text
    gate_state = state_manager.get_gate_state(gate_id)
    gate_state_dict = {
        "request_count": gate_state.request_count,
        "auto_pass_count": gate_state.auto_pass_count,
        "user_pass_count": gate_state.user_pass_count,
        "user_amend_count": gate_state.user_amend_count,
        "pass_rate": gate_state.pass_rate,
        "last_result": gate_state.last_result,
    }
    renderer = TemplateRenderer(path, {}, gate_state_dict)
    next_text = ""
    if action_key and action_key in actions:
        action_def = actions[action_key]
        # 兼容 actions 值为字符串的旧格式
        if isinstance(action_def, str):
            next_text = renderer.render(action_def)
        else:
            next_text = renderer.render(action_def.get("next", ""))

    # 9. 输出确认行 + Result_JSON
    click.echo(f"✅ 已手动通过: {gate_id}")
    result_json = build_result_json(
        gate_id=gate_id,
        result="pass",
        action=action_key,
        next_text=next_text,
        note=note,
        user_prompt=user_prompt,
    )
    click.echo(json_module.dumps(result_json, ensure_ascii=False, indent=2))

    # 上报：pass（record_result 之后读取最新 stats）
    report_gate_event(
        gate_id=gate_id,
        gate_name=gate.get("name", ""),
        gate_level=gate.get("level", "blocking"),
        result="pass",
        action=action_key,
        note=note,
        feature_path=path,
        gate_state=gate_state,
    )
