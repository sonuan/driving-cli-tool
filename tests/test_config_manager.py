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
        """配置文件不存在时返回默认配置，但不写磁盘"""
        mgr = ConfigManager(tmp_path)
        config = mgr.load()

        assert config.version == "2"
        assert config.repos == []
        assert config.default_commit_message == "update by driving"
        # load() 不应创建文件，文件应在首次写操作时才落盘
        assert not (tmp_path / CONFIG_FILE_NAME).exists()

    def test_config_file_created_on_first_write(self, tmp_path):
        """配置文件不存在时，首次写操作（add_repo）才创建文件"""
        mgr = ConfigManager(tmp_path)
        mgr.load()
        assert not (tmp_path / CONFIG_FILE_NAME).exists()

        mgr.add_repo(make_repo("first"))
        assert (tmp_path / CONFIG_FILE_NAME).exists()
        reloaded = ConfigManager(tmp_path).load()
        assert len(reloaded.repos) == 1
        assert reloaded.repos[0].name == "first"

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


# ==================== _merge_configs check_sample_rate 测试 ====================

from driving_cli.utils.config_manager import _merge_configs


class TestMergeConfigsCheckSampleRate:
    """_merge_configs 对 check_sample_rate 的合并行为测试（本次 bugfix 覆盖）"""

    def _cfg(self, rate):
        """创建只设置 check_sample_rate 的 DrivingConfig"""
        return DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=rate,
        )

    def test_zero在合并时不被过滤(self):
        """check_sample_rate=0 不应被当作默认值过滤，应保留"""
        merged = _merge_configs([self._cfg(0), self._cfg(None)], ["a", "b"])
        assert merged.check_sample_rate == 0

    def test_100在合并时不被替换(self):
        """check_sample_rate=100 不应被替换，应保留"""
        merged = _merge_configs([self._cfg(100), self._cfg(None)], ["a", "b"])
        assert merged.check_sample_rate == 100

    def test_两个none合并后结果为none(self):
        """两个 None 合并后结果应为 None"""
        merged = _merge_configs([self._cfg(None), self._cfg(None)], ["a", "b"])
        assert merged.check_sample_rate is None

    def test_minus1在合并时正确保留(self):
        """check_sample_rate=-1（auto_pull）合并后应保留"""
        merged = _merge_configs([self._cfg(-1), self._cfg(None)], ["a", "b"])
        assert merged.check_sample_rate == -1

    def test_相同非None值不报冲突(self):
        """两个 power 均设置相同的 check_sample_rate 应不报冲突"""
        merged = _merge_configs([self._cfg(50), self._cfg(50)], ["a", "b"])
        assert merged.check_sample_rate == 50

    def test_不同非None值报冲突(self):
        """两个 power 设置不同的 check_sample_rate 应抛出 ValueError"""
        with pytest.raises(ValueError, match="配置冲突"):
            _merge_configs([self._cfg(0), self._cfg(50)], ["a", "b"])


# ==================== PowerManager.check_power_updates 测试 ====================


from unittest.mock import patch, MagicMock
from driving_cli.utils.config_manager import PowerManager, POWER_FILE_NAME
from driving_cli.models.power_config import PowerConfig, PowerEntry


def _make_power_json(powers: list) -> dict:
    """构造 driving.power.json 的字典结构"""
    return {"powers": powers}


def _remote_entry(name: str, path: str) -> dict:
    return {"name": name, "type": "remote", "path": path, "url": f"https://example.com/{name}.git"}


def _local_entry(name: str, path: str) -> dict:
    return {"name": name, "type": "local", "path": path}


class TestCheckPowerUpdates:
    """PowerManager.check_power_updates 单元测试

    验证新实现：纯本地对比（_compare_local_remote），不执行 git fetch，并发检测。
    """

    def _setup(self, tmp_path: Path, powers: list) -> PowerManager:
        """写入 driving.power.json 并返回 PowerManager"""
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps(_make_power_json(powers), ensure_ascii=False), encoding="utf-8"
        )
        return PowerManager(tmp_path)

    # ------------------------------------------------------------------
    # 基础场景
    # ------------------------------------------------------------------

    def test_returns_empty_when_no_power_file(self, tmp_path):
        """不存在 driving.power.json 时返回空列表"""
        pm = PowerManager(tmp_path)
        assert pm.check_power_updates() == []

    def test_returns_empty_when_no_remote_powers(self, tmp_path):
        """只有 local 类型的 power 时不检测，返回空列表"""
        pm = self._setup(tmp_path, [_local_entry("local-power", "ai-driving/local-power")])
        assert pm.check_power_updates() == []

    def test_skips_uninitialized_repo(self, tmp_path):
        """power 目录不存在或无 .git 时跳过"""
        pm = self._setup(tmp_path, [_remote_entry("p1", "ai-driving/p1")])
        # ai-driving/p1/.git 不存在
        assert pm.check_power_updates() == []

    # ------------------------------------------------------------------
    # 不执行 git fetch（核心行为验证）
    # ------------------------------------------------------------------

    def test_does_not_call_git_fetch(self, tmp_path):
        """改动后不应再调用 git fetch，全程纯本地"""
        power_dir = tmp_path / "ai-driving" / "p1"
        (power_dir / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [_remote_entry("p1", "ai-driving/p1")])

        with patch("driving_cli.commands.check._compare_local_remote", return_value=False) as mock_cmp, \
             patch("subprocess.run") as mock_run:
            pm.check_power_updates()
            # _compare_local_remote 应被调用
            mock_cmp.assert_called_once()
            # subprocess.run 不应被调用（即没有 git fetch）
            mock_run.assert_not_called()

    # ------------------------------------------------------------------
    # 有更新 / 无更新 场景
    # ------------------------------------------------------------------

    def test_returns_updatable_power(self, tmp_path):
        """_compare_local_remote 返回 True 时，该 power 出现在结果中"""
        power_dir = tmp_path / "ai-driving" / "p1"
        (power_dir / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [_remote_entry("p1", "ai-driving/p1")])

        with patch("driving_cli.commands.check._compare_local_remote", return_value=True):
            result = pm.check_power_updates()

        assert len(result) == 1
        assert result[0].name == "p1"

    def test_returns_empty_when_up_to_date(self, tmp_path):
        """_compare_local_remote 返回 False 时返回空列表"""
        power_dir = tmp_path / "ai-driving" / "p1"
        (power_dir / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [_remote_entry("p1", "ai-driving/p1")])

        with patch("driving_cli.commands.check._compare_local_remote", return_value=False):
            result = pm.check_power_updates()

        assert result == []

    def test_ignores_power_when_compare_raises(self, tmp_path):
        """_compare_local_remote 抛出异常时该 power 被忽略，不影响其他 power"""
        for name in ("p1", "p2"):
            (tmp_path / "ai-driving" / name / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [
            _remote_entry("p1", "ai-driving/p1"),
            _remote_entry("p2", "ai-driving/p2"),
        ])

        def _side_effect(path):
            if "p1" in str(path):
                raise RuntimeError("git error")
            return True  # p2 有更新

        with patch("driving_cli.commands.check._compare_local_remote", side_effect=_side_effect):
            result = pm.check_power_updates()

        assert len(result) == 1
        assert result[0].name == "p2"

    # ------------------------------------------------------------------
    # 多 power 场景：顺序 & 并发
    # ------------------------------------------------------------------

    def test_result_order_matches_config(self, tmp_path):
        """返回结果顺序与 driving.power.json 中的定义顺序一致"""
        for name in ("alpha", "beta", "gamma"):
            (tmp_path / "ai-driving" / name / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [
            _remote_entry("alpha", "ai-driving/alpha"),
            _remote_entry("beta", "ai-driving/beta"),
            _remote_entry("gamma", "ai-driving/gamma"),
        ])

        # 全部有更新，但并发返回顺序不确定
        with patch("driving_cli.commands.check._compare_local_remote", return_value=True):
            result = pm.check_power_updates()

        assert [e.name for e in result] == ["alpha", "beta", "gamma"]

    def test_partial_update_mixed_local_remote(self, tmp_path):
        """local power 跳过，只有部分 remote power 有更新"""
        for name in ("r1", "r2"):
            (tmp_path / "ai-driving" / name / ".git").mkdir(parents=True)

        pm = self._setup(tmp_path, [
            _local_entry("local1", "ai-driving/local1"),
            _remote_entry("r1", "ai-driving/r1"),
            _remote_entry("r2", "ai-driving/r2"),
        ])

        def _side_effect(path):
            return "r2" in str(path)

        with patch("driving_cli.commands.check._compare_local_remote", side_effect=_side_effect):
            result = pm.check_power_updates()

        assert [e.name for e in result] == ["r2"]
