"""Condition_Checker 单元测试

测试 ConditionChecker 的 10 种验证类型和 6 种操作符，覆盖：
- 每种 condition type 的正常和异常场景
- 操作符比较逻辑
- 文件系统异常处理（视为失败，不中断）
- 模板变量渲染后再验证

Requirements: 4.1-4.11
"""

import json
import os

import pytest

from driving_cli.gate.condition_checker import ConditionChecker
from driving_cli.gate.models import ConditionResult
from driving_cli.gate.template_renderer import TemplateRenderer


@pytest.fixture
def renderer():
    """创建默认的 TemplateRenderer"""
    return TemplateRenderer(path="/tmp/test-project", context={}, state={})


@pytest.fixture
def checker(renderer):
    """创建默认的 ConditionChecker"""
    return ConditionChecker(renderer)


# ============================================================
# 测试 _apply_operator - Requirements 4.11
# ============================================================


class TestApplyOperator:
    """测试操作符比较逻辑 - Requirements 4.11"""

    def test_eq_相等(self, checker):
        assert checker._apply_operator("hello", "eq", "hello") is True

    def test_eq_不相等(self, checker):
        assert checker._apply_operator("hello", "eq", "world") is False

    def test_eq_数值(self, checker):
        assert checker._apply_operator(5, "eq", 5) is True
        assert checker._apply_operator(5, "eq", 3) is False

    def test_ne_不等于(self, checker):
        assert checker._apply_operator("a", "ne", "b") is True

    def test_ne_相等时返回False(self, checker):
        assert checker._apply_operator("a", "ne", "a") is False

    def test_gt_大于(self, checker):
        assert checker._apply_operator(10, "gt", 5) is True
        assert checker._apply_operator(5, "gt", 10) is False
        assert checker._apply_operator(5, "gt", 5) is False

    def test_gte_大于等于(self, checker):
        assert checker._apply_operator(10, "gte", 5) is True
        assert checker._apply_operator(5, "gte", 5) is True
        assert checker._apply_operator(4, "gte", 5) is False

    def test_empty_None(self, checker):
        assert checker._apply_operator(None, "empty", None) is True

    def test_empty_空字符串(self, checker):
        assert checker._apply_operator("", "empty", None) is True

    def test_empty_空列表(self, checker):
        assert checker._apply_operator([], "empty", None) is True

    def test_empty_非空(self, checker):
        assert checker._apply_operator("hello", "empty", None) is False
        assert checker._apply_operator([1], "empty", None) is False

    def test_not_empty_非空(self, checker):
        assert checker._apply_operator("hello", "not_empty", None) is True
        assert checker._apply_operator([1, 2], "not_empty", None) is True

    def test_not_empty_空(self, checker):
        assert checker._apply_operator("", "not_empty", None) is False
        assert checker._apply_operator([], "not_empty", None) is False

    def test_not_empty_None(self, checker):
        assert checker._apply_operator(None, "not_empty", None) is False

    def test_未知操作符返回False(self, checker):
        assert checker._apply_operator(1, "unknown", 1) is False


# ============================================================
# 测试 path_valid - Requirements 4.1
# ============================================================


class TestPathValid:
    """测试 path_valid 验证 - Requirements 4.1"""

    def test_合法路径(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features/login-page"}
        )
        assert result.passed is True

    def test_包含空格(self, checker):
        # 空格在文件系统中合法，path_valid 不再拒绝
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features/login page"}
        )
        assert result.passed is True

    def test_包含中文(self, checker):
        # 中文目录名在 macOS/Linux 上合法，path_valid 不再拒绝
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features/登录页面"}
        )
        assert result.passed is True

    def test_包含双点(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features/../secret"}
        )
        assert result.passed is False

    def test_包含连续特殊字符(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features//login"}
        )
        assert result.passed is False

    def test_包含连续横线(self, checker):
        # -- 不再被视为非法字符
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "features/--login"}
        )
        assert result.passed is True

    def test_空路径(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": ""}
        )
        assert result.passed is False

    def test_模板变量渲染后验证(self):
        renderer = TemplateRenderer(
            path="features/valid-path", context={}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {"type": "path_valid", "label": "路径合法", "target": "{{path}}"}
        )
        assert result.passed is True


# ============================================================
# 测试 path_exists - Requirements 4.2
# ============================================================


class TestPathExists:
    """测试 path_exists 验证 - Requirements 4.2"""

    def test_路径存在(self, checker, tmp_path):
        target = tmp_path / "existing_dir"
        target.mkdir()
        result = checker.check(
            {"type": "path_exists", "label": "路径存在", "target": str(target)}
        )
        assert result.passed is True

    def test_路径不存在(self, checker):
        result = checker.check(
            {"type": "path_exists", "label": "路径存在", "target": "/nonexistent/path/xyz"}
        )
        assert result.passed is False


# ============================================================
# 测试 path_not_empty - Requirements 4.3
# ============================================================


class TestPathNotEmpty:
    """测试 path_not_empty 验证 - Requirements 4.3"""

    def test_目录非空(self, checker, tmp_path):
        target = tmp_path / "nonempty_dir"
        target.mkdir()
        (target / "file.txt").write_text("content")
        result = checker.check(
            {"type": "path_not_empty", "label": "目录非空", "target": str(target)}
        )
        assert result.passed is True

    def test_目录为空(self, checker, tmp_path):
        target = tmp_path / "empty_dir"
        target.mkdir()
        result = checker.check(
            {"type": "path_not_empty", "label": "目录非空", "target": str(target)}
        )
        assert result.passed is False

    def test_路径不存在(self, checker):
        result = checker.check(
            {"type": "path_not_empty", "label": "目录非空", "target": "/nonexistent/dir"}
        )
        assert result.passed is False


# ============================================================
# 测试 path_not_duplicate - Requirements 4.4
# ============================================================


class TestPathNotDuplicate:
    """测试 path_not_duplicate 验证 - Requirements 4.4"""

    def test_无重复(self, checker, tmp_path):
        scope = tmp_path / "scope"
        scope.mkdir()
        (scope / "other-dir").mkdir()
        result = checker.check(
            {
                "type": "path_not_duplicate",
                "label": "无重复",
                "target": str(tmp_path / "new-feature"),
                "scope": str(scope),
            }
        )
        assert result.passed is True

    def test_有重复(self, checker, tmp_path):
        scope = tmp_path / "scope"
        scope.mkdir()
        (scope / "login-page").mkdir()
        result = checker.check(
            {
                "type": "path_not_duplicate",
                "label": "无重复",
                "target": str(tmp_path / "somewhere" / "login-page"),
                "scope": str(scope),
            }
        )
        assert result.passed is False

    def test_scope不存在(self, checker):
        result = checker.check(
            {
                "type": "path_not_duplicate",
                "label": "无重复",
                "target": "/some/path/feature",
                "scope": "/nonexistent/scope",
            }
        )
        assert result.passed is True


# ============================================================
# 测试 file_exists - Requirements 4.5
# ============================================================


class TestFileExists:
    """测试 file_exists 验证 - Requirements 4.5"""

    def test_文件存在(self, checker, tmp_path):
        target = tmp_path / "test.json"
        target.write_text("{}")
        result = checker.check(
            {"type": "file_exists", "label": "文件存在", "target": str(target)}
        )
        assert result.passed is True

    def test_文件不存在(self, checker):
        result = checker.check(
            {"type": "file_exists", "label": "文件存在", "target": "/nonexistent/file.json"}
        )
        assert result.passed is False

    def test_目录不算文件(self, checker, tmp_path):
        target = tmp_path / "a_dir"
        target.mkdir()
        result = checker.check(
            {"type": "file_exists", "label": "文件存在", "target": str(target)}
        )
        assert result.passed is False


# ============================================================
# 测试 file_not_empty - Requirements 4.6
# ============================================================


class TestFileNotEmpty:
    """测试 file_not_empty 验证 - Requirements 4.6"""

    def test_文件非空(self, checker, tmp_path):
        target = tmp_path / "nonempty.txt"
        target.write_text("some content")
        result = checker.check(
            {"type": "file_not_empty", "label": "文件非空", "target": str(target)}
        )
        assert result.passed is True

    def test_文件为空(self, checker, tmp_path):
        target = tmp_path / "empty.txt"
        target.write_text("")
        result = checker.check(
            {"type": "file_not_empty", "label": "文件非空", "target": str(target)}
        )
        assert result.passed is False

    def test_文件不存在(self, checker):
        result = checker.check(
            {"type": "file_not_empty", "label": "文件非空", "target": "/nonexistent/file.txt"}
        )
        assert result.passed is False


# ============================================================
# 测试 json_field - Requirements 4.7
# ============================================================


class TestJsonField:
    """测试 json_field 验证 - Requirements 4.7"""

    def test_顶层字段eq(self, checker, tmp_path):
        target = tmp_path / "data.json"
        target.write_text(json.dumps({"version": "1.0"}))
        result = checker.check(
            {
                "type": "json_field",
                "label": "版本检查",
                "file": str(target),
                "field": "version",
                "op": "eq",
                "value": "1.0",
            }
        )
        assert result.passed is True

    def test_嵌套字段(self, checker, tmp_path):
        target = tmp_path / "data.json"
        target.write_text(json.dumps({"project": {"name": "my-app"}}))
        result = checker.check(
            {
                "type": "json_field",
                "label": "项目名检查",
                "file": str(target),
                "field": "project.name",
                "op": "eq",
                "value": "my-app",
            }
        )
        assert result.passed is True

    def test_数值gt(self, checker, tmp_path):
        target = tmp_path / "data.json"
        target.write_text(json.dumps({"count": 10}))
        result = checker.check(
            {
                "type": "json_field",
                "label": "数量检查",
                "file": str(target),
                "field": "count",
                "op": "gt",
                "value": 5,
            }
        )
        assert result.passed is True

    def test_字段不存在(self, checker, tmp_path):
        target = tmp_path / "data.json"
        target.write_text(json.dumps({"a": 1}))
        result = checker.check(
            {
                "type": "json_field",
                "label": "字段检查",
                "file": str(target),
                "field": "nonexistent",
                "op": "eq",
                "value": "x",
            }
        )
        assert result.passed is False

    def test_文件不存在(self, checker):
        result = checker.check(
            {
                "type": "json_field",
                "label": "字段检查",
                "file": "/nonexistent/data.json",
                "field": "x",
                "op": "eq",
                "value": "y",
            }
        )
        assert result.passed is False

    def test_JSON格式非法(self, checker, tmp_path):
        target = tmp_path / "bad.json"
        target.write_text("not valid json {{{")
        result = checker.check(
            {
                "type": "json_field",
                "label": "字段检查",
                "file": str(target),
                "field": "x",
                "op": "eq",
                "value": "y",
            }
        )
        assert result.passed is False

    def test_not_empty操作符(self, checker, tmp_path):
        target = tmp_path / "data.json"
        target.write_text(json.dumps({"items": [1, 2, 3]}))
        result = checker.check(
            {
                "type": "json_field",
                "label": "列表非空",
                "file": str(target),
                "field": "items",
                "op": "not_empty",
                "value": None,
            }
        )
        assert result.passed is True


# ============================================================
# 测试 all_tasks_done - Requirements 4.8
# ============================================================


class TestAllTasksDone:
    """测试 all_tasks_done 验证 - Requirements 4.8"""

    def test_全部完成(self, checker, tmp_path):
        target = tmp_path / "tasks.md"
        target.write_text(
            "- [x] 任务1\n- [x] 任务2\n- [x] 任务3\n其他内容\n"
        )
        result = checker.check(
            {
                "type": "all_tasks_done",
                "label": "任务完成",
                "file": str(target),
                "pattern": r"- \[.\] ",
            }
        )
        assert result.passed is True

    def test_部分未完成(self, checker, tmp_path):
        target = tmp_path / "tasks.md"
        target.write_text(
            "- [x] 任务1\n- [ ] 任务2\n- [x] 任务3\n"
        )
        result = checker.check(
            {
                "type": "all_tasks_done",
                "label": "任务完成",
                "file": str(target),
                "pattern": r"- \[.\] ",
            }
        )
        assert result.passed is False

    def test_无匹配行视为通过(self, checker, tmp_path):
        target = tmp_path / "readme.md"
        target.write_text("# README\n普通内容\n")
        result = checker.check(
            {
                "type": "all_tasks_done",
                "label": "任务完成",
                "file": str(target),
                "pattern": r"- \[.\] ",
            }
        )
        assert result.passed is True

    def test_文件不存在(self, checker):
        result = checker.check(
            {
                "type": "all_tasks_done",
                "label": "任务完成",
                "file": "/nonexistent/tasks.md",
                "pattern": r"- \[.\] ",
            }
        )
        assert result.passed is False


# ============================================================
# 测试 no_match - Requirements 4.9
# ============================================================


class TestNoMatch:
    """测试 no_match 验证 - Requirements 4.9"""

    def test_无匹配行(self, checker, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("def hello():\n    pass\n")
        result = checker.check(
            {
                "type": "no_match",
                "label": "无TODO",
                "file": str(target),
                "pattern": r"TODO",
            }
        )
        assert result.passed is True

    def test_有匹配行(self, checker, tmp_path):
        target = tmp_path / "code.py"
        target.write_text("def hello():\n    # TODO: fix this\n    pass\n")
        result = checker.check(
            {
                "type": "no_match",
                "label": "无TODO",
                "file": str(target),
                "pattern": r"TODO",
            }
        )
        assert result.passed is False

    def test_文件不存在(self, checker):
        result = checker.check(
            {
                "type": "no_match",
                "label": "无TODO",
                "file": "/nonexistent/code.py",
                "pattern": r"TODO",
            }
        )
        assert result.passed is False


# ============================================================
# 测试 context_field - Requirements 4.10
# ============================================================


class TestContextField:
    """测试 context_field 验证 - Requirements 4.10"""

    def test_context字段eq(self):
        renderer = TemplateRenderer(
            path="", context={"task_count": 12}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "context_field",
                "label": "任务数检查",
                "field": "task_count",
                "op": "eq",
                "value": 12,
            }
        )
        assert result.passed is True

    def test_context嵌套字段(self):
        renderer = TemplateRenderer(
            path="", context={"project": {"status": "active"}}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "context_field",
                "label": "状态检查",
                "field": "project.status",
                "op": "eq",
                "value": "active",
            }
        )
        assert result.passed is True

    def test_context字段不存在(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "context_field",
                "label": "字段检查",
                "field": "nonexistent",
                "op": "eq",
                "value": "x",
            }
        )
        assert result.passed is False

    def test_context字段not_empty(self):
        renderer = TemplateRenderer(
            path="", context={"items": [1, 2, 3]}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "context_field",
                "label": "列表非空",
                "field": "items",
                "op": "not_empty",
                "value": None,
            }
        )
        assert result.passed is True

    def test_context字段empty(self):
        renderer = TemplateRenderer(
            path="", context={"items": []}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "context_field",
                "label": "列表为空",
                "field": "items",
                "op": "empty",
                "value": None,
            }
        )
        assert result.passed is True


# ============================================================
# 测试 check 方法通用行为
# ============================================================


class TestCheckGeneral:
    """测试 check 方法的通用行为"""

    def test_未知type返回失败(self, checker):
        result = checker.check(
            {"type": "unknown_type", "label": "未知类型"}
        )
        assert result.passed is False

    def test_返回ConditionResult类型(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "测试", "target": "valid/path"}
        )
        assert isinstance(result, ConditionResult)

    def test_label正确传递(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "我的标签", "target": "valid/path"}
        )
        assert result.label == "我的标签"

    def test_成功时detail为空(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "测试", "target": "valid/path"}
        )
        assert result.detail == ""

    def test_失败时detail非空(self, checker):
        result = checker.check(
            {"type": "path_valid", "label": "测试", "target": "features/../secret"}
        )
        assert result.detail != ""

    def test_文件系统异常不中断(self, checker, tmp_path, monkeypatch):
        """文件系统异常视为 condition 失败，不抛出异常"""
        # 模拟 Path.exists() 抛出异常
        import pathlib

        original_exists = pathlib.Path.exists

        def mock_exists(self):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(pathlib.Path, "exists", mock_exists)

        result = checker.check(
            {"type": "path_exists", "label": "路径存在", "target": "/some/path"}
        )
        assert result.passed is False
        assert "Permission denied" in result.detail


# ============================================================
# 测试模板变量渲染集成
# ============================================================


class TestTemplateRendering:
    """测试 condition 字段中的模板变量渲染"""

    def test_target字段渲染(self, tmp_path):
        target_dir = tmp_path / "features" / "login"
        target_dir.mkdir(parents=True)
        renderer = TemplateRenderer(
            path=str(tmp_path / "features" / "login"), context={}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {"type": "path_exists", "label": "路径存在", "target": "{{path}}"}
        )
        assert result.passed is True

    def test_file字段渲染(self, tmp_path):
        data_file = tmp_path / "data.json"
        data_file.write_text(json.dumps({"key": "value"}))
        renderer = TemplateRenderer(
            path=str(data_file), context={}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "json_field",
                "label": "字段检查",
                "file": "{{path}}",
                "field": "key",
                "op": "eq",
                "value": "value",
            }
        )
        assert result.passed is True

    def test_scope字段渲染(self, tmp_path):
        scope_dir = tmp_path / "scope"
        scope_dir.mkdir()
        renderer = TemplateRenderer(
            path=str(scope_dir), context={}, state={}
        )
        checker = ConditionChecker(renderer)
        result = checker.check(
            {
                "type": "path_not_duplicate",
                "label": "无重复",
                "target": str(tmp_path / "new-feature"),
                "scope": "{{path}}",
            }
        )
        assert result.passed is True
