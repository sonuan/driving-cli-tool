"""gate_reporter 单元测试

覆盖 build_report_payload 和 report_gate_event 的核心行为，
重点验证 platform 参数写入 env 字段的正确性。
"""

import pytest
from unittest.mock import patch

from driving_cli.utils.gate_reporter import build_report_payload, report_gate_event


# ==================== build_report_payload ====================


class TestBuildReportPayload:
    """build_report_payload 单元测试"""

    def _base_kwargs(self, **override):
        kwargs = dict(
            gate_id="GATE-R1",
            gate_name="工作区间确认",
            gate_level="blocking",
            result="pass",
            action="确认",
        )
        kwargs.update(override)
        return kwargs

    def test_必填字段正确写入顶层(self):
        payload = build_report_payload(**self._base_kwargs())
        assert payload["gate_id"] == "GATE-R1"
        assert payload["gate_name"] == "工作区间确认"
        assert payload["gate_level"] == "blocking"
        assert payload["last_event"]["result"] == "pass"
        assert payload["last_event"]["action"] == "确认"

    def test_platform有值时写入顶层(self):
        payload = build_report_payload(**self._base_kwargs(platform="android"))
        assert payload["platform"] == "android"
        # platform 不再在 env 内
        assert "platform" not in payload.get("env", {})

    def test_platform为空时不写入顶层(self):
        payload = build_report_payload(**self._base_kwargs(platform=""))
        assert "platform" not in payload

    def test_platform不传时不写入顶层(self):
        payload = build_report_payload(**self._base_kwargs())
        assert "platform" not in payload

    def test_platform与repo和cli_version分离(self):
        payload = build_report_payload(
            **self._base_kwargs(platform="harmony", repo="driving", cli_version="1.2.8")
        )
        # platform 在顶层
        assert payload["platform"] == "harmony"
        # repo/cli_version 仍在 env
        assert payload["env"]["repo"] == "driving"
        assert payload["env"]["cli_version"] == "1.2.8"
        # env 不含 platform
        assert "platform" not in payload["env"]

    def test_platform单独存在时env不存在(self):
        payload = build_report_payload(**self._base_kwargs(platform="iOS"))
        assert payload["platform"] == "iOS"
        assert "env" not in payload

    def test_repo有值时写入env(self):
        payload = build_report_payload(**self._base_kwargs(repo="driving-base"))
        assert payload["env"]["repo"] == "driving-base"

    def test_repo为空时不写入env(self):
        payload = build_report_payload(**self._base_kwargs(repo=""))
        env = payload.get("env", {})
        assert "repo" not in env

    def test_feature_path写入feature字段(self):
        payload = build_report_payload(**self._base_kwargs(feature_path="/path/to/feature"))
        assert payload["feature"] == "/path/to/feature"

    def test_context有值时写入payload(self):
        ctx = {"pr_url": "https://example.com/pr/1"}
        payload = build_report_payload(**self._base_kwargs(context=ctx))
        assert payload["context"] == ctx

    def test_context为空时不写入payload(self):
        payload = build_report_payload(**self._base_kwargs(context=None))
        assert "context" not in payload

    def test_stats有值时过滤None并写入(self):
        stats = {"request_count": 3, "auto_pass_count": None, "user_pass_count": 2, "user_amend_count": 1}
        payload = build_report_payload(**self._base_kwargs(stats=stats))
        assert "stats" in payload
        assert "auto_pass_count" not in payload["stats"]
        assert payload["stats"]["request_count"] == 3

    def test_stats为空时不写入payload(self):
        payload = build_report_payload(**self._base_kwargs(stats=None))
        assert "stats" not in payload

    def test_actor从git_user读取(self):
        with patch(
            "driving_cli.utils.gate_reporter.get_git_user",
            return_value={"name": "张三", "email": "zhangsan@example.com"},
        ):
            payload = build_report_payload(**self._base_kwargs())
        assert payload["actor"] == "张三"

    def test_actor为空时不写入payload(self):
        with patch(
            "driving_cli.utils.gate_reporter.get_git_user",
            return_value={"name": "", "email": ""},
        ):
            payload = build_report_payload(**self._base_kwargs())
        assert "actor" not in payload

    def test_triggered_at有值时使用传入值(self):
        payload = build_report_payload(**self._base_kwargs(triggered_at="2026/06/04 10:00"))
        assert payload["last_event"]["triggered_at"] == "2026/06/04 10:00"

    def test_triggered_at为空时使用当前时间(self):
        with patch("driving_cli.utils.gate_reporter.now_timestamp", return_value="2026/06/04 12:00"):
            payload = build_report_payload(**self._base_kwargs(triggered_at=None))
        assert payload["last_event"]["triggered_at"] == "2026/06/04 12:00"

    @pytest.mark.parametrize("platform", ["android", "iOS", "harmony", "kuikly"])
    def test_所有平台值均正确写入顶层(self, platform):
        payload = build_report_payload(**self._base_kwargs(platform=platform))
        assert payload["platform"] == platform
        assert "platform" not in payload.get("env", {})


# ==================== report_gate_event ====================


class TestReportGateEvent:
    """report_gate_event 集成测试（mock do_post）"""

    def _invoke(self, extra_kwargs=None):
        """调用 report_gate_event，mock 掉 webhook url 和异步上报"""
        captured = {}

        def fake_report_async(url, payload):
            captured["url"] = url
            captured["payload"] = payload

        kwargs = dict(
            gate_id="GATE-R1",
            gate_name="确认",
            gate_level="blocking",
            result="pass",
            action="confirm",
        )
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        with patch(
            "driving_cli.utils.gate_reporter._get_webhook_url",
            return_value="https://example.com/hook",
        ):
            with patch("driving_cli.utils.gate_reporter.report_async", side_effect=fake_report_async):
                with patch(
                    "driving_cli.utils.gate_reporter.get_git_user",
                    return_value={"name": "", "email": ""},
                ):
                    report_gate_event(**kwargs)

        return captured

    def test_platform传入时payload顶层含platform(self):
        captured = self._invoke({"platform": "android"})
        assert captured["payload"]["platform"] == "android"
        assert "platform" not in captured["payload"].get("env", {})

    def test_platform未传时payload顶层不含platform(self):
        captured = self._invoke()
        assert "platform" not in captured.get("payload", {})

    def test_webhook未配置时静默跳过不抛异常(self):
        with patch(
            "driving_cli.utils.gate_reporter._get_webhook_url",
            return_value="",
        ):
            with patch("driving_cli.utils.gate_reporter.get_git_user", return_value={"name": "", "email": ""}):
                # 不应抛出异常
                report_gate_event(
                    gate_id="GATE-R1",
                    gate_name="确认",
                    gate_level="blocking",
                    result="pass",
                    action="confirm",
                )

    def test_gate_state传入时stats写入payload(self):
        gate_state = type(
            "GateState",
            (),
            {
                "request_count": 5,
                "auto_pass_count": 2,
                "user_pass_count": 3,
                "user_amend_count": 1,
            },
        )()
        captured = self._invoke({"gate_state": gate_state})
        assert captured["payload"]["stats"]["request_count"] == 5

    def test_gate_state为None时payload无stats(self):
        captured = self._invoke({"gate_state": None})
        assert "stats" not in captured.get("payload", {})
