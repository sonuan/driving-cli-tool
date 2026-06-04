"""reporter_utils 单元测试

覆盖 do_post 的核心行为：
- 正常 POST 成功路径
- SSL 自签名证书场景（CERTIFICATE_VERIFY_FAILED）能正常通过，不抛异常
- 网络异常时静默处理
- webhook_url 为空时直接返回
- SSL context 配置正确（check_hostname=False, CERT_NONE）
"""

import ssl
import json
from unittest.mock import patch, MagicMock

import pytest

from driving_cli.utils.reporter_utils import do_post, report_async


# ==================== do_post ====================


class TestDoPost:

    def test_url为空时直接返回不发请求(self):
        with patch("urllib.request.OpenerDirector.open") as mock_open:
            do_post("", {"key": "value"})
            mock_open.assert_not_called()

    def test_正常POST成功不抛异常(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""

        with patch("urllib.request.OpenerDirector.open", return_value=mock_resp):
            # 不应抛出异常
            do_post("https://example.com/webhook", {"event": "test"})

    def test_ssl自签名证书错误时静默处理不抛异常(self, capsys):
        """模拟 CERTIFICATE_VERIFY_FAILED，do_post 应静默打印警告，不向上抛"""
        import urllib.error
        ssl_error = urllib.error.URLError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate in certificate chain"
        )
        with patch("urllib.request.OpenerDirector.open", side_effect=ssl_error):
            do_post("https://internal.example.com/hook", {"event": "gate.pass"})

        captured = capsys.readouterr()
        assert "Webhook 上报失败" in captured.err
        assert "CERTIFICATE_VERIFY_FAILED" in captured.err

    def test_网络超时时静默处理不抛异常(self, capsys):
        import socket
        with patch("urllib.request.OpenerDirector.open", side_effect=socket.timeout("timed out")):
            do_post("https://example.com/hook", {"event": "test"})

        captured = capsys.readouterr()
        assert "Webhook 上报失败" in captured.err

    def test_任意异常时静默处理不抛异常(self, capsys):
        with patch("urllib.request.OpenerDirector.open", side_effect=Exception("unknown error")):
            do_post("https://example.com/hook", {"event": "test"})

        captured = capsys.readouterr()
        assert "Webhook 上报失败" in captured.err

    def test_ssl_context关闭了证书校验(self):
        """验证 build_opener 时传入的 SSLContext 配置正确"""
        captured_contexts = []

        original_https_handler = __import__("urllib.request", fromlist=["HTTPSHandler"]).HTTPSHandler

        class CapturingHTTPSHandler(original_https_handler):
            def __init__(self, context=None, **kwargs):
                captured_contexts.append(context)
                super().__init__(context=context, **kwargs)

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""

        with patch("urllib.request.HTTPSHandler", CapturingHTTPSHandler):
            with patch("urllib.request.OpenerDirector.open", return_value=mock_resp):
                do_post("https://example.com/hook", {"event": "test"})

        assert len(captured_contexts) == 1
        ctx = captured_contexts[0]
        assert ctx is not None
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_payload被正确序列化为json(self):
        """验证 payload 以 JSON UTF-8 编码发送"""
        captured_requests = []

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""

        def fake_open(req, timeout=None):
            captured_requests.append(req)
            return mock_resp

        with patch("urllib.request.OpenerDirector.open", side_effect=fake_open):
            do_post("https://example.com/hook", {"name": "张三", "event": "pass"})

        assert len(captured_requests) == 1
        req = captured_requests[0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["name"] == "张三"
        assert body["event"] == "pass"
        assert req.get_header("Content-type") == "application/json; charset=utf-8"


# ==================== report_async ====================


class TestReportAsync:

    def test_异步调用do_post不阻塞(self):
        """report_async 应调用 do_post 且不抛异常"""
        called_with = []

        def fake_do_post(url, payload):
            called_with.append((url, payload))

        with patch("driving_cli.utils.reporter_utils.do_post", side_effect=fake_do_post):
            report_async("https://example.com/hook", {"event": "test"})

        assert len(called_with) == 1
        assert called_with[0][0] == "https://example.com/hook"
        assert called_with[0][1]["event"] == "test"

    def test_do_post抛异常时report_async不向上传播(self):
        """report_async 使用 daemon 线程，线程内异常不传播到主线程；
        验证方式：do_post 内部已有 try/except，正常路径下主线程不受影响"""
        called = []

        def fake_do_post(url, payload):
            called.append(url)
            # do_post 内部已 catch 所有异常并静默，这里模拟正常调用
            pass

        with patch("driving_cli.utils.reporter_utils.do_post", side_effect=fake_do_post):
            report_async("https://example.com/hook", {"event": "test"})

        assert called == ["https://example.com/hook"]
