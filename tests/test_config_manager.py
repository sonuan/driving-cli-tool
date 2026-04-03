"""ConfigManager 单元测试

覆盖 load、save、add_repo、remove_repo、get_repo、get_all_repos
以及路径辅助方法和 find_project_root 函数。
"""

import json
import tempfile
from pathlib import Path

import pytest

from driving_cli.models.config import DrivingConfig, RepoConfig
from driving_cli.utils.config_manager import (
    AI_DRIVING_DIR_NAME,
    CONFIG_FILE_NAME,
    ConfigManager,
    find_project_root,
)


# ==================== 测试辅助工具 ====================


def make_repo(name: str = "main", repo_type: str = "remote") -> RepoConfig:
    """创建测试用 RepoConfig"""
    return RepoConfig(
        name=name,
        type=repo_type,
        url="https://github.com/example/driving" if repo_type == "remote" else None,
        path=f"ai-driving/{name}",
        local_path=None,
    )


def make_config(repos=None) -> DrivingConfig:
    """创建测试用 DrivingConfig"""
    return DrivingConfig(
        version="2",
        repos=repos or [],
        default_commit_message="update by driving",
        update_version_url="",
    )


# ==================== find_project_root 测试 ====================


class TestFindProjectRoot:
    """find_project_root 函数测试"""

    def test_finds_dir_with_config_file(self, tmp_path):
        """找到包含 driving.config.json 的目录"""
        # 创建配置文件
        (tmp_path / CONFIG_FILE_NAME).write_text("{}", encoding="utf-8")
        # 在子目录中调用
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(sub)
            root = find_project_root()
            # 应该找到 tmp_path（包含 driving.config.json）
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_finds_dir_with_ai_driving(self, tmp_path):
        """找到包含 ai-driving/ 目录的目录"""
        (tmp_path / AI_DRIVING_DIR_NAME).mkdir()
        sub = tmp_path / "sub"
        sub.mkdir()

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(sub)
            root = find_project_root()
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_returns_cwd_when_not_found(self, tmp_path):
        """找不到时返回当前工作目录"""
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            root = find_project_root()
            assert root == tmp_path
        finally:
            os.chdir(original_cwd)


# ==================== ConfigManager.load 测试 ====================


class TestConfigManagerLoad:
    """ConfigManager.load() 方法测试"""

    def test_creates_default_config_when_file_missing(self, tmp_path):
        """配置文件不存在时自动创建默认配置"""
        mgr = ConfigManager(tmp_path)
        config = mgr.load()

        assert config.version == "2"
        assert config.repos == []
        assert config.default_commit_message == "update by driving"
        # 配置文件应已被创建
        assert (tmp_path / CONFIG_FILE_NAME).exists()

    def test_loads_existing_config(self, tmp_path):
        """正常加载已存在的配置文件"""
        data = make_config([make_repo("main")]).to_dict()
        (tmp_path / CONFIG_FILE_NAME).write_text(
            json.dumps(data), encoding="utf-8"
        )

        mgr = ConfigManager(tmp_path)
        config = mgr.load()

        assert len(config.repos) == 1
        assert config.repos[0].name == "main"

    def test_raises_on_invalid_json(self, tmp_path):
        """JSON 格式非法时抛出 ValueError"""
        (tmp_path / CONFIG_FILE_NAME).write_text("not valid json", encoding="utf-8")

        mgr = ConfigManager(tmp_path)
        with pytest.raises(ValueError, match="JSON 解析失败"):
            mgr.load()

    def test_raises_on_missing_required_field(self, tmp_path):
        """缺少必填字段时抛出 ValueError"""
        # 缺少 version 字段
        data = {"repos": [], "default_commit_message": "msg", "update_version_url": ""}
        (tmp_path / CONFIG_FILE_NAME).write_text(json.dumps(data), encoding="utf-8")

        mgr = ConfigManager(tmp_path)
        with pytest.raises(ValueError, match="缺少必填字段"):
            mgr.load()

    def test_raises_on_non_dict_json(self, tmp_path):
        """顶层不是对象时抛出 ValueError"""
        (tmp_path / CONFIG_FILE_NAME).write_text("[1, 2, 3]", encoding="utf-8")

        mgr = ConfigManager(tmp_path)
        with pytest.raises(ValueError, match="顶层结构必须为 JSON 对象"):
            mgr.load()

    def test_raises_on_repos_not_list(self, tmp_path):
        """repos 字段不是列表时抛出 ValueError"""
        data = {
            "version": "2",
            "repos": "not-a-list",
            "default_commit_message": "msg",
            "update_version_url": "",
        }
        (tmp_path / CONFIG_FILE_NAME).write_text(json.dumps(data), encoding="utf-8")

        mgr = ConfigManager(tmp_path)
        with pytest.raises(ValueError):
            mgr.load()


# ==================== ConfigManager.save 测试 ====================


class TestConfigManagerSave:
    """ConfigManager.save() 方法测试"""

    def test_saves_formatted_json(self, tmp_path):
        """保存为格式化 JSON（带缩进）"""
        mgr = ConfigManager(tmp_path)
        config = make_config()
        mgr.save(config)

        raw = (tmp_path / CONFIG_FILE_NAME).read_text(encoding="utf-8")
        # 格式化 JSON 应包含换行符
        assert "\n" in raw
        # 可以正常解析
        parsed = json.loads(raw)
        assert parsed["version"] == "2"

    def test_save_and_reload(self, tmp_path):
        """保存后重新加载应得到相同配置"""
        mgr = ConfigManager(tmp_path)
        original = make_config([make_repo("main"), make_repo("local", "local")])
        mgr.save(original)

        mgr2 = ConfigManager(tmp_path)
        loaded = mgr2.load()

        assert loaded.version == original.version
        assert len(loaded.repos) == 2
        assert loaded.repos[0].name == "main"
        assert loaded.repos[1].name == "local"


# ==================== ConfigManager.add_repo 测试 ====================


class TestConfigManagerAddRepo:
    """ConfigManager.add_repo() 方法测试"""

    def test_add_repo_success(self, tmp_path):
        """成功添加仓库"""
        mgr = ConfigManager(tmp_path)
        mgr.load()  # 初始化默认配置

        repo = make_repo("new-repo")
        mgr.add_repo(repo)

        assert mgr.get_repo("new-repo") is not None

    def test_add_repo_duplicate_raises(self, tmp_path):
        """添加重名仓库时抛出 ValueError"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("main"))

        with pytest.raises(ValueError, match="已存在"):
            mgr.add_repo(make_repo("main"))

    def test_add_repo_persists_to_file(self, tmp_path):
        """添加仓库后配置应持久化到文件"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("main"))

        # 重新加载验证持久化
        mgr2 = ConfigManager(tmp_path)
        config = mgr2.load()
        assert any(r.name == "main" for r in config.repos)


# ==================== ConfigManager.remove_repo 测试 ====================


class TestConfigManagerRemoveRepo:
    """ConfigManager.remove_repo() 方法测试"""

    def test_remove_repo_success(self, tmp_path):
        """成功删除仓库"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("main"))
        mgr.remove_repo("main")

        assert mgr.get_repo("main") is None

    def test_remove_nonexistent_raises(self, tmp_path):
        """删除不存在的仓库时抛出 ValueError"""
        mgr = ConfigManager(tmp_path)
        mgr.load()

        with pytest.raises(ValueError, match="不存在"):
            mgr.remove_repo("nonexistent")

    def test_remove_repo_persists_to_file(self, tmp_path):
        """删除仓库后配置应持久化到文件"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("main"))
        mgr.remove_repo("main")

        mgr2 = ConfigManager(tmp_path)
        config = mgr2.load()
        assert not any(r.name == "main" for r in config.repos)


# ==================== ConfigManager.get_repo 测试 ====================


class TestConfigManagerGetRepo:
    """ConfigManager.get_repo() 方法测试"""

    def test_get_existing_repo(self, tmp_path):
        """获取已存在的仓库"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("main"))

        repo = mgr.get_repo("main")
        assert repo is not None
        assert repo.name == "main"

    def test_get_nonexistent_returns_none(self, tmp_path):
        """获取不存在的仓库返回 None"""
        mgr = ConfigManager(tmp_path)
        mgr.load()

        assert mgr.get_repo("nonexistent") is None


# ==================== ConfigManager.get_all_repos 测试 ====================


class TestConfigManagerGetAllRepos:
    """ConfigManager.get_all_repos() 方法测试"""

    def test_returns_all_repos(self, tmp_path):
        """返回所有仓库列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        repos = mgr.get_all_repos()
        assert len(repos) == 2
        names = {r.name for r in repos}
        assert names == {"repo1", "repo2"}

    def test_returns_empty_list_when_no_repos(self, tmp_path):
        """没有仓库时返回空列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()

        assert mgr.get_all_repos() == []


# ==================== 路径辅助方法测试 ====================


class TestConfigManagerPaths:
    """路径辅助方法测试"""

    def test_get_ai_driving_dir(self, tmp_path):
        """返回正确的 ai-driving/ 路径"""
        mgr = ConfigManager(tmp_path)
        assert mgr.get_ai_driving_dir() == tmp_path / "ai-driving"

    def test_get_repo_dir(self, tmp_path):
        """返回正确的 ai-driving/<name>/ 路径"""
        mgr = ConfigManager(tmp_path)
        assert mgr.get_repo_dir("main") == tmp_path / "ai-driving" / "main"

    def test_get_framework_base_dir(self, tmp_path):
        """返回正确的 ai-driving/<name>/submodules/ 路径"""
        mgr = ConfigManager(tmp_path)
        assert mgr.get_framework_base_dir("main") == tmp_path / "ai-driving" / "main" / "submodules"

    def test_get_all_gitlist_files_only_existing(self, tmp_path):
        """只返回实际存在的 gitlist.json 文件"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        # 只为 repo1 创建 gitlist.json
        gitlist_dir = tmp_path / "ai-driving" / "repo1" / "frameworks"
        gitlist_dir.mkdir(parents=True)
        (gitlist_dir / "gitlist.json").write_text("[]", encoding="utf-8")

        files = mgr.get_all_gitlist_files()
        assert len(files) == 1
        assert files[0][0] == "repo1"
        assert files[0][1] == gitlist_dir / "gitlist.json"

    def test_get_all_skills_dirs_only_existing(self, tmp_path):
        """只返回实际存在的 skills/ 目录"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        # 只为 repo2 创建 skills 目录
        skills_dir = tmp_path / "ai-driving" / "repo2" / "skills"
        skills_dir.mkdir(parents=True)

        dirs = mgr.get_all_skills_dirs()
        assert len(dirs) == 1
        assert dirs[0][0] == "repo2"
        assert dirs[0][1] == skills_dir

    def test_get_all_gitlist_files_empty_when_no_repos(self, tmp_path):
        """没有仓库时返回空列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        assert mgr.get_all_gitlist_files() == []

    def test_get_all_skills_dirs_empty_when_no_repos(self, tmp_path):
        """没有仓库时返回空列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        assert mgr.get_all_skills_dirs() == []

    def test_get_all_features_dirs_only_existing(self, tmp_path):
        """只返回实际存在的 features/ 目录"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        # 只为 repo1 创建 features 目录
        features_dir = tmp_path / "ai-driving" / "repo1" / "features"
        features_dir.mkdir(parents=True)

        dirs = mgr.get_all_features_dirs()
        assert len(dirs) == 1
        assert dirs[0][0] == "repo1"
        assert dirs[0][1] == features_dir

    def test_get_all_features_dirs_empty_when_no_repos(self, tmp_path):
        """没有仓库时返回空列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        assert mgr.get_all_features_dirs() == []

    def test_get_all_features_dirs_multiple_repos(self, tmp_path):
        """多个仓库都有 features/ 目录时全部返回"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        for name in ("repo1", "repo2"):
            (tmp_path / "ai-driving" / name / "features").mkdir(parents=True)

        dirs = mgr.get_all_features_dirs()
        assert len(dirs) == 2
        names = {d[0] for d in dirs}
        assert names == {"repo1", "repo2"}

    def test_get_all_rules_dirs_only_existing(self, tmp_path):
        """只返回实际存在的 rules/ 目录"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        # 只为 repo2 创建 rules 目录
        rules_dir = tmp_path / "ai-driving" / "repo2" / "rules"
        rules_dir.mkdir(parents=True)

        dirs = mgr.get_all_rules_dirs()
        assert len(dirs) == 1
        assert dirs[0][0] == "repo2"
        assert dirs[0][1] == rules_dir

    def test_get_all_rules_dirs_empty_when_no_repos(self, tmp_path):
        """没有仓库时返回空列表"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        assert mgr.get_all_rules_dirs() == []

    def test_get_all_rules_dirs_multiple_repos(self, tmp_path):
        """多个仓库都有 rules/ 目录时全部返回"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        mgr.add_repo(make_repo("repo1"))
        mgr.add_repo(make_repo("repo2"))

        for name in ("repo1", "repo2"):
            (tmp_path / "ai-driving" / name / "rules").mkdir(parents=True)

        dirs = mgr.get_all_rules_dirs()
        assert len(dirs) == 2
        names = {d[0] for d in dirs}
        assert names == {"repo1", "repo2"}
