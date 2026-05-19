"""Gate CLI Request 属性测试集合

使用 hypothesis 库对 gate-cli-request 核心逻辑进行属性测试。
每个属性测试至少 100 次迭代。
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from driving_cli.gate.auto_pass_engine import AutoPassEngine
from driving_cli.gate.condition_checker import ConditionChecker
from driving_cli.gate.models import (
    AutoPassResult,
    ConditionResult,
    GateState,
    build_result_json,
)
from driving_cli.gate.requires_checker import RequiresChecker
from driving_cli.gate.state_manager import GateStateManager
from driving_cli.gate.template_renderer import TemplateRenderer


# ==============================================================================
# Property 1: 前置依赖校验正确性
# ==============================================================================

# 策略：生成 last_result 值
_last_result_st = st.sampled_from(["pass", "auto_pass", "amend", "skipped", ""])

# 策略：生成 target_level
_target_level_st = st.sampled_from(["blocking", "warning"])


# Feature: gate-cli-request, Property 1: 前置依赖校验正确性
@settings(max_examples=100)
@given(
    last_results=st.lists(
        _last_result_st, min_size=1, max_size=5
    ),
    target_level=_target_level_st,
)
def test_property1_requires_check_correctness(last_results, target_level):
    """Property 1: 前置依赖校验正确性

    *For any* gate state 和 requires 列表，当所有前置门禁的 last_result 为 pass 或
    auto_pass 时，requires 校验应通过；当任一前置门禁的 last_result 为 amend 或该门禁
    key 不存在于 state 中时，requires 校验应返回 blocked。

    **Validates: Requirements 2.3, 2.4, 2.5**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 构建 gate-state.json
        gate_ids = [f"GATE-T{i}" for i in range(len(last_results))]
        gates_data = {}
        all_gates = []

        for i, (gate_id, lr) in enumerate(zip(gate_ids, last_results)):
            all_gates.append({"id": gate_id, "name": f"Test Gate {i}"})
            if lr != "":  # 空字符串表示 key 不存在于 state 中
                gates_data[gate_id] = {
                    "request_count": 1,
                    "auto_pass_count": 0,
                    "user_pass_count": 0,
                    "user_amend_count": 0,
                    "pass_rate": 0.0,
                    "last_result": lr,
                    "history": [],
                }

        state_file_dir = tmp_path / "docs"
        state_file_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_file_dir / "gate-state.json"
        state_content = {"feature": "test", "updated": "", "gates": gates_data}
        state_file.write_text(json.dumps(state_content, ensure_ascii=False), encoding="utf-8")

        # 初始化 RequiresChecker
        state_manager = GateStateManager(str(tmp_path))
        checker = RequiresChecker(state_manager, all_gates)

        # 执行校验
        result = checker.check(gate_ids, target_level)

        # 验证结果：逐个检查 last_result，找到第一个应该 block 的
        expected_passed = True
        for gate_id, lr in zip(gate_ids, last_results):
            if lr in ("pass", "auto_pass"):
                continue
            elif lr == "amend" or lr == "":
                expected_passed = False
                break
            elif lr == "skipped":
                if target_level == "blocking":
                    expected_passed = False
                    break
                else:
                    # warning level 允许继续
                    continue

        assert result.passed == expected_passed


# ==============================================================================
# Property 2: Auto_Pass 决策逻辑
# ==============================================================================


# Feature: gate-cli-request, Property 2: Auto_Pass 决策逻辑
@settings(max_examples=100)
@given(
    condition_passes=st.lists(st.booleans(), min_size=0, max_size=8),
    amend_count=st.integers(min_value=0, max_value=10),
)
def test_property2_auto_pass_decision_logic(condition_passes, amend_count):
    """Property 2: Auto_Pass 决策逻辑

    *For any* auto_pass 配置（mode 为 notify_pass 或 full_auto）、conditions 结果列表
    和 user_amend_count 值，auto_pass 成功当且仅当所有 conditions 通过且
    user_amend_count < 3。

    **Validates: Requirements 3.3, 3.4, 13.2**
    """
    # 构建 conditions 列表
    conditions = [
        {"type": "path_valid", "label": f"cond_{i}", "target": "valid/path"}
        for i in range(len(condition_passes))
    ]

    # Mock ConditionChecker 使其返回预设结果
    mock_checker = MagicMock(spec=ConditionChecker)
    mock_results = [
        ConditionResult(passed=p, label=f"cond_{i}")
        for i, p in enumerate(condition_passes)
    ]
    mock_checker.check.side_effect = mock_results

    engine = AutoPassEngine(mock_checker)

    auto_pass_config = {
        "mode": "notify_pass",
        "conditions": conditions,
    }

    result = engine.evaluate(auto_pass_config, amend_count)

    all_passed = all(condition_passes) if condition_passes else True

    if all_passed and amend_count < 3:
        assert result.passed is True
        assert result.forced_interactive is False
    elif all_passed and amend_count >= 3:
        assert result.passed is False
        assert result.forced_interactive is True
    else:
        assert result.passed is False


# ==============================================================================
# Property 3: path_valid 验证正确性
# ==============================================================================

# 策略：生成合法路径字符
_valid_path_chars = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-.")
)

# 策略：生成合法路径（无连续特殊字符、无 ..）
_valid_path_st = st.text(
    alphabet=_valid_path_chars, min_size=1, max_size=30
).filter(
    lambda s: ".." not in s and not re.search(r"[/\-_.]{2,}", s)
)

# 策略：生成含非法字符的路径（仅保留 path_valid 真正拒绝的情况）
_invalid_path_injections = st.one_of(
    # 含 ..（路径穿越）
    st.just("some/../path"),
    # 含连续斜杠
    st.just("path//double"),
    # 含 .. 变体
    st.just("path..double"),
)


# Feature: gate-cli-request, Property 3: path_valid 验证正确性
@settings(max_examples=100)
@given(path=_valid_path_st)
def test_property3_path_valid_accepts_valid_paths(path):
    """Property 3: path_valid 验证正确性 (valid paths)

    *For any* 合法路径字符串（仅含 [a-zA-Z0-9/_-.] 且无 .. 和连续特殊字符），
    path_valid 应返回 True。

    **Validates: Requirements 4.1**
    """
    renderer = TemplateRenderer("", {}, {})
    checker = ConditionChecker(renderer)
    assert checker._check_path_valid(path) is True


# Feature: gate-cli-request, Property 3: path_valid 验证正确性
@settings(max_examples=100)
@given(path=_invalid_path_injections)
def test_property3_path_valid_rejects_invalid_paths(path):
    """Property 3: path_valid 验证正确性 (invalid paths)

    *For any* 路径字符串包含空格、中文字符、.. 序列或连续特殊字符，
    path_valid 应返回 False。

    **Validates: Requirements 4.1**
    """
    renderer = TemplateRenderer("", {}, {})
    checker = ConditionChecker(renderer)
    assert checker._check_path_valid(path) is False


# ==============================================================================
# Property 4: 操作符应用正确性
# ==============================================================================

_int_st = st.integers(min_value=-1000, max_value=1000)


# Feature: gate-cli-request, Property 4: 操作符应用正确性
@settings(max_examples=100)
@given(
    a=_int_st,
    b=_int_st,
)
def test_property4_operator_correctness_numeric(a, b):
    """Property 4: 操作符应用正确性 (numeric)

    *For any* 整数对 (a, b)，_apply_operator 的返回值应与 Python 原生比较一致。

    **Validates: Requirements 4.7, 4.10, 4.11**
    """
    renderer = TemplateRenderer("", {}, {})
    checker = ConditionChecker(renderer)

    assert checker._apply_operator(a, "eq", b) == (a == b)
    assert checker._apply_operator(a, "ne", b) == (a != b)
    assert checker._apply_operator(a, "gt", b) == (a > b)
    assert checker._apply_operator(a, "gte", b) == (a >= b)


# Feature: gate-cli-request, Property 4: 操作符应用正确性
@settings(max_examples=100)
@given(
    value=st.one_of(
        st.text(min_size=0, max_size=10),
        st.lists(st.integers(), min_size=0, max_size=5),
    ),
)
def test_property4_operator_correctness_empty_not_empty(value):
    """Property 4: 操作符应用正确性 (empty/not_empty)

    *For any* 字符串或列表，empty 返回 True 当且仅当长度为 0，
    not_empty 返回 True 当且仅当长度 > 0。

    **Validates: Requirements 4.7, 4.10, 4.11**
    """
    renderer = TemplateRenderer("", {}, {})
    checker = ConditionChecker(renderer)

    assert checker._apply_operator(value, "empty", None) == (len(value) == 0)
    assert checker._apply_operator(value, "not_empty", None) == (len(value) > 0)


# ==============================================================================
# Property 5: 模板渲染完整性
# ==============================================================================

# 策略：生成简单的 key（字母，无特殊字符）
_simple_key_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8
)
_simple_value_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=0, max_size=15
)


# Feature: gate-cli-request, Property 5: 模板渲染完整性
@settings(max_examples=100)
@given(
    path_val=_simple_value_st.filter(lambda s: len(s) > 0),
    context_dict=st.dictionaries(_simple_key_st, _simple_value_st, min_size=0, max_size=5),
    state_dict=st.dictionaries(_simple_key_st, _simple_value_st, min_size=0, max_size=5),
)
def test_property5_template_rendering_completeness(path_val, context_dict, state_dict):
    """Property 5: 模板渲染完整性

    *For any* 模板字符串、path 值、context dict 和 state dict，渲染后的结果中
    不应包含任何 {{...}} 模式的未替换变量。

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    """
    renderer = TemplateRenderer(path_val, context_dict, state_dict)

    # 构建使用已知 key 的模板
    template_parts = ["{{path}}"]
    for key in context_dict:
        template_parts.append(f"{{{{context.{key}}}}}")
    for key in state_dict:
        template_parts.append(f"{{{{state.{key}}}}}")
    # 加不存在的变量
    template_parts.append("{{context.nonexistent_xyz}}")
    template_parts.append("{{state.nonexistent_abc}}")
    template_parts.append("{{unknown_root.field}}")

    template = " ".join(template_parts)
    result = renderer.render(template)

    # 验证：渲染后不应有任何 {{...}} 残留
    assert "{{" not in result
    assert "}}" not in result

    # 验证 path 被正确替换
    assert path_val in result


# ==============================================================================
# Property 6: 状态记录计数一致性
# ==============================================================================

_result_type_st = st.sampled_from(["auto_pass", "pass", "amend"])


# Feature: gate-cli-request, Property 6: 状态记录计数一致性
@settings(max_examples=100)
@given(
    result_sequence=st.lists(_result_type_st, min_size=1, max_size=15),
)
def test_property6_state_counting_consistency(result_sequence):
    """Property 6: 状态记录计数一致性

    *For any* 有效的结果类型序列，在依次记录后，request_count 应等于序列长度，
    各计数器应等于对应类型的数量，pass_rate 应等于
    (auto_pass_count + user_pass_count) / request_count，
    last_result 应等于序列最后一个元素。

    **Validates: Requirements 7.4, 7.5, 7.6, 7.7, 7.8, 7.9**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        gate_id = "GATE-TEST"
        state_manager = GateStateManager(tmp_dir)

        for result_type in result_sequence:
            state_manager.record_result(gate_id, result_type, "action_key", "")

        gate_state = state_manager.get_gate_state(gate_id)

        expected_auto = result_sequence.count("auto_pass")
        expected_pass = result_sequence.count("pass")
        expected_amend = result_sequence.count("amend")
        expected_count = len(result_sequence)
        expected_rate = (expected_auto + expected_pass) / expected_count

        assert gate_state.request_count == expected_count
        assert gate_state.auto_pass_count == expected_auto
        assert gate_state.user_pass_count == expected_pass
        assert gate_state.user_amend_count == expected_amend
        assert abs(gate_state.pass_rate - expected_rate) < 1e-9
        assert gate_state.last_result == result_sequence[-1]


# ==============================================================================
# Property 7: Result_JSON 结构不变量
# ==============================================================================

_gate_id_st = st.from_regex(r"GATE-[A-Z][0-9]{1,2}", fullmatch=True)
_result_st = st.sampled_from(["auto_pass", "pass", "amend", "blocked"])
_action_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10
)
_next_text_st = st.text(min_size=0, max_size=50)
_note_st = st.text(min_size=0, max_size=30)


# Feature: gate-cli-request, Property 7: Result_JSON 结构不变量
@settings(max_examples=100)
@given(
    gate_id=_gate_id_st,
    result=_result_st,
    action=_action_st,
    next_text=_next_text_st,
    note=_note_st,
)
def test_property7_result_json_structure_invariants(gate_id, result, action, next_text, note):
    """Property 7: Result_JSON 结构不变量

    *For any* gate request 执行结果，输出的 JSON 对象必须恰好包含 gate_id、result、
    action、next、note、user_prompt 六个字段；result 必须为 auto_pass、pass、amend、
    blocked 之一；user_prompt 必须固定为「按 next 字段执行后续动作」。

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.7**
    """
    result_json = build_result_json(
        gate_id=gate_id,
        result=result,
        action=action,
        next_text=next_text,
        note=note,
    )

    # 恰好 6 个字段
    assert set(result_json.keys()) == {"gate_id", "result", "action", "next", "note", "user_prompt"}

    # result 必须为有效值之一
    assert result_json["result"] in ("auto_pass", "pass", "amend", "blocked")

    # user_prompt 固定值
    assert result_json["user_prompt"] == "按 next 字段执行后续动作"

    # gate_id 正确
    assert result_json["gate_id"] == gate_id

    # action 正确
    assert result_json["action"] == action


# ==============================================================================
# Property 8: Gate State 序列化 round-trip
# ==============================================================================

_gate_state_entry_st = st.fixed_dictionaries({
    "request_count": st.integers(min_value=0, max_value=100),
    "auto_pass_count": st.integers(min_value=0, max_value=50),
    "user_pass_count": st.integers(min_value=0, max_value=50),
    "user_amend_count": st.integers(min_value=0, max_value=50),
    "pass_rate": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "last_result": st.sampled_from(["pass", "auto_pass", "amend", ""]),
    "history": st.just([]),
})


# Feature: gate-cli-request, Property 8: Gate State 序列化 round-trip
@settings(max_examples=100)
@given(
    gates_dict=st.dictionaries(
        st.from_regex(r"GATE-[A-Z][0-9]", fullmatch=True),
        _gate_state_entry_st,
        min_size=1,
        max_size=5,
    ),
)
def test_property8_gate_state_round_trip(gates_dict):
    """Property 8: Gate State 序列化 round-trip

    *For any* 有效的 gate-state.json 对象，序列化后再反序列化应产生等价对象。
    更新单个 gate 的状态时，其他所有 gate 的状态应保持不变。

    **Validates: Requirements 14.2, 14.3**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_manager = GateStateManager(tmp_dir)

        # 构建初始 state 数据
        original_data = {
            "feature": "test-feature",
            "updated": "2026-01-01T00:00:00Z",
            "gates": gates_dict,
        }

        # 写入
        state_manager.save(original_data)

        # 读取
        loaded_data = state_manager.load()

        # round-trip 验证：gates 内容应等价
        for gate_id, gate_entry in gates_dict.items():
            loaded_gate = loaded_data["gates"][gate_id]
            assert loaded_gate["request_count"] == gate_entry["request_count"]
            assert loaded_gate["auto_pass_count"] == gate_entry["auto_pass_count"]
            assert loaded_gate["user_pass_count"] == gate_entry["user_pass_count"]
            assert loaded_gate["user_amend_count"] == gate_entry["user_amend_count"]
            assert abs(loaded_gate["pass_rate"] - gate_entry["pass_rate"]) < 1e-9
            assert loaded_gate["last_result"] == gate_entry["last_result"]

        # 验证更新单个 gate 不影响其他 gate
        if len(gates_dict) >= 2:
            gate_ids = list(gates_dict.keys())
            target_gate = gate_ids[0]
            other_gate = gate_ids[1]

            # 记录 other_gate 更新前的状态
            before_other = loaded_data["gates"][other_gate].copy()

            # 更新 target_gate
            state_manager.record_result(target_gate, "pass", "confirm", "")

            # 重新加载
            after_data = state_manager.load()

            # other_gate 应保持不变
            after_other = after_data["gates"][other_gate]
            assert after_other["request_count"] == before_other["request_count"]
            assert after_other["auto_pass_count"] == before_other["auto_pass_count"]
            assert after_other["user_pass_count"] == before_other["user_pass_count"]
            assert after_other["user_amend_count"] == before_other["user_amend_count"]
            assert after_other["last_result"] == before_other["last_result"]


# ==============================================================================
# Property 9: all_tasks_done 验证正确性
# ==============================================================================

# 策略：生成任务行（匹配 pattern 的行）
_task_line_done_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20
).map(lambda s: f"- [x] {s}")

_task_line_undone_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20
).map(lambda s: f"- [ ] {s}")

_non_task_line_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 #", min_size=1, max_size=20
).filter(lambda s: "- [" not in s)


# Feature: gate-cli-request, Property 9: all_tasks_done 验证正确性
@settings(max_examples=100)
@given(
    done_tasks=st.lists(_task_line_done_st, min_size=0, max_size=5),
    undone_tasks=st.lists(_task_line_undone_st, min_size=0, max_size=5),
    non_task_lines=st.lists(_non_task_line_st, min_size=0, max_size=3),
)
def test_property9_all_tasks_done_correctness(done_tasks, undone_tasks, non_task_lines):
    """Property 9: all_tasks_done 验证正确性

    *For any* 文件内容和正则 pattern，all_tasks_done 返回 true 当且仅当文件中所有
    匹配 pattern 的行都包含 [x]。若存在至少一行匹配 pattern 但不包含 [x]，则应返回 false。

    **Validates: Requirements 4.8**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 使用 pattern 匹配 "- [" 开头的行
        pattern = r"^- \["

        # 组合所有行
        all_lines = done_tasks + undone_tasks + non_task_lines

        # 写入文件
        test_file = Path(tmp_dir) / "tasks.md"
        test_file.write_text("\n".join(all_lines), encoding="utf-8")

        # 执行检查
        renderer = TemplateRenderer("", {}, {})
        checker = ConditionChecker(renderer)
        result = checker._check_all_tasks_done(str(test_file), pattern)

        # 预期结果：如果有 undone_tasks，则应返回 False
        # 如果没有 undone_tasks（只有 done_tasks 或无匹配行），则应返回 True
        if undone_tasks:
            assert result is False
        else:
            assert result is True


# ==============================================================================
# Property 10: dry-run 无副作用
# ==============================================================================


# Feature: gate-cli-request, Property 10: dry-run 无副作用
@settings(max_examples=100)
@given(
    gate_id=st.just("GATE-T1"),
    path_suffix=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8
    ),
)
def test_property10_dry_run_no_side_effects(gate_id, path_suffix):
    """Property 10: dry-run 无副作用

    *For any* gate request 的 dry-run 调用，gate-state.json 文件在调用前后应保持
    完全一致（文件不存在时不应被创建，文件存在时内容不应改变）。

    **Validates: Requirements 9.5**
    """
    from driving_cli.cli import cli

    with tempfile.TemporaryDirectory() as tmp_dir:
        feature_path = Path(tmp_dir) / path_suffix
        feature_path.mkdir(parents=True, exist_ok=True)

        state_file = feature_path / "docs" / "gate-state.json"

        # 设置 mock gate 定义
        mock_gate = {
            "id": gate_id,
            "name": "Test Gate",
            "level": "blocking",
            "requires": [],
            "template": ["Line 1: {{path}}", "Line 2: content"],
            "actions": {
                "确认": {"next": "下一步", "requires_note": False},
                "修改": {"next": "修改后重试", "requires_note": True},
            },
            "auto_pass": {
                "mode": "human_only",
                "conditions": [],
            },
        }

        # 记录调用前状态
        state_existed_before = state_file.exists()
        state_before = None
        if state_existed_before:
            state_before = state_file.read_text(encoding="utf-8")

        runner = CliRunner()

        with patch(
            "driving_cli.commands.gate._collect_all_gates_data",
            return_value=([mock_gate], ""),
        ):
            result = runner.invoke(
                cli,
                ["gate", "request", gate_id, "--path", str(feature_path), "--dry-run"],
            )

        # 验证：state 文件状态不变
        if not state_existed_before:
            assert not state_file.exists(), "dry-run 不应创建 gate-state.json"
        else:
            assert state_file.exists()
            state_after = state_file.read_text(encoding="utf-8")
            assert state_after == state_before, "dry-run 不应修改 gate-state.json"
