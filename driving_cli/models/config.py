"""配置数据模型

定义 driving.config.json 的数据结构，包含仓库配置和全局配置。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RepoConfig:
    """单个仓库的配置信息"""

    name: str  # 仓库名称（唯一标识）
    type: str  # 仓库类型："remote" 或 "local"
    path: str  # 安装路径（相对于项目根目录，如 ai-driving/main）
    url: Optional[str] = None  # Git URL（remote 类型必填）
    local_path: Optional[str] = None  # 本地原始路径（local 类型可选，有值时创建软链接）
    description: Optional[str] = None  # 仓库描述，用于 AI 关键词匹配
    tags: Optional[List[str]] = None  # 仓库标签，含 "base" 时默认加载，否则需关键词匹配
    version: Optional[str] = None  # 最后一次 pull 后的 commit hash
    skills: Optional[dict] = None  # 技能过滤配置，格式：{"enabled": [...], "disabled": [...]}
    rules: Optional[dict] = None  # 规则过滤配置，格式：{"enabled": [...], "disabled": [...]}
    agents: Optional[dict] = None  # agent 过滤配置，格式：{"enabled": [...], "disabled": [...]}

    def to_dict(self) -> dict:
        """序列化为字典（JSON 兼容格式）"""
        d = {
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "path": self.path,
            "local_path": self.local_path,
        }
        if self.description is not None:
            d["description"] = self.description
        if self.tags is not None:
            d["tags"] = self.tags
        if self.version is not None:
            d["version"] = self.version
        # 只在有值时写入，保持 config.json 简洁
        if self.skills is not None:
            d["skills"] = self.skills
        if self.rules is not None:
            d["rules"] = self.rules
        if self.agents is not None:
            d["agents"] = self.agents
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RepoConfig":
        """从字典反序列化为 RepoConfig 对象"""
        for required_field in ("name", "type", "path"):
            if required_field not in data:
                raise KeyError(f"缺少必填字段：{required_field}")

        return cls(
            name=data["name"],
            type=data["type"],
            path=data["path"],
            url=data.get("url"),
            local_path=data.get("local_path"),
            description=data.get("description"),
            tags=data.get("tags"),
            version=data.get("version"),
            skills=data.get("skills"),
            rules=data.get("rules"),
            agents=data.get("agents"),
        )


@dataclass
class DrivingConfig:
    """driving.config.json 的完整配置结构"""

    version: str  # 配置文件版本，当前为 "2"
    repos: List[RepoConfig]  # 已安装的仓库列表
    default_commit_message: str  # 默认提交信息
    update_version_url: str  # 更新检查 URL
    user_prompt: str = ""  # 用户提示词，注入到 driving load 输出的 user_prompt 字段

    def to_dict(self) -> dict:
        """序列化为字典（JSON 兼容格式）

        Returns:
            dict: 包含所有字段的字典，repos 列表中每个元素也已序列化
        """
        d = {
            "version": self.version,
            "repos": [repo.to_dict() for repo in self.repos],
            "default_commit_message": self.default_commit_message,
            "update_version_url": self.update_version_url,
        }
        if self.user_prompt:
            d["user_prompt"] = self.user_prompt
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DrivingConfig":
        """从字典反序列化为 DrivingConfig 对象

        Args:
            data: 包含完整配置的字典

        Returns:
            DrivingConfig: 配置对象

        Raises:
            KeyError: 缺少必填字段时抛出
            ValueError: 字段类型不合法时抛出
        """
        # 校验必填字段
        for required_field in ("version", "repos", "default_commit_message", "update_version_url"):
            if required_field not in data:
                raise KeyError(f"缺少必填字段：{required_field}")

        # 校验 repos 必须为列表
        if not isinstance(data["repos"], list):
            raise ValueError("repos 字段必须为列表")

        repos = [RepoConfig.from_dict(repo) for repo in data["repos"]]

        return cls(
            version=str(data["version"]),
            repos=repos,
            default_commit_message=str(data["default_commit_message"]),
            update_version_url=str(data["update_version_url"]),
            user_prompt=str(data.get("user_prompt", "")),
        )
