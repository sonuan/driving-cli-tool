"""Gate State 持久化管理器

负责 gate-state.json 的读取、写入、状态更新。
"""

import datetime
import json
from pathlib import Path
from typing import Dict

import click

from driving_cli.gate.models import GateHistoryEntry, GateState


class GateStateManager:
    """Gate State 持久化管理器

    负责 gate-state.json 的读取、写入、状态更新。
    """

    def __init__(self, path: str, platform: str = "", owner: str = ""):
        """
        Args:
            path: --path 参数值，feature 目录路径
            platform: 开发平台（android/iOS/harmony/kuikly）。
                      非空时 state 文件位于 <path>/docs/<platform>/gate-state.json；
                      为空时保持旧路径 <path>/docs/gate-state.json（向后兼容）。
            owner: 负责人标识（如 main、apple 或 owner-main）。
                   非空时 state 文件写入 owner 子目录下：
                     <path>/docs/<platform>/owner-<owner>/gate-state.json；
                   已含 "owner-" 前缀则直接使用，不重复拼接。
                   为空时路径不含 owner 层（向后兼容）。
        """
        self._path = path
        self._platform = platform
        self._owner = owner

    def _resolve_owner_dir_name(self) -> str:
        """将 owner 规范化为完整目录名（含 owner- 前缀）。"""
        if not self._owner:
            return ""
        if self._owner.lower().startswith("owner-"):
            return self._owner
        return f"owner-{self._owner}"

    @property
    def state_file(self) -> Path:
        """返回 gate-state.json 的完整路径。

        路径规则：
          - 有 platform + owner → <path>/docs/<platform>/owner-<owner>/gate-state.json
          - 有 platform，无 owner → <path>/docs/<platform>/gate-state.json
          - 无 platform            → <path>/docs/gate-state.json（向后兼容）
        """
        base = Path(self._path) / "docs"
        if self._platform:
            base = base / self._platform
            owner_dir = self._resolve_owner_dir_name()
            if owner_dir:
                base = base / owner_dir
        return base / "gate-state.json"

    def load(self) -> dict:
        """加载 gate-state.json

        文件不存在时返回初始结构。
        文件 JSON 格式非法时抛出 click.ClickException。

        Returns:
            完整的 state dict
        """
        if not self.state_file.exists():
            return {"feature": "", "updated": "", "gates": {}}

        try:
            content = self.state_file.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            raise click.ClickException("gate-state.json 格式非法，请检查文件内容")

    def get_gate_state(self, gate_id: str) -> GateState:
        """获取指定 gate 的状态，不存在时返回默认值"""
        data = self.load()
        gates = data.get("gates", {})
        gate_data = gates.get(gate_id, {})

        if not gate_data:
            return GateState()

        history = [
            GateHistoryEntry(
                at=entry.get("at", ""),
                action=entry.get("action", ""),
                note=entry.get("note", ""),
            )
            for entry in gate_data.get("history", [])
        ]

        return GateState(
            request_count=gate_data.get("request_count", 0),
            auto_pass_count=gate_data.get("auto_pass_count", 0),
            user_pass_count=gate_data.get("user_pass_count", 0),
            user_amend_count=gate_data.get("user_amend_count", 0),
            pass_rate=gate_data.get("pass_rate", 0.0),
            last_result=gate_data.get("last_result", ""),
            history=history,
        )

    def record_result(
        self,
        gate_id: str,
        result_type: str,
        action: str,
        note: str = "",
        gate_name: str = "",
    ) -> None:
        """记录一次 gate 执行结果

        自动更新 request_count、对应计数器、pass_rate、last_result、history。
        追加 history entry（ISO 8601 时间戳）。
        更新顶层 updated 字段。

        Args:
            gate_id: 门禁 ID
            result_type: 结果类型（auto_pass / pass / amend）
            action: 动作 key
            note: 备注
            gate_name: 门禁名称（来自 gate 定义的 name 字段）
        """
        data = self.load()

        # 确保 gates 字典存在
        if "gates" not in data:
            data["gates"] = {}

        # 获取或初始化 gate 数据
        gate_data = data["gates"].get(
            gate_id,
            {
                "name": "",
                "request_count": 0,
                "auto_pass_count": 0,
                "user_pass_count": 0,
                "user_amend_count": 0,
                "pass_rate": 0.0,
                "last_result": "",
                "history": [],
            },
        )

        # 更新 name（始终以最新定义为准）
        if gate_name:
            gate_data["name"] = gate_name

        # 更新计数
        gate_data["request_count"] = gate_data.get("request_count", 0) + 1

        if result_type == "auto_pass":
            gate_data["auto_pass_count"] = gate_data.get("auto_pass_count", 0) + 1
        elif result_type == "pass":
            gate_data["user_pass_count"] = gate_data.get("user_pass_count", 0) + 1
        elif result_type == "amend":
            gate_data["user_amend_count"] = gate_data.get("user_amend_count", 0) + 1

        # 计算 pass_rate
        request_count = gate_data["request_count"]
        auto_pass_count = gate_data.get("auto_pass_count", 0)
        user_pass_count = gate_data.get("user_pass_count", 0)
        gate_data["pass_rate"] = (auto_pass_count + user_pass_count) / request_count

        # 更新 last_result
        gate_data["last_result"] = result_type

        # 追加 history entry
        tz_beijing = datetime.timezone(datetime.timedelta(hours=8))
        timestamp = datetime.datetime.now(tz_beijing).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        history_entry = {"at": timestamp, "action": action, "note": note}

        if "history" not in gate_data:
            gate_data["history"] = []
        gate_data["history"].append(history_entry)

        # 写回 gate 数据（name 始终排在第一位）
        ordered = {"name": gate_data.get("name", "")}
        ordered.update({k: v for k, v in gate_data.items() if k != "name"})
        data["gates"][gate_id] = ordered

        # 更新顶层 updated 字段
        data["updated"] = timestamp

        # 保存
        self.save(data)

    def save(self, data: dict) -> None:
        """保存 gate-state.json（UTF-8, 2-space indent）

        自动创建 <path>/docs/ 目录。
        --path 为空时跳过保存（不写入文件）。
        """
        # --path 为空时不存储 state 文件
        if not self._path:
            return

        # 确保目录存在
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self.state_file.write_text(content, encoding="utf-8")
