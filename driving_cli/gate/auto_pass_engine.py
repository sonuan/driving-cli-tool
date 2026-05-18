"""Auto_Pass_Engine 结构化验证引擎

根据 auto_pass 配置逐条执行 conditions，结合返工阈值判断是否自动通过。
"""

from typing import List

from driving_cli.gate.condition_checker import ConditionChecker
from driving_cli.gate.models import AutoPassResult, ConditionResult


class AutoPassEngine:
    """结构化验证引擎

    根据 auto_pass 配置逐条执行 conditions，结合返工阈值判断是否自动通过。
    """

    def __init__(self, checker: ConditionChecker):
        """
        Args:
            checker: 条件检查器实例，用于逐条执行 condition 验证
        """
        self._checker = checker

    def evaluate(
        self,
        auto_pass_config: dict,
        user_amend_count: int,
    ) -> AutoPassResult:
        """执行 auto_pass 验证

        Args:
            auto_pass_config: gate 定义中的 auto_pass 对象
            user_amend_count: 当前 gate 的 user_amend_count

        Returns:
            AutoPassResult
        """
        mode = auto_pass_config.get("mode", "human_only")

        # mode 为 human_only 时跳过条件检查
        if mode == "human_only":
            return AutoPassResult(
                passed=False,
                condition_results=[],
                skipped=True,
            )

        # mode 为 notify_pass 或 full_auto 时逐条执行 conditions
        conditions = auto_pass_config.get("conditions", [])
        results: List[ConditionResult] = []

        for condition in conditions:
            # 兼容旧格式：conditions 元素为字符串（自然语言描述）时无法自动验证，
            # 视为该 condition 跳过（passed=True），不阻断 auto_pass 流程
            if isinstance(condition, str):
                results.append(ConditionResult(passed=True, label=condition))
                continue
            result = self._checker.check(condition)
            results.append(result)

        all_passed = all(r.passed for r in results)

        # 全部通过但返工阈值触发（user_amend_count >= 3）
        if all_passed and user_amend_count >= 3:
            return AutoPassResult(
                passed=False,
                condition_results=results,
                forced_interactive=True,
            )

        # 全部通过且未触发返工阈值
        if all_passed:
            return AutoPassResult(
                passed=True,
                condition_results=results,
            )

        # 任一 condition 失败
        return AutoPassResult(
            passed=False,
            condition_results=results,
        )
