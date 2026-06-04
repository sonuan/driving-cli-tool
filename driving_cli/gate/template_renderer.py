"""模板变量渲染器

支持 {{path}}、{{context.xxx}}、{{state.xxx}}、{{$vars.xxx}} 四种变量替换。

{{$vars.xxx}} 为 CLI 内部预计算常量，统一前缀 `$vars.`，当前支持：
  - {{$vars.platform_dir}}  → {path}/docs/{platform}（无 platform 时为 {path}/docs）
  - {{$vars.review_dir}}    → {path}/docs/{platform}/review
  - {{$vars.state_file}}    → {path}/docs/{platform}/state.json
"""

import re
from typing import Any, Dict, List, Optional


class TemplateRenderer:
    """模板变量渲染器

    支持 {{path}}、{{context.xxx}}、{{state.xxx}}、{{$vars.xxx}} 四种变量替换。

    {{$vars.xxx}} 为 CLI 内部预计算常量，由调用方通过 vars 参数注入，
    统一前缀 `$vars.` 以区分用户上下文变量。
    """

    _PATTERN = re.compile(r"\{\{(.+?)\}\}")

    def __init__(
        self,
        path: str,
        context: Dict[str, Any],
        state: Dict[str, Any],
        vars: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            path: --path 参数值
            context: --context 解析后的 dict
            state: gate-state.json 中当前 gate 的状态 dict
            vars: CLI 内部预计算常量，键名以 $vars. 开头（如 "$vars.platform_dir"）
        """
        self._path = path
        self._context = context
        self._state = state
        self._vars: Dict[str, str] = vars or {}

    def render(self, template: str) -> str:
        """渲染单个字符串中的模板变量

        Args:
            template: 包含 {{xxx}} 占位符的字符串

        Returns:
            替换后的字符串。未找到的变量替换为空字符串。
        """

        def _replace(match: re.Match) -> str:
            expr = match.group(1).strip()
            return self._resolve(expr)

        return self._PATTERN.sub(_replace, template)

    def render_lines(self, lines: List[str]) -> str:
        """渲染模板行列表，返回拼接后的字符串"""
        return "\n".join(self.render(line) for line in lines)

    def _resolve(self, expr: str) -> str:
        """解析变量表达式，返回对应值的字符串形式

        支持四种模式：
        - path → 返回 --path 参数值
        - $vars.xxx → 从 CLI 内部预计算常量（vars）中取值
        - context.xxx.yyy → 从 context dict 逐层取值
        - state.xxx.yyy → 从 state dict 逐层取值

        变量不存在时返回空字符串。
        """
        if expr == "path":
            return self._path

        # CLI 内部预计算常量，以 $vars. 开头
        if expr.startswith("$vars."):
            return self._vars.get(expr, "")

        parts = expr.split(".")
        if len(parts) < 2:
            # 不是 context.xxx 或 state.xxx 格式，也不是 path
            return ""

        root = parts[0]
        if root == "context":
            return self._deep_get(self._context, parts[1:])
        elif root == "state":
            return self._deep_get(self._state, parts[1:])

        # 未知的根变量，替换为空字符串
        return ""

    @staticmethod
    def _deep_get(data: Any, keys: List[str]) -> str:
        """按 key 路径逐层取值，不存在时返回空字符串"""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return ""
        return str(current)
