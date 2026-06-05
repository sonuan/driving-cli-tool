"""Power 数据模型

定义 driving.power.json 的数据结构。
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PowerEntry:
    """单个 power 条目

    字段设计与 RepoConfig 对齐：
    - url 有值 → remote 类型（git submodule）
    - url 无值 → local 类型（本地目录）
    """

    name: str                       # power 标识符，用于 --power 参数指定写入目标
    path: str                       # 安装路径（相对于项目根目录，如 ai-driving/my-config）
    url: Optional[str] = None       # Git URL（remote 类型必填）
    description: Optional[str] = None  # 描述，默认为空
    branch: Optional[str] = None    # 指定分支（初始化后自动 checkout；未配置则不切换，缺少 driving.config.json 时给出警告）

    @property
    def type(self) -> str:
        """根据 url 是否有值推断类型"""
        return "remote" if self.url else "local"

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "url": self.url,
            "description": self.description or "",
        }
        if self.branch:
            d["branch"] = self.branch
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PowerEntry":
        for field in ("name", "path"):
            if field not in data:
                raise KeyError(f"power 条目缺少必填字段：{field}")
        return cls(
            name=str(data["name"]),
            path=str(data["path"]),
            url=data.get("url") or None,
            description=data.get("description") or None,
            branch=data.get("branch") or None,
            # type 字段由 url 推断，从文件读取时忽略（向后兼容）
        )


@dataclass
class PowerConfig:
    """driving.power.json 的完整结构"""

    powers: List[PowerEntry]

    def to_dict(self) -> dict:
        return {"powers": [p.to_dict() for p in self.powers]}

    @classmethod
    def from_dict(cls, data: dict) -> "PowerConfig":
        if "powers" not in data:
            raise KeyError("缺少必填字段：powers")
        if not isinstance(data["powers"], list):
            raise ValueError("powers 字段必须为列表")
        return cls(powers=[PowerEntry.from_dict(p) for p in data["powers"]])
