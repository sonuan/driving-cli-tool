"""上报公共工具

提供各上报模块共用的基础设施：时间戳、HTTP 发送、异步上报。
"""

import datetime
import json
import ssl
import threading
import urllib.request
import urllib.error


def now_timestamp() -> str:
    """返回当前北京时间，格式：2026/05/21 21:39"""
    tz_beijing = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_beijing).strftime("%Y/%m/%d %H:%M")


def do_post(webhook_url: str, payload: dict) -> None:
    """向指定 Webhook 执行 HTTP POST，失败静默处理。

    Args:
        webhook_url: 目标 Webhook 地址，为空时直接返回
        payload:     要上报的数据字典
    """
    if not webhook_url:
        return
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        # 绕过环境变量中的代理设置，直连目标
        # 忽略 SSL 证书校验（兼容内网自签名证书）
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        no_proxy_handler = urllib.request.ProxyHandler({})
        https_handler = urllib.request.HTTPSHandler(context=ssl_ctx)
        opener = urllib.request.build_opener(no_proxy_handler, https_handler)
        with opener.open(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        import sys

        print(f"⚠️ Webhook 上报失败 [{webhook_url}]: {e}", file=sys.stderr)


def report_async(webhook_url: str, payload: dict) -> None:
    """异步上报（后台线程），最多等待 3 秒，不阻塞 CLI 主输出。

    Args:
        webhook_url: 目标 Webhook 地址
        payload:     要上报的数据字典
    """
    t = threading.Thread(target=do_post, args=(webhook_url, payload), daemon=True)
    t.start()
    t.join(timeout=3)
