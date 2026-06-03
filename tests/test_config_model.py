"""配置数据模型单元测试

测试 RepoConfig 和 DrivingConfig 的序列化/反序列化往返一致性。
"""

import pytest

from driving_cli.models.config import DrivingConfig, ModuleConfig, RepoConfig


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

    def test_rules_none_not_in_to_dict(self):
        """rules=None 时，to_dict() 输出不应包含 rules 键"""
        repo = RepoConfig(name="r", type="local", path="ai-driving/r", rules=None)
        d = repo.to_dict()
        assert "rules" not in d

    def test_rules_value_in_to_dict(self):
        """rules 有值时，to_dict() 应包含 rules 键"""
        rules = {"enabled": ["nav", "style"], "disabled": []}
        repo = RepoConfig(name="r", type="local", path="ai-driving/r", rules=rules)
        d = repo.to_dict()
        assert "rules" in d
        assert d["rules"] == rules

    def test_rules_roundtrip(self):
        """rules 字段通过 to_dict() / from_dict() 往返后应保持一致"""
        rules = {"enabled": ["nav"], "disabled": ["old-rule"]}
        repo = RepoConfig(name="r", type="local", path="ai-driving/r", rules=rules)
        restored = RepoConfig.from_dict(repo.to_dict())
        assert restored.rules == rules

    def test_rules_none_roundtrip(self):
        """rules=None 往返后仍为 None"""
        repo = RepoConfig(name="r", type="local", path="ai-driving/r", rules=None)
        restored = RepoConfig.from_dict(repo.to_dict())
        assert restored.rules is None

    # ---------- modules 字段测试 ----------

    def test_modules_none_serializes_to_empty_list(self):
        """modules=None 时，to_dict() 应输出空数组（字段始终存在）"""
        repo = RepoConfig(name="r", type="local", path="ai-driving/r")
        d = repo.to_dict()
        assert "modules" in d
        assert d["modules"] == []

    def test_modules_with_items_serializes_correctly(self):
        """modules 有值时，to_dict() 应输出对应数组"""
        repo = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            modules=[
                ModuleConfig(name="order", description="订单模块"),
                ModuleConfig(name="pay", description="支付模块"),
            ]
        )
        d = repo.to_dict()
        assert len(d["modules"]) == 2
        assert d["modules"][0] == {"name": "order", "description": "订单模块"}
        assert d["modules"][1] == {"name": "pay", "description": "支付模块"}

    def test_modules_roundtrip(self):
        """modules 字段通过 to_dict() / from_dict() 往返后应保持一致"""
        repo = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            modules=[ModuleConfig(name="im", description="即时通讯")]
        )
        restored = RepoConfig.from_dict(repo.to_dict())
        assert restored.modules is not None
        assert len(restored.modules) == 1
        assert restored.modules[0].name == "im"
        assert restored.modules[0].description == "即时通讯"

    def test_modules_empty_list_roundtrip(self):
        """modules=[] 序列化后反序列化应得到 None（因为空列表被归一化）"""
        data = {"name": "r", "type": "local", "path": "ai-driving/r", "modules": []}
        restored = RepoConfig.from_dict(data)
        # 空数组反序列化后 modules 字段为 None（无有效 module）
        assert not restored.modules

    def test_modules_from_dict_ignores_invalid_items(self):
        """from_dict 忽略 modules 中非字典类型的元素"""
        data = {
            "name": "r", "type": "local", "path": "ai-driving/r",
            "modules": [{"name": "valid", "description": "ok"}, "not-a-dict", 42]
        }
        restored = RepoConfig.from_dict(data)
        assert restored.modules is not None
        assert len(restored.modules) == 1
        assert restored.modules[0].name == "valid"

    def test_module_config_to_dict(self):
        """ModuleConfig.to_dict() 输出正确格式"""
        mod = ModuleConfig(name="chat", description="聊天模块")
        d = mod.to_dict()
        assert d == {"name": "chat", "description": "聊天模块"}

    def test_module_config_from_dict(self):
        """ModuleConfig.from_dict() 反序列化正确"""
        mod = ModuleConfig.from_dict({"name": "live", "description": "直播模块"})
        assert mod.name == "live"
        assert mod.description == "直播模块"

    def test_module_config_from_dict_missing_description(self):
        """ModuleConfig.from_dict() 缺少 description 时默认为空字符串"""
        mod = ModuleConfig.from_dict({"name": "payment"})
        assert mod.name == "payment"
        assert mod.description == ""


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


class TestDrivingConfigCheckSampleRate:
    """DrivingConfig.check_sample_rate 字段行为测试（本次 bugfix 覆盖）"""

    def test_check_sample_rate_zero_roundtrip(self):
        """check_sample_rate=0（永不检测）序列化往返后应保持为 0"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=0,
        )
        restored = DrivingConfig.from_dict(cfg.to_dict())
        assert restored.check_sample_rate == 0

    def test_check_sample_rate_100_roundtrip(self):
        """check_sample_rate=100（全量检测）序列化往返后应保持为 100"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=100,
        )
        restored = DrivingConfig.from_dict(cfg.to_dict())
        assert restored.check_sample_rate == 100

    def test_check_sample_rate_none_when_not_in_json(self):
        """JSON 中未包含 check_sample_rate 时，应反序列化为 None"""
        cfg = DrivingConfig.from_dict({
            "version": "2", "repos": [],
            "default_commit_message": "msg", "update_version_url": "",
        })
        assert cfg.check_sample_rate is None

    def test_check_sample_rate_zero_not_in_to_dict_for_default_none(self):
        """check_sample_rate=None 时，to_dict() 不应包含该字段"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=None,
        )
        assert "check_sample_rate" not in cfg.to_dict()

    def test_check_sample_rate_zero_in_to_dict(self):
        """check_sample_rate=0 时，to_dict() 应包含该字段"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=0,
        )
        assert cfg.to_dict()["check_sample_rate"] == 0

    def test_check_sample_rate_50_roundtrip(self):
        """check_sample_rate=50 序列化往返后应保持为 50"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=50,
        )
        restored = DrivingConfig.from_dict(cfg.to_dict())
        assert restored.check_sample_rate == 50

    def test_check_sample_rate_minus1_roundtrip(self):
        """check_sample_rate=-1（auto_pull）序列化往返后应保持为 -1"""
        cfg = DrivingConfig(
            version="2", repos=[], default_commit_message="msg",
            update_version_url="", check_sample_rate=-1,
        )
        restored = DrivingConfig.from_dict(cfg.to_dict())
        assert restored.check_sample_rate == -1


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
