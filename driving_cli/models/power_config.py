"""Power 数据模型

定义 driving.power.json 的数据结构。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RepoOverrideConfig:
    """PowerEntry.repo_config 中单个 repo 的覆盖配置。

    目前支持：
    - branch：driving load 时强制切换到的分支（优先级高于 PowerEntry.branch）
    """
    branch: Optional[str] = None

    def to_dict(self) -> dict:
        d = {}
        if self.branch:
            d["branch"] = self.branch
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepoOverrideConfig":
        return cls(branch=data.get("branch") or None)


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
    branch: Optional[str] = None    # 指定分支（安装时 checkout；未配置则不切换）
    repo_config: Dict[str, RepoOverrideConfig] = field(default_factory=dict)
    # repo_config：driving load 时各 repo/power 的分支覆盖配置，key 为 repo name 或 power name
    # 示例：{"driving-base": {"branch": "develop"}, "f-message": {"branch": "feature/xxx"}}
    # 优先级高于 branch 字段

    @property
    def type(self) -> str:
        """根据 url 是否有值推断类型"""
        return "remote" if self.url else "local"

    def get_load_branch(self) -> Optional[str]:
        """返回 driving load 时本 power 应切换的分支。

        查找规则（以 power 自身 name 为 key）：
        1. repo_config[self.name].branch
        2. self.branch
        3. None
        """
        override = self.repo_config.get(self.name)
        if override and override.branch:
            return override.branch
        return self.branch

    def get_repo_load_branch(self, repo_name: str) -> Optional[str]:
        """返回 driving load 时某个 repo 应切换的分支。

        查找规则：
        1. repo_config[repo_name].branch
        2. None（repo 自身的 branch 字段由 driving.config.json 管理，不在此处维护）
        """
        override = self.repo_config.get(repo_name)
        if override and override.branch:
            return override.branch
        return None

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
        if self.repo_config:
            d["repo_config"] = {k: v.to_dict() for k, v in self.repo_config.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PowerEntry":
        for f in ("name", "path"):
            if f not in data:
                raise KeyError(f"power 条目缺少必填字段：{f}")
        repo_config: Dict[str, RepoOverrideConfig] = {}
        if "repo_config" in data:
            raw = data["repo_config"]
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict):
                        repo_config[k] = RepoOverrideConfig.from_dict(v)
        return cls(
            name=str(data["name"]),
            path=str(data["path"]),
            url=data.get("url") or None,
            description=data.get("description") or None,
            branch=data.get("branch") or None,
            repo_config=repo_config,
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
