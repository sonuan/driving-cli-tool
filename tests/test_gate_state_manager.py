"""Gate_State_Manager 单元测试

测试 GateStateManager 的状态持久化功能，覆盖：
- 文件不存在时初始化
- 记录结果后计数正确
- pass_rate 计算
- history 追加
- JSON 非法时抛出异常
- state_file 属性
- get_gate_state 方法
- save 方法自动创建目录

Requirements: 7.1-7.11, 14.1-14.4
"""

import json
import os

import click
import pytest

from driving_cli.gate.state_manager import GateStateManager


class TestStateFile:
    """测试 state_file 属性 - Requirements 7.1"""

    def test_返回正确路径(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        expected = tmp_path / "docs" / "gate-state.json"
        assert manager.state_file == expected

    def test_相对路径(self):
        manager = GateStateManager("features/login-page")
        from pathlib import Path

        expected = Path("features/login-page") / "docs" / "gate-state.json"
        assert manager.state_file == expected


class TestLoad:
    """测试 load 方法 - Requirements 7.1, 7.2, 14.4"""

    def test_文件不存在时返回初始结构(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data = manager.load()
        assert data == {"feature": "", "updated": "", "gates": {}}

    def test_文件存在时正常加载(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        state_file = docs_dir / "gate-state.json"
        state_data = {
            "feature": "login-page",
            "updated": "2026-05-15T10:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 2,
                    "auto_pass_count": 1,
                    "user_pass_count": 1,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "pass",
                    "history": [
                        {"at": "2026-05-15T08:00:00Z", "action": "auto_pass", "note": ""}
                    ],
                }
            },
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        manager = GateStateManager(str(tmp_path))
        data = manager.load()
        assert data == state_data

    def test_JSON非法时抛出ClickException(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        state_file = docs_dir / "gate-state.json"
        state_file.write_text("这不是有效的JSON{{{", encoding="utf-8")

        manager = GateStateManager(str(tmp_path))
        with pytest.raises(click.ClickException) as exc_info:
            manager.load()
        assert "格式非法" in str(exc_info.value.message)

    def test_空文件时抛出ClickException(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        state_file = docs_dir / "gate-state.json"
        state_file.write_text("", encoding="utf-8")

        manager = GateStateManager(str(tmp_path))
        with pytest.raises(click.ClickException):
            manager.load()


class TestGetGateState:
    """测试 get_gate_state 方法 - Requirements 7.4-7.11"""

    def test_gate不存在时返回默认值(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        state = manager.get_gate_state("GATE-R5")
        assert state.request_count == 0
        assert state.auto_pass_count == 0
        assert state.user_pass_count == 0
        assert state.user_amend_count == 0
        assert state.pass_rate == 0.0
        assert state.last_result == ""
        assert state.history == []

    def test_gate存在时返回正确状态(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        state_file = docs_dir / "gate-state.json"
        state_data = {
            "feature": "login-page",
            "updated": "2026-05-15T10:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 3,
                    "auto_pass_count": 1,
                    "user_pass_count": 1,
                    "user_amend_count": 1,
                    "pass_rate": 0.67,
                    "last_result": "amend",
                    "history": [
                        {"at": "2026-05-15T08:00:00Z", "action": "auto_pass", "note": ""},
                        {"at": "2026-05-15T09:00:00Z", "action": "确认", "note": ""},
                        {"at": "2026-05-15T10:00:00Z", "action": "修改", "note": "需要调整"},
                    ],
                }
            },
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        manager = GateStateManager(str(tmp_path))
        state = manager.get_gate_state("GATE-R5")
        assert state.request_count == 3
        assert state.auto_pass_count == 1
        assert state.user_pass_count == 1
        assert state.user_amend_count == 1
        assert state.pass_rate == 0.67
        assert state.last_result == "amend"
        assert len(state.history) == 3
        assert state.history[0].at == "2026-05-15T08:00:00Z"
        assert state.history[0].action == "auto_pass"
        assert state.history[2].note == "需要调整"


class TestRecordResult:
    """测试 record_result 方法 - Requirements 7.4-7.11"""

    def test_首次记录auto_pass(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "auto_pass", "确认", "")

        data = manager.load()
        gate = data["gates"]["GATE-R5"]
        assert gate["request_count"] == 1
        assert gate["auto_pass_count"] == 1
        assert gate["user_pass_count"] == 0
        assert gate["user_amend_count"] == 0
        assert gate["pass_rate"] == 1.0
        assert gate["last_result"] == "auto_pass"
        assert len(gate["history"]) == 1
        assert gate["history"][0]["action"] == "确认"
        assert gate["history"][0]["note"] == ""
        assert data["updated"] != ""

    def test_记录user_pass(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "pass", "确认", "")

        data = manager.load()
        gate = data["gates"]["GATE-R5"]
        assert gate["request_count"] == 1
        assert gate["auto_pass_count"] == 0
        assert gate["user_pass_count"] == 1
        assert gate["user_amend_count"] == 0
        assert gate["pass_rate"] == 1.0
        assert gate["last_result"] == "pass"

    def test_记录amend(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "amend", "修改", "缺少边界条件")

        data = manager.load()
        gate = data["gates"]["GATE-R5"]
        assert gate["request_count"] == 1
        assert gate["auto_pass_count"] == 0
        assert gate["user_pass_count"] == 0
        assert gate["user_amend_count"] == 1
        assert gate["pass_rate"] == 0.0
        assert gate["last_result"] == "amend"
        assert gate["history"][0]["note"] == "缺少边界条件"

    def test_多次记录后计数正确(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "auto_pass", "确认", "")
        manager.record_result("GATE-R5", "amend", "修改", "需要调整")
        manager.record_result("GATE-R5", "amend", "修改", "再次修改")
        manager.record_result("GATE-R5", "pass", "确认", "")

        data = manager.load()
        gate = data["gates"]["GATE-R5"]
        assert gate["request_count"] == 4
        assert gate["auto_pass_count"] == 1
        assert gate["user_pass_count"] == 1
        assert gate["user_amend_count"] == 2
        assert gate["pass_rate"] == 0.5  # (1 + 1) / 4
        assert gate["last_result"] == "pass"
        assert len(gate["history"]) == 4

    def test_pass_rate计算精度(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "auto_pass", "确认", "")
        manager.record_result("GATE-R5", "pass", "确认", "")
        manager.record_result("GATE-R5", "amend", "修改", "")

        data = manager.load()
        gate = data["gates"]["GATE-R5"]
        # (1 + 1) / 3 = 0.6666...
        assert abs(gate["pass_rate"] - 2.0 / 3.0) < 1e-10

    def test_history追加顺序正确(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "auto_pass", "action1", "note1")
        manager.record_result("GATE-R5", "pass", "action2", "note2")

        data = manager.load()
        history = data["gates"]["GATE-R5"]["history"]
        assert len(history) == 2
        assert history[0]["action"] == "action1"
        assert history[0]["note"] == "note1"
        assert history[1]["action"] == "action2"
        assert history[1]["note"] == "note2"
        # 时间戳格式验证
        assert "T" in history[0]["at"]
        assert "+08:00" in history[0]["at"]

    def test_更新updated字段(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "auto_pass", "确认", "")

        data = manager.load()
        assert data["updated"] != ""
        assert "T" in data["updated"]
        assert "+08:00" in data["updated"]

    def test_不同gate互不影响(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R2", "auto_pass", "确认", "")
        manager.record_result("GATE-R5", "amend", "修改", "需要调整")

        data = manager.load()
        assert data["gates"]["GATE-R2"]["request_count"] == 1
        assert data["gates"]["GATE-R2"]["auto_pass_count"] == 1
        assert data["gates"]["GATE-R2"]["last_result"] == "auto_pass"
        assert data["gates"]["GATE-R5"]["request_count"] == 1
        assert data["gates"]["GATE-R5"]["user_amend_count"] == 1
        assert data["gates"]["GATE-R5"]["last_result"] == "amend"

    def test_传入gate_name时写入name字段(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "pass", "确认", "", gate_name="代码审查")

        data = manager.load()
        assert data["gates"]["GATE-R5"]["name"] == "代码审查"

    def test_不传gate_name时name字段为空字符串(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "pass", "确认", "")

        data = manager.load()
        assert data["gates"]["GATE-R5"]["name"] == ""

    def test_gate_name更新以最新值为准(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "amend", "修改", "", gate_name="旧名称")
        manager.record_result("GATE-R5", "pass", "确认", "", gate_name="新名称")

        data = manager.load()
        assert data["gates"]["GATE-R5"]["name"] == "新名称"

    def test_gate_name为空时不覆盖已有name(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "amend", "修改", "", gate_name="已有名称")
        manager.record_result("GATE-R5", "pass", "确认", "", gate_name="")

        data = manager.load()
        assert data["gates"]["GATE-R5"]["name"] == "已有名称"

    def test_name字段始终排在第一位(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "pass", "确认", "", gate_name="代码审查")

        data = manager.load()
        keys = list(data["gates"]["GATE-R5"].keys())
        assert keys[0] == "name"

    def test_多次记录后name字段仍排在第一位(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        manager.record_result("GATE-R5", "amend", "修改", "", gate_name="旧名称")
        manager.record_result("GATE-R5", "pass", "确认", "", gate_name="新名称")

        data = manager.load()
        keys = list(data["gates"]["GATE-R5"].keys())
        assert keys[0] == "name"
        assert data["gates"]["GATE-R5"]["name"] == "新名称"


class TestSave:
    """测试 save 方法 - Requirements 14.1, 14.2"""

    def test_自动创建docs目录(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data = {"feature": "test", "updated": "", "gates": {}}
        manager.save(data)

        assert (tmp_path / "docs").exists()
        assert (tmp_path / "docs" / "gate-state.json").exists()

    def test_UTF8编码(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data = {"feature": "登录页面", "updated": "", "gates": {}}
        manager.save(data)

        content = manager.state_file.read_bytes()
        # 验证 UTF-8 编码（中文字符不应被 escape）
        assert "登录页面".encode("utf-8") in content

    def test_2space_indent(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data = {"feature": "test", "updated": "", "gates": {"GATE-R5": {}}}
        manager.save(data)

        content = manager.state_file.read_text(encoding="utf-8")
        # 验证 2-space indent
        lines = content.split("\n")
        # 第二行应该以 2 个空格开头
        assert lines[1].startswith("  ")
        # 不应该有 4-space indent 在第二层
        assert not any(line.startswith("    ") and '"feature"' in line for line in lines)

    def test_保存后可正常加载(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data = {
            "feature": "login-page",
            "updated": "2026-05-15T10:00:00Z",
            "gates": {
                "GATE-R5": {
                    "request_count": 1,
                    "auto_pass_count": 1,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "auto_pass",
                    "history": [
                        {"at": "2026-05-15T10:00:00Z", "action": "确认", "note": ""}
                    ],
                }
            },
        }
        manager.save(data)
        loaded = manager.load()
        assert loaded == data

    def test_覆盖已有文件(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        data1 = {"feature": "old", "updated": "", "gates": {}}
        manager.save(data1)

        data2 = {"feature": "new", "updated": "2026-05-15T10:00:00Z", "gates": {}}
        manager.save(data2)

        loaded = manager.load()
        assert loaded["feature"] == "new"

    def test_深层嵌套目录自动创建(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c"
        manager = GateStateManager(str(deep_path))
        data = {"feature": "test", "updated": "", "gates": {}}
        manager.save(data)

        assert manager.state_file.exists()


class TestRoundTrip:
    """测试序列化 round-trip - Requirements 14.2, 14.3"""

    def test_写入后读取等价(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        original = {
            "feature": "login-page",
            "updated": "2026-05-15T10:00:00Z",
            "gates": {
                "GATE-R2": {
                    "request_count": 2,
                    "auto_pass_count": 2,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "auto_pass",
                    "history": [
                        {"at": "2026-05-15T08:00:00Z", "action": "auto_pass", "note": ""},
                        {"at": "2026-05-15T09:00:00Z", "action": "auto_pass", "note": ""},
                    ],
                },
                "GATE-R5": {
                    "request_count": 1,
                    "auto_pass_count": 0,
                    "user_pass_count": 1,
                    "user_amend_count": 0,
                    "pass_rate": 1.0,
                    "last_result": "pass",
                    "history": [
                        {"at": "2026-05-15T10:00:00Z", "action": "确认", "note": ""},
                    ],
                },
            },
        }
        manager.save(original)
        loaded = manager.load()
        assert loaded == original

    def test_更新单个gate不影响其他gate(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        # 先写入两个 gate
        manager.record_result("GATE-R2", "auto_pass", "确认", "")
        manager.record_result("GATE-R5", "pass", "确认", "")

        # 记录 GATE-R2 的状态
        data_before = manager.load()
        gate_r5_before = json.dumps(data_before["gates"]["GATE-R5"], sort_keys=True)

        # 更新 GATE-R2
        manager.record_result("GATE-R2", "amend", "修改", "需要调整")

        # 验证 GATE-R5 未受影响
        data_after = manager.load()
        gate_r5_after = json.dumps(data_after["gates"]["GATE-R5"], sort_keys=True)
        assert gate_r5_before == gate_r5_after


class TestPlatform:
    """测试 --platform 参数对 state_file 路径的影响"""

    def test_不传platform时路径为docs下(self, tmp_path):
        manager = GateStateManager(str(tmp_path))
        expected = tmp_path / "docs" / "gate-state.json"
        assert manager.state_file == expected

    def test_传platform时路径为docs_platform下(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "android")
        expected = tmp_path / "docs" / "android" / "gate-state.json"
        assert manager.state_file == expected

    def test_iOS平台路径正确(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "iOS")
        expected = tmp_path / "docs" / "iOS" / "gate-state.json"
        assert manager.state_file == expected

    def test_harmony平台路径正确(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "harmony")
        expected = tmp_path / "docs" / "harmony" / "gate-state.json"
        assert manager.state_file == expected

    def test_kuikly平台路径正确(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "kuikly")
        expected = tmp_path / "docs" / "kuikly" / "gate-state.json"
        assert manager.state_file == expected

    def test_空字符串platform回退到旧路径(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "")
        expected = tmp_path / "docs" / "gate-state.json"
        assert manager.state_file == expected

    def test_platform存储数据与无platform互不干扰(self, tmp_path):
        manager_android = GateStateManager(str(tmp_path), "android")
        manager_default = GateStateManager(str(tmp_path))

        manager_android.record_result("GATE-R5", "pass", "确认", "")
        manager_default.record_result("GATE-R5", "amend", "修改", "旧路径记录")

        # android 平台数据
        android_state = manager_android.get_gate_state("GATE-R5")
        assert android_state.last_result == "pass"
        assert android_state.user_pass_count == 1
        assert android_state.user_amend_count == 0

        # 默认路径数据不受影响
        default_state = manager_default.get_gate_state("GATE-R5")
        assert default_state.last_result == "amend"
        assert default_state.user_amend_count == 1

    def test_不同平台数据相互独立(self, tmp_path):
        manager_android = GateStateManager(str(tmp_path), "android")
        manager_ios = GateStateManager(str(tmp_path), "iOS")

        manager_android.record_result("GATE-R5", "pass", "确认", "")
        manager_ios.record_result("GATE-R5", "amend", "修改", "iOS修改")

        android_state = manager_android.get_gate_state("GATE-R5")
        assert android_state.last_result == "pass"
        assert android_state.user_amend_count == 0

        ios_state = manager_ios.get_gate_state("GATE-R5")
        assert ios_state.last_result == "amend"
        assert ios_state.user_amend_count == 1

    def test_platform目录自动创建(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "android")
        manager.record_result("GATE-R5", "pass", "确认", "")

        assert (tmp_path / "docs" / "android").exists()
        assert (tmp_path / "docs" / "android" / "gate-state.json").exists()

    def test_platform文件不存在时返回默认state(self, tmp_path):
        manager = GateStateManager(str(tmp_path), "android")
        state = manager.get_gate_state("GATE-R5")
        assert state.request_count == 0
        assert state.history == []
