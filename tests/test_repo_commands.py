"""repo 子命令组单元测试

覆盖 driving repo install / list / uninstall / pull / commit / push 的主要功能。
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.repo import _resolve_repos, repo_group
from driving_cli.models.config import DrivingConfig, RepoConfig
from driving_cli.utils.config_manager import ConfigManager


# ==================== 测试夹具 ====================

@pytest.fixture
def tmp_project(tmp_path):
    """创建临时项目目录，包含基础配置文件"""
    config = DrivingConfig(
        version="2",
        repos=[],
        default_commit_message="update by driving",
        update_version_url="",
    )
    config_file = tmp_path / "driving.config.json"
    config_file.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp_path


@pytest.fixture
def config_mgr(tmp_project):
    """返回指向临时项目的 ConfigManager"""
    return ConfigManager(tmp_project)


@pytest.fixture
def runner():
    return CliRunner()


# ==================== repo list 测试 ====================

class TestRepoList:
    def test_list_empty(self, runner, tmp_project):
        """空配置时提示尚未安装任何仓库"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        assert "尚未安装任何仓库" in result.output

    def test_list_with_remote_repo(self, runner, tmp_project, config_mgr):
        """有远程仓库时正确展示"""
        repo_cfg = RepoConfig(
            name="main",
            type="remote",
            url="https://github.com/org/repo.git",
            path="ai-driving/main",
        )
        config_mgr.add_repo(repo_cfg)

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        assert "main" in result.output
        assert "remote" in result.output
        assert "https://github.com/org/repo.git" in result.output

    def test_list_with_local_repo(self, runner, tmp_project, config_mgr):
        """有本地仓库时正确展示"""
        repo_cfg = RepoConfig(
            name="local-docs",
            type="local",
            url=None,
            path="ai-driving/local-docs",
            local_path=None,
        )
        config_mgr.add_repo(repo_cfg)

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        assert "local-docs" in result.output
        assert "local" in result.output

    def test_list_distinguishes_remote_and_local(self, runner, tmp_project, config_mgr):
        """列表中区分 remote 和 local 仓库"""
        config_mgr.add_repo(RepoConfig(name="remote-repo", type="remote",
                                        url="https://github.com/org/r.git",
                                        path="ai-driving/remote-repo"))
        config_mgr.add_repo(RepoConfig(name="local-repo", type="local",
                                        url=None, path="ai-driving/local-repo"))

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        assert "远程仓库" in result.output
        assert "本地仓库" in result.output


# ==================== repo install 测试 ====================

class TestRepoInstall:
    def test_install_no_args_no_config(self, runner, tmp_project):
        """无参数且配置为空时提示无远程仓库"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["install"])
        assert result.exit_code == 0
        assert "没有远程仓库" in result.output

    def test_install_invalid_url(self, runner, tmp_project):
        """非法 URL 应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["install", "--url", "not-a-url"])
        assert result.exit_code != 0
        assert "URL 格式不合法" in result.output

    def test_install_invalid_repo_name(self, runner, tmp_project):
        """非法仓库名称应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/repo.git",
                "--name", "invalid name!"
            ])
        assert result.exit_code != 0
        assert "仓库名称" in result.output

    def test_install_duplicate_name_without_force(self, runner, tmp_project, config_mgr):
        """重复名称不加 --force 应报错"""
        config_mgr.add_repo(RepoConfig(name="main", type="remote",
                                        url="https://github.com/org/r.git",
                                        path="ai-driving/main"))
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/other.git", "--name", "main"
            ])
        assert result.exit_code != 0
        assert "已存在" in result.output

    def test_install_local_nonexistent_path(self, runner, tmp_project):
        """本地路径不存在时应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "/nonexistent/path/xyz", "--name", "mylocal"
            ])
        assert result.exit_code != 0
        assert "本地路径不存在" in result.output

    def test_install_local_no_path_creates_directory(self, runner, tmp_project):
        """--local 无路径时创建普通目录并写入配置"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "--name", "mylocal"
            ])
        assert result.exit_code == 0
        assert (tmp_project / "ai-driving" / "mylocal").is_dir()
        # 验证配置已写入
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("mylocal")
        assert repo_cfg is not None
        assert repo_cfg.type == "local"
        assert repo_cfg.local_path is None

    def test_install_local_with_path_creates_symlink(self, runner, tmp_project, tmp_path):
        """--local <path> 时创建软链接并写入配置"""
        # 创建一个真实的本地目录
        src_dir = tmp_path / "my-source"
        src_dir.mkdir()

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", str(src_dir), "--name", "linked-repo"
            ])
        assert result.exit_code == 0
        link_path = tmp_project / "ai-driving" / "linked-repo"
        assert link_path.is_symlink()
        # 验证配置
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("linked-repo")
        assert repo_cfg is not None
        assert repo_cfg.type == "local"
        assert repo_cfg.local_path == str(src_dir.resolve())

    def test_install_no_args_initializes_uninitialized(self, runner, tmp_project, config_mgr):
        """无参数 install 对未初始化的远程仓库执行 submodule update"""
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="https://github.com/org/repo.git",
            path="ai-driving/main",
        ))

        mock_git_repo = MagicMock()
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(repo_group, ["install"])

        assert result.exit_code == 0
        # 应调用 submodule update --init
        mock_git_repo.git.submodule.assert_called_once_with("update", "--init", "ai-driving/main")


# ==================== repo uninstall 测试 ====================

class TestRepoUninstall:
    def test_uninstall_nonexistent(self, runner, tmp_project):
        """卸载不存在的仓库应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["uninstall", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_uninstall_local_symlink(self, runner, tmp_project, config_mgr, tmp_path):
        """卸载本地软链接仓库：移除软链接并更新配置"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        link_dir = tmp_project / "ai-driving" / "linked"
        link_dir.parent.mkdir(parents=True, exist_ok=True)
        link_dir.symlink_to(src_dir)

        config_mgr.add_repo(RepoConfig(
            name="linked", type="local",
            url=None, path="ai-driving/linked",
            local_path=str(src_dir),
        ))

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["uninstall", "linked"])

        assert result.exit_code == 0
        assert not link_dir.exists()
        assert not link_dir.is_symlink()
        # 配置中已移除
        assert config_mgr.get_repo("linked") is None

    def test_uninstall_local_directory(self, runner, tmp_project, config_mgr):
        """卸载本地普通目录仓库：删除目录并更新配置"""
        repo_dir = tmp_project / "ai-driving" / "mylocal"
        repo_dir.mkdir(parents=True)

        config_mgr.add_repo(RepoConfig(
            name="mylocal", type="local",
            url=None, path="ai-driving/mylocal",
        ))

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["uninstall", "mylocal"])

        assert result.exit_code == 0
        assert not repo_dir.exists()
        assert config_mgr.get_repo("mylocal") is None

    def test_uninstall_removes_from_config(self, runner, tmp_project, config_mgr):
        """卸载后配置中不再包含该仓库"""
        config_mgr.add_repo(RepoConfig(
            name="to-remove", type="local",
            url=None, path="ai-driving/to-remove",
        ))
        assert config_mgr.get_repo("to-remove") is not None

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["uninstall", "to-remove"])

        assert config_mgr.get_repo("to-remove") is None


# ==================== repo pull/commit/push 测试 ====================

class TestRepoGitOps:
    def _make_remote_repo(self, config_mgr, name="main"):
        config_mgr.add_repo(RepoConfig(
            name=name, type="remote",
            url="https://github.com/org/repo.git",
            path=f"ai-driving/{name}",
        ))

    def _make_local_repo(self, config_mgr, name="local-docs"):
        config_mgr.add_repo(RepoConfig(
            name=name, type="local",
            url=None, path=f"ai-driving/{name}",
        ))

    def test_pull_skips_local_repo(self, runner, tmp_project, config_mgr):
        """pull 对 local 仓库跳过并给出提示"""
        self._make_local_repo(config_mgr)
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "pull" in result.output

    def test_push_skips_local_repo(self, runner, tmp_project, config_mgr):
        """push 对 local 仓库跳过并给出提示"""
        self._make_local_repo(config_mgr)
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["push", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "push" in result.output

    def test_commit_skips_local_repo(self, runner, tmp_project, config_mgr):
        """commit 对 local 仓库跳过并给出提示"""
        self._make_local_repo(config_mgr)
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["commit", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "commit" in result.output

    def test_pull_nonexistent_repo(self, runner, tmp_project):
        """pull 指定不存在的仓库应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_push_nonexistent_repo(self, runner, tmp_project):
        """push 指定不存在的仓库应报错"""
        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["push", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_pull_all_skips_local(self, runner, tmp_project, config_mgr):
        """不指定仓库时，pull 跳过所有 local 仓库"""
        self._make_local_repo(config_mgr, "local1")
        self._make_local_repo(config_mgr, "local2")

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull"])
        assert result.exit_code == 0
        assert result.output.count("跳过") == 2

    def test_commit_message_as_first_arg(self, runner, tmp_project, config_mgr):
        """commit 第一个参数不是仓库名时视为提交信息"""
        self._make_local_repo(config_mgr, "local-docs")

        with patch("driving.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["commit", "my commit message"])
        # local 仓库跳过，不报错
        assert result.exit_code == 0


# ==================== _resolve_repos 辅助函数测试 ====================

class TestResolveRepos:
    def test_resolve_specific_repo(self, config_mgr):
        """指定存在的仓库名时返回该仓库"""
        config_mgr.add_repo(RepoConfig(name="main", type="remote",
                                        url="https://github.com/org/r.git",
                                        path="ai-driving/main"))
        result = _resolve_repos(config_mgr, "main", "pull")
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "main"

    def test_resolve_nonexistent_repo(self, config_mgr):
        """指定不存在的仓库名时返回 None"""
        result = _resolve_repos(config_mgr, "nonexistent", "pull")
        assert result is None

    def test_resolve_all_repos(self, config_mgr):
        """不指定仓库名时返回所有仓库"""
        config_mgr.add_repo(RepoConfig(name="r1", type="remote",
                                        url="https://github.com/org/r1.git",
                                        path="ai-driving/r1"))
        config_mgr.add_repo(RepoConfig(name="r2", type="local",
                                        url=None, path="ai-driving/r2"))
        result = _resolve_repos(config_mgr, None, "pull")
        assert result is not None
        assert len(result) == 2
