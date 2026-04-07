"""load 命令单元测试

覆盖：
- _build_repos：字段正确、无 status/version/url
- _build_system_prompt：无可更新仓库时返回空字符串
- load 命令：输出结构、必需字段、repos 始终全量、keywords 透传
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.load import _build_repos, _build_system_prompt
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


# ==================== _build_repos ====================

class TestBuildRepos:
    def test_返回所有仓库(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        result = _build_repos(tmp_project, mgr)
        assert len(result) == 2

    def test_包含必需字段(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        result = _build_repos(tmp_project, mgr)
        for entry in result:
            for field in ("name", "type", "description", "path"):
                assert field in entry

    def test_不含status_version_url(self, tmp_project):
        mgr = ConfigManager(tmp_project)
        result = _build_repos(tmp_project, mgr)
        for entry in result:
            assert "status" not in entry
            assert "version" not in entry
            assert "url" not in entry

    def test_description为空时返回空字符串(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "r", "type": "local", "path": "ai-driving/r"},
        ])
        mgr = ConfigManager(tmp_path)
        result = _build_repos(tmp_path, mgr)
        assert result[0]["description"] == ""

    def test_空仓库列表返回空数组(self, tmp_path):
        _make_config(tmp_path, [])
        mgr = ConfigManager(tmp_path)
        result = _build_repos(tmp_path, mgr)
        assert result == []


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


# ==================== load 命令集成测试 ====================

class TestLoadCommand:
    def test_输出合法JSON(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project):
            result = runner.invoke(cli, ["load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_输出包含必需字段(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        for field in ("cli_version", "skills", "rules", "agents", "repos",
                      "system_prompt", "user_prompt"):
            assert field in data

    def test_repos始终全量输出(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        assert len(data["repos"]) == 2

    def test_repos字段不含status_version_url(self, runner, tmp_project):
        with patch("driving_cli.commands.load.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.skill.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.rule.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project):
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
             patch("driving_cli.commands.agent.find_project_root", return_value=tmp_project):
            result = runner.invoke(cli, ["load"])
        data = json.loads(result.output)
        assert isinstance(data["skills"], list)
        assert isinstance(data["rules"], list)
        assert isinstance(data["agents"], list)
