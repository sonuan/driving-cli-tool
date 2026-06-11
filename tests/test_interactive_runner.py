"""Interactive_Runner 单元测试

测试 action 选择、note 输入、返工提示展示。
Requirements: 6.1-6.5, 13.1, 13.3
"""

from unittest.mock import MagicMock, patch

import pytest

from driving_cli.gate.interactive_runner import InteractiveRunner
from driving_cli.gate.models import ConditionResult


@pytest.fixture(autouse=True)
def mock_isatty():
    """测试环境下模拟 TTY，避免触发 NonTTYInterrupt"""
    with patch("driving_cli.gate.interactive_runner._is_interactive", return_value=True):
        yield


@pytest.fixture
def mock_renderer():
    """创建 mock TemplateRenderer"""
    renderer = MagicMock()
    renderer.render_lines.return_value = "渲染后的模板内容\n第二行"
    # render 透传原始字符串，模拟无变量需要替换的情况
    renderer.render.side_effect = lambda s: s
    return renderer


@pytest.fixture
def runner(mock_renderer):
    """创建 InteractiveRunner 实例"""
    return InteractiveRunner(renderer=mock_renderer)


@pytest.fixture
def sample_gate():
    """创建示例 gate 定义"""
    return {
        "id": "GATE-R5",
        "name": "需求拆解文档确认",
        "template": ["模板第一行", "模板第二行"],
        "actions": {
            "确认": {"next": "通过，进入「技术方案设计」阶段", "requires_note": False},
            "修改": {"next": "修改拆解文档后重新确认", "requires_note": True},
        },
    }


class TestActionSelection:
    """Requirement 6.2: action 选择菜单展示"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_select_first_action_no_note(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """选择第一个 action（requires_note=False）时返回空 note"""
        mock_input.return_value = "1"

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "确认"
        assert note == ""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_select_second_action_with_note(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """Requirement 6.3: 选择 requires_note=True 的 action 时提示输入 note"""
        # 第一次 input 返回选择 "2"，第二次 input 返回 note 内容
        mock_input.side_effect = ["2", "缺少边界条件"]

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "修改"
        assert note == "缺少边界条件"

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_action_choices_format(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """验证 action 选择菜单格式为 'action_key — next_description'"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        # 检查 echo 调用中包含正确格式的选项
        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any(
            "确认 — 通过，进入「技术方案设计」阶段" in text for text in echo_texts
        )
        assert any(
            "修改 — 修改拆解文档后重新确认" in text for text in echo_texts
        )

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_prompt_text_is_correct(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """验证 prompt 文本为 '请选择操作'"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        # 验证 input 被调用，且提示文本包含 "请选择操作"
        first_call = mock_input.call_args_list[0]
        assert "请选择操作" in first_call[0][0]
        assert "输入序号或名称" in first_call[0][0]

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_select_action_by_name(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """支持通过 action 名称选择操作"""
        mock_input.return_value = "确认"

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "确认"
        assert note == ""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_select_action_by_name_case_insensitive(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """action 名称匹配大小写不敏感"""
        mock_input.return_value = "修改"

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "修改"

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_invalid_input_retries(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """无效输入时提示错误并重试"""
        mock_input.side_effect = ["99", "abc", "1"]

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "确认"
        assert mock_input.call_count == 3


class TestNoteInput:
    """Requirement 6.3, 6.4: note 输入逻辑"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_requires_note_true_prompts_for_note(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """requires_note=True 时应提示输入修改说明"""
        mock_input.side_effect = ["2", "需要修改的内容"]

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "修改"
        assert note == "需要修改的内容"
        # 验证提示文字通过 _echo 单独输出
        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("修改说明" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_requires_note_false_returns_empty_note(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """Requirement 6.4: requires_note=False 时 note 为空字符串"""
        mock_input.return_value = "1"

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        assert action_key == "确认"
        assert note == ""
        # 只应有一次 input 调用（选择操作）
        assert mock_input.call_count == 1


class TestReworkHint:
    """Requirement 6.5, 13.1: 返工提示展示"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_rework_hint_displayed_when_amend_count_gte_2(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """Requirement 6.5: user_amend_count >= 2 时展示返工提示"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=2,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("已返工 2 次" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_rework_hint_displayed_when_amend_count_3(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """user_amend_count=3 时也展示返工提示"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=3,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("已返工 3 次" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_no_rework_hint_when_amend_count_below_2(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """user_amend_count < 2 时不展示返工提示"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=1,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert not any("已返工" in text for text in echo_texts)


class TestForcedInteractive:
    """Requirement 13.3: 阈值警告展示"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_forced_interactive_shows_warning(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """forced_interactive=True 时展示阈值警告"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=3,
            forced_interactive=True,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("返工次数已达阈值，强制进入交互模式" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_no_warning_when_not_forced(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """forced_interactive=False 时不展示阈值警告"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert not any("返工次数已达阈值" in text for text in echo_texts)


class TestConditionResultsDisplay:
    """condition 结果展示：说明标题 + 通过显示 ✓，未通过显示 ✗"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_human_only_shows_reference_header(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """skipped=True（human_only）时，说明标题为「供参考，需人工确认」"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=False, label="文件存在"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
            skipped=True,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("供参考，需人工确认" in text for text in echo_texts)
        assert not any("自动检查项" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_all_passed_shows_all_passed_header(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """非 human_only 且全部通过时，说明标题为「已全部通过，需人工确认」"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=True, label="文件存在"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
            skipped=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("已全部通过，需人工确认" in text for text in echo_texts)
        assert not any("存在未通过项" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_some_failed_shows_failed_header(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """非 human_only 且存在未通过项时，说明标题为「存在未通过项，请确认后操作」"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=False, label="文件存在", detail="文件不存在"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
            skipped=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("存在未通过项，请确认后操作" in text for text in echo_texts)
        assert not any("已全部通过" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_passed_conditions_displayed_with_check_prefix(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """通过的 condition 以缩进 ✓ 前缀展示"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=True, label="文件存在"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("✓ 路径合法" in text for text in echo_texts)
        assert any("✓ 文件存在" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_failed_conditions_displayed_with_cross_prefix(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """未通过的 condition 以缩进 ✗ 前缀展示，detail 附加在后"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=False, label="文件存在", detail="文件不存在: /tmp/x"),
            ConditionResult(passed=False, label="目录非空", detail="目录为空"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("✓ 路径合法" in text for text in echo_texts)
        assert any("✗ 文件存在: 文件不存在: /tmp/x" in text for text in echo_texts)
        assert any("✗ 目录非空: 目录为空" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_empty_condition_results_no_output(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """condition_results 为空列表时不输出任何条件行，也不输出标题"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert not any("✗" in text for text in echo_texts)
        assert not any("✓" in text for text in echo_texts)
        assert not any("检查项" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_failed_condition_without_detail(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """失败 condition 无 detail 时只展示 label，不附加冒号"""
        mock_input.return_value = "1"
        condition_results = [
            ConditionResult(passed=False, label="路径合法"),
        ]

        runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("✗ 路径合法" in text for text in echo_texts)
        assert not any("✓ 路径合法" in text for text in echo_texts)


class TestTemplateRendering:
    """Requirement 6.1: 渲染并展示 template 内容"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_template_rendered_and_displayed(
        self, mock_echo, mock_input, runner, sample_gate, mock_renderer
    ):
        """template 内容应通过 renderer 渲染后展示"""
        mock_input.return_value = "1"

        runner.run(
            gate=sample_gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        # 验证 renderer.render_lines 被调用
        mock_renderer.render_lines.assert_called_once_with(["模板第一行", "模板第二行"])
        # 验证渲染结果被 echo
        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        assert any("渲染后的模板内容" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_empty_template_not_displayed(
        self, mock_echo, mock_input, runner, mock_renderer
    ):
        """空 template 时不展示模板内容"""
        mock_input.return_value = "1"
        gate = {
            "id": "GATE-R5",
            "template": [],
            "actions": {
                "确认": {"next": "通过", "requires_note": False},
            },
        }

        runner.run(
            gate=gate,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        mock_renderer.render_lines.assert_not_called()


class TestCompleteFlow:
    """完整交互流程测试"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_full_flow_with_forced_interactive_and_failed_conditions(
        self, mock_echo, mock_input, runner, sample_gate
    ):
        """完整流程：阈值警告 + 返工提示 + 失败条件 + 模板 + 选择 + note"""
        mock_input.side_effect = ["2", "修改原因"]
        condition_results = [
            ConditionResult(passed=True, label="路径合法"),
            ConditionResult(passed=False, label="文件存在", detail="文件缺失"),
        ]

        action_key, note = runner.run(
            gate=sample_gate,
            condition_results=condition_results,
            user_amend_count=3,
            forced_interactive=True,
        )

        assert action_key == "修改"
        assert note == "修改原因"

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        # 验证展示顺序：阈值警告 → 返工提示 → 失败条件 → 模板 → 选项
        warning_idx = next(
            i for i, t in enumerate(echo_texts) if "返工次数已达阈值" in t
        )
        rework_idx = next(
            i for i, t in enumerate(echo_texts) if "已返工 3 次" in t
        )
        failed_idx = next(
            i for i, t in enumerate(echo_texts) if "✗ 文件存在" in t
        )
        template_idx = next(
            i for i, t in enumerate(echo_texts) if "渲染后的模板内容" in t
        )
        action_idx = next(
            i for i, t in enumerate(echo_texts) if "确认 —" in t
        )

        assert warning_idx < rework_idx < failed_idx < template_idx < action_idx


class TestActionNextRendering:
    """验证 action 菜单里 next 字段经过 renderer 渲染"""

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_action_next_is_rendered_via_renderer(
        self, mock_echo, mock_input, mock_renderer
    ):
        """action.next 字符串应通过 renderer.render() 渲染后展示，而非原始字符串"""
        # renderer.render 将 {{$vars.state_file}} 替换为真实路径
        mock_renderer.render.side_effect = lambda s: s.replace(
            "{{$vars.state_file}}", "/features/login/docs/android/state.json"
        )
        mock_input.return_value = "1"

        gate_with_vars = {
            "id": "GATE-R5",
            "template": [],
            "actions": {
                "确认": {
                    "next": "将 `{{$vars.state_file}}` 中 `stages.xxx.status` 更新为 `completed`",
                    "requires_note": False,
                },
            },
        }
        runner = InteractiveRunner(renderer=mock_renderer)
        runner.run(
            gate=gate_with_vars,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        echo_texts = [call[0][0] for call in mock_echo.call_args_list if call[0]]
        # 展示的文本应包含渲染后的路径，而不是原始模板变量
        assert any(
            "/features/login/docs/android/state.json" in text for text in echo_texts
        )
        assert not any("{{$vars.state_file}}" in text for text in echo_texts)

    @patch("driving_cli.gate.interactive_runner._prompt")
    @patch("driving_cli.gate.interactive_runner._echo")
    def test_renderer_render_called_for_each_action(
        self, mock_echo, mock_input, mock_renderer
    ):
        """每个 action 的 next 都应调用 renderer.render()"""
        mock_renderer.render.side_effect = lambda s: s
        mock_input.return_value = "1"

        gate_with_two_actions = {
            "id": "GATE-R5",
            "template": [],
            "actions": {
                "确认": {"next": "next_a", "requires_note": False},
                "修改": {"next": "next_b", "requires_note": True},
            },
        }
        runner = InteractiveRunner(renderer=mock_renderer)
        runner.run(
            gate=gate_with_two_actions,
            condition_results=[],
            user_amend_count=0,
            forced_interactive=False,
        )

        # render 被调用了两次（每个 action 各一次）
        render_calls = [call[0][0] for call in mock_renderer.render.call_args_list]
        assert "next_a" in render_calls
        assert "next_b" in render_calls
