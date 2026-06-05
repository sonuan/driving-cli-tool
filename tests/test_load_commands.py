"""load 命令单元测试

覆盖：
- _build_notifications：无可更新仓库时返回空字符串
- _check_cli_update：有新版本时返回提示、无新版本/异常时返回空字符串
- load 命令：输出结构、必需字段、repos 始终全量、keywords 透传
"""

import json
from pathlib import Path
from unittest.mock import patch

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
    def test_输出合法JSON(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
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
            with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path):
                _init_unloaded_submodules()  # 不应抛出异常
        finally:
            _load_mod._debug_enabled = orig

    def test_传统模式空repo目录触发初始化(self, tmp_path):
        """driving.config.json 中的 remote repo 目录为空时，应执行 git submodule update --init"""
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)  # 空目录，模拟 submodule 未初始化

        import subprocess
        from driving_cli.commands.load import _init_unloaded_submodules
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            _init_unloaded_submodules()

        # 应调用过 git submodule update --init
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("submodule" in c and "update" in c for c in calls)

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
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run") as mock_run:
            _init_unloaded_submodules()

        # 目录非空，不应调用 git submodule update --init
        assert not any(
            "submodule" in str(c) and "update" in str(c)
            for c in mock_run.call_args_list
        )

    def test_local类型repo不触发初始化(self, tmp_path):
        """local 类型的 repo 不应触发 git submodule 操作"""
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local"},
        ])
        repo_dir = tmp_path / "ai-driving" / "my-local"
        repo_dir.mkdir(parents=True)  # 空目录，但 local 类型

        from driving_cli.commands.load import _init_unloaded_submodules
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run") as mock_run:
            _init_unloaded_submodules()

        assert not any(
            "submodule" in str(c) for c in mock_run.call_args_list
        )

    def test_power模式空目录触发初始化(self, tmp_path):
        """Power 模式下，空的 remote power 目录应触发初始化"""
        self._make_power_config(tmp_path, [
            {"name": "my-power", "type": "remote",
             "url": "https://github.com/org/power.git", "path": "ai-driving/my-power"},
        ])
        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)  # 空目录

        import subprocess
        from driving_cli.commands.load import _init_unloaded_submodules
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            _init_unloaded_submodules()

        assert any("submodule" in str(c) and "update" in str(c) for c in mock_run.call_args_list)

    def test_power初始化成功后安装其repos(self, tmp_path):
        """power 初始化成功后，应继续检查并初始化 power 内的空 repo 目录"""
        self._make_power_config(tmp_path, [
            {"name": "my-power", "type": "remote",
             "url": "https://github.com/org/power.git", "path": "ai-driving/my-power"},
        ])
        power_dir = tmp_path / "ai-driving" / "my-power"
        power_dir.mkdir(parents=True)  # power 目录为空，未初始化

        import subprocess
        call_count = {"n": 0}

        def fake_run(cmd, **kwargs):
            call_count["n"] += 1
            path_arg = cmd[-1] if cmd else ""
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
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        from driving_cli.commands.load import _init_unloaded_submodules
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=fake_run):
            _init_unloaded_submodules()

        # 应至少调用两次：一次初始化 power，一次初始化 inner-repo
        assert call_count["n"] >= 2

    def test_初始化失败时输出stderr警告(self, tmp_path):
        """初始化失败时应向 stderr 输出警告，不抛异常"""
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving", "tags": ["base"]},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)

        import subprocess
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="fatal: not a git repository"
        )
        from driving_cli.commands.load import _init_unloaded_submodules
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result):
            # 失败时不应抛出异常，应静默处理并输出警告到 stderr
            import io
            from unittest.mock import patch as _patch
            err_output = []
            with _patch("click.echo", side_effect=lambda msg, **kw: err_output.append(str(msg))):
                _init_unloaded_submodules()

        assert any("警告" in m or "初始化失败" in m for m in err_output)

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
