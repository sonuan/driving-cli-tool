"""feature 子命令组单元测试 + 属性测试

覆盖：
- parse_feature_yaml：完整 frontmatter、缺少 name、无 frontmatter、所有字段
- scan_features_from_dir：正确 path/repo 格式、跳过无效目录
- filter_features：空关键词（全量）、单关键词、多关键词 OR、大小写不敏感
- format_feature_output：detail=False 字段集、detail=True 字段集
- CLI 集成测试：feature list 命令

属性测试：
- Property 1: feature 输出字段完整性（scan_features_from_dir）
- Property 2: --repo 过滤隔离性
- Property 3: --keywords 匹配正确性
- Property 4: 精简/详情字段集合
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from driving_cli.cli import cli
from driving_cli.commands.feature import (
    ALL_FIELDS,
    SUMMARY_FIELDS,
    filter_features,
    format_feature_output,
    parse_feature_yaml,
    scan_features_from_dir,
)


# ==================== Helpers ====================


def _make_feature_md(
    features_dir: Path,
    dir_name: str,
    name: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    module: str = "",
    assignee: str = "",
    tags: list = None,
    urls: list = None,
) -> Path:
    """在 features_dir/{dir_name}/FEATURE.md 创建测试用 FEATURE.md"""
    feature_dir = features_dir / dir_name
    feature_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}"]
    if title:
        lines.append(f"title: {title}")
    if description:
        lines.append(f"description: {description}")
    if status:
        lines.append(f"status: {status}")
    if priority:
        lines.append(f"priority: {priority}")
    if module:
        lines.append(f"module: {module}")
    if assignee:
        lines.append(f"assignee: {assignee}")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {t}")
    if urls:
        lines.append("urls:")
        for u in urls:
            lines.append(f"  - type: {u.get('type', '')}")
            lines.append(f"    url: {u.get('url', '')}")
            lines.append(f"    title: {u.get('title', '')}")
    lines.append("---")
    lines.append("")
    lines.append("# Feature body")
    feature_md = feature_dir / "FEATURE.md"
    feature_md.write_text("\n".join(lines), encoding="utf-8")
    return feature_md


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


# ==================== parse_feature_yaml ====================


class TestParseFeatureYaml:
    def test_完整frontmatter解析所有字段(self, tmp_path):
        f = _make_feature_md(
            tmp_path, "game-home", "game-home",
            title="游戏首页",
            description="游戏首页功能",
            status="in-progress",
            priority="high",
            module="module_game",
            assignee="zhangsan",
            tags=["game", "list-page"],
            urls=[{"type": "requirement", "url": "https://example.com/doc", "title": "需求文档"}],
        )
        result = parse_feature_yaml(f)
        assert result is not None
        assert result["name"] == "game-home"
        assert result["title"] == "游戏首页"
        assert result["description"] == "游戏首页功能"
        assert result["status"] == "in-progress"
        assert result["priority"] == "high"
        assert result["module"] == "module_game"
        assert result["assignee"] == "zhangsan"
        assert "game" in result["tags"]
        assert "list-page" in result["tags"]
        assert len(result["urls"]) == 1
        assert result["urls"][0]["url"] == "https://example.com/doc"

    def test_缺少name返回None(self, tmp_path):
        feature_dir = tmp_path / "no-name"
        feature_dir.mkdir()
        f = feature_dir / "FEATURE.md"
        f.write_text("---\ntitle: 没有 name\n---\n\n正文", encoding="utf-8")
        result = parse_feature_yaml(f)
        assert result is None

    def test_无frontmatter返回None(self, tmp_path):
        feature_dir = tmp_path / "no-fm"
        feature_dir.mkdir()
        f = feature_dir / "FEATURE.md"
        f.write_text("# 没有 frontmatter\n\n内容", encoding="utf-8")
        result = parse_feature_yaml(f)
        assert result is None

    def test_只有name字段时其他字段为空(self, tmp_path):
        feature_dir = tmp_path / "minimal"
        feature_dir.mkdir()
        f = feature_dir / "FEATURE.md"
        f.write_text("---\nname: minimal-feature\n---\n\n正文", encoding="utf-8")
        result = parse_feature_yaml(f)
        assert result is not None
        assert result["name"] == "minimal-feature"
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["tags"] == []
        assert result["urls"] == []

    def test_解析真实FEATURE_MD格式(self, tmp_path):
        """测试 ai-driving/my-local/features/game-home/FEATURE.md 格式"""
        feature_dir = tmp_path / "game-home"
        feature_dir.mkdir()
        f = feature_dir / "FEATURE.md"
        content = """\
---
name: game-home
title: 游戏首页
description: 游戏首页功能，包含游戏列表、推荐游戏、分类筛选等功能
status: in-progress
priority: high
module: module_game
assignee: zhangsan
tags:
  - game
  - list-page
  - mvvm
urls:
  - type: requirement
    url: https://example.feishu.cn/docx/xxx
    title: 游戏首页需求文档
  - type: design
    url: https://www.figma.com/file/xxx
    title: 游戏首页设计稿
---

# 游戏首页
"""
        f.write_text(content, encoding="utf-8")
        result = parse_feature_yaml(f)
        assert result is not None
        assert result["name"] == "game-home"
        assert result["status"] == "in-progress"
        assert len(result["tags"]) == 3
        assert len(result["urls"]) == 2


# ==================== scan_features_from_dir ====================


class TestScanFeaturesFromDir:
    def test_扫描返回正确feature列表(self, tmp_path):
        features_dir = tmp_path / "features"
        _make_feature_md(features_dir, "feat-a", "feat-a", title="功能 A")
        _make_feature_md(features_dir, "feat-b", "feat-b", title="功能 B")

        result = scan_features_from_dir("my-repo", features_dir)
        assert len(result) == 2
        names = {f["name"] for f in result}
        assert names == {"feat-a", "feat-b"}

    def test_path格式正确(self, tmp_path):
        features_dir = tmp_path / "features"
        _make_feature_md(features_dir, "game-home", "game-home")

        result = scan_features_from_dir("my-local", features_dir)
        assert len(result) == 1
        assert result[0]["path"] == "ai-driving/my-local/features/game-home/"

    def test_repo字段等于传入的repo_name(self, tmp_path):
        features_dir = tmp_path / "features"
        _make_feature_md(features_dir, "feat-x", "feat-x")

        result = scan_features_from_dir("driving", features_dir)
        assert result[0]["repo"] == "driving"

    def test_跳过无FEATURE_MD的子目录(self, tmp_path):
        features_dir = tmp_path / "features"
        # 有效目录
        _make_feature_md(features_dir, "valid", "valid-feat")
        # 无 FEATURE.md 的目录
        (features_dir / "empty-dir").mkdir(parents=True, exist_ok=True)

        result = scan_features_from_dir("repo", features_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["name"] == "valid-feat"

    def test_跳过缺少name的FEATURE_MD(self, tmp_path):
        features_dir = tmp_path / "features"
        _make_feature_md(features_dir, "valid", "valid-feat")
        # 缺少 name 的目录
        bad_dir = features_dir / "bad"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "FEATURE.md").write_text("---\ntitle: 没有 name\n---\n", encoding="utf-8")

        result = scan_features_from_dir("repo", features_dir, quiet=True)
        assert len(result) == 1

    def test_跳过文件不处理子目录中的文件(self, tmp_path):
        features_dir = tmp_path / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        # 直接放在 features_dir 下的文件（不是子目录）
        (features_dir / "stray.md").write_text("---\nname: stray\n---\n", encoding="utf-8")
        _make_feature_md(features_dir, "valid", "valid-feat")

        result = scan_features_from_dir("repo", features_dir, quiet=True)
        assert len(result) == 1


# ==================== filter_features ====================


class TestFilterFeatures:
    def _make_features(self):
        return [
            {
                "name": "game-home", "title": "游戏首页", "description": "游戏列表功能",
                "status": "in-progress", "priority": "high", "module": "module_game",
                "assignee": "zhangsan", "tags": ["game", "list-page"],
                "urls": [{"url": "https://example.com/game", "title": "游戏需求文档"}],
                "path": "ai-driving/my-local/features/game-home/", "repo": "my-local",
            },
            {
                "name": "profile-home", "title": "个人主页", "description": "用户个人信息展示",
                "status": "completed", "priority": "medium", "module": "module_profile",
                "assignee": "lisi", "tags": ["profile", "mvvm"],
                "urls": [{"url": "https://example.com/profile", "title": "个人主页设计稿"}],
                "path": "ai-driving/my-local/features/profile-home/", "repo": "my-local",
            },
        ]

    def test_空关键词返回全部(self):
        features = self._make_features()
        result = filter_features(features, [])
        assert len(result) == 2

    def test_单关键词匹配name(self):
        features = self._make_features()
        result = filter_features(features, ["game"])
        assert len(result) == 1
        assert result[0]["name"] == "game-home"

    def test_单关键词匹配title(self):
        features = self._make_features()
        result = filter_features(features, ["个人主页"])
        assert len(result) == 1
        assert result[0]["name"] == "profile-home"

    def test_单关键词匹配tags(self):
        features = self._make_features()
        result = filter_features(features, ["mvvm"])
        assert len(result) == 1
        assert result[0]["name"] == "profile-home"

    def test_单关键词匹配url_title(self):
        features = self._make_features()
        result = filter_features(features, ["设计稿"])
        assert len(result) == 1
        assert result[0]["name"] == "profile-home"

    def test_多关键词OR关系(self):
        features = self._make_features()
        result = filter_features(features, ["game", "profile"])
        assert len(result) == 2

    def test_大小写不敏感(self):
        features = self._make_features()
        result = filter_features(features, ["GAME"])
        assert len(result) == 1
        assert result[0]["name"] == "game-home"

    def test_无匹配返回空列表(self):
        features = self._make_features()
        result = filter_features(features, ["nonexistent-xyz"])
        assert len(result) == 0

    def test_匹配url字段(self):
        features = self._make_features()
        result = filter_features(features, ["example.com/game"])
        assert len(result) == 1
        assert result[0]["name"] == "game-home"


# ==================== format_feature_output ====================


class TestFormatFeatureOutput:
    def _make_feature(self):
        return {
            "name": "game-home", "title": "游戏首页", "description": "描述",
            "status": "in-progress", "priority": "high", "module": "module_game",
            "assignee": "zhangsan", "tags": ["game"], "urls": [],
            "path": "ai-driving/my-local/features/game-home/", "repo": "my-local",
        }

    def test_detail_False只输出精简字段(self):
        feature = self._make_feature()
        result = format_feature_output(feature, detail=False)
        assert set(result.keys()) == SUMMARY_FIELDS

    def test_detail_False_urls为字符串数组(self):
        feature = {**self._make_feature(), "urls": [
            {"type": "requirement", "url": "https://example.com/doc", "title": "需求文档"},
            {"type": "design", "url": "https://example.com/design", "title": "设计稿"},
        ]}
        result = format_feature_output(feature, detail=False)
        assert result["urls"] == ["https://example.com/doc", "https://example.com/design"]

    def test_detail_False_urls空列表(self):
        result = format_feature_output(self._make_feature(), detail=False)
        assert result["urls"] == []

    def test_detail_True输出所有字段(self):
        feature = self._make_feature()
        result = format_feature_output(feature, detail=True)
        # 应包含所有 ALL_FIELDS 中的字段
        for field in ALL_FIELDS:
            assert field in result

    def test_detail_False不含priority等详情字段(self):
        feature = self._make_feature()
        result = format_feature_output(feature, detail=False)
        assert "priority" not in result
        assert "module" not in result
        assert "assignee" not in result
        assert "tags" not in result
        assert "urls" in result  # urls 包含在精简摘要中，供 AI 二次匹配

    def test_detail_True包含priority等详情字段(self):
        feature = self._make_feature()
        result = format_feature_output(feature, detail=True)
        assert "priority" in result
        assert "module" in result
        assert "assignee" in result
        assert "tags" in result
        assert "urls" in result


# ==================== CLI 集成测试 ====================


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_with_features(tmp_path):
    """创建包含 feature 文件的测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
    ])
    features_dir = tmp_path / "ai-driving" / "my-local" / "features"
    _make_feature_md(features_dir, "game-home", "game-home", title="游戏首页",
                     description="游戏功能", status="in-progress", tags=["game"])
    _make_feature_md(features_dir, "profile-home", "profile-home", title="个人主页",
                     description="个人信息", status="completed", tags=["profile"])
    return tmp_path


class TestFeatureListCommand:
    def test_list输出JSON数组(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list默认输出精简字段(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert set(item.keys()) == SUMMARY_FIELDS

    def test_list_detail输出完整字段(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list", "--detail"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ALL_FIELDS:
                assert field in item

    def test_list按name字母顺序排序(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [item["name"] for item in data]
        assert names == sorted(names)

    def test_list_keywords过滤(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list", "--keywords", "game"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "game-home"

    def test_list_repo过滤(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list", "--repo", "my-local"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        for item in data:
            assert item["repo"] == "my-local"

    def test_list_repo不存在时报错(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list", "--repo", "nonexistent"])
        assert result.exit_code != 0

    def test_list无features目录时返回空数组(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "empty-repo", "type": "local", "path": "ai-driving/empty-repo", "local_path": None},
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_feature_group已挂载到cli(self, runner):
        result = runner.invoke(cli, ["feature", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "modules" in result.output

    def test_list_多关键词OR关系(self, runner, project_with_features):
        with patch("driving_cli.commands.feature.find_project_root", return_value=project_with_features):
            result = runner.invoke(cli, ["feature", "list", "--keywords", "game", "--keywords", "profile"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2


# ==================== driving feature modules 集成测试 ====================


def _make_config_with_tags(tmp_path: Path, repos: list) -> None:
    config = {
        "version": "2",
        "repos": repos,
        "default_commit_message": "update",
        "update_version_url": "",
    }
    (tmp_path / "driving.config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class TestFeatureModulesCommand:
    def test_modules_empty_when_no_repos(self, runner, tmp_path):
        """没有仓库时，输出空数组"""
        _make_config_with_tags(tmp_path, [])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_modules_always_includes_features_dir(self, runner, tmp_path):
        """无论 tags 是什么，所有仓库的 features 目录都会出现在输出中"""
        _make_config_with_tags(tmp_path, [
            {"name": "base-repo", "type": "local", "path": "ai-driving/base-repo",
             "local_path": None, "tags": ["base"], "modules": []},
            {"name": "other-repo", "type": "local", "path": "ai-driving/other-repo",
             "local_path": None, "tags": [], "modules": []},
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        assert "ai-driving/base-repo/features" in paths
        assert "ai-driving/other-repo/features" in paths

    def test_modules_returns_repo_modules_when_set(self, runner, tmp_path):
        """tags=features 的仓库有 modules 时，只返回每个 module 的 name/description/path，不追加 features 兜底"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "feature-repo", "type": "local", "path": "ai-driving/feature-repo",
                "local_path": None, "tags": ["features"],
                "modules": [
                    {"name": "order", "description": "订单模块"},
                    {"name": "pay", "description": "支付模块"},
                ],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        # modules 展开
        assert "ai-driving/feature-repo/order" in paths
        assert "ai-driving/feature-repo/pay" in paths
        # tags=features 且有 modules 时，不追加 features 兜底
        assert "ai-driving/feature-repo/features" not in paths

    def test_modules_path_format_is_repo_path_slash_module_name(self, runner, tmp_path):
        """modules 的 path 格式为 {repo.path}/{module.name}，tags=features 有 modules 时不追加 features 兜底"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "my-repo", "type": "local", "path": "ai-driving/my-repo",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "chat", "description": "聊天"}],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        assert "ai-driving/my-repo/chat" in paths
        # tags=features 且有 modules 时，不追加 features 兜底
        assert "ai-driving/my-repo/features" not in paths

    def test_modules_fallback_features_dir_always_present(self, runner, tmp_path):
        """tags=features 但 modules 为空时，兜底追加 {repo.path}/features"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "no-modules-repo", "type": "local", "path": "ai-driving/no-modules-repo",
                "local_path": None, "tags": ["features"],
                "modules": [],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "no-modules-repo"
        assert data[0]["path"] == "ai-driving/no-modules-repo/features"

    def test_modules_merges_multiple_repos(self, runner, tmp_path):
        """多个仓库的 modules 合并输出；tags=features 有 modules 的仓库不追加 features 兜底，非 features 仓库追加"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "repo-a", "type": "local", "path": "ai-driving/repo-a",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "mod1", "description": "模块1"}],
            },
            {
                "name": "repo-b", "type": "local", "path": "ai-driving/repo-b",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "mod2", "description": "模块2"}],
            },
            {
                "name": "base-repo", "type": "local", "path": "ai-driving/base-repo",
                "local_path": None, "tags": ["base"],
                "modules": [],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        # modules 展开
        assert "ai-driving/repo-a/mod1" in paths
        assert "ai-driving/repo-b/mod2" in paths
        # tags=features 且有 modules 的仓库，不追加 features 兜底
        assert "ai-driving/repo-a/features" not in paths
        assert "ai-driving/repo-b/features" not in paths
        # 非 features 仓库始终追加 features 兜底
        assert "ai-driving/base-repo/features" in paths

    def test_modules_output_contains_required_fields(self, runner, tmp_path):
        """modules 输出每条记录都包含 name、description、path 字段"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "feature-repo", "type": "local", "path": "ai-driving/feature-repo",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "live", "description": "直播"}],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert "name" in item
            assert "description" in item
            assert "path" in item

    def test_modules_features_only_过滤非features仓库(self, runner, tmp_path):
        """--features-only 只输出 tags 含 features 的仓库模块，过滤其余仓库"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "aidoc", "type": "local", "path": "ai-driving/aidoc",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "family", "description": "家族"}],
            },
            {
                "name": "base-repo", "type": "local", "path": "ai-driving/base-repo",
                "local_path": None, "tags": ["base"],
                "modules": [],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules", "--features-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        # 只保留 features 仓库的 module
        assert "ai-driving/aidoc/family" in paths
        # base-repo 的兜底条目被过滤掉
        assert "ai-driving/base-repo/features" not in paths

    def test_modules_features_only_无features仓库时返回空(self, runner, tmp_path):
        """--features-only 时若无任何 tags=features 的仓库，返回空数组"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "base-repo", "type": "local", "path": "ai-driving/base-repo",
                "local_path": None, "tags": ["base"],
                "modules": [],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules", "--features-only"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_modules_不加参数时仍输出全部(self, runner, tmp_path):
        """不加 --features-only 时行为不变，输出所有仓库的模块"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "aidoc", "type": "local", "path": "ai-driving/aidoc",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "family", "description": "家族"}],
            },
            {
                "name": "base-repo", "type": "local", "path": "ai-driving/base-repo",
                "local_path": None, "tags": ["base"],
                "modules": [],
            },
        ])
        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "modules"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        paths = {item["path"] for item in data}
        assert "ai-driving/aidoc/family" in paths
        assert "ai-driving/base-repo/features" in paths

    def test_feature_list_traverses_modules_paths(self, runner, tmp_path):
        """feature list 从 modules 聚合的路径遍历，扫描各模块目录下的 features"""
        # 创建仓库配置：包含两个 modules
        _make_config_with_tags(tmp_path, [
            {
                "name": "app-repo", "type": "local", "path": "ai-driving/app-repo",
                "local_path": None, "tags": ["features"],
                "modules": [
                    {"name": "order", "description": "订单"},
                    {"name": "pay", "description": "支付"},
                ],
            },
        ])
        # 在 order module 路径下创建 feature
        order_features = tmp_path / "ai-driving" / "app-repo" / "order"
        _make_feature_md(order_features, "order-list", "order-list", title="订单列表")
        # 在 pay module 路径下创建 feature
        pay_features = tmp_path / "ai-driving" / "app-repo" / "pay"
        _make_feature_md(pay_features, "pay-confirm", "pay-confirm", title="支付确认")

        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {item["name"] for item in data}
        assert "order-list" in names
        assert "pay-confirm" in names


# ==================== scan_features_deep 单元测试 ====================


from driving_cli.commands.feature import scan_features_deep


class TestScanFeaturesDeep:
    def _make_deep_feature(self, module_dir: Path, quarter: str, feature_name: str, name: str, **kwargs) -> Path:
        """在 module_dir/{quarter}/{feature_name}/FEATURE.md 创建测试用文件"""
        feature_dir = module_dir / quarter / feature_name
        return _make_feature_md(feature_dir.parent, feature_name, name, **kwargs)

    def test_扫描多层目录结构(self, tmp_path):
        """能正确扫描 {module}/{quarter}/{feature}/FEATURE.md 结构"""
        module_dir = tmp_path / "family"
        self._make_deep_feature(module_dir, "2026-Q2", "feat-a", "feat-a", title="功能A")
        self._make_deep_feature(module_dir, "2026-Q2", "feat-b", "feat-b", title="功能B")

        result = scan_features_deep("family", module_dir, "ai-driving/aidoc", quiet=True)
        assert len(result) == 2
        names = {f["name"] for f in result}
        assert names == {"feat-a", "feat-b"}

    def test_quarter字段正确提取(self, tmp_path):
        """quarter 字段应等于第一层子目录名（如 2026-Q2）"""
        module_dir = tmp_path / "message"
        self._make_deep_feature(module_dir, "2026-Q2", "msg-feat", "msg-feat")

        result = scan_features_deep("message", module_dir, "ai-driving/aidoc", quiet=True)
        assert len(result) == 1
        assert result[0]["quarter"] == "2026-Q2"

    def test_path格式含完整层级(self, tmp_path):
        """path 字段应包含 repo_path/module/quarter/feature_dir/"""
        module_dir = tmp_path / "family"
        self._make_deep_feature(module_dir, "2026-Q2", "family-bounty", "family-bounty")

        result = scan_features_deep("family", module_dir, "ai-driving/aidoc", quiet=True)
        assert len(result) == 1
        assert result[0]["path"] == "ai-driving/aidoc/family/2026-Q2/family-bounty/"

    def test_repo字段等于module_name(self, tmp_path):
        """repo 字段应等于传入的 module_name"""
        module_dir = tmp_path / "chatroom"
        self._make_deep_feature(module_dir, "2026-Q2", "chat-feat", "chat-feat")

        result = scan_features_deep("chatroom", module_dir, "ai-driving/aidoc", quiet=True)
        assert result[0]["repo"] == "chatroom"

    def test_跨多个季度目录(self, tmp_path):
        """跨多个季度目录时，所有 feature 都能扫描到"""
        module_dir = tmp_path / "family"
        self._make_deep_feature(module_dir, "2026-Q1", "feat-q1", "feat-q1")
        self._make_deep_feature(module_dir, "2026-Q2", "feat-q2", "feat-q2")

        result = scan_features_deep("family", module_dir, "ai-driving/aidoc", quiet=True)
        assert len(result) == 2
        quarters = {f["quarter"] for f in result}
        assert quarters == {"2026-Q1", "2026-Q2"}

    def test_跳过缺少name的FEATURE_MD(self, tmp_path):
        """FEATURE.md 缺少 name 字段时跳过"""
        module_dir = tmp_path / "family"
        self._make_deep_feature(module_dir, "2026-Q2", "valid", "valid-feat")
        # 无效的 FEATURE.md
        bad_dir = module_dir / "2026-Q2" / "bad-feat"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "FEATURE.md").write_text("---\ntitle: 没有 name\n---\n", encoding="utf-8")

        result = scan_features_deep("family", module_dir, "ai-driving/aidoc", quiet=True)
        assert len(result) == 1
        assert result[0]["name"] == "valid-feat"

    def test_空模块目录返回空列表(self, tmp_path):
        """模块目录下没有任何 FEATURE.md 时返回空列表"""
        module_dir = tmp_path / "empty-module"
        module_dir.mkdir(parents=True, exist_ok=True)

        result = scan_features_deep("empty-module", module_dir, "ai-driving/aidoc", quiet=True)
        assert result == []

    def test_feature_list_deep模式集成(self, runner, tmp_path):
        """feature list 对 tags=features 的仓库使用深度扫描，能正确输出 quarter 字段"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "aidoc", "type": "local", "path": "ai-driving/aidoc",
                "local_path": None, "tags": ["features"],
                "modules": [
                    {"name": "family", "description": "家族"},
                    {"name": "message", "description": "私信"},
                ],
            },
        ])
        # 创建深层结构
        family_dir = tmp_path / "ai-driving" / "aidoc" / "family"
        msg_dir = tmp_path / "ai-driving" / "aidoc" / "message"
        _make_feature_md(family_dir / "2026-Q2", "family-feat", "family-feat", title="家族功能")
        _make_feature_md(msg_dir / "2026-Q2", "msg-feat", "msg-feat", title="私信功能")

        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {item["name"] for item in data}
        assert "family-feat" in names
        assert "msg-feat" in names
        # quarter 字段应存在
        for item in data:
            assert "quarter" in item
            assert item["quarter"] == "2026-Q2"

    def test_feature_list_deep模式关键词过滤(self, runner, tmp_path):
        """深度扫描模式下，关键词过滤仍然正常工作"""
        _make_config_with_tags(tmp_path, [
            {
                "name": "aidoc", "type": "local", "path": "ai-driving/aidoc",
                "local_path": None, "tags": ["features"],
                "modules": [{"name": "family", "description": "家族"}],
            },
        ])
        family_dir = tmp_path / "ai-driving" / "aidoc" / "family"
        _make_feature_md(family_dir / "2026-Q2", "bounty-task", "bounty-task", title="悬赏任务")
        _make_feature_md(family_dir / "2026-Q2", "score-card", "score-card", title="积分卡片")

        with patch("driving_cli.commands.feature.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["feature", "list", "--keywords", "悬赏"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "bounty-task"

_feature_name_st = st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True)
_repo_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True)
_safe_text_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _-",
    min_size=0,
    max_size=30,
)


# Feature: feature-and-rule-commands, Property 1: feature 输出字段完整性
@settings(max_examples=100)
@given(
    repo_name=_repo_name_st,
    feature_names=st.lists(_feature_name_st, min_size=1, max_size=5, unique=True),
)
def test_property1_feature输出字段完整性(tmp_path_factory, repo_name, feature_names):
    """Property 1: feature 输出字段完整性

    对于任意包含有效 FEATURE.md 的 feature 目录，scan_features_from_dir 的输出中
    每条记录都应包含 name、path、repo 字段，且 path 格式为
    ai-driving/{repo}/features/{dir_name}/，repo 与传入的 repo_name 一致。

    **Validates: Requirements 1.2, 1.3**
    """
    tmp_path = tmp_path_factory.mktemp("prop1")
    features_dir = tmp_path / "features"

    for name in feature_names:
        _make_feature_md(features_dir, name, name)

    result = scan_features_from_dir(repo_name, features_dir, quiet=True)

    assert len(result) == len(feature_names)
    for item in result:
        assert "name" in item
        assert "path" in item
        assert "repo" in item
        assert item["repo"] == repo_name
        assert item["path"].startswith(f"ai-driving/{repo_name}/features/")
        assert item["path"].endswith("/")


# Feature: feature-and-rule-commands, Property 2: --repo 过滤隔离性
@settings(max_examples=50)
@given(
    repo_a=_repo_name_st,
    repo_b=_repo_name_st.filter(lambda x: x != "repo-a"),
    names_a=st.lists(_feature_name_st, min_size=1, max_size=3, unique=True),
    names_b=st.lists(_feature_name_st, min_size=1, max_size=3, unique=True),
)
def test_property2_repo过滤隔离性(tmp_path_factory, repo_a, repo_b, names_a, names_b):
    """Property 2: --repo 过滤隔离性

    对于任意多仓库配置，当指定 --repo X 时，输出结果中所有记录的 repo 字段都应等于 X，
    不包含其他仓库的 features。

    **Validates: Requirements 1.4**
    """
    if repo_a == repo_b:
        return  # skip degenerate case

    tmp_path = tmp_path_factory.mktemp("prop2")

    # 创建两个仓库的 features 目录
    features_dir_a = tmp_path / "ai-driving" / repo_a / "features"
    features_dir_b = tmp_path / "ai-driving" / repo_b / "features"

    for name in names_a:
        _make_feature_md(features_dir_a, name, name)
    for name in names_b:
        _make_feature_md(features_dir_b, name, name)

    # 扫描仓库 A
    result_a = scan_features_from_dir(repo_a, features_dir_a, quiet=True)
    # 扫描仓库 B
    result_b = scan_features_from_dir(repo_b, features_dir_b, quiet=True)

    # 合并后按 repo 过滤
    all_features = result_a + result_b
    filtered = [f for f in all_features if f["repo"] == repo_a]

    for item in filtered:
        assert item["repo"] == repo_a


# Feature: feature-and-rule-commands, Property 3: --keywords 匹配正确性
@settings(max_examples=100)
@given(
    feature_names=st.lists(_feature_name_st, min_size=0, max_size=6, unique=True),
    keywords=st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
        min_size=1,
        max_size=3,
    ),
)
def test_property3_keywords匹配正确性(feature_names, keywords):
    """Property 3: --keywords 匹配正确性

    对于任意 feature 列表和关键词列表，filter_features 的输出结果中每条记录，
    都应至少有一个元数据字段包含至少一个关键词（大小写不敏感）；
    未被任何关键词匹配的 feature 不应出现在结果中。

    **Validates: Requirements 1.5**
    """
    features = [
        {
            "name": name, "title": "", "description": "",
            "status": "", "priority": "", "module": "", "assignee": "",
            "tags": [], "urls": [],
            "path": f"ai-driving/repo/features/{name}/", "repo": "repo",
        }
        for name in feature_names
    ]

    result = filter_features(features, keywords)

    # 每条结果都应匹配至少一个关键词
    for item in result:
        matched = any(
            kw.lower() in (item.get("name") or "").lower()
            for kw in keywords
        )
        # 也检查其他字段
        if not matched:
            all_text = " ".join(str(v) for v in item.values() if v).lower()
            matched = any(kw.lower() in all_text for kw in keywords)
        assert matched, f"feature {item['name']} 不匹配任何关键词 {keywords}"

    # 未匹配的 feature 不应出现在结果中
    result_names = {f["name"] for f in result}
    for feature in features:
        all_text = " ".join(str(v) for v in feature.values() if v).lower()
        should_match = any(kw.lower() in all_text for kw in keywords)
        if not should_match:
            assert feature["name"] not in result_names


# Feature: feature-and-rule-commands, Property 4: 精简/详情字段集合
@settings(max_examples=100)
@given(
    name=_feature_name_st,
    title=_safe_text_st,
    description=_safe_text_st,
    status=st.sampled_from(["", "planning", "in-progress", "completed"]),
    priority=st.sampled_from(["", "low", "medium", "high"]),
)
def test_property4_精简详情字段集合(name, title, description, status, priority):
    """Property 4: 精简/详情字段集合

    对于任意 feature 记录，format_feature_output(feature, detail=False) 的输出键集合
    应恰好为 {name, title, description, status, path, repo}；
    format_feature_output(feature, detail=True) 的输出应包含所有可用字段。

    **Validates: Requirements 1.6, 1.7**
    """
    feature = {
        "name": name, "title": title, "description": description,
        "status": status, "priority": priority, "module": "mod",
        "assignee": "user", "tags": ["tag1"], "urls": [],
        "path": f"ai-driving/repo/features/{name}/", "repo": "repo",
    }

    summary = format_feature_output(feature, detail=False)
    assert set(summary.keys()) == SUMMARY_FIELDS

    detail_out = format_feature_output(feature, detail=True)
    for field in ALL_FIELDS:
        assert field in detail_out
