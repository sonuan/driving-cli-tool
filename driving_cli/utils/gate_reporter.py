"""Gate 日志上报模块

在每次门禁触发结果（pass / auto_pass / amend / blocked）后，
异步向飞书 Webhook 上报结构化日志，失败静默处理，不阻塞主流程。
"""

from typing import Any, Dict, Optional

from driving_cli.utils.git_helper import get_git_user
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.reporter_utils import now_timestamp, report_async


def _get_webhook_url() -> str:
    """从 driving.config.json 读取 gate_webhook，未配置时返回空字符串"""
    try:
        project_root = find_project_root()
        config = ConfigManager(project_root).load()
        return config.gate_webhook or ""
    except Exception:
        return ""


def build_report_payload(
    *,
    gate_id: str,
    gate_name: str,
    gate_level: str,
    result: str,
    action: str,
    note: str = "",
    triggered_at: Optional[str] = None,
    feature_path: str = "",
    repo: str = "",
    cli_version: str = "",
    context: Optional[Dict[str, Any]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> dict:
    """构建 gate 上报 payload

    Args:
        gate_id:       门禁 ID，如 GATE-R5
        gate_name:     门禁名称
        gate_level:    门禁级别：blocking / warning
        result:        结果类型：pass / auto_pass / amend / blocked
        action:        用户选择的操作 key
        note:          修改说明（amend / blocked 时有值）
        triggered_at:  触发时间，默认取当前北京时间
        feature_path:  --path 参数值
        repo:          所属仓库名
        cli_version:   CLI 版本号
        context:       业务上下文字段（稀疏传递，只传本 gate 用到的）
        stats:         门禁累计统计

    Returns:
        符合接口规范的 dict
    """
    payload: Dict[str, Any] = {
        "gate_id": gate_id,
        "gate_name": gate_name,
        "gate_level": gate_level,
        "feature": feature_path,
        "last_event": {
            "result": result,
            "action": action,
            "note": note,
            "triggered_at": triggered_at or now_timestamp(),
        },
    }

    # context：原样上报，--context 传什么就上报什么
    if context:
        payload["context"] = context

    # stats：只传非空字段
    if stats:
        payload["stats"] = {k: v for k, v in stats.items() if v is not None}

    # env：只在有值时附加
    env: Dict[str, str] = {}
    if repo:
        env["repo"] = repo
    if cli_version:
        env["cli_version"] = cli_version
    if env:
        payload["env"] = env

    # actor：从 git config 读取执行者姓名
    actor = get_git_user()
    if actor["name"]:
        payload["actor"] = actor["name"]

    return payload


def report_gate_event(
    *,
    gate_id: str,
    gate_name: str,
    gate_level: str,
    result: str,
    action: str,
    note: str = "",
    triggered_at: Optional[str] = None,
    feature_path: str = "",
    repo: str = "",
    cli_version: str = "",
    context: Optional[Dict[str, Any]] = None,
    gate_state=None,  # GateState 对象，用于提取 stats
) -> None:
    """构建 payload 并异步上报到 gate_webhook。

    这是对外的主入口，在每个门禁结果输出后调用。

    Args:
        gate_state: GateStateManager.get_gate_state() 返回的 GateState 对象，
                    record_result 之后调用，确保统计含本次操作。
    """
    stats: Optional[Dict[str, Any]] = None
    if gate_state is not None:
        stats = {
            "request_count": gate_state.request_count,
            "auto_pass_count": gate_state.auto_pass_count,
            "user_pass_count": gate_state.user_pass_count,
            "user_amend_count": gate_state.user_amend_count,
        }

    payload = build_report_payload(
        gate_id=gate_id,
        gate_name=gate_name,
        gate_level=gate_level,
        result=result,
        action=action,
        note=note,
        triggered_at=triggered_at,
        feature_path=feature_path,
        repo=repo,
        cli_version=cli_version,
        context=context,
        stats=stats,
    )
    report_async(_get_webhook_url(), payload)
