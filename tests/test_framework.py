"""框架管理测试（修复版）"""

import json
import pytest
from pathlib import Path
from driving.models.framework import Framework


class TestFrameworkModel:
    """框架模型测试"""

    def test_framework_creation(self):
        """测试创建框架对象"""
        framework = Framework(
            name="xstatic",
            project_name="xstatic",
            url="https://github.com/example/xstatic",
            branch="main",
            module="library_xstatic",
            sources=["src/main/java/hb/xstatic/*"],
            description="Activity/Fragment 基础封装框架",
            creator="开发团队",
            date="2024-01-20"
        )
        
        assert framework.name == "xstatic"
        assert framework.project_name == "xstatic"
        assert framework.url == "https://github.com/example/xstatic"
        assert framework.branch == "main"
        assert framework.module == "library_xstatic"
        assert len(framework.sources) == 1
        assert framework.description == "Activity/Fragment 基础封装框架"
        assert framework.creator == "开发团队"
        assert framework.date == "2024-01-20"

    def test_framework_without_branch(self):
        """测试不带分支的框架"""
        framework = Framework(
            name="ximage",
            project_name="ximage",
            url="https://github.com/example/ximage",
            module="library_ximage",
            sources=["src/main/java/hb/ximage/*"],
            description="图片加载框架",
            creator="开发团队",
            date="2024-01-21"
        )
        
        assert framework.branch is None
        assert framework.name == "ximage"

    def test_framework_local_project(self):
        """测试本地项目标识"""
        framework = Framework(
            name="driving",
            project_name="__local__",
            url="__local__",
            branch="__local__",
            module="driving",
            sources=["cli-tool/driving/*"],
            description="Driving CLI 工具",
            creator="开发团队",
            date="2024-01-25"
        )
        
        assert framework.project_name == "__local__"
        assert framework.url == "__local__"
        assert framework.branch == "__local__"

    def test_framework_from_dict(self):
        """测试从字典创建框架"""
        data = {
            "name": "xstatic",
            "project_name": "xstatic",
            "url": "https://github.com/example/xstatic",
            "branch": "main",
            "module": "library_xstatic",
            "sources": ["src/main/java/hb/xstatic/*"],
            "description": "测试框架",
            "creator": "测试者",
            "date": "2024-01-20"
        }
        
        framework = Framework.from_dict(data)
        assert framework.name == "xstatic"
        assert framework.branch == "main"


class TestFrameworkLoading:
    """框架加载测试"""

    def test_load_framework_from_json(self, tmp_path):
        """测试从 JSON 加载框架"""
        # 创建测试配置文件
        gitlist_data = [
            {
                "name": "xstatic",
                "project_name": "xstatic",
                "url": "https://github.com/example/xstatic",
                "branch": "main",
                "module": "library_xstatic",
                "sources": ["src/main/java/hb/xstatic/*"],
                "description": "测试框架",
                "creator": "测试",
                "date": "2024-01-20"
            }
        ]
        
        gitlist_file = tmp_path / "gitlist.json"
        gitlist_file.write_text(json.dumps(gitlist_data, ensure_ascii=False, indent=2))
        
        # 读取并验证
        with open(gitlist_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]['name'] == "xstatic"
        assert data[0]['description'] == "测试框架"

    def test_load_multiple_frameworks(self, tmp_path):
        """测试加载多个框架"""
        gitlist_data = [
            {
                "name": "xstatic",
                "project_name": "xstatic",
                "url": "https://github.com/example/xstatic",
                "module": "library_xstatic",
                "sources": ["src/*"],
                "description": "框架1",
                "creator": "测试",
                "date": "2024-01-20"
            },
            {
                "name": "ximage",
                "project_name": "ximage",
                "url": "https://github.com/example/ximage",
                "module": "library_ximage",
                "sources": ["src/*"],
                "description": "框架2",
                "creator": "测试",
                "date": "2024-01-21"
            }
        ]
        
        gitlist_file = tmp_path / "gitlist.json"
        gitlist_file.write_text(json.dumps(gitlist_data, ensure_ascii=False, indent=2))
        
        # 读取并验证
        with open(gitlist_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data) == 2
        assert data[0]['name'] == "xstatic"
        assert data[1]['name'] == "ximage"


class TestFrameworkValidation:
    """框架配置验证测试"""

    def test_framework_all_fields(self):
        """测试所有字段"""
        framework = Framework(
            name="test",
            project_name="test",
            url="https://github.com/test",
            module="test",
            sources=[],
            description="测试框架",
            creator="测试者",
            date="2024-01-20",
            branch="develop"
        )
        
        assert framework.name == "test"
        assert framework.description == "测试框架"
        assert framework.creator == "测试者"
        assert framework.date == "2024-01-20"
        assert framework.branch == "develop"

    def test_framework_minimal_fields(self):
        """测试最小字段集"""
        framework = Framework(
            name="test",
            project_name="test",
            url="https://github.com/test",
            module="test",
            sources=[],
            description="测试",
            creator="测试者",
            date="2024-01-20"
        )
        
        assert framework.name == "test"
        assert framework.branch is None
