"""配置管理器

负责读写 driving.config.json，提供仓库配置的增删查改及路径辅助方法。
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from driving.models.config import DrivingConfig, RepoConfig

# 配置文件名称
CONFIG_FILE_NAME = "driving.config.json"

# ai-driving 根目录名称
AI_DRIVING_DIR_NAME = "ai-driving"

# 默认配置值
DEFAULT_VERSION = "2"
DEFAULT_COMMIT_MESSAGE = "update by driving"
DEFAULT_UPDATE_VERSION_URL = ""


def find_project_root() -> Path:
    """向上查找项目根目录

    从当前目录向上遍历，直到找到包含 driving.config.json 或 ai-driving/ 的目录。
    如果都找不到，返回当前工作目录。

    Returns:
        Path: 项目根目录路径
    """
    current = Path.cwd()

    # 向上查找，直到文件系统根目录
    while current != current.parent:
        if (current / CONFIG_FILE_NAME).exists() or (current / AI_DRIVING_DIR_NAME).exists():
            return current
        current = current.parent

    # 检查根目录本身
    if (current / CONFIG_FILE_NAME).exists() or (current / AI_DRIVING_DIR_NAME).exists():
        return current

    # 都找不到，返回当前工作目录
    return Path.cwd()


class ConfigManager:
    """配置管理器

    负责读写 driving.config.json，提供仓库配置的增删查改及路径辅助方法。
    配置文件路径为 {project_root}/driving.config.json。
    """

    def __init__(self, project_root: Path):
        """初始化配置管理器

        Args:
            project_root: 项目根目录路径
        """
        self._project_root = project_root
        self._config_file = project_root / CONFIG_FILE_NAME
        # 内存中缓存的配置对象，None 表示尚未加载
        self._config: Optional[DrivingConfig] = None

    # ==================== 核心读写方法 ====================

    def load(self) -> DrivingConfig:
        """加载配置文件

        若配置文件不存在，自动创建并返回默认配置。
        若配置文件格式非法，抛出 ValueError 并附带描述性错误信息。

        Returns:
            DrivingConfig: 配置对象

        Raises:
            ValueError: 配置文件格式非法时抛出
        """
        if not self._config_file.exists():
            # 配置文件不存在，创建默认配置
            default_config = DrivingConfig(
                version=DEFAULT_VERSION,
                repos=[],
                default_commit_message=DEFAULT_COMMIT_MESSAGE,
                update_version_url=DEFAULT_UPDATE_VERSION_URL,
            )
            self.save(default_config)
            self._config = default_config
            return default_config

        # 读取并解析配置文件
        try:
            raw_text = self._config_file.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"配置文件读取失败：{e}") from e

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误：JSON 解析失败 — {e}") from e

        if not isinstance(data, dict):
            raise ValueError("配置文件格式错误：顶层结构必须为 JSON 对象")

        try:
            config = DrivingConfig.from_dict(data)
        except KeyError as e:
            raise ValueError(f"配置文件格式错误：缺少必填字段 {e}") from e
        except (TypeError, ValueError) as e:
            raise ValueError(f"配置文件格式错误：{e}") from e

        self._config = config
        return config

    def save(self, config: DrivingConfig) -> None:
        """将配置保存为格式化 JSON

        Args:
            config: 要保存的配置对象
        """
        # 确保父目录存在
        self._config_file.parent.mkdir(parents=True, exist_ok=True)

        json_text = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        self._config_file.write_text(json_text, encoding="utf-8")
        self._config = config

    # ==================== 仓库增删查改 ====================

    def add_repo(self, repo: RepoConfig) -> None:
        """添加仓库到配置

        Args:
            repo: 要添加的仓库配置

        Raises:
            ValueError: 仓库名称已存在时抛出
        """
        config = self.load()

        # 检查名称是否重复
        if any(r.name == repo.name for r in config.repos):
            raise ValueError(f"仓库 '{repo.name}' 已存在，使用 --force 覆盖")

        config.repos.append(repo)
        self.save(config)

    def remove_repo(self, name: str) -> None:
        """从配置中删除仓库

        Args:
            name: 要删除的仓库名称

        Raises:
            ValueError: 仓库不存在时抛出
        """
        config = self.load()

        # 查找仓库
        original_count = len(config.repos)
        config.repos = [r for r in config.repos if r.name != name]

        if len(config.repos) == original_count:
            raise ValueError(f"仓库 '{name}' 不存在，使用 'driving repo list' 查看已安装仓库")

        self.save(config)

    def get_repo(self, name: str) -> Optional[RepoConfig]:
        """获取指定名称的仓库配置

        Args:
            name: 仓库名称

        Returns:
            RepoConfig: 仓库配置对象，不存在时返回 None
        """
        config = self.load()
        for repo in config.repos:
            if repo.name == name:
                return repo
        return None

    def get_all_repos(self) -> List[RepoConfig]:
        """获取所有仓库配置列表

        Returns:
            List[RepoConfig]: 所有仓库配置的列表
        """
        config = self.load()
        return list(config.repos)

    # ==================== 路径辅助方法 ====================

    def get_ai_driving_dir(self) -> Path:
        """返回 ai-driving/ 目录路径

        Returns:
            Path: ai-driving/ 目录的绝对路径
        """
        return self._project_root / AI_DRIVING_DIR_NAME

    def get_repo_dir(self, name: str) -> Path:
        """返回指定仓库的目录路径

        Args:
            name: 仓库名称

        Returns:
            Path: ai-driving/<name>/ 目录的绝对路径
        """
        return self.get_ai_driving_dir() / name

    def get_framework_base_dir(self, repo_name: str) -> Path:
        """返回指定仓库的框架安装目录路径

        Args:
            repo_name: 仓库名称

        Returns:
            Path: ai-driving/<repo_name>/submodules/ 目录的绝对路径
        """
        return self.get_repo_dir(repo_name) / "submodules"

    def get_all_gitlist_files(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 gitlist.json 文件路径列表

        只返回文件实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, gitlist_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            gitlist_path = self.get_repo_dir(repo.name) / "frameworks" / "gitlist.json"
            if gitlist_path.exists():
                result.append((repo.name, gitlist_path))
        return result

    def get_all_skills_dirs(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 skills/ 目录路径列表

        只返回目录实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, skills_dir_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            skills_dir = self.get_repo_dir(repo.name) / "skills"
            if skills_dir.exists():
                result.append((repo.name, skills_dir))
        return result

    def update_repo(self, repo: RepoConfig) -> None:
        """更新已存在仓库的配置

        Args:
            repo: 更新后的仓库配置

        Raises:
            ValueError: 仓库不存在时抛出
        """
        config = self.load()
        for i, r in enumerate(config.repos):
            if r.name == repo.name:
                config.repos[i] = repo
                self.save(config)
                return
        raise ValueError(f"仓库 '{repo.name}' 不存在")
