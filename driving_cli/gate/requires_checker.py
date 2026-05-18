"""前置依赖校验器

检查 requires 数组中所有前置门禁的 last_result 状态，
决定是否允许当前门禁继续执行。
"""

from typing import List, Optional

from driving_cli.gate.models import RequiresResult
from driving_cli.gate.state_manager import GateStateManager


class RequiresChecker:
    """前置依赖校验器"""

    def __init__(self, state_manager: GateStateManager, all_gates: List[dict]):
        """
        Args:
            state_manager: 状态管理器
            all_gates: 所有 gate 定义列表（用于查找 gate name）
        """
        self._state_manager = state_manager
        self._all_gates = all_gates

    def _find_gate_name(self, gate_id: str) -> str:
        """根据 gate_id 查找 gate name

        在 all_gates 列表中查找匹配的 gate 定义，
        未找到时使用 gate_id 作为 name。
        """
        for gate in self._all_gates:
            if gate.get("id") == gate_id:
                return gate.get("name", gate_id)
        return gate_id

    def check(self, requires: List[str], target_level: str) -> RequiresResult:
        """校验前置依赖

        Args:
            requires: 前置 gate-id 列表
            target_level: 目标 gate 的 level（blocking/warning）

        Returns:
            RequiresResult
        """
        # requires 为空时直接返回 passed=True
        if not requires:
            return RequiresResult(passed=True)

        for gate_id in requires:
            gate_state = self._state_manager.get_gate_state(gate_id)
            last_result = gate_state.last_result

            # pass 或 auto_pass 视为满足
            if last_result in ("pass", "auto_pass"):
                continue

            # amend 或 key 不存在（last_result 为空字符串）时返回 blocked
            if last_result == "amend" or last_result == "":
                gate_name = self._find_gate_name(gate_id)
                return RequiresResult(
                    passed=False,
                    blocked_by=gate_id,
                    blocked_name=gate_name,
                    message=f"前置门禁 {gate_id}：{gate_name} 未通过，禁止继续，需先触发并通过该门禁",
                )

            # skipped 时根据 target_level 决定
            if last_result == "skipped":
                if target_level == "blocking":
                    gate_name = self._find_gate_name(gate_id)
                    return RequiresResult(
                        passed=False,
                        blocked_by=gate_id,
                        blocked_name=gate_name,
                        message=f"前置门禁 {gate_id}：{gate_name} 未通过，禁止继续，需先触发并通过该门禁",
                    )
                # warning level 时允许继续
                continue

            # 其他未知状态视为 blocked
            gate_name = self._find_gate_name(gate_id)
            return RequiresResult(
                passed=False,
                blocked_by=gate_id,
                blocked_name=gate_name,
                message=f"前置门禁 {gate_id}：{gate_name} 未通过，禁止继续，需先触发并通过该门禁",
            )

        # 所有前置门禁都满足
        return RequiresResult(passed=True)
