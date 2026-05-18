"""Condition_Checker 验证类型执行器

支持 10 种验证类型 + 6 种操作符。
文件系统异常视为 condition 失败，不中断流程。
"""

import json
import re
from pathlib import Path
from typing import Any

from driving_cli.gate.models import ConditionResult
from driving_cli.gate.template_renderer import TemplateRenderer


class ConditionChecker:
    """内置验证类型执行器

    支持 10 种验证类型 + 6 种操作符。
    """

    # 路径合法性检查：中文字符范围
    _CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    # 连续特殊字符模式（如 //、--、__、.. 等）
    _CONSECUTIVE_SPECIAL_PATTERN = re.compile(r"[/\-_.]{2,}")

    def __init__(self, renderer: TemplateRenderer):
        """
        Args:
            renderer: 模板渲染器，用于渲染 condition 字段中的变量
        """
        self._renderer = renderer

    def check(self, condition: dict) -> ConditionResult:
        """执行单条 condition 验证

        Args:
            condition: condition JSON 对象，必须包含 type 和 label

        Returns:
            ConditionResult 检查结果
        """
        cond_type = condition.get("type", "")
        label = condition.get("label", "")

        try:
            passed = self._dispatch(cond_type, condition)
        except Exception as e:
            # 文件系统异常视为 condition 失败，不中断流程
            return ConditionResult(passed=False, label=label, detail=str(e))

        detail = "" if passed else self._build_failure_detail(cond_type, condition)
        return ConditionResult(passed=passed, label=label, detail=detail)

    def _dispatch(self, cond_type: str, condition: dict) -> bool:
        """按 type 分发到对应的检查方法"""
        if cond_type == "path_valid":
            target = self._render_field(condition, "target")
            return self._check_path_valid(target)
        elif cond_type == "path_exists":
            target = self._render_field(condition, "target")
            return self._check_path_exists(target)
        elif cond_type == "path_not_empty":
            target = self._render_field(condition, "target")
            return self._check_path_not_empty(target)
        elif cond_type == "path_not_duplicate":
            target = self._render_field(condition, "target")
            scope = self._render_field(condition, "scope")
            return self._check_path_not_duplicate(target, scope)
        elif cond_type == "file_exists":
            target = self._render_field(condition, "target")
            return self._check_file_exists(target)
        elif cond_type == "file_not_empty":
            target = self._render_field(condition, "target")
            return self._check_file_not_empty(target)
        elif cond_type == "json_field":
            file = self._render_field(condition, "file")
            field = condition.get("field", "")
            op = condition.get("op", "eq")
            value = condition.get("value")
            # value 如果是字符串也需要渲染
            if isinstance(value, str):
                value = self._renderer.render(value)
            return self._check_json_field(file, field, op, value)
        elif cond_type == "all_tasks_done":
            file = self._render_field(condition, "file")
            pattern = condition.get("pattern", "")
            return self._check_all_tasks_done(file, pattern)
        elif cond_type == "no_match":
            file = self._render_field(condition, "file")
            pattern = condition.get("pattern", "")
            return self._check_no_match(file, pattern)
        elif cond_type == "context_field":
            field = condition.get("field", "")
            op = condition.get("op", "eq")
            value = condition.get("value")
            if isinstance(value, str):
                value = self._renderer.render(value)
            return self._check_context_field(field, op, value)
        else:
            # 未知类型视为失败
            return False

    def _render_field(self, condition: dict, field_name: str) -> str:
        """渲染 condition 中的字段值"""
        raw = condition.get(field_name, "")
        if isinstance(raw, str):
            return self._renderer.render(raw)
        return str(raw)

    def _build_failure_detail(self, cond_type: str, condition: dict) -> str:
        """构建失败时的详细信息"""
        if cond_type == "path_valid":
            return "路径包含非法字符"
        elif cond_type == "path_exists":
            target = self._render_field(condition, "target")
            return f"路径不存在: {target}"
        elif cond_type == "path_not_empty":
            target = self._render_field(condition, "target")
            return f"目录为空: {target}"
        elif cond_type == "path_not_duplicate":
            target = self._render_field(condition, "target")
            scope = self._render_field(condition, "scope")
            return f"scope 下存在同名目录: {target} in {scope}"
        elif cond_type == "file_exists":
            target = self._render_field(condition, "target")
            return f"文件不存在: {target}"
        elif cond_type == "file_not_empty":
            target = self._render_field(condition, "target")
            return f"文件为空: {target}"
        elif cond_type == "json_field":
            field = condition.get("field", "")
            op = condition.get("op", "")
            value = condition.get("value", "")
            return f"JSON 字段验证失败: {field} {op} {value}"
        elif cond_type == "all_tasks_done":
            return "存在未完成的任务"
        elif cond_type == "no_match":
            pattern = condition.get("pattern", "")
            return f"存在匹配行: pattern={pattern}"
        elif cond_type == "context_field":
            field = condition.get("field", "")
            op = condition.get("op", "")
            value = condition.get("value", "")
            return f"context 字段验证失败: {field} {op} {value}"
        return "验证失败"

    def _apply_operator(self, actual: Any, op: str, expected: Any) -> bool:
        """应用操作符比较

        支持: eq, ne, gt, gte, empty, not_empty
        """
        if op == "eq":
            return actual == expected
        elif op == "ne":
            return actual != expected
        elif op == "gt":
            return actual > expected
        elif op == "gte":
            return actual >= expected
        elif op == "empty":
            if actual is None:
                return True
            return len(actual) == 0
        elif op == "not_empty":
            if actual is None:
                return False
            return len(actual) > 0
        else:
            return False

    def _check_path_valid(self, target: str) -> bool:
        """验证路径不含空格、中文、..、连续特殊字符"""
        if not target:
            return False
        # 检查空格
        if " " in target:
            return False
        # 检查中文字符
        if self._CHINESE_PATTERN.search(target):
            return False
        # 检查 .. 序列
        if ".." in target:
            return False
        # 检查连续特殊字符
        if self._CONSECUTIVE_SPECIAL_PATTERN.search(target):
            return False
        return True

    def _check_path_exists(self, target: str) -> bool:
        """验证路径存在"""
        return Path(target).exists()

    def _check_path_not_empty(self, target: str) -> bool:
        """验证目录非空"""
        p = Path(target)
        if not p.exists() or not p.is_dir():
            return False
        return any(p.iterdir())

    def _check_path_not_duplicate(self, target: str, scope: str) -> bool:
        """验证 scope 下无同名子目录"""
        target_name = Path(target).name
        scope_path = Path(scope)
        if not scope_path.exists() or not scope_path.is_dir():
            # scope 不存在时视为无重复
            return True
        for child in scope_path.iterdir():
            if child.is_dir() and child.name == target_name:
                # 如果找到的就是 target 本身，不算重复
                try:
                    if child.resolve() == Path(target).resolve():
                        continue
                except (OSError, ValueError):
                    pass
                return False
        return True

    def _check_file_exists(self, target: str) -> bool:
        """验证文件存在"""
        return Path(target).is_file()

    def _check_file_not_empty(self, target: str) -> bool:
        """验证文件大小 > 0"""
        p = Path(target)
        if not p.is_file():
            return False
        return p.stat().st_size > 0

    def _check_json_field(self, file: str, field: str, op: str, value: Any) -> bool:
        """读取 JSON 文件，dot notation 提取字段，应用操作符"""
        p = Path(file)
        if not p.is_file():
            return False
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)

        # 按 dot notation 提取字段
        actual = self._extract_field(data, field)
        return self._apply_operator(actual, op, value)

    def _check_all_tasks_done(self, file: str, pattern: str) -> bool:
        """匹配行全部包含 [x]"""
        p = Path(file)
        if not p.is_file():
            return False
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()

        regex = re.compile(pattern)
        matched_lines = [line for line in lines if regex.search(line)]

        # 如果没有匹配行，视为通过（没有需要检查的任务）
        if not matched_lines:
            return True

        # 所有匹配行都必须包含 [x]
        return all("[x]" in line for line in matched_lines)

    def _check_no_match(self, file: str, pattern: str) -> bool:
        """无匹配行"""
        p = Path(file)
        if not p.is_file():
            return False
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()

        regex = re.compile(pattern)
        return not any(regex.search(line) for line in lines)

    def _check_context_field(self, field: str, op: str, value: Any) -> bool:
        """从 context 提取字段，应用操作符"""
        actual = self._extract_field(self._renderer._context, field)
        return self._apply_operator(actual, op, value)

    @staticmethod
    def _extract_field(data: Any, field: str) -> Any:
        """按 dot notation 从 dict 中提取字段值"""
        keys = field.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
