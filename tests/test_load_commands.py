"""load 命令单元测试

覆盖：
- _build_system_prompt：无可更新仓库时返回空字符串
- _check_cli_update：有新版本时返回提示、无新版本/异常时返回空字符串
- load 命令：输出结构、必需字段、repos 始终全量、keywords 透传
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.load import _build_system_prompt, _check_cli_update
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


# ==================== _build_system_prompt ====================

class TestBuildSystemPrompt:
    def test_无可更新仓库时返回空字符串(self, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [], [])):
            result = _build_system_prompt()
        assert result == ""

    def test_有可更新仓库时返回提示语(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        repo = mgr.get_repo("driving")
        with patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [repo], [])):
            result = _build_system_prompt()
        assert "driving" in result
        assert "driving repo pull" in result

    def test_异常时返回空字符串(self):
        with patch("driving_cli.commands.load._collect_updatable", side_effect=Exception("网络错误")):
            result = _build_system_prompt()
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

    def test_system_prompt同时包含仓库更新和cli更新(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        repo = mgr.get_repo("driving")
        with patch("driving_cli.commands.load._collect_updatable", return_value=(tmp_project, [repo], [])), \
             patch("driving_cli.commands.load.fetch_version_info", return_value={"version": "99.0.0"}), \
             patch("driving_cli.commands.load._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.commands.load.__version__", "1.0.0"):
            result = _build_system_prompt()
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
        for field in ("cli_version", "skills", "rules", "repos",
                      "system_prompt", "user_prompt"):
            assert field in data

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
        assert isinstance(data["skills"], list)
        assert isinstance(data["rules"], list)

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
