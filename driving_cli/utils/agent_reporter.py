"""Agent 启动上报模块

在子 agent 启动时（加载步骤第 0 步）异步向飞书 Webhook 上报结构化日志，
失败静默处理，不阻塞主流程。
"""

from typing import Any, Dict

from driving_cli.utils.git_helper import get_git_user
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.reporter_utils import now_timestamp, report_async


def _get_webhook_url() -> str:
    """从 driving.config.json 读取 agent_webhook，未配置时返回空字符串"""
    try:
        project_root = find_project_root()
        config = ConfigManager(project_root).load()
        return config.agent_webhook or ""
    except Exception:
        return ""


def report_agent_event(
    *,
    agent_name: str,
    feature_path: str = "",
    source: str = "",
) -> None:
    """上报子 agent 启动事件到 agent_webhook。

    Args:
        agent_name:   被启动的 agent 名称
        feature_path: --path 参数值（需求目录）
        source:       触发来源描述（来自 agent-dispatcher Step 3 的触发来源字段）
    """
    payload: Dict[str, Any] = {
        "agent_name": agent_name,
        "feature": feature_path,
        "source": source,
        "triggered_at": now_timestamp(),
    }

    # actor：从 git config 读取执行者姓名
    actor = get_git_user()
    if actor["name"]:
        payload["actor"] = actor["name"]

    report_async(_get_webhook_url(), payload)
