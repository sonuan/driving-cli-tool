"""Auto_Pass_Engine 单元测试

测试 human_only 跳过、全部通过、部分失败、返工阈值强制交互。
Requirements: 3.1-3.8, 13.2
"""

from unittest.mock import MagicMock

import pytest

from driving_cli.gate.auto_pass_engine import AutoPassEngine
from driving_cli.gate.models import AutoPassResult, ConditionResult


@pytest.fixture
def mock_checker():
    """创建 mock ConditionChecker"""
    return MagicMock()


@pytest.fixture
def engine(mock_checker):
    """创建 AutoPassEngine 实例"""
    return AutoPassEngine(checker=mock_checker)


class TestHumanOnlyMode:
    """Requirement 3.1: mode 为 human_only 时跳过自动通过判断，但仍执行 conditions 供展示"""

    def test_human_only_returns_skipped(self, engine, mock_checker):
        """human_only 模式应返回 skipped=True、passed=False，且执行 conditions 供展示"""
        mock_checker.check.return_value = ConditionResult(passed=True, label="文件存在")
        config = {
            "mode": "human_only",
            "conditions": [
                {"type": "file_exists", "label": "文件存在", "target": "/tmp/x"}
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.skipped is True
        assert result.passed is False
        assert result.forced_interactive is False
        # conditions 应被执行，结果用于展示
        assert len(result.condition_results) == 1
        assert result.condition_results[0].label == "文件存在"
        mock_checker.check.assert_called_once()

    def test_human_only_condition_results_returned(self, engine, mock_checker):
        """human_only 模式下多个 condition 均应执行并返回结果"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=True, label="条件1"),
            ConditionResult(passed=False, label="条件2", detail="未满足"),
        ]
        config = {
            "mode": "human_only",
            "conditions": [
                {"type": "path_valid", "label": "条件1", "target": "a"},
                {"type": "file_exists", "label": "条件2", "target": "b"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.skipped is True
        assert result.passed is False
        assert len(result.condition_results) == 2
        assert result.condition_results[0].passed is True
        assert result.condition_results[1].passed is False
        assert mock_checker.check.call_count == 2

    def test_human_only_ignores_amend_count(self, engine, mock_checker):
        """human_only 模式不受 user_amend_count 影响（不触发 forced_interactive）"""
        config = {"mode": "human_only", "conditions": []}

        result = engine.evaluate(config, user_amend_count=5)

        assert result.skipped is True
        assert result.passed is False
        assert result.forced_interactive is False

    def test_human_only_no_conditions(self, engine, mock_checker):
        """human_only 模式无 conditions 时返回空列表，不调用 checker"""
        config = {"mode": "human_only", "conditions": []}

        result = engine.evaluate(config, user_amend_count=0)

        assert result.skipped is True
        assert result.condition_results == []
        mock_checker.check.assert_not_called()


class TestNotifyPassMode:
    """Requirement 3.2: mode 为 notify_pass 时逐条执行 conditions"""

    def test_all_conditions_pass_low_amend_count(self, engine, mock_checker):
        """Requirement 3.3: 全部通过且 user_amend_count < 3 时返回 passed=True"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=True, label="文件存在"),
        ]
        config = {
            "mode": "notify_pass",
            "conditions": [
                {"type": "path_valid", "label": "路径合法", "target": "a/b"},
                {"type": "file_exists", "label": "文件存在", "target": "/tmp/x"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is True
        assert result.skipped is False
        assert result.forced_interactive is False
        assert len(result.condition_results) == 2
        assert all(r.passed for r in result.condition_results)

    def test_all_conditions_pass_amend_count_2(self, engine, mock_checker):
        """user_amend_count=2 (< 3) 时仍然可以 auto_pass"""
        mock_checker.check.return_value = ConditionResult(
            passed=True, label="检查通过"
        )
        config = {
            "mode": "notify_pass",
            "conditions": [{"type": "path_valid", "label": "检查通过", "target": "x"}],
        }

        result = engine.evaluate(config, user_amend_count=2)

        assert result.passed is True
        assert result.forced_interactive is False

    def test_some_conditions_fail(self, engine, mock_checker):
        """Requirement 3.5: 任一 condition 失败时返回 passed=False"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=False, label="文件存在", detail="文件不存在: /tmp/x"),
        ]
        config = {
            "mode": "notify_pass",
            "conditions": [
                {"type": "path_valid", "label": "路径合法", "target": "a/b"},
                {"type": "file_exists", "label": "文件存在", "target": "/tmp/x"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is False
        assert result.skipped is False
        assert result.forced_interactive is False
        assert len(result.condition_results) == 2
        assert result.condition_results[0].passed is True
        assert result.condition_results[1].passed is False

    def test_rework_threshold_forces_interactive(self, engine, mock_checker):
        """Requirement 3.4 / 13.2: user_amend_count >= 3 时强制交互"""
        mock_checker.check.return_value = ConditionResult(
            passed=True, label="检查通过"
        )
        config = {
            "mode": "notify_pass",
            "conditions": [{"type": "path_valid", "label": "检查通过", "target": "x"}],
        }

        result = engine.evaluate(config, user_amend_count=3)

        assert result.passed is False
        assert result.forced_interactive is True
        assert result.skipped is False
        assert len(result.condition_results) == 1
        assert result.condition_results[0].passed is True

    def test_rework_threshold_amend_count_5(self, engine, mock_checker):
        """user_amend_count=5 (>= 3) 时也应强制交互"""
        mock_checker.check.return_value = ConditionResult(
            passed=True, label="检查通过"
        )
        config = {
            "mode": "notify_pass",
            "conditions": [{"type": "path_valid", "label": "检查通过", "target": "x"}],
        }

        result = engine.evaluate(config, user_amend_count=5)

        assert result.passed is False
        assert result.forced_interactive is True


class TestFullAutoMode:
    """Requirement 3.6: mode 为 full_auto 时的行为"""

    def test_full_auto_all_pass(self, engine, mock_checker):
        """full_auto 模式全部通过时返回 passed=True"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=True, label="条件1"),
            ConditionResult(passed=True, label="条件2"),
            ConditionResult(passed=True, label="条件3"),
        ]
        config = {
            "mode": "full_auto",
            "conditions": [
                {"type": "path_valid", "label": "条件1", "target": "a"},
                {"type": "file_exists", "label": "条件2", "target": "b"},
                {"type": "path_exists", "label": "条件3", "target": "c"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is True
        assert result.skipped is False
        assert result.forced_interactive is False
        assert len(result.condition_results) == 3

    def test_full_auto_condition_failure(self, engine, mock_checker):
        """full_auto 模式条件失败时返回 passed=False"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=True, label="条件1"),
            ConditionResult(passed=False, label="条件2", detail="验证失败"),
        ]
        config = {
            "mode": "full_auto",
            "conditions": [
                {"type": "path_valid", "label": "条件1", "target": "a"},
                {"type": "file_exists", "label": "条件2", "target": "b"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is False
        assert result.forced_interactive is False

    def test_full_auto_rework_threshold(self, engine, mock_checker):
        """full_auto 模式也受返工阈值约束"""
        mock_checker.check.return_value = ConditionResult(
            passed=True, label="条件通过"
        )
        config = {
            "mode": "full_auto",
            "conditions": [{"type": "path_valid", "label": "条件通过", "target": "x"}],
        }

        result = engine.evaluate(config, user_amend_count=3)

        assert result.passed is False
        assert result.forced_interactive is True


class TestEmptyConditions:
    """空 conditions 数组的边界情况"""

    def test_empty_conditions_pass(self, engine, mock_checker):
        """空 conditions 数组时，all() 返回 True，应 auto_pass"""
        config = {
            "mode": "notify_pass",
            "conditions": [],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is True
        assert result.condition_results == []
        assert result.skipped is False
        mock_checker.check.assert_not_called()

    def test_empty_conditions_with_rework_threshold(self, engine, mock_checker):
        """空 conditions + 返工阈值触发时仍应强制交互"""
        config = {
            "mode": "full_auto",
            "conditions": [],
        }

        result = engine.evaluate(config, user_amend_count=3)

        assert result.passed is False
        assert result.forced_interactive is True


class TestConditionExecution:
    """验证 conditions 逐条执行"""

    def test_all_conditions_are_executed(self, engine, mock_checker):
        """即使前面的 condition 失败，后续 condition 仍应执行"""
        mock_checker.check.side_effect = [
            ConditionResult(passed=False, label="条件1", detail="失败"),
            ConditionResult(passed=True, label="条件2"),
            ConditionResult(passed=False, label="条件3", detail="失败"),
        ]
        config = {
            "mode": "notify_pass",
            "conditions": [
                {"type": "path_valid", "label": "条件1", "target": "a"},
                {"type": "file_exists", "label": "条件2", "target": "b"},
                {"type": "path_exists", "label": "条件3", "target": "c"},
            ],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.passed is False
        assert len(result.condition_results) == 3
        # 验证所有 condition 都被执行了
        assert mock_checker.check.call_count == 3

    def test_conditions_passed_to_checker_correctly(self, engine, mock_checker):
        """验证 condition dict 正确传递给 checker"""
        mock_checker.check.return_value = ConditionResult(
            passed=True, label="test"
        )
        condition = {"type": "json_field", "label": "JSON检查", "file": "a.json", "field": "name", "op": "eq", "value": "test"}
        config = {
            "mode": "full_auto",
            "conditions": [condition],
        }

        engine.evaluate(config, user_amend_count=0)

        mock_checker.check.assert_called_once_with(condition)


class TestDefaultMode:
    """mode 字段缺失时的默认行为"""

    def test_missing_mode_defaults_to_human_only(self, engine, mock_checker):
        """mode 字段缺失时默认为 human_only，仍执行 conditions"""
        mock_checker.check.return_value = ConditionResult(passed=True, label="test")
        config = {
            "conditions": [{"type": "path_valid", "label": "test", "target": "x"}],
        }

        result = engine.evaluate(config, user_amend_count=0)

        assert result.skipped is True
        assert result.passed is False
        # conditions 依然被执行
        assert len(result.condition_results) == 1
        mock_checker.check.assert_called_once()
