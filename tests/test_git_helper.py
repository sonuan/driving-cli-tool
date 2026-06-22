"""Git 操作辅助函数测试"""

import pytest
from pathlib import Path
import git
from driving_cli.utils.git_helper import find_git_root


class TestFindGitRoot:
    """查找 Git 仓库根目录测试"""

    def test_find_git_root_in_repo(self, tmp_path, monkeypatch):
        """测试在 Git 仓库中查找根目录"""
        # 初始化真实的 Git 仓库
        repo = git.Repo.init(tmp_path)
        
        # 创建子目录
        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)
        
        # 切换到子目录
        monkeypatch.chdir(subdir)
        
        # 应该能找到 Git 根目录
        root = find_git_root()
        assert root == tmp_path

    def test_find_git_root_not_in_repo(self, tmp_path, monkeypatch):
        """测试不在 Git 仓库中"""
        monkeypatch.chdir(tmp_path)
        
        # 应该抛出异常
        with pytest.raises(git.exc.InvalidGitRepositoryError):
            find_git_root()

    def test_find_git_root_from_current_dir(self, tmp_path, monkeypatch):
        """测试从当前目录查找"""
        # 初始化真实的 Git 仓库
        repo = git.Repo.init(tmp_path)
        
        monkeypatch.chdir(tmp_path)
        
        # 应该返回当前目录
        root = find_git_root()
        assert root == tmp_path

    def test_find_git_root_nested_structure(self, tmp_path, monkeypatch):
        """测试嵌套目录结构"""
        # 初始化真实的 Git 仓库
        repo = git.Repo.init(tmp_path)
        
        # 创建深层嵌套目录
        deep_dir = tmp_path / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True)
        
        # 切换到深层目录
        monkeypatch.chdir(deep_dir)
        
        # 应该能找到根目录
        root = find_git_root()
        assert root == tmp_path


# ==================== push_with_upstream 测试 ====================

from unittest.mock import MagicMock, patch
from driving_cli.utils.git_helper import push_with_upstream


class TestPushWithUpstream:
    """push_with_upstream 工具函数测试

    覆盖场景：
    - detached HEAD 时返回失败
    - 已有 upstream 时直接 push（不带 set_upstream）
    - 无 upstream 时自动加 set_upstream=True 推送
    - push_infos 中有 ERROR flag 时返回失败
    - GitCommandError "rejected" 时返回冲突错误
    - GitCommandError 其他错误时返回原始错误信息
    """

    def _make_repo(self, branch="main", is_detached=False, has_upstream=True):
        """构造标准 mock git.Repo"""
        repo = MagicMock()
        repo.head.is_detached = is_detached
        if not is_detached:
            repo.active_branch.name = branch
            if has_upstream:
                repo.active_branch.tracking_branch.return_value = MagicMock()
            else:
                repo.active_branch.tracking_branch.return_value = None
        return repo

    def _make_push_info(self, has_error=False, summary=""):
        info = MagicMock()
        info.ERROR = 1024
        info.flags = info.ERROR if has_error else 0
        info.summary = summary
        return info

    def test_detached_head_returns_failure(self):
        """detached HEAD 时直接返回失败，不执行 push"""
        repo = self._make_repo(is_detached=True)
        ok, err = push_with_upstream(repo)
        assert ok is False
        assert "detached" in err
        repo.remotes.origin.push.assert_not_called()

    def test_has_upstream_pushes_directly(self):
        """已有 upstream 时直接调用 push()，不传 refspec/set_upstream"""
        repo = self._make_repo(has_upstream=True)
        push_info = self._make_push_info(has_error=False)
        repo.remotes.origin.push.return_value = [push_info]

        ok, err = push_with_upstream(repo)

        assert ok is True
        assert err == ""
        # 直接 push()，不带额外参数
        repo.remotes.origin.push.assert_called_once_with()

    def test_no_upstream_uses_set_upstream(self):
        """无 upstream 时使用 refspec + set_upstream=True 推送"""
        repo = self._make_repo(branch="feature/my-branch", has_upstream=False)
        push_info = self._make_push_info(has_error=False)
        repo.remotes.origin.push.return_value = [push_info]

        ok, err = push_with_upstream(repo)

        assert ok is True
        assert err == ""
        repo.remotes.origin.push.assert_called_once_with(
            refspec="feature/my-branch:feature/my-branch",
            set_upstream=True,
        )

    def test_push_info_error_flag_returns_failure(self):
        """push_infos 中有 ERROR flag 时返回失败"""
        repo = self._make_repo(has_upstream=True)
        push_info = self._make_push_info(has_error=True, summary="remote rejected")
        repo.remotes.origin.push.return_value = [push_info]

        ok, err = push_with_upstream(repo)

        assert ok is False
        assert "remote rejected" in err

    def test_git_command_error_rejected(self):
        """GitCommandError 含 'rejected' 时返回冲突提示"""
        import git as _git
        repo = self._make_repo(has_upstream=True)
        repo.remotes.origin.push.side_effect = _git.exc.GitCommandError(
            "push", 1, stderr="error: failed to push some refs (rejected)"
        )

        ok, err = push_with_upstream(repo)

        assert ok is False
        assert "冲突" in err

    def test_git_command_error_other(self):
        """GitCommandError 其他错误时返回原始错误信息"""
        import git as _git
        repo = self._make_repo(has_upstream=True)
        repo.remotes.origin.push.side_effect = _git.exc.GitCommandError(
            "push", 128, stderr="fatal: repository not found"
        )

        ok, err = push_with_upstream(repo)

        assert ok is False
        assert len(err) > 0

    def test_tracking_branch_exception_treated_as_no_upstream(self):
        """tracking_branch() 抛异常时视为无 upstream，使用 set_upstream 推送"""
        repo = self._make_repo(branch="main", has_upstream=True)
        repo.active_branch.tracking_branch.side_effect = Exception("config error")
        push_info = self._make_push_info(has_error=False)
        repo.remotes.origin.push.return_value = [push_info]

        ok, err = push_with_upstream(repo)

        assert ok is True
        # 应使用 set_upstream 路径
        repo.remotes.origin.push.assert_called_once_with(
            refspec="main:main",
            set_upstream=True,
        )


# ==================== ensure_submodule_initialized 路径测试 ====================

from driving_cli.utils.git_helper import ensure_submodule_initialized, checkout_branch_after_install


class TestEnsureSubmoduleInitializedCheckoutPath:
    """验证 ensure_submodule_initialized 在 project_root != git_root 时，
    checkout_branch_after_install 收到的路径是 git_root/rel_path 而非 project_root/rel_path。

    背景：rel_path 是相对于 git_root 的路径（如 "sub/ai-driving/my-power"），
    当 project_root 是 git_root 下的子目录时，拼 project_root/rel_path 会多一层前缀，
    导致"目录不存在，跳过分支切换"的误报。
    """

    def _make_mock_git_repo(self):
        mock = MagicMock()
        mock.git.submodule.return_value = None  # update --init 成功
        return mock

    def test_checkout_uses_git_root_when_project_root_differs(self, tmp_path):
        """project_root 是 git_root 子目录时，checkout 路径应基于 git_root"""
        git_root = tmp_path / "repo"
        git_root.mkdir()
        # project_root 是 git_root 下的子目录 "sub"
        project_root = git_root / "sub"
        project_root.mkdir()

        # submodule 在 git_root 下的路径
        rel_path = "sub/ai-driving/my-power"
        actual_submodule_dir = git_root / rel_path
        actual_submodule_dir.mkdir(parents=True)

        mock_git_repo = self._make_mock_git_repo()
        checkout_calls = []

        def fake_checkout(repo_dir, repo_name, branch):
            checkout_calls.append(repo_dir)

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install",
                   side_effect=fake_checkout) as mock_checkout:
            result = ensure_submodule_initialized(
                project_root=project_root,
                git_root=git_root,
                rel_path=rel_path,
                url="https://github.com/org/repo.git",
                branch="main",
                label="power 'my-power'",
            )

        assert result is True
        assert mock_checkout.called
        called_path = checkout_calls[0]
        # 路径应该是 git_root / rel_path，而不是 project_root / rel_path
        assert called_path == git_root / rel_path
        assert called_path != project_root / rel_path  # 两者确实不同

    def test_checkout_path_correct_when_project_root_equals_git_root(self, tmp_path):
        """project_root == git_root 时，路径行为与之前一致（回归保护）"""
        git_root = tmp_path
        project_root = tmp_path  # 相同
        rel_path = "ai-driving/my-repo"
        (git_root / rel_path).mkdir(parents=True)

        mock_git_repo = self._make_mock_git_repo()
        checkout_calls = []

        def fake_checkout(repo_dir, repo_name, branch):
            checkout_calls.append(repo_dir)

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install",
                   side_effect=fake_checkout):
            result = ensure_submodule_initialized(
                project_root=project_root,
                git_root=git_root,
                rel_path=rel_path,
                url="https://github.com/org/repo.git",
                branch="develop",
                label="repo 'my-repo'",
            )

        assert result is True
        assert checkout_calls[0] == git_root / rel_path

    def test_no_branch_skips_checkout(self, tmp_path):
        """branch 为空时不调用 checkout_branch_after_install"""
        git_root = tmp_path
        rel_path = "ai-driving/my-repo"
        (git_root / rel_path).mkdir(parents=True)

        mock_git_repo = self._make_mock_git_repo()

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install") as mock_checkout:
            ensure_submodule_initialized(
                project_root=tmp_path,
                git_root=git_root,
                rel_path=rel_path,
                url="https://github.com/org/repo.git",
                branch="",  # 空分支
                label="repo 'my-repo'",
            )

        mock_checkout.assert_not_called()

    def test_submodule_add_fallback_also_uses_git_root(self, tmp_path):
        """降级走 submodule add 路径时，checkout 路径同样应基于 git_root"""
        import git as _git

        git_root = tmp_path / "repo"
        git_root.mkdir()
        project_root = git_root / "sub"
        project_root.mkdir()

        rel_path = "sub/ai-driving/my-power"
        (git_root / rel_path).mkdir(parents=True)

        mock_git_repo = MagicMock()
        # update --init 失败，触发 submodule add 路径
        update_err = _git.exc.GitCommandError("submodule update", 128)
        update_err.stderr = "not registered"
        mock_git_repo.git.submodule.side_effect = [
            update_err,   # update --init 失败
            None,         # submodule add 成功
        ]

        checkout_calls = []

        def fake_checkout(repo_dir, repo_name, branch):
            checkout_calls.append(repo_dir)

        with patch("driving_cli.utils.git_helper.git.Repo", return_value=mock_git_repo), \
             patch("driving_cli.utils.git_helper.checkout_branch_after_install",
                   side_effect=fake_checkout):
            result = ensure_submodule_initialized(
                project_root=project_root,
                git_root=git_root,
                rel_path=rel_path,
                url="https://github.com/org/power.git",
                branch="main",
                label="power 'my-power'",
            )

        assert result is True
        assert checkout_calls[0] == git_root / rel_path
        assert checkout_calls[0] != project_root / rel_path
