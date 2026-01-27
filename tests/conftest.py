"""Pytest 配置和共享 fixtures"""

from pathlib import Path

import pytest


@pytest.fixture
def sample_gitlist_data():
    """示例 gitlist.json 数据"""
    return [
        {
            "name": "xstatic",
            "project_name": "xstatic",
            "url": "https://github.com/example/xstatic",
            "branch": "main",
            "module": "library_xstatic",
            "sources": ["src/main/java/hb/xstatic/*"],
            "description": "Activity/Fragment 基础封装框架",
            "creator": "开发团队",
            "date": "2024-01-20",
        },
        {
            "name": "ximage",
            "project_name": "ximage",
            "url": "https://github.com/example/ximage",
            "branch": "develop",
            "module": "library_ximage",
            "sources": ["src/main/java/hb/ximage/*"],
            "description": "图片加载框架",
            "creator": "开发团队",
            "date": "2024-01-21",
        },
    ]


@pytest.fixture
def sample_local_project_data():
    """示例本地项目数据"""
    return {
        "name": "driving",
        "project_name": "__local__",
        "url": "__local__",
        "branch": "__local__",
        "module": "driving",
        "sources": ["cli-tool/driving/*", "cli-tool/README.md"],
        "description": "Driving CLI 工具",
        "creator": "开发团队",
        "date": "2024-01-25",
    }


@pytest.fixture
def mock_git_repo(tmp_path):
    """创建模拟的 Git 仓库"""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path


@pytest.fixture
def mock_driving_project(tmp_path):
    """创建模拟的 driving 项目结构"""
    # 创建 .driving 目录
    driving_dir = tmp_path / ".driving"
    driving_dir.mkdir()

    # 创建 gitlist.json
    gitlist = driving_dir / "gitlist.json"
    gitlist.write_text("[]")

    # 创建 submodules 目录
    submodules = driving_dir / "submodules"
    submodules.mkdir()

    return tmp_path


@pytest.fixture
def mock_local_mode_project(tmp_path):
    """创建模拟的本地模式项目"""
    # 创建 gitlist.json
    gitlist = tmp_path / "gitlist.json"
    gitlist.write_text("[]")

    # 创建 submodules 目录
    submodules = tmp_path / "submodules"
    submodules.mkdir()

    return tmp_path
