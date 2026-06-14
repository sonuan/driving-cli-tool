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
from driving_cli.commands.repo import (
    _checkout_branch_after_install,
    _git_checkout,
    _resolve_repos,
    _set_submodule_config,
    _set_submodule_ignore,
    repo_group,
)
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
        """空配置时输出空数组"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_list_with_remote_repo(self, runner, tmp_project, config_mgr):
        """有远程仓库时正确展示"""
        repo_cfg = RepoConfig(
            name="main",
            type="remote",
            url="https://github.com/org/repo.git",
            path="ai-driving/main",
        )
        config_mgr.add_repo(repo_cfg)

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(r["name"] == "main" and r["type"] == "remote" for r in data)

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

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        types = {r["name"]: r["type"] for r in data}
        assert types["remote-repo"] == "remote"
        assert types["local-repo"] == "local"


# ==================== repo install 测试 ====================

class TestRepoInstall:
    def test_install_no_args_no_config(self, runner, tmp_project):
        """无参数且配置为空时提示无远程仓库"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["install"])
        assert result.exit_code == 0
        assert "没有远程仓库" in result.output

    def test_install_invalid_url(self, runner, tmp_project):
        """非法 URL 应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["install", "--url", "not-a-url"])
        assert result.exit_code != 0
        assert "URL 格式不合法" in result.output

    def test_install_invalid_repo_name(self, runner, tmp_project):
        """非法仓库名称应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/other.git", "--name", "main"
            ])
        assert result.exit_code != 0
        assert "已存在" in result.output

    def test_install_local_nonexistent_path(self, runner, tmp_project):
        """本地路径不存在时应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "/nonexistent/path/xyz", "--name", "mylocal"
            ])
        assert result.exit_code != 0
        assert "本地路径不存在" in result.output

    def test_install_local_no_path_creates_directory(self, runner, tmp_project):
        """--local 无路径时创建普通目录并写入配置"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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

    def test_install_local_with_tag_and_desc(self, runner, tmp_project):
        """--tag 和 --desc 参数写入配置"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "--name", "tagged-repo",
                "--tag", "base", "--tag", "features",
                "--desc", "测试仓库描述",
            ])
        assert result.exit_code == 0
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("tagged-repo")
        assert repo_cfg is not None
        assert "base" in (repo_cfg.tags or [])
        assert "features" in (repo_cfg.tags or [])
        assert repo_cfg.description == "测试仓库描述"

    def test_install_local_desc_alias_for_description(self, runner, tmp_project):
        """--desc 是 --description 的简写，两者效果相同"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "--name", "desc-repo",
                "--desc", "简写描述",
            ])
        assert result.exit_code == 0
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("desc-repo")
        assert repo_cfg.description == "简写描述"

    def test_install_local_with_module(self, runner, tmp_project):
        """--module name:description 写入 modules 配置"""
        from driving_cli.models.config import ModuleConfig
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "--name", "module-repo",
                "--module", "order:订单模块",
                "--module", "pay:支付模块",
            ])
        assert result.exit_code == 0
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("module-repo")
        assert repo_cfg is not None
        assert repo_cfg.modules is not None
        assert len(repo_cfg.modules) == 2
        mod_names = {m.name for m in repo_cfg.modules}
        assert mod_names == {"order", "pay"}
        mod_map = {m.name: m.description for m in repo_cfg.modules}
        assert mod_map["order"] == "订单模块"
        assert mod_map["pay"] == "支付模块"

    def test_install_local_module_without_description(self, runner, tmp_project):
        """--module name 不带冒号时描述默认为空字符串"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", "--name", "no-desc-module-repo",
                "--module", "chat",
            ])
        assert result.exit_code == 0
        mgr = ConfigManager(tmp_project)
        repo_cfg = mgr.get_repo("no-desc-module-repo")
        assert repo_cfg.modules is not None
        assert repo_cfg.modules[0].name == "chat"
        assert repo_cfg.modules[0].description == ""

    def test_install_local_with_path_creates_symlink(self, runner, tmp_project, tmp_path):
        """--local <path> 时 Unix 创建软链接，Windows 给出错误提示"""
        import sys
        # 创建一个真实的本地目录
        src_dir = tmp_path / "my-source"
        src_dir.mkdir()

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", str(src_dir), "--name", "linked-repo"
            ])

        if sys.platform == "win32":
            # Windows：应给出错误提示，不创建软链接
            assert result.exit_code != 0
            assert "Windows" in result.output or "不支持" in result.output
        else:
            assert result.exit_code == 0
            link_path = tmp_project / "ai-driving" / "linked-repo"
            assert link_path.is_symlink()
            # 验证配置
            mgr = ConfigManager(tmp_project)
            repo_cfg = mgr.get_repo("linked-repo")
            assert repo_cfg is not None
            assert repo_cfg.type == "local"
            assert repo_cfg.local_path == str(src_dir.resolve())

    def test_install_local_with_path_windows_error(self, runner, tmp_project, tmp_path):
        """Windows 下 --local <path> 给出友好错误提示"""
        src_dir = tmp_path / "my-source"
        src_dir.mkdir()

        with patch("sys.platform", "win32"), \
             patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--local", str(src_dir), "--name", "linked-repo"
            ])
        assert result.exit_code != 0
        assert "Windows" in result.output
        assert "不支持" in result.output

    def test_install_no_args_initializes_uninitialized(self, runner, tmp_project, config_mgr):
        """无参数 install 对未初始化的远程仓库执行 submodule update"""
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="https://github.com/org/repo.git",
            path="ai-driving/main",
        ))

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(repo_group, ["install"])

        assert result.exit_code == 0
        # 应调用 submodule update --init（路径分隔符跨平台兼容）
        import os
        call_args = mock_git_repo.git.submodule.call_args
        assert call_args is not None
        called_path = call_args[0][-1]  # 最后一个位置参数是路径
        assert os.path.normpath(called_path) == os.path.normpath("ai-driving/main")

    def test_install_remote_sets_ignore_all(self, runner, tmp_project, config_mgr):
        """--url 安装 submodule 后，.gitmodules 中应补充 ignore = all"""
        gitmodules = tmp_project / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/myrepo"]\n'
            '\tpath = ai-driving/myrepo\n'
            '\turl = https://github.com/org/myrepo.git\n',
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/myrepo.git", "--name", "myrepo"
            ])

        assert result.exit_code == 0
        content = gitmodules.read_text(encoding="utf-8")
        assert "ignore = all" in content
        assert "fetchRecurseSubmodules = false" in content

    def test_install_remote_yet_to_be_born(self, runner, tmp_project, config_mgr):
        """主仓库无 commit 时，checkout 失败但 .gitmodules 已写入，应视为成功"""
        import git as _git
        gitmodules = tmp_project / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/myrepo"]\n'
            '\tpath = ai-driving/myrepo\n'
            '\turl = https://github.com/org/myrepo.git\n',
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.side_effect = _git.exc.GitCommandError(
            "submodule", 128, stderr="fatal: You are on a branch yet to be born"
        )
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/myrepo.git", "--name", "myrepo"
            ])

        assert result.exit_code == 0
        assert "尚无 commit" in result.output

    def test_install_no_args_submodule_add_sets_ignore_all(self, runner, tmp_project, config_mgr):
        """无参数 install 走 submodule add 路径时，.gitmodules 中应补充 ignore = all 和 fetchRecurseSubmodules"""
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="https://github.com/org/repo.git",
            path="ai-driving/main",
        ))
        gitmodules = tmp_project / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/main"]\n'
            '\tpath = ai-driving/main\n'
            '\turl = https://github.com/org/repo.git\n',
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        # 让 submodule update --init 失败（抛 GitCommandError），触发 submodule add 路径
        import git as _git
        mock_git_repo.git.submodule.side_effect = [
            _git.exc.GitCommandError("submodule", 128),  # update --init 失败
            None,                                          # submodule add 成功
        ]
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.commands.repo._cleanup_stale_git_modules"):
            runner.invoke(repo_group, ["install"])

        content = gitmodules.read_text(encoding="utf-8")
        assert "ignore = all" in content
        assert "fetchRecurseSubmodules = false" in content


# ==================== _set_submodule_ignore 单元测试 ====================

class TestSetSubmoduleIgnore:
    def test_adds_ignore_all(self, tmp_path):
        """正常情况：为 submodule 块末尾插入 ignore = all 和 fetchRecurseSubmodules = false"""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\turl = https://github.com/org/foo.git\n',
            encoding="utf-8",
        )
        _set_submodule_ignore(tmp_path, "ai-driving/foo")
        content = gitmodules.read_text(encoding="utf-8")
        assert "ignore = all" in content
        assert "fetchRecurseSubmodules = false" in content

    def test_idempotent_when_ignore_exists(self, tmp_path):
        """已有 ignore 配置时不重复写入"""
        original = (
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\turl = https://github.com/org/foo.git\n'
            '\tignore = all\n'
            '\tfetchRecurseSubmodules = false\n'
        )
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(original, encoding="utf-8")
        _set_submodule_ignore(tmp_path, "ai-driving/foo")
        assert gitmodules.read_text(encoding="utf-8").count("ignore") == 1
        assert gitmodules.read_text(encoding="utf-8").count("fetchRecurseSubmodules") == 1

    def test_only_affects_target_submodule(self, tmp_path):
        """多个 submodule 时只修改目标块"""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\turl = https://github.com/org/foo.git\n'
            '[submodule "ai-driving/bar"]\n'
            '\tpath = ai-driving/bar\n'
            '\turl = https://github.com/org/bar.git\n',
            encoding="utf-8",
        )
        _set_submodule_ignore(tmp_path, "ai-driving/foo")
        content = gitmodules.read_text(encoding="utf-8")
        lines = content.splitlines()
        foo_idx = next(i for i, l in enumerate(lines) if "foo" in l and l.startswith("["))
        bar_idx = next(i for i, l in enumerate(lines) if "bar" in l and l.startswith("["))
        foo_block = lines[foo_idx:bar_idx]
        bar_block = lines[bar_idx:]
        assert any("ignore = all" in l for l in foo_block)
        assert not any("ignore" in l for l in bar_block)

    def test_no_gitmodules_file(self, tmp_path):
        """不存在 .gitmodules 时静默跳过，不报错"""
        _set_submodule_ignore(tmp_path, "ai-driving/foo")

    def test_submodule_not_found(self, tmp_path):
        """submodule 不在 .gitmodules 中时静默跳过"""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/other"]\n'
            '\tpath = ai-driving/other\n'
            '\turl = https://github.com/org/other.git\n',
            encoding="utf-8",
        )
        _set_submodule_ignore(tmp_path, "ai-driving/foo")
        content = gitmodules.read_text(encoding="utf-8")
        assert "ignore" not in content


# ==================== _set_submodule_config 单元测试 ====================

class TestSetSubmoduleConfig:
    def _make_gitmodules(self, tmp_path, content):
        f = tmp_path / ".gitmodules"
        f.write_text(content, encoding="utf-8")
        return f

    def test_adds_new_key(self, tmp_path):
        """正常写入新 key"""
        f = self._make_gitmodules(tmp_path,
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\turl = https://github.com/org/foo.git\n'
        )
        _set_submodule_config(tmp_path, "ai-driving/foo", "mykey", "myval")
        assert "mykey = myval" in f.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path):
        """key 已存在时不重复写入"""
        f = self._make_gitmodules(tmp_path,
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\tmykey = myval\n'
        )
        _set_submodule_config(tmp_path, "ai-driving/foo", "mykey", "myval")
        assert f.read_text(encoding="utf-8").count("mykey") == 1

    def test_preserves_other_sections(self, tmp_path):
        """不影响其他 submodule 块"""
        f = self._make_gitmodules(tmp_path,
            '[submodule "ai-driving/foo"]\n'
            '\tpath = ai-driving/foo\n'
            '\turl = https://github.com/org/foo.git\n'
            '[submodule "ai-driving/bar"]\n'
            '\tpath = ai-driving/bar\n'
            '\turl = https://github.com/org/bar.git\n'
        )
        _set_submodule_config(tmp_path, "ai-driving/foo", "mykey", "myval")
        content = f.read_text(encoding="utf-8")
        lines = content.splitlines()
        bar_idx = next(i for i, l in enumerate(lines) if "bar" in l and l.startswith("["))
        bar_block = lines[bar_idx:]
        assert not any("mykey" in l for l in bar_block)

    def test_no_gitmodules(self, tmp_path):
        """文件不存在时静默跳过"""
        _set_submodule_config(tmp_path, "ai-driving/foo", "k", "v")

    def test_submodule_not_found(self, tmp_path):
        """submodule 不存在时静默跳过"""
        f = self._make_gitmodules(tmp_path,
            '[submodule "ai-driving/other"]\n'
            '\tpath = ai-driving/other\n'
        )
        _set_submodule_config(tmp_path, "ai-driving/foo", "k", "v")
        assert "k = v" not in f.read_text(encoding="utf-8")


# ==================== _migrate_local_to_remote 单元测试 ====================

class TestMigrateLocalToRemote:
    def test_migrate_confirms_and_pushes(self, runner, tmp_project, config_mgr, tmp_path):
        """检测到 local 仓库时，用户确认后执行推送并切换为 submodule"""
        import sys
        import git as _git

        if sys.platform == "win32":
            pytest.skip("Windows 下符号链接需要管理员权限，跳过此测试")

        # 创建本地 git 仓库
        src_dir = tmp_path / "my-local"
        src_dir.mkdir()
        local_repo = _git.Repo.init(src_dir)
        (src_dir / "README.md").write_text("hello")
        local_repo.index.add(["README.md"])
        local_repo.index.commit("init")

        # 注册为 local 仓库
        config_mgr.add_repo(RepoConfig(
            name="my-local", type="local",
            url=None, path="ai-driving/my-local",
            local_path=str(src_dir),
        ))
        install_dir = tmp_project / "ai-driving" / "my-local"
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.symlink_to(src_dir)

        mock_git_repo = MagicMock()
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/my-local.git", "--name", "my-local"
            ], input="y\n")

        assert "检测到本地仓库" in result.output

    def test_migrate_aborts_on_no(self, runner, tmp_project, config_mgr, tmp_path):
        """用户拒绝时中止，不执行任何操作"""
        src_dir = tmp_path / "my-local"
        src_dir.mkdir()

        config_mgr.add_repo(RepoConfig(
            name="my-local", type="local",
            url=None, path="ai-driving/my-local",
            local_path=str(src_dir),
        ))

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/my-local.git", "--name", "my-local"
            ], input="n\n")

        assert result.exit_code != 0
        # 配置中仍保留 local 仓库
        assert config_mgr.get_repo("my-local") is not None

    def test_migrate_skips_push_if_no_git(self, runner, tmp_project, config_mgr, tmp_path):
        """本地目录不是 git 仓库时，自动 init + commit 后继续推送"""
        import sys
        import git as _git

        if sys.platform == "win32":
            pytest.skip("Windows 下符号链接需要管理员权限，跳过此测试")

        src_dir = tmp_path / "my-local"
        src_dir.mkdir()
        (src_dir / "README.md").write_text("hello")  # 有内容可提交

        config_mgr.add_repo(RepoConfig(
            name="my-local", type="local",
            url=None, path="ai-driving/my-local",
            local_path=str(src_dir),
        ))
        install_dir = tmp_project / "ai-driving" / "my-local"
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.symlink_to(src_dir)

        mock_git_repo = MagicMock()
        real_git_repo = _git.Repo  # 保存真实引用，避免 patch 后递归

        def fake_repo(path=None, *args, **kwargs):
            # 主仓库用 mock，local_dir 用真实 git.Repo
            if path is not None and str(path) == str(src_dir):
                return real_git_repo(path)
            return mock_git_repo

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", side_effect=fake_repo), \
             patch("driving_cli.commands.repo.git.Repo.init", side_effect=real_git_repo.init):
            result = runner.invoke(repo_group, [
                "install", "--url", "https://github.com/org/my-local.git", "--name", "my-local"
            ], input="y\n")

        # 自动初始化后 src_dir 应成为 git 仓库
        assert "自动初始化" in result.output


# ==================== repo uninstall 测试 ====================

class TestRepoUninstall:
    def test_uninstall_nonexistent(self, runner, tmp_project):
        """卸载不存在的仓库应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["uninstall", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_uninstall_local_symlink(self, runner, tmp_project, config_mgr, tmp_path):
        """卸载本地软链接仓库：移除软链接并更新配置"""
        import sys
        if sys.platform == "win32":
            pytest.skip("Windows 下符号链接需要管理员权限，跳过此测试")

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

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
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
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "pull" in result.output

    def test_push_skips_local_repo(self, runner, tmp_project, config_mgr):
        """push 对 local 仓库跳过并给出提示"""
        self._make_local_repo(config_mgr)
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["push", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "push" in result.output

    def test_commit_skips_local_repo(self, runner, tmp_project, config_mgr):
        """commit 对 local 仓库跳过并给出提示"""
        self._make_local_repo(config_mgr)
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["commit", "local-docs"])
        assert result.exit_code == 0
        assert "跳过" in result.output
        assert "commit" in result.output

    def test_pull_nonexistent_repo(self, runner, tmp_project):
        """pull 指定不存在的仓库应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_push_nonexistent_repo(self, runner, tmp_project):
        """push 指定不存在的仓库应报错"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["push", "nonexistent"])
        assert result.exit_code != 0
        assert "不存在" in result.output

    def test_pull_all_skips_local(self, runner, tmp_project, config_mgr):
        """不指定仓库时，pull 跳过所有 local 仓库"""
        self._make_local_repo(config_mgr, "local1")
        self._make_local_repo(config_mgr, "local2")

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull"])
        assert result.exit_code == 0
        assert result.output.count("跳过") == 2

    def test_commit_message_as_first_arg(self, runner, tmp_project, config_mgr):
        """commit 第一个参数不是仓库名时视为提交信息"""
        self._make_local_repo(config_mgr, "local-docs")

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["commit", "my commit message"])
        # local 仓库跳过，不报错
        assert result.exit_code == 0

    def test_pull_empty_dir_auto_initializes(self, runner, tmp_project, config_mgr):
        """pull 时目录为空（submodule 未初始化），应自动调用 ensure_submodule_initialized"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url="https://github.com/org/aidoc.git",
            path="ai-driving/aidoc",
        ))
        # 创建空目录，模拟 submodule 注册了但未初始化
        empty_dir = tmp_project / "ai-driving" / "aidoc"
        empty_dir.mkdir(parents=True)

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.ensure_submodule_initialized", return_value=True) as mock_init:
            result = runner.invoke(repo_group, ["pull", "aidoc"])

        assert result.exit_code == 0
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args
        assert call_kwargs.kwargs.get("url") == "https://github.com/org/aidoc.git"
        assert "初始化" in result.output or "成功" in result.output

    def test_pull_missing_dir_auto_initializes(self, runner, tmp_project, config_mgr):
        """pull 时目录不存在（submodule 完全未创建），应自动调用 ensure_submodule_initialized"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url="https://github.com/org/aidoc.git",
            path="ai-driving/aidoc",
        ))
        # 不创建目录，模拟目录完全缺失

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.ensure_submodule_initialized", return_value=True) as mock_init:
            result = runner.invoke(repo_group, ["pull", "aidoc"])

        assert result.exit_code == 0
        mock_init.assert_called_once()

    def test_pull_empty_dir_init_failure(self, runner, tmp_project, config_mgr):
        """pull 时目录为空但初始化失败，应报错"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url="https://github.com/org/aidoc.git",
            path="ai-driving/aidoc",
        ))
        empty_dir = tmp_project / "ai-driving" / "aidoc"
        empty_dir.mkdir(parents=True)

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.ensure_submodule_initialized", return_value=False):
            result = runner.invoke(repo_group, ["pull", "aidoc"])

        assert result.exit_code == 0  # exit_code=0，通过 ERROR 日志提示
        assert "失败" in result.output or "手动" in result.output

    def test_pull_empty_dir_no_url(self, runner, tmp_project, config_mgr):
        """pull 时目录为空且配置无 URL，应给出提示而非 crash"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url=None,  # 无 URL
            path="ai-driving/aidoc",
        ))
        empty_dir = tmp_project / "ai-driving" / "aidoc"
        empty_dir.mkdir(parents=True)

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["pull", "aidoc"])

        assert result.exit_code == 0
        assert "URL" in result.output or "install" in result.output

    def test_checkout_empty_dir_auto_initializes(self, runner, tmp_project, config_mgr):
        """checkout 时目录为空，应自动初始化后再切换分支"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url="https://github.com/org/aidoc.git",
            path="ai-driving/aidoc",
        ))
        empty_dir = tmp_project / "ai-driving" / "aidoc"
        empty_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.is_dirty.return_value = False
        mock_repo.remotes = []

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.ensure_submodule_initialized", return_value=True) as mock_init, \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            result = runner.invoke(repo_group, ["checkout", "aidoc", "feature/new-branch"])

        assert result.exit_code == 0
        mock_init.assert_called_once()
        # 确认 branch 参数为空（不在初始化时切换，由后续 checkout 逻辑处理）
        assert mock_init.call_args.kwargs.get("branch") == ""

    def test_checkout_empty_dir_init_failure(self, runner, tmp_project, config_mgr):
        """checkout 时目录为空但初始化失败，应报错退出"""
        config_mgr.add_repo(RepoConfig(
            name="aidoc", type="remote",
            url="https://github.com/org/aidoc.git",
            path="ai-driving/aidoc",
        ))
        empty_dir = tmp_project / "ai-driving" / "aidoc"
        empty_dir.mkdir(parents=True)

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.ensure_submodule_initialized", return_value=False):
            result = runner.invoke(repo_group, ["checkout", "aidoc", "main"])

        assert result.exit_code == 0
        assert "失败" in result.output or "手动" in result.output


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


# ==================== repo load / collect_repos 测试 ====================

from driving_cli.commands.repo import collect_repos


class TestCollectRepos:
    def test_no_keywords_returns_all(self, tmp_project, config_mgr):
        """不传关键词时返回所有仓库"""
        config_mgr.add_repo(RepoConfig(name="r1", type="remote",
                                        url="https://github.com/org/r1.git",
                                        path="ai-driving/r1"))
        config_mgr.add_repo(RepoConfig(name="r2", type="local",
                                        url=None, path="ai-driving/r2"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(())
        assert len(result) == 2
        assert {r["name"] for r in result} == {"r1", "r2"}

    def test_keyword_filters_by_name(self, tmp_project, config_mgr):
        """传入关键词时只返回匹配的仓库"""
        config_mgr.add_repo(RepoConfig(name="r1", type="remote",
                                        url="https://github.com/org/r1.git",
                                        path="ai-driving/r1"))
        config_mgr.add_repo(RepoConfig(name="r2", type="local",
                                        url=None, path="ai-driving/r2"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(("r1",))
        assert len(result) == 1
        assert result[0]["name"] == "r1"

    def test_multiple_keywords(self, tmp_project, config_mgr):
        """多个关键词取并集"""
        for name in ("r1", "r2", "r3"):
            config_mgr.add_repo(RepoConfig(name=name, type="local",
                                            url=None, path=f"ai-driving/{name}"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(("r1", "r3"))
        assert {r["name"] for r in result} == {"r1", "r3"}

    def test_unknown_keyword_returns_empty(self, tmp_project, config_mgr):
        """关键词不匹配任何仓库时返回空列表"""
        config_mgr.add_repo(RepoConfig(name="r1", type="local",
                                        url=None, path="ai-driving/r1"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(("nonexistent",))
        assert result == []

    def test_result_fields(self, tmp_project, config_mgr):
        """返回结果包含 name、type、description、path 字段"""
        config_mgr.add_repo(RepoConfig(name="r1", type="remote",
                                        url="https://github.com/org/r1.git",
                                        path="ai-driving/r1",
                                        description="test desc"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(())
        assert result[0] == {
            "name": "r1",
            "type": "remote",
            "description": "test desc",
            "path": "ai-driving/r1",
        }

    def test_empty_config_returns_empty(self, tmp_project):
        """配置为空时返回空列表"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = collect_repos(())
        assert result == []


class TestRepoLoad:
    def test_load_all(self, runner, tmp_project, config_mgr):
        """不传参数时输出所有仓库"""
        config_mgr.add_repo(RepoConfig(name="r1", type="local",
                                        url=None, path="ai-driving/r1"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "r1"

    def test_load_with_keyword(self, runner, tmp_project, config_mgr):
        """传入关键词时只输出匹配仓库"""
        config_mgr.add_repo(RepoConfig(name="r1", type="local",
                                        url=None, path="ai-driving/r1"))
        config_mgr.add_repo(RepoConfig(name="r2", type="local",
                                        url=None, path="ai-driving/r2"))
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["load", "r1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "r1"

    def test_load_empty(self, runner, tmp_project):
        """无仓库时输出空数组"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project):
            result = runner.invoke(repo_group, ["load"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []


# ==================== _git_push（使用 push_with_upstream）测试 ====================

from driving_cli.commands.repo import _git_push


class TestGitPush:
    """_git_push 函数测试

    覆盖场景：
    - 仓库目录不存在时报错
    - 未配置远程仓库时报错
    - push_with_upstream 成功时输出成功
    - push_with_upstream 失败时输出错误
    """

    def _make_repo_cfg(self, name="main", path="ai-driving/main"):
        return RepoConfig(name=name, type="remote",
                          url="https://github.com/org/repo.git", path=path)

    def test_repo_dir_not_exist(self, tmp_project, capsys):
        """仓库目录不存在时报错"""
        cfg = self._make_repo_cfg(path="ai-driving/nonexistent")
        _git_push(cfg, tmp_project)
        captured = capsys.readouterr()
        assert "不存在" in captured.out or "不存在" in captured.err

    def test_no_remotes(self, tmp_project, capsys):
        """未配置远程仓库时报错"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)
        cfg = self._make_repo_cfg()

        mock_repo = MagicMock()
        mock_repo.remotes = []

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _git_push(cfg, tmp_project)

        captured = capsys.readouterr()
        assert "未配置远程仓库" in captured.out or "未配置远程仓库" in captured.err

    def test_push_success(self, tmp_project, capsys):
        """push_with_upstream 成功时输出成功提示"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)
        cfg = self._make_repo_cfg()

        mock_repo = MagicMock()

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo), \
             patch("driving_cli.commands.repo.push_with_upstream", return_value=(True, "")):
            _git_push(cfg, tmp_project)

        captured = capsys.readouterr()
        assert "推送成功" in captured.out or "推送成功" in captured.err

    def test_push_failure(self, tmp_project, capsys):
        """push_with_upstream 失败时输出错误提示"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)
        cfg = self._make_repo_cfg()

        mock_repo = MagicMock()

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo), \
             patch("driving_cli.commands.repo.push_with_upstream",
                   return_value=(False, "存在冲突，请先执行 pull")):
            _git_push(cfg, tmp_project)

        captured = capsys.readouterr()
        assert "推送失败" in captured.out or "推送失败" in captured.err
        assert "冲突" in captured.out or "冲突" in captured.err


# ==================== _install_all_uninitialized 错误信息测试 ====================

from driving_cli.commands.repo import _git_checkout


class TestInstallAllUninitializedErrorMessage:
    """验证 update --init 失败时错误原因被打印（而不是静默吞掉）"""

    def test_update_init_failure_reason_logged(self, runner, tmp_project, config_mgr, capsys):
        """submodule update --init 失败时，应打印失败原因，而不是完全静默"""
        import git as _git
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="git@github.com:org/repo.git",
            path="ai-driving/main",
        ))

        mock_git_repo = MagicMock()
        ssh_error = _git.exc.GitCommandError("submodule update", 128)
        ssh_error.stderr = "Permission denied (publickey)."
        # update --init 抛 SSH 错误
        mock_git_repo.git.submodule.side_effect = [
            ssh_error,          # 第一次 update --init 失败
            ssh_error,          # 第二次 submodule add 也失败（触发最终 log_error）
        ]

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(cli, ["repo", "install"])

        # 关键：update --init 的失败原因应出现在输出中，不能完全静默
        assert "Permission denied" in result.output or "失败" in result.output

    def test_update_init_failure_then_add_success(self, runner, tmp_project, config_mgr):
        """update --init 失败后降级 submodule add 成功时，最终应显示成功"""
        import git as _git
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="git@github.com:org/repo.git",
            path="ai-driving/main",
        ))

        gitmodules = tmp_project / ".gitmodules"
        gitmodules.write_text(
            '[submodule "ai-driving/main"]\n\tpath = ai-driving/main\n\turl = git@github.com:org/repo.git\n',
            encoding="utf-8",
        )

        mock_git_repo = MagicMock()
        update_err = _git.exc.GitCommandError("submodule update", 128)
        update_err.stderr = "not registered"
        mock_git_repo.git.submodule.side_effect = [
            update_err,   # update --init 失败
            None,         # submodule add 成功
        ]

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo):
            result = runner.invoke(cli, ["repo", "install"])

        assert "成功" in result.output or result.exit_code == 0


# ==================== _git_checkout fetch 失败提示测试 ====================

class TestGitCheckoutFetchWarning:
    """验证 checkout 时 fetch 失败会打印 warning 而不是静默 pass"""

    def _make_repo_cfg(self, name="main"):
        return RepoConfig(name=name, type="remote",
                          url="git@github.com:org/repo.git", path=f"ai-driving/{name}")

    def test_fetch_failure_shows_warning(self, tmp_project, capsys):
        """fetch 失败（如 SSH 错误）时应显示 warning，不能静默"""
        import git as _git
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)
        cfg = self._make_repo_cfg()

        mock_repo = MagicMock()
        mock_repo.is_dirty.return_value = False
        # 有 remotes，fetch 抛 SSH 错误
        fetch_err = _git.exc.GitCommandError("fetch", 128)
        fetch_err.stderr = "Permission denied (publickey)."
        mock_repo.remotes.origin.fetch.side_effect = fetch_err
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _git_checkout(cfg, tmp_project, "main")

        captured = capsys.readouterr()
        # fetch 失败应有 warning 提示，不能完全静默
        assert "fetch 失败" in captured.out or "fetch 失败" in captured.err \
               or "Permission" in captured.out or "Permission" in captured.err

    def test_fetch_failure_does_not_block_checkout(self, tmp_project, capsys):
        """fetch 失败后仍继续执行 checkout（不阻断流程）"""
        import git as _git
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)
        cfg = self._make_repo_cfg()

        mock_repo = MagicMock()
        mock_repo.is_dirty.return_value = False
        fetch_err = _git.exc.GitCommandError("fetch", 128)
        fetch_err.stderr = "Permission denied (publickey)."
        mock_repo.remotes.origin.fetch.side_effect = fetch_err
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        mock_repo.git.checkout.return_value = None  # checkout 成功

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _git_checkout(cfg, tmp_project, "main")

        # checkout 应该被调用（fetch 失败不应阻断）
        mock_repo.git.checkout.assert_called_once_with("main")
        captured = capsys.readouterr()
        assert "切换到分支" in captured.out or "切换到分支" in captured.err

# ==================== --branch 选项测试 ====================

class TestRepoInstallBranch:
    """验证 repo install --branch 的行为"""

    def test_branch_saved_to_config(self, runner, tmp_project):
        """--branch 参数应保存到 driving.config.json 的 repo.branch 字段"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo") as mock_repo_cls, \
             patch("driving_cli.commands.repo._cleanup_stale_git_modules"), \
             patch("driving_cli.commands.repo._set_submodule_ignore"), \
             patch("driving_cli.commands.repo._checkout_branch_after_install") as mock_checkout:
            mock_git_repo = MagicMock()
            mock_git_repo.git.submodule.return_value = None
            mock_repo_cls.return_value = mock_git_repo

            result = runner.invoke(cli, [
                "repo", "install",
                "--url", "https://github.com/org/repo.git",
                "--name", "main",
                "--branch", "develop",
            ])

        assert result.exit_code == 0, result.output
        # branch 应写入配置
        from driving_cli.utils.config_manager import ConfigManager
        cm = ConfigManager(tmp_project)
        repo = cm.get_repo("main")
        assert repo is not None
        assert repo.branch == "develop"
        # checkout 辅助函数应被调用
        mock_checkout.assert_called_once()
        call_args = mock_checkout.call_args
        assert call_args[0][1] == "main"   # repo_name
        assert call_args[0][2] == "develop"  # branch

    def test_no_branch_option_branch_is_none(self, runner, tmp_project):
        """不传 --branch 时，repo.branch 应为 None（不写入 config.json）"""
        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo") as mock_repo_cls, \
             patch("driving_cli.commands.repo._cleanup_stale_git_modules"), \
             patch("driving_cli.commands.repo._set_submodule_ignore"), \
             patch("driving_cli.commands.repo._checkout_branch_after_install") as mock_checkout:
            mock_git_repo = MagicMock()
            mock_git_repo.git.submodule.return_value = None
            mock_repo_cls.return_value = mock_git_repo

            result = runner.invoke(cli, [
                "repo", "install",
                "--url", "https://github.com/org/repo.git",
                "--name", "main",
            ])

        assert result.exit_code == 0, result.output
        from driving_cli.utils.config_manager import ConfigManager
        cm = ConfigManager(tmp_project)
        repo = cm.get_repo("main")
        assert repo is not None
        assert repo.branch is None
        # 未配置 branch 时不应调用 checkout
        mock_checkout.assert_not_called()


class TestCheckoutBranchAfterInstall:
    """验证 _checkout_branch_after_install 辅助函数行为"""

    def test_checkout_success(self, tmp_project, capsys):
        """checkout 成功时输出成功日志"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        mock_repo.git.checkout.return_value = None

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "develop")

        mock_repo.git.checkout.assert_called_once_with("develop")
        captured = capsys.readouterr()
        assert "develop" in captured.out

    def test_checkout_nonexistent_branch_warns(self, tmp_project, capsys):
        """checkout 不存在的分支时输出 warning，不抛异常"""
        import git as _git
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        err = _git.exc.GitCommandError("checkout", 1)
        err.stderr = "pathspec 'no-such-branch' did not match any"
        mock_repo.git.checkout.side_effect = err

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "no-such-branch")  # 不应抛异常

        captured = capsys.readouterr()
        assert "不存在" in captured.out or "warning" in captured.out.lower() or "警告" in captured.out

    def test_checkout_fetch_failure_does_not_block(self, tmp_project, capsys):
        """fetch 失败时仍继续 checkout，不中断流程"""
        import git as _git
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        fetch_err = _git.exc.GitCommandError("fetch", 128)
        fetch_err.stderr = "Permission denied (publickey)."
        mock_repo.remotes.origin.fetch.side_effect = fetch_err
        mock_repo.git.checkout.return_value = None

        with patch("driving_cli.commands.repo.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "develop")

        # fetch 失败后 checkout 仍应被调用
        mock_repo.git.checkout.assert_called_once_with("develop")

    def test_repo_dir_not_exist_warns(self, tmp_project, capsys):
        """仓库目录不存在时输出 warning，不抛异常"""
        repo_dir = tmp_project / "ai-driving" / "nonexistent"
        # 不创建目录，直接调用

        _checkout_branch_after_install(repo_dir, "nonexistent", "main")

        captured = capsys.readouterr()
        assert "不存在" in captured.out or "跳过" in captured.out


class TestRepoConfigBranchSerialization:
    """验证 RepoConfig.branch 序列化/反序列化"""

    def test_branch_serialized_when_set(self):
        """branch 有值时应序列化到 dict"""
        from driving_cli.models.config import RepoConfig
        cfg = RepoConfig(name="r", type="remote", path="ai-driving/r", branch="develop")
        d = cfg.to_dict()
        assert d.get("branch") == "develop"

    def test_branch_not_serialized_when_none(self):
        """branch 为 None 时不写入 dict（保持 config.json 简洁）"""
        from driving_cli.models.config import RepoConfig
        cfg = RepoConfig(name="r", type="remote", path="ai-driving/r", branch=None)
        d = cfg.to_dict()
        assert "branch" not in d

    def test_branch_deserialized_from_dict(self):
        """from_dict 应正确读取 branch 字段"""
        from driving_cli.models.config import RepoConfig
        d = {"name": "r", "type": "remote", "path": "ai-driving/r", "branch": "main"}
        cfg = RepoConfig.from_dict(d)
        assert cfg.branch == "main"

    def test_branch_defaults_to_none_when_missing(self):
        """旧 config.json 无 branch 字段时应默认 None（向后兼容）"""
        from driving_cli.models.config import RepoConfig
        d = {"name": "r", "type": "remote", "path": "ai-driving/r"}
        cfg = RepoConfig.from_dict(d)
        assert cfg.branch is None


class TestInstallAllUninitializedWithBranch:
    """验证无参数 repo install 初始化后自动 checkout 配置的分支"""

    def test_checkout_called_after_update_init(self, runner, tmp_project, config_mgr):
        """update --init 成功后，若配置了 branch 应自动 checkout"""
        import git as _git
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="git@github.com:org/repo.git",
            path="ai-driving/main",
            branch="develop",
        ))

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None  # update --init 成功

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install") as mock_checkout:
            result = runner.invoke(cli, ["repo", "install"])

        assert result.exit_code == 0, result.output
        mock_checkout.assert_called_once()
        # 第二个参数是 label（"仓库 'main'"），第三个是 branch
        assert "main" in mock_checkout.call_args[0][1]
        assert mock_checkout.call_args[0][2] == "develop"

    def test_no_checkout_when_branch_not_configured(self, runner, tmp_project, config_mgr):
        """未配置 branch 时，update --init 成功后不调用 checkout"""
        config_mgr.add_repo(RepoConfig(
            name="main", type="remote",
            url="git@github.com:org/repo.git",
            path="ai-driving/main",
            branch=None,
        ))

        mock_git_repo = MagicMock()
        mock_git_repo.git.submodule.return_value = None

        with patch("driving_cli.commands.repo.find_project_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.find_git_root", return_value=tmp_project), \
             patch("driving_cli.commands.repo.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install") as mock_checkout:
            runner.invoke(cli, ["repo", "install"])

        mock_checkout.assert_not_called()

# ==================== _checkout_branch_after_install 已在目标分支跳过测试 ====================

class TestCheckoutBranchSkipWhenAlreadyOnBranch:
    """验证已在目标分支时 _checkout_branch_after_install 跳过 checkout"""

    def test_skips_when_already_on_target_branch(self, tmp_project, capsys):
        """当前分支已是目标分支时，不执行 checkout"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "develop"
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "develop")

        # 已在目标分支，不应调用 checkout
        mock_repo.git.checkout.assert_not_called()
        # 也不应调用 fetch
        mock_repo.remotes.origin.fetch.assert_not_called()
        captured = capsys.readouterr()
        assert "已在分支" in captured.out

    def test_checkouts_when_on_different_branch(self, tmp_project, capsys):
        """当前分支不是目标分支时，正常执行 checkout"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "master"  # 当前在 master
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        mock_repo.git.checkout.return_value = None

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "develop")  # 要切到 develop

        mock_repo.git.checkout.assert_called_once_with("develop")

    def test_attempts_checkout_when_detached_head(self, tmp_project, capsys):
        """detached HEAD 时跳过分支比较，直接尝试 checkout"""
        repo_dir = tmp_project / "ai-driving" / "main"
        repo_dir.mkdir(parents=True)

        mock_repo = MagicMock()
        mock_repo.head.is_detached = True
        mock_repo.remotes.__bool__ = lambda self: True
        mock_repo.remotes.__len__ = lambda self: 1
        mock_repo.git.checkout.return_value = None

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_repo):
            _checkout_branch_after_install(repo_dir, "main", "develop")

        mock_repo.git.checkout.assert_called_once_with("develop")
