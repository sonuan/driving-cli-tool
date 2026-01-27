"""配置模块测试"""

import os
from pathlib import Path

import pytest

from driving.utils.config import (
    SENSITIVE_KEYWORDS,
    check_environment,
    get_all_gitlist_files,
    get_driving_dir,
    get_framework_base_dir,
    get_gitlist_file,
    is_local_mode,
)


class TestConfigMode:
    """配置模式检测测试"""

    def test_is_local_mode_with_gitlist(self, tmp_path, monkeypatch):
        """测试本地模式检测 - 存在 gitlist.json"""
        # 创建 gitlist.json
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        # 切换到测试目录
        monkeypatch.chdir(tmp_path)

        # 验证
        assert is_local_mode() is True

    def test_is_local_mode_without_gitlist(self, tmp_path, monkeypatch):
        """测试本地模式检测 - 不存在 gitlist.json"""
        monkeypatch.chdir(tmp_path)
        assert is_local_mode() is False

    def test_is_local_mode_with_driving_dir(self, tmp_path, monkeypatch):
        """测试标准模式检测 - 存在 .driving 目录"""
        # 创建 .driving 目录
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        assert is_local_mode() is False


class TestPathResolution:
    """路径解析测试"""

    def test_get_driving_dir_local_mode(self, tmp_path, monkeypatch):
        """测试获取 driving 目录 - 本地模式"""
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        monkeypatch.chdir(tmp_path)

        assert get_driving_dir() == tmp_path

    def test_get_driving_dir_standard_mode(self, tmp_path, monkeypatch):
        """测试获取 driving 目录 - 标准模式"""
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        assert get_driving_dir() == driving_dir

    def test_get_gitlist_file_local_mode(self, tmp_path, monkeypatch):
        """测试获取 gitlist.json 路径 - 本地模式"""
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        monkeypatch.chdir(tmp_path)

        assert get_gitlist_file() == tmp_path / "gitlist.json"

    def test_get_framework_base_dir_local_mode(self, tmp_path, monkeypatch):
        """测试获取框架目录 - 本地模式"""
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        monkeypatch.chdir(tmp_path)

        assert get_framework_base_dir() == tmp_path / "submodules"

    def test_get_framework_base_dir_standard_mode(self, tmp_path, monkeypatch):
        """测试获取框架目录 - 标准模式"""
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        assert get_framework_base_dir() == driving_dir / "submodules"


class TestMultipleGitlistFiles:
    """多配置文件支持测试"""

    def test_get_all_gitlist_files_empty(self, tmp_path, monkeypatch):
        """测试获取所有 gitlist.json - 无配置文件"""
        monkeypatch.chdir(tmp_path)

        # 创建 .driving 目录但不创建配置文件
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        files = get_all_gitlist_files()
        assert len(files) == 0

    def test_get_all_gitlist_files_root_only(self, tmp_path, monkeypatch):
        """测试获取所有 gitlist.json - 仅根目录配置"""
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        monkeypatch.chdir(tmp_path)

        files = get_all_gitlist_files()
        assert len(files) == 1
        assert files[0] == gitlist

    def test_get_all_gitlist_files_all(self, tmp_path, monkeypatch):
        """测试获取所有 gitlist.json - 所有配置文件"""
        # 创建所有配置文件
        gitlist_root = tmp_path / "gitlist.json"
        gitlist_root.write_text("{}")

        ai_docs = tmp_path / "ai-docs"
        ai_docs.mkdir()
        gitlist_ai_docs = ai_docs / "gitlist.json"
        gitlist_ai_docs.write_text("{}")

        ai_docs_local = tmp_path / "ai-docs-local"
        ai_docs_local.mkdir()
        gitlist_local = ai_docs_local / "gitlist.json"
        gitlist_local.write_text("{}")

        monkeypatch.chdir(tmp_path)

        files = get_all_gitlist_files()
        assert len(files) == 3
        # 验证顺序：local > ai-docs > root
        assert files[0] == gitlist_local
        assert files[1] == gitlist_ai_docs
        assert files[2] == gitlist_root


class TestEnvironmentCheck:
    """环境检查测试"""

    def test_check_environment_with_driving(self, tmp_path, monkeypatch):
        """测试环境检查 - 存在 .driving 目录"""
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        monkeypatch.chdir(tmp_path)

        is_ok, error_msg = check_environment()
        assert is_ok is True
        assert error_msg == ""

    def test_check_environment_with_gitlist(self, tmp_path, monkeypatch):
        """测试环境检查 - 存在 gitlist.json"""
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        monkeypatch.chdir(tmp_path)

        is_ok, error_msg = check_environment()
        assert is_ok is True
        assert error_msg == ""

    def test_check_environment_without_config(self, tmp_path, monkeypatch):
        """测试环境检查 - 无配置"""
        monkeypatch.chdir(tmp_path)

        is_ok, error_msg = check_environment()
        assert is_ok is False
        assert "未配置 driving 环境" in error_msg


class TestSensitiveKeywords:
    """敏感关键词配置测试"""

    def test_default_sensitive_keywords(self):
        """测试默认敏感关键词"""
        assert isinstance(SENSITIVE_KEYWORDS, list)
        assert len(SENSITIVE_KEYWORDS) > 0
        assert "api_key" in SENSITIVE_KEYWORDS
        assert "token" in SENSITIVE_KEYWORDS
        assert "secret" in SENSITIVE_KEYWORDS

    def test_custom_sensitive_keywords(self, monkeypatch):
        """测试自定义敏感关键词"""
        # 设置环境变量
        monkeypatch.setenv("DRIVING_SENSITIVE_KEYWORDS", "custom_key,custom_token")

        # 重新导入模块以应用环境变量
        import importlib

        from driving.utils import config

        importlib.reload(config)

        assert "custom_key" in config.SENSITIVE_KEYWORDS
        assert "custom_token" in config.SENSITIVE_KEYWORDS


class TestSubdirectorySupport:
    """子目录支持测试"""

    def test_find_project_root_from_subdirectory(self, tmp_path, monkeypatch):
        """测试从子目录查找项目根目录"""
        # 创建项目结构
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")

        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)

        # 切换到子目录
        monkeypatch.chdir(subdir)

        # 应该能找到父目录的配置
        assert get_driving_dir() == tmp_path

    def test_find_driving_dir_from_subdirectory(self, tmp_path, monkeypatch):
        """测试从子目录查找 .driving 目录"""
        # 创建项目结构
        driving_dir = tmp_path / ".driving"
        driving_dir.mkdir()

        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)

        # 切换到子目录
        monkeypatch.chdir(subdir)

        # 应该能找到父目录的 .driving
        assert get_driving_dir() == driving_dir
