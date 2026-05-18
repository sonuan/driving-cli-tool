"""模板变量渲染器

支持 {{path}}、{{context.xxx}}、{{state.xxx}} 三种变量替换。
"""

import re
from typing import Any, Dict, List


class TemplateRenderer:
    """模板变量渲染器

    支持 {{path}}、{{context.xxx}}、{{state.xxx}} 三种变量替换。
    """

    _PATTERN = re.compile(r"\{\{(.+?)\}\}")

    def __init__(self, path: str, context: Dict[str, Any], state: Dict[str, Any]):
        """
        Args:
            path: --path 参数值
            context: --context 解析后的 dict
            state: gate-state.json 中当前 gate 的状态 dict
        """
        self._path = path
        self._context = context
        self._state = state

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

        支持三种模式：
        - path → 返回 --path 参数值
        - context.xxx.yyy → 从 context dict 逐层取值
        - state.xxx.yyy → 从 state dict 逐层取值

        变量不存在时返回空字符串。
        """
        if expr == "path":
            return self._path

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
