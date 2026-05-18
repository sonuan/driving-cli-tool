"""Requires_Checker 单元测试

测试前置依赖校验器的各种场景：
- 空 requires 列表
- 全部通过（pass/auto_pass）
- 部分阻断（amend）
- key 不存在
- skipped + blocking/warning 场景
"""

import json
from pathlib import Path

import pytest

from driving_cli.gate.requires_checker import RequiresChecker
from driving_cli.gate.state_manager import GateStateManager


@pytest.fixture
def all_gates():
    """所有 gate 定义列表"""
    return [
        {"id": "GATE-R1", "name": "项目初始化确认"},
        {"id": "GATE-R2", "name": "需求文档确认"},
        {"id": "GATE-R3", "name": "需求拆解确认"},
        {"id": "GATE-R5", "name": "需求拆解文档确认"},
        {"id": "GATE-R6", "name": "技术方案确认"},
    ]


@pytest.fixture
def state_dir(tmp_path):
    """创建临时状态目录"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    return tmp_path


def write_state(state_dir, gates_data):
    """辅助函数：写入 gate-state.json"""
    state_file = state_dir / "docs" / "gate-state.json"
    data = {
        "feature": "test-feature",
        "updated": "2026-05-15T10:00:00Z",
        "gates": gates_data,
    }
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class TestRequiresCheckerEmptyRequires:
    """测试空 requires 列表场景"""

    def test_empty_requires_returns_passed(self, state_dir, all_gates):
        """空 requires 列表应直接返回 passed=True"""
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check([], "blocking")

        assert result.passed is True
        assert result.blocked_by is None
        assert result.message == ""

    def test_none_like_empty_requires(self, state_dir, all_gates):
        """空列表应直接返回 passed=True"""
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check([], "warning")

        assert result.passed is True


class TestRequiresCheckerAllPassed:
    """测试所有前置门禁都通过的场景"""

    def test_all_pass_result(self, state_dir, all_gates):
        """所有前置门禁 last_result 为 pass 时应通过"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
            "GATE-R3": {"last_result": "pass", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is True
        assert result.blocked_by is None

    def test_all_auto_pass_result(self, state_dir, all_gates):
        """所有前置门禁 last_result 为 auto_pass 时应通过"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "auto_pass", "request_count": 1},
            "GATE-R3": {"last_result": "auto_pass", "request_count": 2},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is True

    def test_mixed_pass_and_auto_pass(self, state_dir, all_gates):
        """混合 pass 和 auto_pass 时应通过"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
            "GATE-R3": {"last_result": "auto_pass", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is True


class TestRequiresCheckerBlocked:
    """测试阻断场景"""

    def test_amend_result_blocks(self, state_dir, all_gates):
        """前置门禁 last_result 为 amend 时应阻断"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
            "GATE-R3": {"last_result": "amend", "request_count": 2},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R3"
        assert result.blocked_name == "需求拆解确认"
        assert "GATE-R3" in result.message
        assert "需求拆解确认" in result.message
        assert "未通过" in result.message

    def test_key_not_exist_blocks(self, state_dir, all_gates):
        """前置门禁 key 不存在于 state 中时应阻断"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R3"
        assert result.blocked_name == "需求拆解确认"

    def test_no_state_file_blocks(self, state_dir, all_gates):
        """state 文件不存在时，所有前置门禁都视为不存在，应阻断"""
        # 不写入 state 文件，删除 docs 目录下的文件
        state_file = state_dir / "docs" / "gate-state.json"
        if state_file.exists():
            state_file.unlink()

        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R2"

    def test_first_blocked_gate_reported(self, state_dir, all_gates):
        """多个阻断时应报告第一个阻断的 gate"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "amend", "request_count": 1},
            "GATE-R3": {"last_result": "amend", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R2"

    def test_gate_not_in_all_gates_uses_id_as_name(self, state_dir, all_gates):
        """gate_id 不在 all_gates 列表中时，使用 gate_id 作为 name"""
        write_state(state_dir, {})
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-UNKNOWN"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-UNKNOWN"
        assert result.blocked_name == "GATE-UNKNOWN"
        assert "GATE-UNKNOWN" in result.message


class TestRequiresCheckerSkipped:
    """测试 skipped 状态场景"""

    def test_skipped_with_blocking_level_blocks(self, state_dir, all_gates):
        """前置门禁 skipped + target_level=blocking 时应阻断"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "skipped", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R2"
        assert result.blocked_name == "需求文档确认"
        assert "未通过" in result.message

    def test_skipped_with_warning_level_allows(self, state_dir, all_gates):
        """前置门禁 skipped + target_level=warning 时应允许继续"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "skipped", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2"], "warning")

        assert result.passed is True
        assert result.blocked_by is None

    def test_skipped_mixed_with_pass_blocking(self, state_dir, all_gates):
        """混合 pass 和 skipped，target_level=blocking 时 skipped 应阻断"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
            "GATE-R3": {"last_result": "skipped", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "blocking")

        assert result.passed is False
        assert result.blocked_by == "GATE-R3"

    def test_skipped_mixed_with_pass_warning(self, state_dir, all_gates):
        """混合 pass 和 skipped，target_level=warning 时应全部通过"""
        write_state(state_dir, {
            "GATE-R2": {"last_result": "pass", "request_count": 1},
            "GATE-R3": {"last_result": "skipped", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R2", "GATE-R3"], "warning")

        assert result.passed is True


class TestRequiresCheckerMessageFormat:
    """测试阻断消息格式"""

    def test_blocked_message_format(self, state_dir, all_gates):
        """阻断消息应符合指定格式"""
        write_state(state_dir, {
            "GATE-R5": {"last_result": "amend", "request_count": 1},
        })
        sm = GateStateManager(str(state_dir))
        checker = RequiresChecker(sm, all_gates)

        result = checker.check(["GATE-R5"], "blocking")

        expected_msg = "前置门禁 GATE-R5：需求拆解文档确认 未通过，禁止继续，需先触发并通过该门禁"
        assert result.message == expected_msg
