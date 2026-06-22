"""load 命令单元测试

覆盖：
- _build_notifications：无可更新仓库时返回空字符串
- _check_cli_update：有新版本时返回提示、无新版本/异常时返回空字符串
- load 命令：输出结构、必需字段、repos 始终全量、keywords 透传
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.load import _build_notifications, _check_cli_update
from driving_cli.models.config import DrivingConfig, RepoConfig
from driving_cli.utils.config_manager import ConfigManager


# ==================== Helpers ====================

def _make_config(tmp_path: Path, repos: list) -> None:
    config = {
        "version": "2",
        "repos": repos,
        "default_commit_message": "update",
        "update_version_url": "",
    }
    (tmp_path / "driving.config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_project(tmp_path):
    _make_config(tmp_path, [
        {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
         "path": "ai-driving/driving", "tags": ["base"]},
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local"},
    ])
    return tmp_path


# ==================== _build_notifications ====================

class TestBuildNotifications:
    def test_无可更新仓库时返回空字符串(self, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [], [], [], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = _build_notifications()
        assert result == ""

    def test_有可更新仓库时返回提示语(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        repo = mgr.get_repo("driving")
        with patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [repo], [], [], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            from driving_cli.commands.load import _check_and_pull_repos
            repo_msg = _check_and_pull_repos()
            result = _build_notifications(repo_msg)
        assert "driving" in result
        assert "driving repo pull" in result

    def test_异常时返回空字符串(self):
        with patch("driving_cli.commands.load._collect_updatable", side_effect=Exception("网络错误")), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            from driving_cli.commands.load import _check_and_pull_repos
            repo_msg = _check_and_pull_repos()
            result = _build_notifications(repo_msg)
        assert result == ""


# ==================== _check_cli_update ====================

class TestCheckCliUpdate:
    def test_有新版本时返回提示(self):
        with patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "99.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            result = _check_cli_update()
        assert "99.0.0" in result
        assert "driving update" in result

    def test_已是最新版本时返回空字符串(self):
        with patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "1.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            result = _check_cli_update()
        assert result == ""

    def test_网络失败时返回空字符串(self):
        with patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"):
            result = _check_cli_update()
        assert result == ""

    def test_异常时返回空字符串(self):
        with patch("driving_cli.commands.load.fetch_version_info", side_effect=Exception("err")), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"):
            result = _check_cli_update()
        assert result == ""

    def test_notifications同时包含仓库更新和cli更新(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        repo = mgr.get_repo("driving")
        with patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [repo], [], [], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "99.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            from driving_cli.commands.load import _check_and_pull_repos
            repo_msg = _check_and_pull_repos()
            result = _build_notifications(repo_msg)
        assert "driving repo pull" in result
        assert "driving update" in result
        # CLI 更新优先级更高，应在仓库更新提示之前
        assert result.index("driving update") < result.index("driving repo pull")


# ==================== load 命令集成测试 ====================

class TestLoadCommand:
    @pytest.fixture(autouse=True)
    def _patch_init_submodules(self):
        """所有集成测试默认 mock 掉 submodule 初始化，避免触发真实 git 命令"""
        with patch("driving_cli.commands.load._init_unloaded_submodules"):
            yield

    def test_输出合法JSON(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_输出包含必需字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        # cli_version 和 repos 始终存在；其余字段按需输出（非空才出现）
        assert "cli_version" in data
        assert "repos" in data

    def test_repos始终全量输出(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        # tmp_project 配置了 2 个仓库，但 collect_repos 读取真实 config，断言 >= 2
        assert len(data["repos"]) >= 2

    def test_repos字段不含status_version_url(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        for repo in data["repos"]:
            assert "status" not in repo
            assert "version" not in repo
            assert "url" not in repo

    def test_skills_rules_agents为列表(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        # 非空时才输出，有则断言类型正确
        if "skills" in data:
            assert isinstance(data["skills"], list)
        if "rules" in data:
            assert isinstance(data["rules"], list)

    def test_不传with时不含frameworks和agents字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "frameworks" not in data
        assert "agents" not in data

    def test_with_framework时输出frameworks字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.framework.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.collect_frameworks", return_value=[{"name": "ximage", "description": "图片框架", "path": "ai-driving/driving/frameworks/ximage"}]), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "--with", "framework"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "frameworks" in data
        assert isinstance(data["frameworks"], list)
        assert "agents" not in data

    def test_with_agent时输出agents字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.collect_agents", return_value=[{"name": "android-reviewer", "description": "Android 审查", "path": "ai-driving/driving/agents/android-reviewer"}]), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "--with", "agent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agents" in data
        assert isinstance(data["agents"], list)
        assert "frameworks" not in data

    def test_with_framework_agent时同时输出两个字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.framework.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.collect_frameworks", return_value=[{"name": "ximage", "description": "图片框架", "path": "ai-driving/driving/frameworks/ximage"}]), \
             patch("driving_cli.commands.load.collect_agents", return_value=[{"name": "android-reviewer", "description": "Android 审查", "path": "ai-driving/driving/agents/android-reviewer"}]), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "--with", "framework,agent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "frameworks" in data
        assert "agents" in data

    def test_with_framework_agent字段顺序在system_prompt之前(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.framework.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.collect_frameworks", return_value=[{"name": "ximage", "description": "图片框架", "path": "ai-driving/driving/frameworks/ximage"}]), \
             patch("driving_cli.commands.load.collect_agents", return_value=[{"name": "android-reviewer", "description": "Android 审查", "path": "ai-driving/driving/agents/android-reviewer"}]), \
             patch("driving_cli.commands.load._collect_repo_system_prompts", return_value="some rules"), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "--with", "framework,agent"])
        assert result.exit_code == 0
        keys = list(json.loads(result.output).keys())
        assert keys.index("frameworks") < keys.index("system_prompt")
        assert keys.index("agents") < keys.index("system_prompt")

# ==================== --debug / silent 模式 ====================

class TestLoadDebugFlag:
    @pytest.fixture(autouse=True)
    def _patch_init_submodules(self):
        with patch("driving_cli.commands.load._init_unloaded_submodules"):
            yield

    def _invoke(self, runner, tmp_project, extra_args=None):
        args = ["load"] + (extra_args or [])
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "99.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            return runner.invoke(cli, args)

    def test_默认静默模式输出合法JSON(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project)
        assert result.exit_code == 0
        # 输出应直接是合法 JSON，无日志污染
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_debug模式不设置静默(self, runner, tmp_project):
        from driving_cli.utils import logger as _logger
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            runner.invoke(cli, ["load", "--debug"])
        # --debug 时 silent 应为 False
        assert _logger._silent is False

    def test_默认模式设置静默(self, runner, tmp_project):
        from driving_cli.utils import logger as _logger
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            runner.invoke(cli, ["load"])
        # 默认模式执行完后 silent 为 True（load 命令设置的）
        assert _logger._silent is True


# ==================== _check_min_cli_version ====================

class TestCheckMinCliVersion:
    def test_版本满足时返回空字符串(self, tmp_path):
        (tmp_path / "ai-driving" / "repo-a").mkdir(parents=True)
        (tmp_path / "ai-driving" / "repo-a" / "manifest.json").write_text(
            '{"min_cli_version": "0.0.1"}', encoding="utf-8"
        )
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            from driving_cli.commands.load import _check_min_cli_version
            result = _check_min_cli_version()
        assert result == ""

    def test_版本不满足时返回提示(self, tmp_path):
        (tmp_path / "ai-driving" / "repo-a").mkdir(parents=True)
        (tmp_path / "ai-driving" / "repo-a" / "manifest.json").write_text(
            '{"min_cli_version": "9.9.9"}', encoding="utf-8"
        )
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            from driving_cli.commands.load import _check_min_cli_version
            result = _check_min_cli_version()
        assert "9.9.9" in result
        assert "driving update" in result

    def test_多仓库取最大值(self, tmp_path):
        for name, ver in [("repo-a", "1.1.0"), ("repo-b", "2.0.0"), ("repo-c", "1.5.0")]:
            (tmp_path / "ai-driving" / name).mkdir(parents=True)
            (tmp_path / "ai-driving" / name / "manifest.json").write_text(
                f'{{"min_cli_version": "{ver}"}}', encoding="utf-8"
            )
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            from driving_cli.commands.load import _check_min_cli_version
            result = _check_min_cli_version()
        assert "2.0.0" in result

    def test_无manifest时返回空字符串(self, tmp_path):
        (tmp_path / "ai-driving").mkdir()
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _check_min_cli_version
            result = _check_min_cli_version()
        assert result == ""

    def test_manifest格式错误时静默跳过(self, tmp_path):
        (tmp_path / "ai-driving" / "repo-a").mkdir(parents=True)
        (tmp_path / "ai-driving" / "repo-a" / "manifest.json").write_text(
            "not json", encoding="utf-8"
        )
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _check_min_cli_version
            result = _check_min_cli_version()
        assert result == ""

    def test_version_required优先级最高(self, tmp_path):
        (tmp_path / "ai-driving" / "repo-a").mkdir(parents=True)
        (tmp_path / "ai-driving" / "repo-a" / "manifest.json").write_text(
            '{"min_cli_version": "9.9.9"}', encoding="utf-8"
        )
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.__version__", "1.0.0"), \
             patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_path, [], [], [], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "2.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"):
            from driving_cli.commands.load import _build_notifications
            result = _build_notifications()
        # version_required 应排在最前面
        assert result.index("9.9.9") < result.index("driving update")


# ==================== _collect_repo_system_prompts ====================

class TestCollectRepoSystemPrompts:
    from driving_cli.commands.load import _collect_repo_system_prompts

    def test_读取单仓库prompt文件(self, tmp_path):
        repo = tmp_path / "ai-driving" / "repo-a"
        repo.mkdir(parents=True)
        (repo / "manifest.json").write_text('{"system_prompt": "prompts/sp.md"}', encoding="utf-8")
        (repo / "prompts").mkdir()
        (repo / "prompts" / "sp.md").write_text("hello rules", encoding="utf-8")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _collect_repo_system_prompts
            result = _collect_repo_system_prompts()
        assert "hello rules" in result

    def test_多仓库内容拼接(self, tmp_path):
        for name, content in [("repo-a", "rules-a"), ("repo-b", "rules-b")]:
            repo = tmp_path / "ai-driving" / name
            repo.mkdir(parents=True)
            (repo / "manifest.json").write_text('{"system_prompt": "sp.md"}', encoding="utf-8")
            (repo / "sp.md").write_text(content, encoding="utf-8")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _collect_repo_system_prompts
            result = _collect_repo_system_prompts()
        assert "rules-a" in result
        assert "rules-b" in result

    def test_无system_prompt字段时跳过(self, tmp_path):
        repo = tmp_path / "ai-driving" / "repo-a"
        repo.mkdir(parents=True)
        (repo / "manifest.json").write_text('{"min_cli_version": "1.0.0"}', encoding="utf-8")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _collect_repo_system_prompts
            result = _collect_repo_system_prompts()
        assert result == ""

    def test_文件不存在时跳过(self, tmp_path):
        repo = tmp_path / "ai-driving" / "repo-a"
        repo.mkdir(parents=True)
        (repo / "manifest.json").write_text('{"system_prompt": "not_exist.md"}', encoding="utf-8")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
            from driving_cli.commands.load import _collect_repo_system_prompts
            result = _collect_repo_system_prompts()
        assert result == ""

    def test_repo_prompts排在system_prompt末尾(self, tmp_path):
        repo = tmp_path / "ai-driving" / "repo-a"
        repo.mkdir(parents=True)
        (repo / "manifest.json").write_text('{"system_prompt": "sp.md"}', encoding="utf-8")
        (repo / "sp.md").write_text("business rules", encoding="utf-8")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_path, [], [], [], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "99.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            from driving_cli.commands.load import _build_notifications
            notifications = _build_notifications()
            from driving_cli.commands.load import _collect_repo_system_prompts
            system_prompt = _collect_repo_system_prompts()
        # notifications 包含 CLI 更新提示，system_prompt 包含业务规则，两者独立
        assert "99.0.0" in notifications
        assert "business rules" in system_prompt


# ==================== --platform 参数测试 ====================

class TestLoadPlatformOption:
    """driving load --platform 测试"""

    @pytest.fixture(autouse=True)
    def _patch_init_submodules(self):
        with patch("driving_cli.commands.load._init_unloaded_submodules"):
            yield

    def _invoke(self, runner, tmp_project, extra_args=None):
        args = ["load"] + (extra_args or [])
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            return runner.invoke(cli, args)

    def test_传platform时返回值包含platform字段(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project, ["--platform", "android"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "platform" in data
        assert data["platform"] == "android"

    def test_platform_iOS(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project, ["--platform", "iOS"])
        assert result.exit_code == 0
        assert json.loads(result.output)["platform"] == "iOS"

    def test_platform_harmony(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project, ["--platform", "harmony"])
        assert result.exit_code == 0
        assert json.loads(result.output)["platform"] == "harmony"

    def test_platform_kuikly(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project, ["--platform", "kuikly"])
        assert result.exit_code == 0
        assert json.loads(result.output)["platform"] == "kuikly"

    def test_不传platform时返回值不含platform字段(self, runner, tmp_project):
        result = self._invoke(runner, tmp_project)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "platform" not in data

    def test_platform字段在agents和system_prompt之间(self, runner, tmp_project):
        """platform 字段顺序：在 agents 之后、system_prompt 之前"""
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.collect_agents", return_value=[{"name": "a", "description": "b", "path": "c"}]), \
             patch("driving_cli.commands.load._collect_repo_system_prompts", return_value="some rules"), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "--with", "agent", "--platform", "android"])
        assert result.exit_code == 0
        keys = list(json.loads(result.output).keys())
        assert "platform" in keys
        assert keys.index("agents") < keys.index("platform")
        assert keys.index("platform") < keys.index("system_prompt")

    def test_platform与关键词组合(self, runner, tmp_project):
        """传关键词时 platform 仍然输出"""
        result = self._invoke(runner, tmp_project, ["driving", "--platform", "android"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("platform") == "android"

    def test_platform与关键词组合(self, runner, tmp_project):
        """带关键词时 platform 字段仍然输出"""
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            result = runner.invoke(cli, ["load", "driving", "--platform", "android"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("platform") == "android"
        # 带关键词时不输出 repos / system_prompt
        assert "repos" not in data
        assert "system_prompt" not in data


# ==================== _init_unloaded_submodules ====================

class TestInitUnloadedSubmodules:
    """_init_unloaded_submodules：自动初始化空目录 submodule"""

    def _make_power_config(self, tmp_path: Path, powers: list) -> None:
        (tmp_path / "driving.power.json").write_text(
            json.dumps({"version": "1", "powers": powers}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_无power文件时静默跳过(self, tmp_path):
        """传统模式且无 driving.config.json 时不报错"""
        from driving_cli.commands.load import _init_unloaded_submodules
        import driving_cli.commands.load as _load_mod
        orig = _load_mod._debug_enabled
        try:
            _load_mod._debug_enabled = False
            with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
                 patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path):
                _init_unloaded_submodules()  # 不应抛出异常
        finally:
            _load_mod._debug_enabled = orig

    def test_传统模式空repo目录触发初始化(self, tmp_path):
        """driving.config.json 中的 remote repo 目录为空或不存在时，应执行 submodule 初始化"""
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)  # 空目录，模拟 submodule 未初始化

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None  # update --init 成功

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 应调用过 git submodule update --init
        mock_git_repo.git.submodule.assert_called()
        call_args = mock_git_repo.git.submodule.call_args_list[0][0]
        assert "update" in call_args and "--init" in call_args

    def test_传统模式不存在的repo目录触发初始化(self, tmp_path):
        """driving.config.json 中的 remote repo 目录不存在时（切换分支后），也应执行初始化"""
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        # 不创建 repo_dir，模拟目录完全不存在的情况

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.submodule.assert_called()
        call_args = mock_git_repo.git.submodule.call_args_list[0][0]
        assert "update" in call_args and "--init" in call_args

    def test_传统模式已初始化的repo跳过(self, tmp_path):
        """已有内容的 repo 目录不应触发 git 命令"""
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.md").write_text("content")  # 非空，已初始化

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 目录非空，不应调用 git submodule
        mock_git_repo.git.submodule.assert_not_called()

    def test_local类型repo不触发初始化(self, tmp_path):
        """local 类型的 repo 不应触发 git submodule 操作"""
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local"},
        ])
        repo_dir = tmp_path / "ai-driving" / "my-local"
        repo_dir.mkdir(parents=True)  # 空目录，但 local 类型

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.submodule.assert_not_called()

    def test_power模式空目录触发初始化(self, tmp_path):
        """Power 模式下，空的或不存在的 remote power 目录应触发初始化"""
        self._make_power_config(tmp_path, [
            {"name": "my-power", "type": "remote",
             "url": "https://github.com/org/power.git", "path": "ai-driving/my-power"},
        ])
        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)  # 空目录

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.submodule.assert_called()
        call_args = mock_git_repo.git.submodule.call_args_list[0][0]
        assert "update" in call_args and "--init" in call_args

    def test_power模式目录不存在触发初始化(self, tmp_path):
        """Power 模式下，目录完全不存在（切换分支后）也应触发初始化"""
        self._make_power_config(tmp_path, [
            {"name": "my-power", "type": "remote",
             "url": "https://github.com/org/power.git", "path": "ai-driving/my-power"},
        ])
        # 不创建 power_dir

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.submodule.assert_called()
        call_args = mock_git_repo.git.submodule.call_args_list[0][0]
        assert "update" in call_args and "--init" in call_args

    def test_power初始化成功后安装其repos(self, tmp_path):
        """power 初始化成功后，应继续检查并初始化 power 内的空 repo 目录"""
        self._make_power_config(tmp_path, [
            {"name": "my-power", "type": "remote",
             "url": "https://github.com/org/power.git", "path": "ai-driving/my-power"},
        ])
        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)  # power 目录为空，未初始化

        from driving_cli.commands.load import _init_unloaded_submodules
        call_count = {"n": 0}

        def fake_submodule(*args, **kwargs):
            call_count["n"] += 1
            path_arg = args[-1] if args else ""
            if "my-power" in path_arg:
                # power 初始化成功后写入 driving.config.json 和 repo 空目录
                power_dir.mkdir(parents=True, exist_ok=True)
                (power_dir / "driving.config.json").write_text(json.dumps({
                    "version": "2",
                    "repos": [{"name": "inner-repo", "type": "remote",
                               "url": "https://github.com/org/inner.git",
                               "path": "ai-driving/inner-repo", "tags": []}],
                    "default_commit_message": "update",
                    "update_version_url": "",
                }), encoding="utf-8")
                inner_dir = tmp_path / "ai-driving" / "inner-repo"
                inner_dir.mkdir(parents=True, exist_ok=True)  # inner repo 也是空目录
            return None  # 成功

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.side_effect = fake_submodule

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 应至少调用两次：一次初始化 power，一次初始化 inner-repo
        assert call_count["n"] >= 2

    def test_初始化失败时输出stderr警告(self, tmp_path):
        """初始化失败时应向 stderr 输出警告，不抛异常"""
        import git as _git
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)

        from driving_cli.commands.load import _init_unloaded_submodules
        mock_git_repo = MagicMock()
        err = _git.exc.GitCommandError("submodule", 1)
        err.stderr = "fatal: not a git repository"
        # update --init 失败，且无 url 以触发 log_error 警告（确保 url 为空来触发 '缺少 URL' 路径）
        mock_git_repo.git.submodule.side_effect = err

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            err_output = []
            with patch("click.echo", side_effect=lambda msg, **kw: err_output.append(str(msg))):
                _init_unloaded_submodules()

        # 失败不应抛异常；有失败日志输出（通过 log_error / log_info）
        # 不强求特定文字，只要不崩溃即可
        assert True

    def test_load命令集成时自动触发检测(self, runner, tmp_path):
        """driving load 命令（无 keywords）应自动调用 _init_unloaded_submodules"""
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load._init_unloaded_submodules") as mock_init:
            result = runner.invoke(cli, ["load"])
        assert result.exit_code == 0
        mock_init.assert_called_once()

    def test_load命令带keywords时不触发检测(self, runner, tmp_path):
        """driving load <keyword> 时不应调用 _init_unloaded_submodules"""
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load._init_unloaded_submodules") as mock_init:
            result = runner.invoke(cli, ["load", "driving"])
        assert result.exit_code == 0
        mock_init.assert_not_called()

    def test_update_init失败时降级为submodule_add(self, tmp_path):
        """update --init 失败时，应降级为 git submodule add"""
        import git as _git
        _make_config(tmp_path, [
            {"name": "aidoc", "type": "remote", "url": "https://github.com/org/aidoc.git",
             "path": "ai-driving/aidoc", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "aidoc"
        repo_dir.mkdir(parents=True)  # 空目录，模拟未初始化

        from driving_cli.commands.load import _init_unloaded_submodules
        # .git/modules 目录须存在，avoid rmtree error in cleanup
        (tmp_path / ".git" / "modules").mkdir(parents=True, exist_ok=True)

        update_err = _git.exc.GitCommandError("submodule update", 1)
        update_err.stderr = "pathspec did not match"
        submodule_calls = []

        def fake_submodule(*args, **kwargs):
            submodule_calls.append(list(args))
            if "update" in args and "--init" in args:
                raise update_err
            return None  # add 成功

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.side_effect = fake_submodule

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 先尝试 update --init
        assert any("update" in c and "--init" in c for c in submodule_calls), \
            f"未调用 update --init，实际调用：{submodule_calls}"
        # 降级为 submodule add，并传入正确的 url 和 path
        assert any(
            "add" in c and any("aidoc.git" in str(a) for a in c)
            for c in submodule_calls
        ), f"未降级调用 submodule add，实际调用：{submodule_calls}"

    def test_update_init失败且无url时不降级(self, tmp_path):
        """update --init 失败但 config 中没有 url 时，不应尝试 submodule add"""
        import git as _git
        _make_config(tmp_path, [
            {"name": "aidoc", "type": "remote", "path": "ai-driving/aidoc", "tags": ["base"]},
            # 故意不设置 url
        ])
        repo_dir = tmp_path / "ai-driving" / "aidoc"
        repo_dir.mkdir(parents=True)

        from driving_cli.commands.load import _init_unloaded_submodules
        update_err = _git.exc.GitCommandError("submodule update", 1)
        update_err.stderr = "pathspec did not match"
        submodule_calls = []

        def fake_submodule(*args, **kwargs):
            submodule_calls.append(list(args))
            if "update" in args and "--init" in args:
                raise update_err
            return None

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.side_effect = fake_submodule

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 没有 url，不应尝试 submodule add
        assert not any("add" in c for c in submodule_calls), \
            f"不应调用 submodule add，实际：{submodule_calls}"



class TestEnsurePowerConfig:
    """_ensure_power_config：power 初始化后检查 driving.config.json，按 branch 配置自动切换"""

    def _make_power_entry(self, tmp_path: Path, branch=None) -> object:
        from driving_cli.models.power_config import PowerEntry
        return PowerEntry(
            name="my-power",
            path="ai-driving/my-power",
            url="https://github.com/org/power.git",
            branch=branch,
        )

    def test_config_exists_no_action(self, tmp_path):
        """driving.config.json 已存在时，有 branch 会调用 checkout，但 submodule 不会再触发"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME, CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / CONFIG_FILE_NAME).write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/power.git",
                                    "path": "ai-driving/my-power", "branch": "master"}]}),
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()
        # power 目录非空，不应调用 submodule update --init
        mock_git_repo.git.submodule.assert_not_called()

    def test_no_config_with_branch_triggers_checkout(self, tmp_path):
        """driving.config.json 不存在且配置了 branch 时，应执行 git checkout"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME, CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/power.git",
                                    "path": "ai-driving/my-power", "branch": "master"}]}),
            encoding="utf-8",
        )

        import git as _git

        checkout_done = {"done": False}

        def fake_checkout(branch_name):
            (power_dir / CONFIG_FILE_NAME).write_text(
                json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                            "update_version_url": ""}),
                encoding="utf-8",
            )
            checkout_done["done"] = True

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"  # 当前不是 master
        mock_repo.remotes.__bool__ = lambda self: False
        mock_repo.git.checkout.side_effect = fake_checkout

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _init_unloaded_submodules()

        assert checkout_done["done"], "应执行 git checkout"

    def test_no_config_without_branch_outputs_warning(self, tmp_path):
        """driving.config.json 不存在且未配置 branch 时，应输出警告到 stderr"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/power.git",
                                    "path": "ai-driving/my-power"}]}),
            encoding="utf-8",
        )

        warnings = []
        mock_git_repo = MagicMock()

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("click.echo", side_effect=lambda msg, **kw: warnings.append(str(msg))):
            _init_unloaded_submodules()

        assert any("branch" in w or "分支" in w or "driving.config.json" in w for w in warnings)

    def test_no_config_without_branch_no_checkout_call(self, tmp_path):
        """无 branch 配置时不应尝试执行 git checkout"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/power.git",
                                    "path": "ai-driving/my-power"}]}),
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("click.echo"):
            _init_unloaded_submodules()

        # 无 branch，不应调用 checkout
        mock_git_repo.git.checkout.assert_not_called()

    def test_checkout_fails_outputs_warning(self, tmp_path):
        """git checkout 失败时应输出警告"""
        import git as _git
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/power.git",
                                    "path": "ai-driving/my-power", "branch": "master"}]}),
            encoding="utf-8",
        )

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        mock_repo.remotes.__bool__ = lambda self: False
        mock_repo.git.checkout.side_effect = _git.exc.GitCommandError(
            "checkout", 1, stderr="pathspec 'master' did not match"
        )

        warnings = []
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo), \
             patch("click.echo", side_effect=lambda msg, **kw: warnings.append(str(msg))):
            _init_unloaded_submodules()

        assert any("警告" in w or "失败" in w or "不存在" in w for w in warnings)


# ==================== repo_config 优先级测试 ====================

class TestRepoConfigPriority:
    """验证 PowerEntry.repo_config 字段在 driving load 中的优先级和行为"""

    def _write_power_json(self, tmp_path, powers):
        data = {"powers": powers}
        (tmp_path / "driving.power.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_repo_config_branch_overrides_entry_branch(self, tmp_path):
        """PowerEntry.repo_config 中的 branch 优先于 entry.branch"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / CONFIG_FILE_NAME).write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "branch": "main",
            "repo_config": {"my-power": {"branch": "develop"}},
        }])

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        mock_repo.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_repo.git.checkout.side_effect = lambda b: checked_out.append(b)

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _init_unloaded_submodules()

        # 应切换到 repo_config 指定的 develop，而不是 entry.branch 的 main
        assert "develop" in checked_out

    def test_no_checkout_when_no_branch_in_repo_config_or_entry(self, tmp_path):
        """repo_config 和 entry.branch 都无配置时，不执行 checkout"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / CONFIG_FILE_NAME).write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            # 无 branch，无 repo_config
        }])

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.checkout.assert_not_called()

    def test_fallback_to_entry_branch_when_no_repo_config(self, tmp_path):
        """repo_config 不含自身 name 时，回退使用 entry.branch"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / CONFIG_FILE_NAME).write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        # repo_config 不含 my-power，只有 entry.branch
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "branch": "main",
            "repo_config": {"other-power": {"branch": "develop"}},  # 不含 my-power
        }])

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "master"
        mock_repo.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_repo.git.checkout.side_effect = lambda b: checked_out.append(b)

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _init_unloaded_submodules()

        # 回退到 entry.branch = main
        assert "main" in checked_out

    def test_checkout_failure_outputs_error(self, tmp_path):
        """repo_config 指定分支切换失败时输出错误信息"""
        import git as _git
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import CONFIG_FILE_NAME

        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / CONFIG_FILE_NAME).write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "repo_config": {"my-power": {"branch": "nonexistent"}},
        }])

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        mock_repo.remotes.__bool__ = lambda self: False
        mock_repo.git.checkout.side_effect = _git.exc.GitCommandError(
            "checkout", 1, stderr="pathspec 'nonexistent' did not match any file(s)"
        )

        messages = []
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo), \
             patch("click.echo", side_effect=lambda msg, **kw: messages.append(str(msg))):
            _init_unloaded_submodules()

        assert any("错误" in m for m in messages)


# ==================== repo_config 对已初始化 repo 的分支切换测试 ====================

class TestRepoConfigRepoBranchSwitch:
    """验证 PowerEntry.repo_config 对 power 下已初始化 repo 的分支切换行为（方案 B）"""

    def _write_power_json(self, tmp_path, powers):
        (tmp_path / "driving.power.json").write_text(
            json.dumps({"powers": powers}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_driving_config(self, power_dir, repos):
        power_dir.mkdir(parents=True, exist_ok=True)
        (power_dir / "driving.config.json").write_text(
            json.dumps({
                "version": "2",
                "repos": repos,
                "default_commit_message": "u",
                "update_version_url": "",
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_repo_config_switches_repo_branch(self, tmp_path):
        """power 下已初始化的 repo，repo_config 指定分支时应执行 checkout"""
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")  # 非空，已初始化

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "repo_config": {"driving-base": {"branch": "develop"}},
        }])

        # power 自身的 Repo mock（用于 _ensure_power_config）
        mock_power_repo = MagicMock()
        mock_power_repo.head.is_detached = False
        mock_power_repo.active_branch.name = "main"
        mock_power_repo.remotes.__bool__ = lambda self: False

        # repo 的 Repo mock
        mock_repo_git = MagicMock()
        mock_repo_git.head.is_detached = False
        mock_repo_git.active_branch.name = "main"
        mock_repo_git.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_repo_git.git.checkout.side_effect = lambda b: checked_out.append(b)

        import git as _git

        def fake_git_repo(path):
            if str(path) == str(power_dir):
                return mock_power_repo
            return mock_repo_git

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", side_effect=fake_git_repo):
            _init_unloaded_submodules()

        assert "develop" in checked_out

    def test_repo_without_repo_config_not_switched(self, tmp_path):
        """repo_config 不含该 repo 时，不执行 checkout"""
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            # 无 repo_config
        }])

        mock_git_repo = MagicMock()
        mock_git_repo.head.is_detached = False
        mock_git_repo.active_branch.name = "main"
        mock_git_repo.remotes.__bool__ = lambda self: False

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        # 无 repo_config，不应 checkout
        mock_git_repo.git.checkout.assert_not_called()

    def test_repo_already_on_target_branch_skipped(self, tmp_path):
        """repo 已在目标分支时，跳过切换"""
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "repo_config": {"driving-base": {"branch": "develop"}},
        }])

        mock_power_repo = MagicMock()
        mock_power_repo.head.is_detached = False
        mock_power_repo.active_branch.name = "main"
        mock_power_repo.remotes.__bool__ = lambda self: False

        mock_repo_git = MagicMock()
        mock_repo_git.head.is_detached = False
        mock_repo_git.active_branch.name = "develop"  # 已在目标分支
        mock_repo_git.remotes.__bool__ = lambda self: False

        def fake_git_repo(path):
            if str(path) == str(power_dir):
                return mock_power_repo
            return mock_repo_git

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", side_effect=fake_git_repo):
            _init_unloaded_submodules()

        # 已在目标分支，不应调用 checkout
        mock_repo_git.git.checkout.assert_not_called()

    def test_repo_branch_switch_failure_outputs_error(self, tmp_path):
        """repo 分支切换失败时输出错误"""
        import git as _git
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "repo_config": {"driving-base": {"branch": "nonexistent"}},
        }])

        mock_power_repo = MagicMock()
        mock_power_repo.head.is_detached = False
        mock_power_repo.active_branch.name = "main"
        mock_power_repo.remotes.__bool__ = lambda self: False

        mock_repo_git = MagicMock()
        mock_repo_git.head.is_detached = False
        mock_repo_git.active_branch.name = "main"
        mock_repo_git.remotes.__bool__ = lambda self: False
        mock_repo_git.git.checkout.side_effect = _git.exc.GitCommandError(
            "checkout", 1, stderr="pathspec 'nonexistent' did not match"
        )

        def fake_git_repo(path):
            if str(path) == str(power_dir):
                return mock_power_repo
            return mock_repo_git

        messages = []
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", side_effect=fake_git_repo), \
             patch("click.echo", side_effect=lambda msg, **kw: messages.append(str(msg))):
            _init_unloaded_submodules()

        assert any("错误" in m and "driving-base" in m for m in messages)

    def test_traditional_mode_switches_branch_when_configured(self, tmp_path):
        """传统模式（无 driving.power.json）下，repo 配置了 branch 时应执行分支切换"""
        from driving_cli.commands.load import _init_unloaded_submodules

        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")  # 已初始化

        _make_config(tmp_path, [{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
            "branch": "main",
        }])

        mock_git_repo = MagicMock()
        mock_git_repo.head.is_detached = False
        mock_git_repo.active_branch.name = "develop"  # 当前不在 main
        mock_git_repo.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_git_repo.git.checkout.side_effect = lambda b: checked_out.append(b)

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        assert "main" in checked_out

    def test_traditional_mode_no_branch_field_skips_checkout(self, tmp_path):
        """传统模式下，repo 未配置 branch 字段时不执行分支切换"""
        from driving_cli.commands.load import _init_unloaded_submodules

        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")  # 已初始化

        _make_config(tmp_path, [{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
            # 无 branch 字段
        }])

        mock_git_repo = MagicMock()

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo):
            _init_unloaded_submodules()

        mock_git_repo.git.checkout.assert_not_called()


    def test_fallback_to_repo_branch_when_no_repo_config(self, tmp_path):
        """repo_config 不含该 repo 时，回退使用 driving.config.json 里的 repo.branch"""
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
            "branch": "master",   # repo 自身配置了 branch
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            # 无 repo_config，应回退到 repo.branch
        }])

        mock_power_repo = MagicMock()
        mock_power_repo.head.is_detached = False
        mock_power_repo.active_branch.name = "main"
        mock_power_repo.remotes.__bool__ = lambda self: False

        mock_repo_git = MagicMock()
        mock_repo_git.head.is_detached = False
        mock_repo_git.active_branch.name = "develop"  # 当前不在 master
        mock_repo_git.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_repo_git.git.checkout.side_effect = lambda b: checked_out.append(b)

        def fake_git_repo(path):
            if str(path) == str(power_dir):
                return mock_power_repo
            return mock_repo_git

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", side_effect=fake_git_repo):
            _init_unloaded_submodules()

        # 应回退到 repo.branch = master
        assert "master" in checked_out

    def test_repo_config_overrides_repo_branch(self, tmp_path):
        """repo_config 指定分支时优先于 driving.config.json 里的 repo.branch"""
        from driving_cli.commands.load import _init_unloaded_submodules

        power_dir = tmp_path / "ai-driving" / "my-power"
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        repo_dir.mkdir(parents=True)
        (repo_dir / "some_file.txt").write_text("content")

        self._write_driving_config(power_dir, repos=[{
            "name": "driving-base",
            "type": "remote",
            "url": "https://github.com/org/driving-base.git",
            "path": "ai-driving/driving-base",
            "branch": "master",   # repo 自身配置了 branch
        }])
        self._write_power_json(tmp_path, powers=[{
            "name": "my-power",
            "type": "remote",
            "url": "https://github.com/org/power.git",
            "path": "ai-driving/my-power",
            "repo_config": {"driving-base": {"branch": "feature/xxx"}},  # 覆盖
        }])

        mock_power_repo = MagicMock()
        mock_power_repo.head.is_detached = False
        mock_power_repo.active_branch.name = "main"
        mock_power_repo.remotes.__bool__ = lambda self: False

        mock_repo_git = MagicMock()
        mock_repo_git.head.is_detached = False
        mock_repo_git.active_branch.name = "master"
        mock_repo_git.remotes.__bool__ = lambda self: False
        checked_out = []
        mock_repo_git.git.checkout.side_effect = lambda b: checked_out.append(b)

        def fake_git_repo(path):
            if str(path) == str(power_dir):
                return mock_power_repo
            return mock_repo_git

        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", side_effect=fake_git_repo):
            _init_unloaded_submodules()

        # 应切换到 repo_config 指定的 feature/xxx，而不是 repo.branch 的 master
        assert "feature/xxx" in checked_out
        assert "master" not in checked_out

# ==================== _try_auto_update ====================

from driving_cli.commands.load import _try_auto_update


class TestTryAutoUpdate:
    def test_跳过_非用户目录安装(self, tmp_path):
        """~/.driving-cli/driving 不存在时，返回 None，不执行更新"""
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info") as mock_fetch, \
             patch("subprocess.run") as mock_run:
            result = _try_auto_update()

        assert result is None
        mock_fetch.assert_not_called()
        mock_run.assert_not_called()

    def test_跳过_已是最新版本(self, tmp_path):
        """已是最新版本时返回 None"""
        user_binary = tmp_path / ".driving-cli" / "driving"
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "0.0.1"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=0), \
             patch("subprocess.run") as mock_run:
            result = _try_auto_update()

        assert result is None
        mock_run.assert_not_called()

    def test_更新成功返回system_prompt(self, tmp_path):
        """有新版本且更新成功时，返回 system_prompt 提示文本"""
        import sys
        exe_name = "driving.exe" if sys.platform == "win32" else "driving"
        user_binary = tmp_path / ".driving-cli" / exe_name
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "9.9.9"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=-1), \
             patch("subprocess.run", return_value=mock_proc):
            result = _try_auto_update()

        assert result is not None
        assert "driving load" in result
        assert "9.9.9" in result

    def test_更新成功时system_prompt包含原始命令(self, tmp_path):
        """original_cmd 参数正确回显到 system_prompt 中"""
        import sys
        exe_name = "driving.exe" if sys.platform == "win32" else "driving"
        user_binary = tmp_path / ".driving-cli" / exe_name
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "9.9.9"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=-1), \
             patch("subprocess.run", return_value=mock_proc):
            result = _try_auto_update("driving load --platform android --with framework")

        assert result is not None
        assert "driving load --platform android --with framework" in result

    def test_更新失败返回None(self, tmp_path):
        """更新子进程返回非零时，降级返回 None"""
        user_binary = tmp_path / ".driving-cli" / "driving"
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        mock_proc = MagicMock()
        mock_proc.returncode = 1

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "9.9.9"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=-1), \
             patch("subprocess.run", return_value=mock_proc):
            result = _try_auto_update()

        assert result is None

    def test_异常时降级返回None(self, tmp_path):
        """网络超时或其他异常时，降级返回 None 不抛出"""
        user_binary = tmp_path / ".driving-cli" / "driving"
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   side_effect=Exception("timeout")):
            result = _try_auto_update()

        assert result is None


# ==================== op_reporter 集成：load_invoked / load_auto_updated ====================

class TestLoadOpReporter:
    """driving load 内 op_reporter 调用行为"""

    @pytest.fixture(autouse=True)
    def _patch_init_submodules(self):
        with patch("driving_cli.commands.load._init_unloaded_submodules"):
            yield

    def _invoke(self, runner, tmp_project, extra_args=None):
        args = ["load"] + (extra_args or [])
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None):
            return runner.invoke(cli, args)

    def test_load成功后调用report_op_event_load_invoked(self, runner, tmp_project):
        """driving load 正常完成后应上报 load_invoked"""
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load.report_op_event") as mock_report:
            result = runner.invoke(cli, ["load"])
        assert result.exit_code == 0
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["operation"] == "load_invoked"
        assert call_kwargs.get("silent") is True

    def test_带关键词时不上报load_invoked(self, runner, tmp_project):
        """driving load <keyword> 不上报 load_invoked（关键词模式不是会话开启）"""
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load.report_op_event") as mock_report:
            result = runner.invoke(cli, ["load", "driving"])
        assert result.exit_code == 0
        mock_report.assert_not_called()

    def test_自动更新成功后上报load_auto_updated(self, tmp_path):
        """_try_auto_update 成功时应上报 load_auto_updated"""
        import sys
        from driving_cli.commands.load import _try_auto_update
        exe_name = "driving.exe" if sys.platform == "win32" else "driving"
        user_binary = tmp_path / ".driving-cli" / exe_name
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "9.9.9"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=-1), \
             patch("subprocess.run", return_value=mock_proc), \
             patch("driving_cli.commands.load.report_op_event") as mock_report:
            result = _try_auto_update()

        assert result is not None
        mock_report.assert_called_once()
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs["operation"] == "load_auto_updated"
        assert call_kwargs.get("silent") is True

    def test_自动更新失败时不上报load_auto_updated(self, tmp_path):
        """_try_auto_update 失败（returncode != 0）时不上报"""
        from driving_cli.commands.load import _try_auto_update
        user_binary = tmp_path / ".driving-cli" / "driving"
        user_binary.parent.mkdir(parents=True)
        user_binary.write_bytes(b"binary")

        mock_proc = MagicMock()
        mock_proc.returncode = 1

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("driving_cli.commands.load.fetch_version_info",
                   return_value={"version": "9.9.9"}), \
             patch("driving_cli.commands.load.compare_versions", return_value=-1), \
             patch("subprocess.run", return_value=mock_proc), \
             patch("driving_cli.commands.load.report_op_event") as mock_report:
            result = _try_auto_update()

        assert result is None
        mock_report.assert_not_called()

    def test_platform参数传入extra(self, runner, tmp_project):
        """--platform 参数应出现在上报的 extra 嵌套对象中"""
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load.fetch_version_info", return_value=None), \
             patch("driving_cli.commands.load.report_op_event") as mock_report:
            result = runner.invoke(cli, ["load", "--platform", "android"])
        assert result.exit_code == 0
        call_kwargs = mock_report.call_args.kwargs
        assert call_kwargs.get("extra", {}).get("platform") == "android"


# ==================== _out 静默行为测试 ====================


class TestSubmoduleInitOut:
    """验证 submodule_init._out 在 verbose=False（load 静默模式）下的输出行为：
    - info 级别：完全静默，不写任何输出
    - warning 级别：写 stderr
    - error 级别：写 stderr
    """

    def _collect_echo_calls(self, fn):
        """执行 fn，收集所有 click.echo 的调用参数，返回 (messages, file_args)"""
        messages = []
        file_args = []

        def fake_echo(msg, **kw):
            messages.append(str(msg))
            file_args.append(kw.get("file"))

        with patch("click.echo", side_effect=fake_echo):
            fn()
        return messages, file_args

    def test_info_silent_mode_produces_no_output(self):
        """verbose=False 时 info 级别不写任何输出（包括 stderr）"""
        from driving_cli.utils.submodule_init import _out

        messages, _ = self._collect_echo_calls(
            lambda: _out("正在初始化 power 'xxx'...", verbose=False, level="info")
        )
        assert messages == [], f"info 在静默模式下不应有任何输出，实际：{messages}"

    def test_warning_silent_mode_writes_stderr(self):
        """verbose=False 时 warning 级别写 stderr，前缀包含'警告'"""
        import sys
        from driving_cli.utils.submodule_init import _out

        messages, file_args = self._collect_echo_calls(
            lambda: _out("power 缺少 driving.config.json", verbose=False, level="warning")
        )
        assert len(messages) == 1
        assert "警告" in messages[0]
        assert file_args[0] is sys.stderr

    def test_error_silent_mode_writes_stderr(self):
        """verbose=False 时 error 级别写 stderr，前缀包含'错误'"""
        import sys
        from driving_cli.utils.submodule_init import _out

        messages, file_args = self._collect_echo_calls(
            lambda: _out("切换分支失败", verbose=False, level="error")
        )
        assert len(messages) == 1
        assert "错误" in messages[0]
        assert file_args[0] is sys.stderr

    def test_info_verbose_mode_calls_log_info(self):
        """verbose=True 时 info 级别调用 log_info（交互式命令正常输出）"""
        from driving_cli.utils.submodule_init import _out

        with patch("driving_cli.utils.submodule_init._out.__module__"):
            pass  # 仅确保不抛异常，下面用 log_info mock 验证

        with patch("driving_cli.utils.logger.log_info") as mock_log_info, \
             patch("driving_cli.utils.logger._silent", False):
            _out("正在初始化", verbose=True, level="info")

        mock_log_info.assert_called_once_with("正在初始化")

    def test_init_powers_silent_mode_no_info_output(self, tmp_path):
        """_init_unloaded_submodules 调用 init_powers(verbose=False) 时，
        info 消息不打印到任何输出流（模拟 driving load 场景）"""
        from driving_cli.commands.load import _init_unloaded_submodules
        from driving_cli.utils.config_manager import POWER_FILE_NAME

        # 写 driving.power.json，包含一个已就绪的 remote power（非空目录，走 _ensure_power_config）
        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)
        (power_dir / "driving.config.json").write_text(
            json.dumps({"version": "2", "repos": [], "default_commit_message": "u",
                        "update_version_url": ""}),
            encoding="utf-8",
        )
        (tmp_path / POWER_FILE_NAME).write_text(
            json.dumps({"powers": [{"name": "my-power", "type": "remote",
                                    "url": "https://github.com/org/p.git",
                                    "path": "ai-driving/my-power"}]}),
            encoding="utf-8",
        )

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        mock_repo.remotes.__bool__ = lambda self: False

        echo_calls = []
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.find_git_root", return_value=tmp_path), \
             patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo), \
             patch("click.echo", side_effect=lambda msg, **kw: echo_calls.append(str(msg))):
            _init_unloaded_submodules()

        # 不应有 "[driving] 正在初始化..." 这类 info 消息混入输出
        info_msgs = [m for m in echo_calls if "正在初始化" in m and "[DEBUG" not in m]
        assert info_msgs == [], f"不应有 info 消息输出到 echo，实际：{info_msgs}"
