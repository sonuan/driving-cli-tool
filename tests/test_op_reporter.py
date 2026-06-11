"""op_reporter 单元测试

覆盖：
- build_op_payload：字段正确注入，extra 收入嵌套对象
- report_op_event：agent_webhook 未配置/配置时的行为
- _get_webhook_url：读取 agent_webhook
- agent_reporter：薄包装行为验证
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from driving_cli.utils.op_reporter import build_op_payload, report_op_event


# ==================== build_op_payload ====================

class TestBuildOpPayload:
    """build_op_payload 字段注入行为"""

    def test_operation字段正确(self):
        payload = build_op_payload(operation="load_invoked")
        assert payload["operation"] == "load_invoked"

    def test_triggered_at默认为当前北京时间(self):
        payload = build_op_payload(operation="load_invoked")
        assert "/" in payload["triggered_at"]
        assert ":" in payload["triggered_at"]

    def test_triggered_at可手动传入(self):
        payload = build_op_payload(operation="load_invoked", triggered_at="2026/01/01 00:00")
        assert payload["triggered_at"] == "2026/01/01 00:00"

    def test_cli_version默认自动读取(self):
        with patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.2.3"):
            payload = build_op_payload(operation="load_invoked")
        assert payload["cli_version"] == "1.2.3"

    def test_cli_version可手动传入(self):
        payload = build_op_payload(operation="load_invoked", cli_version="9.9.9")
        assert payload["cli_version"] == "9.9.9"

    def test_description字段有值时包含(self):
        payload = build_op_payload(operation="load_invoked", description="会话开启")
        assert payload["description"] == "会话开启"

    def test_description为空时不包含(self):
        payload = build_op_payload(operation="load_invoked", description="")
        assert "description" not in payload

    def test_actor有值时包含(self):
        with patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "张三", "email": ""}):
            payload = build_op_payload(operation="load_invoked")
        assert payload["actor"] == "张三"

    def test_actor为空时不包含(self):
        with patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}):
            payload = build_op_payload(operation="load_invoked")
        assert "actor" not in payload

    def test_branch有值时包含(self):
        with patch("driving_cli.utils.op_reporter._get_git_branch", return_value="feature/my-branch"):
            payload = build_op_payload(operation="load_invoked")
        assert payload["branch"] == "feature/my-branch"

    def test_branch为空时不包含(self):
        with patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""):
            payload = build_op_payload(operation="load_invoked")
        assert "branch" not in payload

    # ---- extra 嵌套对象 ----

    def test_extra收入嵌套对象而非展开(self):
        """extra 字段应收入 extra 嵌套对象，不展开到顶层"""
        payload = build_op_payload(
            operation="load_auto_updated",
            extra={"from_version": "1.0.0", "to_version": "1.1.0"},
        )
        assert "extra" in payload
        assert payload["extra"]["from_version"] == "1.0.0"
        assert payload["extra"]["to_version"] == "1.1.0"
        # 不应展开到顶层
        assert "from_version" not in payload
        assert "to_version" not in payload

    def test_extra中None值过滤(self):
        payload = build_op_payload(
            operation="load_invoked",
            extra={"platform": "android", "with_modules": None},
        )
        assert payload["extra"]["platform"] == "android"
        assert "with_modules" not in payload["extra"]

    def test_extra中空字符串过滤(self):
        payload = build_op_payload(
            operation="load_invoked",
            extra={"platform": "android", "with_modules": ""},
        )
        assert payload["extra"]["platform"] == "android"
        assert "with_modules" not in payload["extra"]

    def test_extra全为空时不含extra字段(self):
        payload = build_op_payload(
            operation="repo_pulled",
            extra={"a": None, "b": ""},
        )
        assert "extra" not in payload

    def test_extra为None时不含extra字段(self):
        payload = build_op_payload(operation="update_completed", extra=None)
        assert "extra" not in payload

    def test_agent_started_extra结构(self):
        payload = build_op_payload(
            operation="agent_started",
            description="子 agent 'android-reviewer' 启动，来源：dev-review 阶段",
            extra={
                "agent_name": "android-reviewer",
                "feature_path": "features/login",
                "source": "dev-review 阶段，由 dev-workflow 触发",
            },
        )
        assert payload["extra"]["agent_name"] == "android-reviewer"
        assert payload["extra"]["feature_path"] == "features/login"

    def test_refine_committed_extra结构(self):
        payload = build_op_payload(
            operation="refine_committed",
            description="skill:android-standard-page — 补充 LiveData 使用规范",
            extra={
                "repo": "driving-base",
                "file": "2026-06-11-skill-xxx.md",
                "target_type": "skill",
                "target_name": "android-standard-page",
                "trigger_source": "gate",
                "trigger_reason": "返工超过 2 次",
            },
        )
        assert payload["extra"]["repo"] == "driving-base"
        assert payload["extra"]["target_type"] == "skill"
        assert payload["extra"]["trigger_source"] == "gate"


# ==================== report_op_event ====================

class TestReportOpEvent:
    """report_op_event 的 webhook 读取与上报行为"""

    def test_webhook未配置时输出警告含agent_webhook(self, capsys):
        """警告文案应提示配置 agent_webhook"""
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value=""):
            report_op_event(operation="load_invoked")
        assert "agent_webhook" in capsys.readouterr().err

    def test_webhook未配置且silent时不输出警告(self, capsys):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value=""):
            report_op_event(operation="load_invoked", silent=True)
        assert capsys.readouterr().err == ""

    def test_webhook已配置时调用report_async(self):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.0.0"):
            report_op_event(operation="load_invoked")
        mock_async.assert_called_once()
        url, payload = mock_async.call_args.args
        assert url == "https://example.com/hook"
        assert payload["operation"] == "load_invoked"

    def test_payload含cli_version和branch(self):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "李四", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value="feature/my-feature"), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.3.7"):
            report_op_event(
                operation="update_completed",
                description="CLI 手动更新：1.0.0 → 1.3.7",
                extra={"from_version": "1.0.0", "to_version": "1.3.7"},
            )
        _, payload = mock_async.call_args.args
        assert payload["cli_version"] == "1.3.7"
        assert payload["branch"] == "feature/my-feature"
        assert payload["actor"] == "李四"
        assert payload["extra"]["from_version"] == "1.0.0"
        assert payload["extra"]["to_version"] == "1.3.7"

    def test_读取webhook失败时静默不崩溃(self, capsys):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", side_effect=Exception("cfg err")):
            try:
                report_op_event(operation="load_invoked")
            except Exception:
                pytest.fail("report_op_event 不应抛出异常")

    def test_load_invoked_silent不输出警告(self, capsys):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value=""):
            report_op_event(operation="load_invoked", silent=True)
        assert capsys.readouterr().err == ""

    def test_repo_pulled_extra含repo_name(self):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.3.7"):
            report_op_event(
                operation="repo_pulled",
                description="仓库 'driving' 拉取成功（分支：main）",
                extra={"repo_name": "driving", "trigger": "pull"},
                silent=True,
            )
        _, payload = mock_async.call_args.args
        assert payload["operation"] == "repo_pulled"
        assert payload["extra"]["repo_name"] == "driving"

    def test_power_pulled_extra含power_name(self):
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.3.7"):
            report_op_event(
                operation="power_pulled",
                description="power 'driving-base' 自动拉取成功",
                extra={"power_name": "driving-base"},
                silent=True,
            )
        _, payload = mock_async.call_args.args
        assert payload["extra"]["power_name"] == "driving-base"


# ==================== _get_webhook_url 读取 agent_webhook ====================

class TestGetWebhookUrl:
    """_get_webhook_url 读取 agent_webhook 的行为"""

    def test_读取agent_webhook成功(self, tmp_path):
        import json as _json
        (tmp_path / "driving.config.json").write_text(
            _json.dumps({
                "version": "2",
                "repos": [],
                "default_commit_message": "msg",
                "update_version_url": "",
                "agent_webhook": "https://custom.hook/agent",
            }),
            encoding="utf-8",
        )
        with patch("driving_cli.utils.op_reporter.find_project_root", return_value=tmp_path):
            from driving_cli.utils.op_reporter import _get_webhook_url
            assert _get_webhook_url() == "https://custom.hook/agent"

    def test_未配置时返回空字符串(self, tmp_path):
        import json as _json
        (tmp_path / "driving.config.json").write_text(
            _json.dumps({
                "version": "2",
                "repos": [],
                "default_commit_message": "msg",
                "update_version_url": "",
            }),
            encoding="utf-8",
        )
        with patch("driving_cli.utils.op_reporter.find_project_root", return_value=tmp_path):
            from driving_cli.utils.op_reporter import _get_webhook_url
            assert _get_webhook_url() == ""

    def test_op_webhook字段不再读取(self, tmp_path):
        """旧的 op_webhook 字段不应被读取（字段已废弃）"""
        import json as _json
        (tmp_path / "driving.config.json").write_text(
            _json.dumps({
                "version": "2",
                "repos": [],
                "default_commit_message": "msg",
                "update_version_url": "",
                "op_webhook": "https://old.hook/op",
            }),
            encoding="utf-8",
        )
        with patch("driving_cli.utils.op_reporter.find_project_root", return_value=tmp_path):
            from driving_cli.utils.op_reporter import _get_webhook_url
            # op_webhook 已废弃，应返回空字符串而非该地址
            assert _get_webhook_url() == ""

    def test_异常时返回空字符串(self):
        with patch("driving_cli.utils.op_reporter.find_project_root", side_effect=Exception("err")):
            from driving_cli.utils.op_reporter import _get_webhook_url
            assert _get_webhook_url() == ""



# ==================== agent_started：直接走 report_op_event ====================

class TestAgentStartedViaOpReporter:
    """driving agent report 直接调 report_op_event 的行为"""

    def test_agent_started_调用report_op_event(self):
        """agent_report 命令应直接上报 operation=agent_started"""
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.3.7"):
            report_op_event(
                operation="agent_started",
                description="子 agent 'android-reviewer' 启动，来源：dev-review 阶段",
                extra={
                    "agent_name": "android-reviewer",
                    "feature_path": "features/login",
                    "source": "dev-review 阶段",
                },
                silent=True,
            )
        _, payload = mock_async.call_args.args
        assert payload["operation"] == "agent_started"
        assert "android-reviewer" in payload["description"]
        assert payload["extra"]["agent_name"] == "android-reviewer"
        assert payload["extra"]["feature_path"] == "features/login"

    def test_agent_started_空feature_path被过滤(self):
        """feature_path=None 时 extra 中不含该字段"""
        with patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://example.com/hook"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter.get_git_user", return_value={"name": "", "email": ""}), \
             patch("driving_cli.utils.op_reporter._get_git_branch", return_value=""), \
             patch("driving_cli.utils.op_reporter._get_cli_version", return_value="1.3.7"):
            report_op_event(
                operation="agent_started",
                description="子 agent 'android-reviewer' 启动",
                extra={
                    "agent_name": "android-reviewer",
                    "feature_path": None,
                    "source": None,
                },
                silent=True,
            )
        _, payload = mock_async.call_args.args
        assert "feature_path" not in payload.get("extra", {})
        assert "source" not in payload.get("extra", {})
