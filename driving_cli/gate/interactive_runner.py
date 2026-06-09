"""交互式 action 选择器

在 auto_pass 失败或 mode 为 human_only 时，展示 gate 模板内容并提供 action 选择菜单。
"""

import sys
from typing import Dict, List, Optional, Tuple

import click
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML

from driving_cli.gate.models import ConditionResult
from driving_cli.gate.template_renderer import TemplateRenderer


def _echo(msg: str = "") -> None:
    """输出一行信息到 stdout 并立即 flush。"""
    click.echo(msg)
    sys.stdout.flush()


def _is_interactive() -> bool:
    """检测当前环境是否支持交互输入。"""
    return sys.stdin.isatty()


def _prompt(
    text: str,
    completer: Optional[WordCompleter] = None,
    bottom_toolbar: Optional[str] = None,
) -> str:
    """显示提示并读取一行输入，支持完整行编辑（退格、光标移动、中文宽字符）。

    使用 prompt_toolkit 替代 readline，正确处理 CJK 宽字符的列宽计算。
    completer 非空时支持 Tab 补全；bottom_toolbar 非空时在输入框下方显示工具栏。
    """
    sys.stdout.flush()
    kwargs: Dict = {}
    if completer:
        kwargs["completer"] = completer
        kwargs["complete_while_typing"] = False  # 仅 Tab 触发，不自动弹出
    if bottom_toolbar:
        kwargs["bottom_toolbar"] = HTML(bottom_toolbar)
    return pt_prompt(text, **kwargs)


class NonTTYInterrupt(Exception):
    """非终端环境下无法进行交互时抛出，由调用方捕获处理。"""

    pass


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
        3. 输出全部 condition 结果（通过 ✓，未通过 ✗）
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
            _echo("⚠️ 返工次数已达阈值，强制进入交互模式")
            _echo()

        # 2. user_amend_count >= 2 时展示返工提示
        if user_amend_count >= 2:
            _echo(f"⚠️ 已返工 {user_amend_count} 次，请仔细检查后再做决定")
            _echo()

        # 3. 输出 condition 结果（通过显示 ✓，未通过显示 ✗）
        if condition_results:
            for r in condition_results:
                if r.passed:
                    _echo(f"✓ {r.label}")
                else:
                    detail_suffix = f": {r.detail}" if r.detail else ""
                    _echo(f"✗ {r.label}{detail_suffix}")
            _echo()

        # 4. 渲染并展示 template 内容
        template_lines = gate.get("template", [])
        if template_lines:
            rendered = self._renderer.render_lines(template_lines)
            _echo(rendered)
            _echo()

        # 5. 展示 action 选择菜单
        actions = gate.get("actions", {})
        action_keys = list(actions.keys())
        choices = []
        for i, key in enumerate(action_keys, 1):
            action_def = actions[key]
            # 兼容 actions 值为字符串的旧格式
            if isinstance(action_def, str):
                next_desc = self._renderer.render(action_def)
            else:
                next_desc = self._renderer.render(action_def.get("next", ""))
            choice_text = f"{key} — {next_desc}"
            choices.append(choice_text)
            _echo(f"  {i}. {choice_text}")

        _echo()

        # 非终端环境：输出提示后中断，由调用方处理
        if not _is_interactive():
            raise NonTTYInterrupt()

        # 支持输入数字或 action 名称，Tab 补全 + 底部工具栏提示
        action_keys_lower = [k.lower() for k in action_keys]

        # Tab 补全候选：数字 + action 名称
        number_strs = [str(i) for i in range(1, len(action_keys) + 1)]
        completer = WordCompleter(number_strs + action_keys, sentence=True)

        # 底部工具栏：[1] 确认  [2] 跳过拆解  [3] 补充
        toolbar_parts = "  ".join(
            f"<b>[{i}]</b> {key}" for i, key in enumerate(action_keys, 1)
        )
        toolbar = toolbar_parts

        while True:
            raw = _prompt(
                "请选择操作 (输入序号或名称): ",
                completer=completer,
                bottom_toolbar=toolbar,
            ).strip()
            # 尝试按数字解析
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(action_keys):
                    selected_key = action_keys[idx - 1]
                    break
                else:
                    _echo(f"  请输入 1 到 {len(action_keys)} 之间的数字，或输入操作名称")
                    continue
            # 尝试按 action 名称匹配（大小写不敏感）
            raw_lower = raw.lower()
            if raw_lower in action_keys_lower:
                selected_key = action_keys[action_keys_lower.index(raw_lower)]
                break
            else:
                valid_names = "、".join(action_keys)
                _echo(f"  无效输入，请输入序号（1-{len(action_keys)}）或操作名称（{valid_names}）")

        selected_action = actions[selected_key]

        # 6. 如需 note，提示输入
        note = ""
        if isinstance(selected_action, dict) and selected_action.get("requires_note", False):
            _echo("修改说明：")
            note = _prompt("> ").strip()

        return (selected_key, note)
