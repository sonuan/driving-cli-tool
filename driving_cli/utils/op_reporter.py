"""通用操作记录上报模块

记录 CLI 关键操作到 agent_webhook，用于审计、追踪和团队协作感知。
失败静默处理，不阻塞主流程。

所有上报统一走 agent_webhook 字段，payload 结构如下：
  {
    "operation":   str,          # 操作类型标识
    "description": str,          # 一句话描述（可选）
    "triggered_at": str,         # 北京时间，格式 2026/06/11 14:30
    "cli_version": str,          # CLI 版本号
    "actor":       str,          # 操作者 git user.name（有值时才含）
    "branch":      str,          # 当前 git 分支（有值时才含）
    "extra":       dict,         # 操作相关的扩展字段（有值时才含）
  }

operation 类型：
  load_invoked        — driving load 调用成功（会话开启）
  load_auto_updated   — driving load 内检测到新版本并自动更新 CLI 成功
  update_completed    — driving update 手动更新 CLI 成功
  repo_pulled         — driving repo pull / load 内自动拉取仓库成功
  power_pulled        — driving load 内自动拉取 power 成功
  agent_started       — 子 agent 启动（来自 driving agent report）
  refine_committed    — refine 提案提交（来自 driving refine commit）
  refine_merged       — refine 提案合并（来自 driving refine merge）
"""

import sys
from typing import Any, Dict, Optional

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


def _get_git_branch() -> str:
    """读取当前 git 分支名，失败时返回空字符串"""
    try:
        import git as _git
        from pathlib import Path
        repo = _git.Repo(Path.cwd(), search_parent_directories=True)
        if repo.head.is_detached:
            return ""
        return repo.active_branch.name
    except Exception:
        return ""


def _get_cli_version() -> str:
    """返回当前 CLI 版本号"""
    try:
        from driving_cli import __version__
        return __version__
    except Exception:
        return ""


def build_op_payload(
    *,
    operation: str,
    description: str = "",
    triggered_at: Optional[str] = None,
    cli_version: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建通用操作上报 payload。

    Args:
        operation:    操作类型标识
        description:  一句话描述（人类可读）
        triggered_at: 触发时间（北京时间），默认取当前时间
        cli_version:  CLI 版本号，默认自动读取
        extra:        操作相关扩展字段，收入 extra 嵌套对象

    Returns:
        符合接口规范的 dict
    """
    payload: Dict[str, Any] = {
        "operation": operation,
        "triggered_at": triggered_at or now_timestamp(),
        "cli_version": cli_version or _get_cli_version(),
    }

    if description:
        payload["description"] = description

    # actor：从 git config 读取操作者姓名
    actor = get_git_user()
    if actor["name"]:
        payload["actor"] = actor["name"]

    # branch：当前 git 分支
    branch = _get_git_branch()
    if branch:
        payload["branch"] = branch

    # extra：收入嵌套对象，过滤空值
    if extra:
        filtered = {k: v for k, v in extra.items() if v is not None and v != ""}
        if filtered:
            payload["extra"] = filtered

    return payload


def report_op_event(
    *,
    operation: str,
    description: str = "",
    triggered_at: Optional[str] = None,
    cli_version: str = "",
    extra: Optional[Dict[str, Any]] = None,
    silent: bool = False,
) -> None:
    """构建 payload 并异步上报到 agent_webhook。

    Args:
        operation:    操作类型标识
        description:  一句话描述
        triggered_at: 触发时间，默认取当前北京时间
        cli_version:  CLI 版本号，默认自动读取
        extra:        操作相关扩展字段（收入 extra 嵌套对象）
        silent:       True 时不输出「未配置」警告（load 内调用时使用，避免干扰输出）
    """
    try:
        webhook_url = _get_webhook_url()
    except Exception:
        return
    if not webhook_url:
        if not silent:
            print(
                "⚠️ agent_webhook 未配置，操作记录未上报。请在 driving.config.json 中设置 agent_webhook",
                file=sys.stderr,
            )
        return

    payload = build_op_payload(
        operation=operation,
        description=description,
        triggered_at=triggered_at,
        cli_version=cli_version,
        extra=extra,
    )
    report_async(webhook_url, payload)
