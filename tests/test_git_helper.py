"""Git 操作辅助函数测试"""

import pytest
from pathlib import Path
import git
from driving.utils.git_helper import find_git_root


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
