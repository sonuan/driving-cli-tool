"""Gate 业务逻辑包

提供门禁验证引擎、状态管理、模板渲染等核心模块。
"""

from driving_cli.gate.auto_pass_engine import AutoPassEngine
from driving_cli.gate.condition_checker import ConditionChecker
from driving_cli.gate.interactive_runner import InteractiveRunner
from driving_cli.gate.models import (
    AutoPassResult,
    ConditionResult,
    GateHistoryEntry,
    GateState,
    RequiresResult,
    build_result_json,
)
from driving_cli.gate.requires_checker import RequiresChecker
from driving_cli.gate.state_manager import GateStateManager
from driving_cli.gate.template_renderer import TemplateRenderer

__all__ = [
    "AutoPassEngine",
    "ConditionChecker",
    "ConditionResult",
    "AutoPassResult",
    "InteractiveRunner",
    "RequiresChecker",
    "RequiresResult",
    "GateHistoryEntry",
    "GateState",
    "GateStateManager",
    "build_result_json",
    "TemplateRenderer",
]
