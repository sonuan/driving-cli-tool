"""框架信息数据模型"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Framework:
    """框架信息模型"""

    name: str  # 框架名称（原 framework）
    project_name: str  # 本地仓库名称（原 name）
    url: str
    module: str
    sources: List[str]
    description: str  # 框架描述（原 desc）
    creator: str  # 创建者
    date: str  # 创建日期
    branch: Optional[str] = None  # 分支名（可选）

    @classmethod
    def from_dict(cls, data: dict) -> "Framework":
        """从字典创建 Framework 对象

        Args:
            data: 框架信息字典

        Returns:
            Framework: 框架对象
        """
        return cls(
            name=data.get("name", ""),
            project_name=data.get("project_name", ""),
            url=data.get("url", ""),
            module=data.get("module", ""),
            sources=data.get("sources", []),
            description=data.get("description", ""),
            creator=data.get("creator", ""),
            date=data.get("date", ""),
            branch=data.get("branch"),
        )


def get_framework_by_name(gitlist_file: Path, name: str) -> Optional[dict]:
    """根据框架名称获取框架信息

    Args:
        gitlist_file: gitlist.json 文件路径
        name: 框架名称

    Returns:
        Optional[dict]: 框架信息字典，不存在则返回 None
    """
    if not gitlist_file.exists():
        return None

    with open(gitlist_file, "r", encoding="utf-8") as f:
        frameworks = json.load(f)

    for fw in frameworks:
        if fw.get("name") == name:
            return fw
    return None


def get_all_frameworks(gitlist_file: Path) -> List[Framework]:
    """获取所有框架信息

    Args:
        gitlist_file: gitlist.json 文件路径

    Returns:
        List[Framework]: 框架列表
    """
    if not gitlist_file.exists():
        return []

    with open(gitlist_file, "r", encoding="utf-8") as f:
        frameworks = json.load(f)

    return [Framework.from_dict(fw) for fw in frameworks]
