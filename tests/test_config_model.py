"""配置数据模型单元测试

测试 RepoConfig 和 DrivingConfig 的序列化/反序列化往返一致性。
"""

import pytest

from driving.models.config import DrivingConfig, RepoConfig


class TestRepoConfig:
    """RepoConfig 序列化测试"""

    def test_remote_repo_to_dict(self):
        """测试远程仓库序列化为字典"""
        repo = RepoConfig(
            name="main",
            type="remote",
            url="https://github.com/example/driving",
            path="ai-driving/main",
            local_path=None,
        )
        d = repo.to_dict()
        assert d["name"] == "main"
        assert d["type"] == "remote"
        assert d["url"] == "https://github.com/example/driving"
        assert d["path"] == "ai-driving/main"
        assert d["local_path"] is None

    def test_local_repo_to_dict(self):
        """测试本地仓库序列化为字典"""
        repo = RepoConfig(
            name="local-docs",
            type="local",
            url=None,
            path="ai-driving/local-docs",
            local_path="/absolute/path/to/local-docs",
        )
        d = repo.to_dict()
        assert d["name"] == "local-docs"
        assert d["type"] == "local"
        assert d["url"] is None
        assert d["local_path"] == "/absolute/path/to/local-docs"

    def test_repo_from_dict_remote(self):
        """测试从字典反序列化远程仓库"""
        data = {
            "name": "main",
            "type": "remote",
            "url": "https://github.com/example/driving",
            "path": "ai-driving/main",
            "local_path": None,
        }
        repo = RepoConfig.from_dict(data)
        assert repo.name == "main"
        assert repo.type == "remote"
        assert repo.url == "https://github.com/example/driving"
        assert repo.path == "ai-driving/main"
        assert repo.local_path is None

    def test_repo_from_dict_local(self):
        """测试从字典反序列化本地仓库"""
        data = {
            "name": "private",
            "type": "local",
            "path": "ai-driving/private",
        }
        repo = RepoConfig.from_dict(data)
        assert repo.name == "private"
        assert repo.type == "local"
        assert repo.url is None
        assert repo.local_path is None

    def test_repo_roundtrip(self):
        """测试序列化往返一致性"""
        original = RepoConfig(
            name="test-repo",
            type="remote",
            url="https://github.com/example/test",
            path="ai-driving/test-repo",
            local_path=None,
        )
        restored = RepoConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.url == original.url
        assert restored.path == original.path
        assert restored.local_path == original.local_path

    def test_repo_from_dict_missing_required_field(self):
        """测试缺少必填字段时抛出 KeyError"""
        with pytest.raises(KeyError):
            RepoConfig.from_dict({"type": "remote", "path": "ai-driving/main"})  # 缺少 name

    def test_repo_from_dict_missing_path(self):
        """测试缺少 path 字段时抛出 KeyError"""
        with pytest.raises(KeyError):
            RepoConfig.from_dict({"name": "main", "type": "remote"})  # 缺少 path


class TestDrivingConfig:
    """DrivingConfig 序列化测试"""

    def _make_config(self) -> DrivingConfig:
        """创建测试用配置对象"""
        return DrivingConfig(
            version="2",
            repos=[
                RepoConfig(
                    name="main",
                    type="remote",
                    url="https://github.com/example/driving",
                    path="ai-driving/main",
                    local_path=None,
                ),
                RepoConfig(
                    name="local-docs",
                    type="local",
                    url=None,
                    path="ai-driving/local-docs",
                    local_path="/path/to/local-docs",
                ),
            ],
            default_commit_message="update by driving",
            update_version_url="https://raw.githubusercontent.com/example/driving/main/dist/version.json",
        )

    def test_to_dict_structure(self):
        """测试序列化后的字典结构"""
        config = self._make_config()
        d = config.to_dict()
        assert d["version"] == "2"
        assert len(d["repos"]) == 2
        assert d["default_commit_message"] == "update by driving"
        assert "update_version_url" in d

    def test_to_dict_repos_serialized(self):
        """测试 repos 列表中的元素也被正确序列化"""
        config = self._make_config()
        d = config.to_dict()
        assert isinstance(d["repos"][0], dict)
        assert d["repos"][0]["name"] == "main"

    def test_from_dict(self):
        """测试从字典反序列化"""
        data = {
            "version": "2",
            "repos": [
                {
                    "name": "main",
                    "type": "remote",
                    "url": "https://github.com/example/driving",
                    "path": "ai-driving/main",
                    "local_path": None,
                }
            ],
            "default_commit_message": "update by driving",
            "update_version_url": "https://example.com/version.json",
        }
        config = DrivingConfig.from_dict(data)
        assert config.version == "2"
        assert len(config.repos) == 1
        assert config.repos[0].name == "main"
        assert config.default_commit_message == "update by driving"

    def test_roundtrip(self):
        """测试序列化往返一致性"""
        original = self._make_config()
        restored = DrivingConfig.from_dict(original.to_dict())

        assert restored.version == original.version
        assert restored.default_commit_message == original.default_commit_message
        assert restored.update_version_url == original.update_version_url
        assert len(restored.repos) == len(original.repos)

        for orig_repo, rest_repo in zip(original.repos, restored.repos):
            assert rest_repo.name == orig_repo.name
            assert rest_repo.type == orig_repo.type
            assert rest_repo.url == orig_repo.url
            assert rest_repo.path == orig_repo.path
            assert rest_repo.local_path == orig_repo.local_path

    def test_from_dict_missing_version(self):
        """测试缺少 version 字段时抛出 KeyError"""
        with pytest.raises(KeyError):
            DrivingConfig.from_dict({
                "repos": [],
                "default_commit_message": "msg",
                "update_version_url": "https://example.com",
            })

    def test_from_dict_repos_not_list(self):
        """测试 repos 不是列表时抛出 ValueError"""
        with pytest.raises(ValueError):
            DrivingConfig.from_dict({
                "version": "2",
                "repos": "not-a-list",
                "default_commit_message": "msg",
                "update_version_url": "https://example.com",
            })

    def test_empty_repos(self):
        """测试空仓库列表的序列化往返"""
        config = DrivingConfig(
            version="2",
            repos=[],
            default_commit_message="msg",
            update_version_url="https://example.com",
        )
        restored = DrivingConfig.from_dict(config.to_dict())
        assert restored.repos == []


# ============================================================
# 属性测试（Property-Based Tests）
# Feature: multi-repo-support, Property 1: 配置序列化往返一致性
# Validates: Requirements 1.6
# ============================================================

from hypothesis import given, settings
from hypothesis import strategies as st

# 生成合法仓库名称的策略（字母/数字/连字符/下划线，首字符为字母或数字）
_repo_name_st = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,30}", fullmatch=True)

# 生成仓库类型的策略
_repo_type_st = st.sampled_from(["remote", "local"])

# 生成可选字符串的策略
_optional_text_st = st.one_of(st.none(), st.text(min_size=1, max_size=100))


@st.composite
def repo_config_st(draw) -> RepoConfig:
    """生成任意合法 RepoConfig 的策略"""
    name = draw(_repo_name_st)
    repo_type = draw(_repo_type_st)
    url = draw(_optional_text_st)
    path = draw(st.text(min_size=1, max_size=100))
    local_path = draw(_optional_text_st)
    return RepoConfig(name=name, type=repo_type, url=url, path=path, local_path=local_path)


@st.composite
def driving_config_st(draw) -> DrivingConfig:
    """生成任意合法 DrivingConfig 的策略"""
    version = draw(st.text(min_size=1, max_size=10))
    repos = draw(st.lists(repo_config_st(), min_size=0, max_size=5))
    default_commit_message = draw(st.text(min_size=0, max_size=200))
    update_version_url = draw(st.text(min_size=1, max_size=200))
    return DrivingConfig(
        version=version,
        repos=repos,
        default_commit_message=default_commit_message,
        update_version_url=update_version_url,
    )


class TestPropertySerializationRoundtrip:
    """Property 1：配置序列化往返一致性属性测试"""

    @given(repo_config_st())
    @settings(max_examples=100)
    def test_repo_config_roundtrip(self, repo: RepoConfig):
        """对任意合法 RepoConfig，serialize → deserialize 应得到等价对象
        
        # Feature: multi-repo-support, Property 1: 配置序列化往返一致性
        # Validates: Requirements 1.6
        """
        restored = RepoConfig.from_dict(repo.to_dict())
        assert restored.name == repo.name
        assert restored.type == repo.type
        assert restored.url == repo.url
        assert restored.path == repo.path
        assert restored.local_path == repo.local_path

    @given(driving_config_st())
    @settings(max_examples=100)
    def test_driving_config_roundtrip(self, config: DrivingConfig):
        """对任意合法 DrivingConfig，serialize → deserialize 应得到等价对象
        
        # Feature: multi-repo-support, Property 1: 配置序列化往返一致性
        # Validates: Requirements 1.6
        """
        restored = DrivingConfig.from_dict(config.to_dict())
        assert restored.version == config.version
        assert restored.default_commit_message == config.default_commit_message
        assert restored.update_version_url == config.update_version_url
        assert len(restored.repos) == len(config.repos)

        for orig, rest in zip(config.repos, restored.repos):
            assert rest.name == orig.name
            assert rest.type == orig.type
            assert rest.url == orig.url
            assert rest.path == orig.path
            assert rest.local_path == orig.local_path
