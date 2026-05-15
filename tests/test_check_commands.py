"""check 命令单元测试

覆盖：
- _compare_local_remote：behind>0 返回 True，only-ahead 返回 False，无法解析返回 None
- _collect_updatable：无仓库、跳过未初始化仓库、跳过 local 仓库
- check --json：输出结构、有/无可更新仓库
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.check import _collect_updatable, _compare_local_remote
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


# ==================== _compare_local_remote ====================

class TestCompareLocalRemote:
    def _mock_check_output(self, behind: int, ahead: int = 0):
        """返回模拟 git rev-list --left-right --count 输出的 side_effect"""
        return f"{ahead}\t{behind}\n"

    def test_behind大于0时返回True(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("subprocess.check_output", return_value="0\t3\n"):
            result = _compare_local_remote(tmp_path)
        assert result is True

    def test_仅ahead时返回False(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("subprocess.check_output", return_value="2\t0\n"):
            result = _compare_local_remote(tmp_path)
        assert result is False

    def test_ahead和behind都为0时返回False(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("subprocess.check_output", return_value="0\t0\n"):
            result = _compare_local_remote(tmp_path)
        assert result is False

    def test_ahead和behind都大于0时返回True(self, tmp_path):
        """分叉情况：远端有新提交，仍需提醒"""
        (tmp_path / ".git").mkdir()
        with patch("subprocess.check_output", return_value="1\t2\n"):
            result = _compare_local_remote(tmp_path)
        assert result is True

    def test_所有ref均失败时返回None(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("subprocess.check_output", side_effect=Exception("git error")):
            result = _compare_local_remote(tmp_path)
        assert result is None


# ==================== _collect_updatable ====================

class TestCollectUpdatable:
    def test_无仓库时返回空列表(self, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert updatable == []
        assert warnings == []

    def test_跳过local类型仓库(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local"},
        ])
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert updatable == []
        assert warnings == []

    def test_跳过未初始化的remote仓库(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving"},
        ])
        # 目录不存在，视为未初始化
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert updatable == []
        assert len(warnings) == 1
        assert "driving" in warnings[0]

    def test_compare返回True时加入updatable(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving"},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()  # 模拟已初始化的 git 仓库

        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.check._compare_local_remote", return_value=True):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert len(updatable) == 1
        assert updatable[0].name == "driving"

    def test_compare返回False时不加入updatable(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving"},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()

        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.check._compare_local_remote", return_value=False):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert updatable == []

    def test_compare返回None时加入warnings(self, tmp_path):
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving"},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()

        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.check._compare_local_remote", return_value=None):
            _, updatable, warnings, auto_pull, sample_log = _collect_updatable(fetch=False)
        assert updatable == []
        assert len(warnings) == 1


# ==================== check --json 命令 ====================

class TestCheckJsonCommand:
    def test_输出合法JSON(self, runner, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_输出包含必需字段(self, runner, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["check", "--json"])
        data = json.loads(result.output)
        assert "version" in data
        assert "updatable" in data
        assert "warnings" in data

    def test_无可更新仓库时updatable为空数组(self, runner, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["check", "--json"])
        data = json.loads(result.output)
        assert data["updatable"] == []

    def test_有可更新仓库时updatable包含仓库名(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "driving", "type": "remote", "url": "https://github.com/org/driving",
             "path": "ai-driving/driving"},
        ])
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".git").mkdir()  # 模拟已初始化的 git 仓库

        with patch("driving_cli.commands.check.find_project_root", return_value=tmp_path), \
             patch("driving_cli.commands.check._has_new_version", return_value=True):
            result = runner.invoke(cli, ["check", "--json"])
        data = json.loads(result.output)
        assert "driving" in data["updatable"]
