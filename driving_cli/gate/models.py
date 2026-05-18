"""Gate 数据模型定义

定义 gate 业务逻辑中使用的数据类和工具函数。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ConditionResult:
    """单条 condition 的检查结果"""

    passed: bool
    label: str
    detail: str = ""  # 失败时的详细信息


@dataclass
class AutoPassResult:
    """auto_pass 引擎的执行结果"""

    passed: bool
    condition_results: List[ConditionResult]
    skipped: bool = False  # mode=human_only 时为 True
    forced_interactive: bool = False  # 返工阈值触发时为 True


@dataclass
class RequiresResult:
    """前置依赖校验结果"""

    passed: bool
    blocked_by: Optional[str] = None  # 阻断的 gate-id
    blocked_name: str = ""  # 阻断的 gate name
    message: str = ""  # 阻断原因描述


@dataclass
class GateHistoryEntry:
    """单条历史记录"""

    at: str  # ISO 8601 时间戳
    action: str  # action key
    note: str  # 备注


@dataclass
class GateState:
    """单个 gate 的状态"""

    request_count: int = 0
    auto_pass_count: int = 0
    user_pass_count: int = 0
    user_amend_count: int = 0
    pass_rate: float = 0.0
    last_result: str = ""
    history: List[GateHistoryEntry] = field(default_factory=list)


def build_result_json(
    gate_id: str,
    result: str,
    action: str,
    next_text: str,
    note: str = "",
    user_prompt: str = "按 next 字段执行后续动作",
) -> dict:
    """构建统一返回 JSON 结构

    Args:
        gate_id: 门禁 ID
        result: 结果类型（auto_pass / pass / amend / blocked）
        action: 动作 key
        next_text: 下一步操作描述
        note: 备注（amend 时有值）
        user_prompt: 用户提示语（来自 gates.json 顶层 user_prompt 字段）

    Returns:
        包含 gate_id, result, action, next, note, user_prompt 的 dict
    """
    return {
        "gate_id": gate_id,
        "result": result,
        "action": action,
        "next": next_text,
        "note": note,
        "user_prompt": user_prompt,
    }
