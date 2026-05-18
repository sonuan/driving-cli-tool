"""交互式 action 选择器

在 auto_pass 失败或 mode 为 human_only 时，展示 gate 模板内容并提供 action 选择菜单。
"""

from typing import List, Tuple

import click

from driving_cli.gate.models import ConditionResult
from driving_cli.gate.template_renderer import TemplateRenderer


class InteractiveRunner:
    """交互式 action 选择器

    负责在终端中展示 gate 信息并引导用户选择 action。
    """

    def __init__(self, renderer: TemplateRenderer):
        """
        Args:
            renderer: 模板渲染器，用于渲染 template 内容
        """
        self._renderer = renderer

    def run(
        self,
        gate: dict,
        condition_results: List[ConditionResult],
        user_amend_count: int,
        forced_interactive: bool,
    ) -> Tuple[str, str]:
        """执行交互流程

        1. forced_interactive 时展示阈值警告
        2. user_amend_count >= 2 时展示返工提示
        3. 输出未通过的 condition 结果
        4. 渲染并展示 template 内容
        5. 展示 action 选择菜单
        6. 如需 note，提示输入

        Args:
            gate: gate 定义 dict
            condition_results: condition 检查结果列表
            user_amend_count: 当前修改次数
            forced_interactive: 是否由返工阈值强制触发

        Returns:
            (action_key, note) 元组
        """
        # 1. forced_interactive 时展示阈值警告
        if forced_interactive:
            click.echo("⚠️ 返工次数已达阈值，强制进入交互模式")
            click.echo("")

        # 2. user_amend_count >= 2 时展示返工提示
        if user_amend_count >= 2:
            click.echo(f"⚠️ 已返工 {user_amend_count} 次，请仔细检查后再做决定")
            click.echo("")

        # 3. 输出未通过的 condition 结果
        failed_results = [r for r in condition_results if not r.passed]
        if failed_results:
            for r in failed_results:
                detail_suffix = f": {r.detail}" if r.detail else ""
                click.echo(f"✗ {r.label}{detail_suffix}")
            click.echo("")

        # 4. 渲染并展示 template 内容
        template_lines = gate.get("template", [])
        if template_lines:
            rendered = self._renderer.render_lines(template_lines)
            click.echo(rendered)
            click.echo("")

        # 5. 展示 action 选择菜单
        actions = gate.get("actions", {})
        action_keys = list(actions.keys())
        choices = []
        for i, key in enumerate(action_keys, 1):
            action_def = actions[key]
            # 兼容 actions 值为字符串的旧格式
            if isinstance(action_def, str):
                next_desc = action_def
            else:
                next_desc = action_def.get("next", "")
            choice_text = f"{key} — {next_desc}"
            choices.append(choice_text)
            click.echo(f"  {i}. {choice_text}")

        click.echo("")
        selected_index = click.prompt(
            "请选择操作",
            type=click.IntRange(1, len(action_keys)),
        )

        selected_key = action_keys[selected_index - 1]
        selected_action = actions[selected_key]

        # 6. 如需 note，提示输入
        note = ""
        if isinstance(selected_action, dict) and selected_action.get("requires_note", False):
            note = click.prompt("修改说明")

        return (selected_key, note)
