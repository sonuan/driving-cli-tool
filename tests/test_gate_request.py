"""Gate request / status / history / pass 命令集成测试

使用 CliRunner 测试完整命令流程，mock _collect_all_gates_data 提供 gate 定义。
覆盖 auto_pass 成功、条件失败降级交互、blocked、dry-run、GATE-R1 排除等场景。

Requirements: 1.1-1.8, 2.1-2.8, 3.1-3.8, 8.1-8.7, 9.1-9.6, 10.1-10.5, 11.1-11.4, 12.1-12.6
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.gate.state_manager import GateStateManager


# ==================== Fixtures ====================


@pytest.fixture
def runner():
    return CliRunner()


def _mock_gate_full_auto(path_target="{{path}}"):
    """构造一个 full_auto 模式的 gate 定义"""
    return {
        "id": "GATE-R5",
        "name": "需求拆解文档确认",
        "level": "blocking",
        "requires": [],
        "template": ["模板内容: {{path}}"],
        "actions": {
            "确认": {"next": "通过，进入下一阶段", "requires_note": False},
            "修改": {"next": "修改后重试", "requires_note": True},
        },
        "auto_pass": {
            "mode": "full_auto",
            "conditions": [
                {"type": "path_exists", "label": "路径存在", "target": path_target}
            ],
            "on_pass": {"action": "确认", "next": "自动通过"},
        },
    }


def _mock_gate_notify_pass():
    """构造一个 notify_pass 模式的 gate 定义"""
    return {
        "id": "GATE-R5",
        "name": "需求拆解文档确认",
        "level": "blocking",
        "requires": [],
        "template": ["模板内容: {{path}}"],
        "actions": {
            "确认": {"next": "通过，进入下一阶段", "requires_note": False},
            "修改": {"next": "修改后重试", "requires_note": True},
        },
        "auto_pass": {
            "mode": "notify_pass",
            "conditions": [
                {"type": "path_exists", "label": "路径存在", "target": "{{path}}"}
            ],
            "on_pass": {"action": "确认", "next": "自动通过"},
        },
    }


def _mock_gate_with_requires(requires=None):
    """构造一个有前置依赖的 gate 定义"""
    return {
        "id": "GATE-R5",
        "name": "需求拆解文档确认",
        "level": "blocking",
        "requires": requires or ["GATE-R2"],
        "template": ["模板内容"],
        "actions": {
            "确认": {"next": "通过", "requires_note": False},
            "修改": {"next": "修改后重试", "requires_note": True},
        },
        "auto_pass": {"mode": "human_only"},
    }


def _mock_gate_r2():
    """构造 GATE-R2 定义（用于前置依赖）"""
    return {
        "id": "GATE-R2",
        "name": "需求文档确认",
        "level": "blocking",
        "requires": [],
        "template": ["R2 模板"],
        "actions": {
            "确认": {"next": "通过", "requires_note": False},
        },
        "auto_pass": {"mode": "human_only"},
    }


def _setup_state_file(tmp_path, gates_data):
    """在 tmp_path/docs/gate-state.json 中写入状态数据"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    state_file = docs_dir / "gate-state.json"
    state_file.write_text(
        json.dumps(gates_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state_file


# ==================== Task 14.1: gate request 集成测试 ====================


class TestGateRequestInvalidContext:
    """测试 --context 参数 JSON 格式非法"""

    def test_invalid_context_json(self, runner, tmp_path):
        """Requirements 1.6: 非法 JSON 输出错误并退出"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path), "--context", "{invalid}"],
            )
        assert result.exit_code != 0
        assert "错误：--context 参数不是有效的 JSON 格式" in result.output


class TestGateRequestGateNotFound:
    """测试 gate-id 未找到"""

    def test_gate_not_found(self, runner, tmp_path):
        """Requirements 1.7: 未找到门禁输出错误"""
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-NONEXIST", "--path", str(tmp_path)],
            )
        assert result.exit_code != 0
        assert "错误：未找到门禁 GATE-NONEXIST" in result.output


class TestGateRequestDryRun:
    """测试 dry-run 模式"""

    def test_dry_run_displays_template(self, runner, tmp_path):
        """Requirements 9.3: dry-run 渲染并展示模板"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        assert f"模板内容: {tmp_path}" in result.output

    def test_dry_run_displays_actions(self, runner, tmp_path):
        """Requirements 9.4: dry-run 展示可用操作"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "可用操作：" in result.output
        assert "确认" in result.output
        assert "修改" in result.output

    def test_dry_run_no_state_written(self, runner, tmp_path):
        """Requirements 9.5: dry-run 不写入 state 文件"""
        mock_gate = _mock_gate_full_auto()
        state_file = tmp_path / "docs" / "gate-state.json"
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        assert not state_file.exists()

    def test_dry_run_no_result_json(self, runner, tmp_path):
        """Requirements 9.6: dry-run 不输出 Result_JSON"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        # Result_JSON 包含 "gate_id" 字段，dry-run 不应输出
        assert '"gate_id"' not in result.output


class TestGateRequestBlocked:
    """测试前置依赖阻断"""

    def test_blocked_when_prerequisite_not_met(self, runner, tmp_path):
        """Requirements 2.4, 2.5: 前置门禁未通过时阻断"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        # 不创建 state 文件，GATE-R2 不存在于 state 中 → blocked
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert output_json["result"] == "blocked"
        assert output_json["action"] == "requires_not_met"
        assert "GATE-R2" in output_json["next"]

    def test_blocked_result_json_structure(self, runner, tmp_path):
        """Requirements 8.1, 8.6: blocked Result_JSON 结构正确"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        output_json = json.loads(result.output[result.output.index("{"):])
        # 验证 6 个必需字段
        assert set(output_json.keys()) == {"gate_id", "result", "action", "next", "note", "user_prompt"}
        assert output_json["action"] == "requires_not_met"
        assert output_json["user_prompt"] == "按 next 字段执行后续动作"
        assert output_json["note"] == ""


class TestGateRequestAutoPassFullAuto:
    """测试 auto_pass 成功（full_auto 模式）"""

    def test_auto_pass_full_auto_success(self, runner, tmp_path):
        """Requirements 3.3, 3.6: full_auto 模式 auto_pass 成功"""
        # 创建 path 使 path_exists condition 通过
        mock_gate = _mock_gate_full_auto(path_target="{{path}}")
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert output_json["result"] == "auto_pass"
        assert output_json["action"] == "确认"
        assert output_json["gate_id"] == "GATE-R5"
        assert output_json["user_prompt"] == "按 next 字段执行后续动作"
        assert output_json["note"] == ""

    def test_auto_pass_full_auto_next_field(self, runner, tmp_path):
        """Requirements 8.4: auto_pass 时 next 为 on_pass.next + 。 + actions[action].next"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        output_json = json.loads(result.output[result.output.index("{"):])
        assert "自动通过" in output_json["next"]
        assert "通过，进入下一阶段" in output_json["next"]

    def test_auto_pass_full_auto_state_written(self, runner, tmp_path):
        """Requirements 7.4, 7.5: auto_pass 成功后状态被写入"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        state_file = tmp_path / "docs" / "gate-state.json"
        assert state_file.exists()
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        gate_state = state_data["gates"]["GATE-R5"]
        assert gate_state["request_count"] == 1
        assert gate_state["auto_pass_count"] == 1
        assert gate_state["last_result"] == "auto_pass"


class TestGateRequestAutoPassNotifyPass:
    """测试 auto_pass 成功（notify_pass 模式）"""

    def test_auto_pass_notify_pass_output(self, runner, tmp_path):
        """Requirements 3.7: notify_pass 模式输出通知行 + Result_JSON"""
        mock_gate = _mock_gate_notify_pass()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        # 第一行应该是通知行
        assert "✅" in lines[0]
        assert "自动通过" in lines[0]
        # 空行 + "门禁结果：" + JSON
        assert lines[2].strip() == "门禁结果："
        json_text = "\n".join(lines[3:])
        output_json = json.loads(json_text)
        assert output_json["result"] == "auto_pass"


class TestGateRequestInteractive:
    """测试条件失败降级到交互模式"""

    def test_condition_failure_triggers_interactive(self, runner, tmp_path):
        """Requirements 3.5: 条件失败时进入交互模式"""
        # 使用不存在的路径使 path_exists 失败
        mock_gate = _mock_gate_full_auto(path_target="{{path}}/nonexistent")
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "click.prompt",
            side_effect=[1],  # 选择第一个操作（确认）
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        # 从输出中找到 JSON 块
        output_lines = result.output.strip().split("\n")
        json_start = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(output_lines[json_start:])
        output_json = json.loads(json_text)
        assert output_json["result"] == "pass"
        assert output_json["action"] == "确认"

    def test_interactive_amend_with_note(self, runner, tmp_path):
        """Requirements 6.3, 8.7: 选择需要 note 的操作"""
        mock_gate = _mock_gate_full_auto(path_target="{{path}}/nonexistent")
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "click.prompt",
            side_effect=[2, "需要修改边界条件"],  # 选择第二个操作（修改），输入 note
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        # 找到最后的 JSON 输出
        output_lines = result.output.strip().split("\n")
        # 从后往前找到 JSON 开始
        json_start = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(output_lines[json_start:])
        output_json = json.loads(json_text)
        assert output_json["result"] == "amend"
        assert output_json["action"] == "修改"
        assert output_json["note"] == "需要修改边界条件"


class TestGateRequestReworkThreshold:
    """测试返工阈值强制交互"""

    def test_rework_threshold_forces_interactive(self, runner, tmp_path):
        """Requirements 13.2: user_amend_count >= 3 时强制交互"""
        mock_gate = _mock_gate_full_auto()
        # 预设 state 使 user_amend_count >= 3
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 5,
                    "auto_pass_count": 1,
                    "user_pass_count": 1,
                    "user_amend_count": 3,
                    "pass_rate": 0.4,
                    "last_result": "amend",
                    "history": [],
                }
            },
        }
        _setup_state_file(tmp_path, state_data)

        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "click.prompt",
            side_effect=[1],  # 选择确认
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        # 应该有阈值警告
        assert "返工次数已达阈值" in result.output
        # 最终输出 Result_JSON
        output_lines = result.output.strip().split("\n")
        json_start = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(output_lines[json_start:])
        output_json = json.loads(json_text)
        assert output_json["result"] == "pass"


# ==================== Task 14.2: gate status / history / pass 集成测试 ====================


class TestGateStatus:
    """gate status 命令集成测试"""

    def test_status_no_state_file(self, runner, tmp_path):
        """Requirements 10.5: state 文件不存在时输出提示"""
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "status", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "尚未记录任何门禁状态" in result.output

    def test_status_query_specific_gate(self, runner, tmp_path):
        """Requirements 10.3: 查询指定 gate 状态"""
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 3,
                    "auto_pass_count": 2,
                    "user_pass_count": 1,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "auto_pass",
                    "history": [],
                }
            },
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "status", "GATE-R5", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert output_json["request_count"] == 3
        assert output_json["auto_pass_count"] == 2
        assert output_json["last_result"] == "auto_pass"

    def test_status_query_all_gates(self, runner, tmp_path):
        """Requirements 10.4: 查询所有 gate 状态"""
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {
                "GATE-R2": {
                    "request_count": 1,
                    "auto_pass_count": 1,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "auto_pass",
                    "history": [],
                },
                "GATE-R5": {
                    "request_count": 2,
                    "auto_pass_count": 1,
                    "user_pass_count": 1,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "pass",
                    "history": [],
                },
            },
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "status", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert "GATE-R2" in output_json
        assert "GATE-R5" in output_json

    def test_status_nonexistent_gate_returns_empty(self, runner, tmp_path):
        """查询不存在的 gate 返回空对象"""
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {},
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "status", "GATE-NONEXIST", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert output_json == {}


class TestGateHistory:
    """gate history 命令集成测试"""

    def test_history_no_records(self, runner, tmp_path):
        """Requirements 11.4: 无历史记录时输出提示"""
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 0,
                    "auto_pass_count": 0,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 0.0,
                    "last_result": "",
                    "history": [],
                }
            },
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "history", "GATE-R5", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "门禁 GATE-R5 暂无历史记录" in result.output

    def test_history_with_records(self, runner, tmp_path):
        """Requirements 11.3: 有历史记录时格式化输出"""
        state_data = {
            "feature": "test",
            "updated": "2026-05-15T10:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 3,
                    "auto_pass_count": 1,
                    "user_pass_count": 1,
                    "user_amend_count": 1,
                    "pass_rate": 0.67,
                    "last_result": "pass",
                    "history": [
                        {"at": "2026-05-15T08:00:00Z", "action": "auto_pass", "note": ""},
                        {"at": "2026-05-15T09:00:00Z", "action": "修改", "note": "缺少边界条件"},
                        {"at": "2026-05-15T10:00:00Z", "action": "确认", "note": ""},
                    ],
                }
            },
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "history", "GATE-R5", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "2026-05-15T08:00:00Z" in result.output
        assert "auto_pass" in result.output
        assert "修改" in result.output
        assert "缺少边界条件" in result.output
        assert "确认" in result.output

    def test_history_gate_not_in_state(self, runner, tmp_path):
        """gate 不在 state 中时输出无历史记录"""
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {},
        }
        _setup_state_file(tmp_path, state_data)

        result = runner.invoke(
            cli,
            ["gate", "history", "GATE-R5", "--path", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "门禁 GATE-R5 暂无历史记录" in result.output


class TestGatePass:
    """gate pass 命令集成测试"""

    def test_pass_gate_not_found(self, runner, tmp_path):
        """Requirements 12.1: gate 未找到时输出错误"""
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-NONEXIST", "--path", str(tmp_path)],
            )
        assert result.exit_code != 0
        assert "错误：未找到门禁 GATE-NONEXIST" in result.output

    def test_pass_prerequisites_not_met(self, runner, tmp_path):
        """Requirements 12.6: 前置依赖未满足时输出 blocked"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        output_json = json.loads(result.output[result.output.index("{"):])
        assert output_json["result"] == "blocked"
        assert "GATE-R2" in output_json["next"]

    def test_pass_success(self, runner, tmp_path):
        """Requirements 12.4, 12.5: 前置满足时手动通过"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        # 预设 GATE-R2 已通过
        state_data = {
            "feature": "test",
            "updated": "2026-01-01T00:00:00Z",
            "gates": {
                "GATE-R2": {
                    "request_count": 1,
                    "auto_pass_count": 1,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "auto_pass",
                    "history": [],
                }
            },
        }
        _setup_state_file(tmp_path, state_data)

        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "✅ 已手动通过: GATE-R5" in result.output
        # 解析 Result_JSON（跳过第一行确认行）
        lines = result.output.strip().split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(lines[json_start:])
        output_json = json.loads(json_text)
        assert output_json["result"] == "pass"
        assert output_json["gate_id"] == "GATE-R5"
        assert output_json["user_prompt"] == "按 next 字段执行后续动作"

    def test_pass_with_note(self, runner, tmp_path):
        """Requirements 12.2: 带 --note 参数通过"""
        mock_gate = {
            "id": "GATE-R5",
            "name": "需求拆解文档确认",
            "level": "blocking",
            "requires": [],
            "template": ["模板"],
            "actions": {
                "确认": {"next": "通过", "requires_note": False},
            },
            "auto_pass": {"mode": "human_only"},
        }
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path), "--note", "手动确认通过"],
            )
        assert result.exit_code == 0
        assert "✅ 已手动通过: GATE-R5" in result.output
        # 验证 state 文件中记录了 note
        state_file = tmp_path / "docs" / "gate-state.json"
        assert state_file.exists()
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        gate_state = state_data["gates"]["GATE-R5"]
        assert gate_state["user_pass_count"] == 1
        assert gate_state["history"][-1]["note"] == "手动确认通过"

    def test_pass_no_requires_success(self, runner, tmp_path):
        """无前置依赖的 gate 直接通过"""
        mock_gate = {
            "id": "GATE-R5",
            "name": "需求拆解文档确认",
            "level": "blocking",
            "requires": [],
            "template": ["模板"],
            "actions": {
                "确认": {"next": "通过", "requires_note": False},
            },
            "auto_pass": {"mode": "human_only"},
        }
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ):
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "✅ 已手动通过: GATE-R5" in result.output


# ==================== gate_reporter 上报测试 ====================


class TestGateReporter:
    """gate_reporter 上报模块单元测试"""

    def test_build_report_payload_基本结构(self):
        """build_report_payload 输出包含所有必需字段"""
        from driving_cli.utils.gate_reporter import build_report_payload

        payload = build_report_payload(
            gate_id="GATE-R5",
            gate_name="需求拆解文档确认",
            gate_level="blocking",
            result="pass",
            action="确认",
            feature_path="features/test",
        )
        assert payload["gate_id"] == "GATE-R5"
        assert payload["gate_name"] == "需求拆解文档确认"
        assert payload["gate_level"] == "blocking"
        assert payload["feature"] == "features/test"
        assert payload["last_event"]["result"] == "pass"
        assert payload["last_event"]["action"] == "确认"
        assert "triggered_at" in payload["last_event"]
        assert isinstance(payload["last_event"]["triggered_at"], str)
        # 格式：2026/05/21 21:39
        import re
        assert re.match(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", payload["last_event"]["triggered_at"])

    def test_build_report_payload_context原样上报(self):
        """context 原样上报，--context 传什么就上报什么"""
        from driving_cli.utils.gate_reporter import build_report_payload

        payload = build_report_payload(
            gate_id="GATE-R5",
            gate_name="需求拆解文档确认",
            gate_level="blocking",
            result="pass",
            action="确认",
            context={"review_score": 92, "unanswered_count": 0},
        )
        assert "context" in payload
        assert payload["context"]["review_score"] == 92
        assert payload["context"]["unanswered_count"] == 0

    def test_build_report_payload_无context时不含context字段(self):
        """context 为 None 时 payload 不含 context 字段"""
        from driving_cli.utils.gate_reporter import build_report_payload

        payload = build_report_payload(
            gate_id="GATE-R5",
            gate_name="需求拆解文档确认",
            gate_level="blocking",
            result="pass",
            action="确认",
        )
        assert "context" not in payload

    def test_build_report_payload_stats来自gate_state(self):
        """stats 字段从 gate_state 正确提取"""
        from driving_cli.utils.gate_reporter import build_report_payload, report_gate_event
        from driving_cli.gate.models import GateState

        gate_state = GateState(
            request_count=3,
            auto_pass_count=1,
            user_pass_count=1,
            user_amend_count=1,
            pass_rate=0.67,
            last_result="pass",
        )
        payload = build_report_payload(
            gate_id="GATE-R5",
            gate_name="需求拆解文档确认",
            gate_level="blocking",
            result="pass",
            action="确认",
            stats={
                "request_count": gate_state.request_count,
                "auto_pass_count": gate_state.auto_pass_count,
                "user_pass_count": gate_state.user_pass_count,
                "user_amend_count": gate_state.user_amend_count,
            },
        )
        assert payload["stats"]["request_count"] == 3
        assert payload["stats"]["user_amend_count"] == 1
        assert payload["stats"]["auto_pass_count"] == 1
        assert payload["stats"]["user_pass_count"] == 1

    def test_build_report_payload_blocked时note填入原因(self):
        """blocked 时 note 字段包含阻断原因"""
        from driving_cli.utils.gate_reporter import build_report_payload

        payload = build_report_payload(
            gate_id="GATE-R5",
            gate_name="需求拆解文档确认",
            gate_level="blocking",
            result="blocked",
            action="requires_not_met",
            note="GATE-R2 尚未通过",
        )
        assert payload["last_event"]["result"] == "blocked"
        assert payload["last_event"]["action"] == "requires_not_met"
        assert payload["last_event"]["note"] == "GATE-R2 尚未通过"

    def test_build_report_payload_actor字段来自git(self):
        """actor 字段从 git config 读取 name 和 email"""
        from driving_cli.utils.gate_reporter import build_report_payload
        from unittest.mock import patch

        with patch(
            "driving_cli.utils.gate_reporter.get_git_user",
            return_value={"name": "张三", "email": "zhangsan@example.com"},
        ):
            payload = build_report_payload(
                gate_id="GATE-R5",
                gate_name="需求拆解文档确认",
                gate_level="blocking",
                result="pass",
                action="确认",
            )
        assert "actor" in payload
        assert payload["actor"] == "张三"

    def test_build_report_payload_git读取失败时无actor字段(self):
        """git 读取失败（name 和 email 均为空）时不含 actor 字段"""
        from driving_cli.utils.gate_reporter import build_report_payload
        from unittest.mock import patch

        with patch(
            "driving_cli.utils.gate_reporter.get_git_user",
            return_value={"name": "", "email": ""},
        ):
            payload = build_report_payload(
                gate_id="GATE-R5",
                gate_name="需求拆解文档确认",
                gate_level="blocking",
                result="pass",
                action="确认",
            )
        assert "actor" not in payload

    def test_report_gate_event_异步不阻塞(self, runner, tmp_path):
        """report_gate_event 调用后在合理时间内返回（join timeout=3s）"""
        from driving_cli.utils.gate_reporter import report_gate_event
        from unittest.mock import patch
        import time

        # mock _do_report 避免真实网络请求
        with patch("driving_cli.utils.gate_reporter._do_report"):
            start = time.time()
            report_gate_event(
                gate_id="GATE-R5",
                gate_name="需求拆解文档确认",
                gate_level="blocking",
                result="pass",
                action="确认",
                feature_path=str(tmp_path),
            )
            elapsed = time.time() - start
        # join(timeout=3)，mock 下应远小于 1 秒
        assert elapsed < 1.0

    def test_gate_request_上报被调用_auto_pass(self, runner, tmp_path):
        """gate request auto_pass 时 report_gate_event 被调用"""
        mock_gate = _mock_gate_full_auto()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "driving_cli.commands.gate.report_gate_event"
        ) as mock_report:
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["gate_id"] == "GATE-R5"
        assert call_kwargs["result"] == "auto_pass"
        assert call_kwargs["action"] == "确认"

    def test_gate_request_上报被调用_blocked(self, runner, tmp_path):
        """gate request blocked 时 report_gate_event 被调用"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "driving_cli.commands.gate.report_gate_event"
        ) as mock_report:
            result = runner.invoke(
                cli,
                ["gate", "request", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["result"] == "blocked"
        assert call_kwargs["action"] == "requires_not_met"

    def test_gate_pass_上报被调用_pass(self, runner, tmp_path):
        """gate pass 成功时 report_gate_event 被调用"""
        mock_gate = {
            "id": "GATE-R5",
            "name": "需求拆解文档确认",
            "level": "blocking",
            "requires": [],
            "template": ["模板"],
            "actions": {"确认": {"next": "通过", "requires_note": False}},
            "auto_pass": {"mode": "human_only"},
        }
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "driving_cli.commands.gate.report_gate_event"
        ) as mock_report:
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["gate_id"] == "GATE-R5"
        assert call_kwargs["result"] == "pass"

    def test_gate_pass_上报被调用_blocked(self, runner, tmp_path):
        """gate pass blocked 时 report_gate_event 被调用"""
        mock_gate = _mock_gate_with_requires(["GATE-R2"])
        mock_r2 = _mock_gate_r2()
        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate, mock_r2], "", "按 next 字段执行后续动作", 2),
        ), patch(
            "driving_cli.commands.gate.report_gate_event"
        ) as mock_report:
            result = runner.invoke(
                cli,
                ["gate", "pass", "GATE-R5", "--path", str(tmp_path)],
            )
        assert result.exit_code == 0
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["result"] == "blocked"
        assert call_kwargs["action"] == "requires_not_met"


class TestGateWebhookConfig:
    """gate_webhook 配置控制上报行为"""

    def test_有webhook配置时发送请求(self, tmp_path):
        """gate_webhook 非空时 _do_report 发送 HTTP 请求"""
        from driving_cli.utils.gate_reporter import _do_report

        with patch(
            "driving_cli.utils.gate_reporter._get_webhook_url",
            return_value="https://example.com/webhook",
        ), patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = lambda s, *a: False
            mock_urlopen.return_value.read = lambda: b""
            _do_report({"gate_id": "GATE-R5"})
        mock_urlopen.assert_called_once()

    def test_无webhook配置时不发送请求(self, tmp_path):
        """gate_webhook 为空时 _do_report 直接返回，不发请求"""
        from driving_cli.utils.gate_reporter import _do_report

        with patch(
            "driving_cli.utils.gate_reporter._get_webhook_url",
            return_value="",
        ), patch("urllib.request.urlopen") as mock_urlopen:
            _do_report({"gate_id": "GATE-R5"})
        mock_urlopen.assert_not_called()

    def test_get_webhook_url_从config读取(self, tmp_path):
        """_get_webhook_url 从 driving.config.json 的 gate_webhook 字段读取"""
        from driving_cli.utils.gate_reporter import _get_webhook_url
        from driving_cli.models.config import DrivingConfig

        mock_config = DrivingConfig(
            version="2",
            repos=[],
            default_commit_message="update",
            update_version_url="",
            gate_webhook="https://example.com/my-webhook",
        )
        with patch(
            "driving_cli.utils.gate_reporter.find_project_root",
            return_value=tmp_path,
        ), patch(
            "driving_cli.utils.gate_reporter.ConfigManager"
        ) as mock_cm:
            mock_cm.return_value.load.return_value = mock_config
            url = _get_webhook_url()
        assert url == "https://example.com/my-webhook"

    def test_get_webhook_url_未配置时返回空字符串(self, tmp_path):
        """gate_webhook 未配置时 _get_webhook_url 返回空字符串"""
        from driving_cli.utils.gate_reporter import _get_webhook_url
        from driving_cli.models.config import DrivingConfig

        mock_config = DrivingConfig(
            version="2",
            repos=[],
            default_commit_message="update",
            update_version_url="",
            gate_webhook="",
        )
        with patch(
            "driving_cli.utils.gate_reporter.find_project_root",
            return_value=tmp_path,
        ), patch(
            "driving_cli.utils.gate_reporter.ConfigManager"
        ) as mock_cm:
            mock_cm.return_value.load.return_value = mock_config
            url = _get_webhook_url()
        assert url == ""
