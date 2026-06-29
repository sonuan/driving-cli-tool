"""framework 子命令组单元测试

覆盖 driving framework list/install/checkout/pull/sources 的主要功能。
"""

import json
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.framework import (
    _load_all_frameworks_with_repo,
    _resolve_framework_name,
    framework_group,
)
from driving_cli.models.config import DrivingConfig, RepoConfig
from driving_cli.utils.config_manager import ConfigManager


# ==================== Fixtures ====================


@pytest.fixture
def runner():
    """Click 测试 runner"""
    return CliRunner()


@pytest.fixture
def project_with_two_repos(tmp_path):
    """创建包含两个仓库的项目结构，每个仓库有独立的 gitlist.json"""
    # 创建 driving.config.json
    config = {
        "version": "2",
        "repos": [
            {
                "name": "main",
                "type": "remote",
                "url": "https://github.com/example/main",
                "path": "ai-driving/main",
                "local_path": None,
            },
            {
                "name": "local-docs",
                "type": "local",
                "path": "ai-driving/local-docs",
                "local_path": None,
            },
        ],
        "default_commit_message": "update by driving",
        "update_version_url": "",
    }
    (tmp_path / "driving.config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 创建 main 仓库的 gitlist.json
    main_frameworks_dir = tmp_path / "ai-driving" / "main" / "frameworks"
    main_frameworks_dir.mkdir(parents=True)
    main_gitlist = [
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
            "categories": ["ui-page"],
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
    (main_frameworks_dir / "gitlist.json").write_text(
        json.dumps(main_gitlist, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 创建 local-docs 仓库的 gitlist.json（含同名框架 ximage）
    local_frameworks_dir = tmp_path / "ai-driving" / "local-docs" / "frameworks"
    local_frameworks_dir.mkdir(parents=True)
    local_gitlist = [
        {
            "name": "ximage",
            "project_name": "ximage-local",
            "url": "https://github.com/example/ximage-local",
            "branch": "main",
            "module": "library_ximage_local",
            "sources": ["src/main/java/hb/ximage/*"],
            "description": "本地图片加载框架",
            "creator": "本地团队",
            "date": "2024-02-01",
        },
        {
            "name": "xnet",
            "project_name": "xnet",
            "url": "https://github.com/example/xnet",
            "branch": "main",
            "module": "library_xnet",
            "sources": ["src/main/java/hb/xnet/*"],
            "description": "网络请求框架",
            "creator": "开发团队",
            "date": "2024-02-10",
        },
    ]
    (local_frameworks_dir / "gitlist.json").write_text(
        json.dumps(local_gitlist, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def config_manager(project_with_two_repos):
    """返回指向测试项目的 ConfigManager"""
    return ConfigManager(project_with_two_repos)


# ==================== _load_all_frameworks_with_repo 测试 ====================


class TestLoadAllFrameworksWithRepo:
    """测试 _load_all_frameworks_with_repo 辅助函数"""

    def test_加载所有仓库框架并附加repo字段(self, config_manager):
        """所有框架都应包含 _repo_name 字段"""
        frameworks = _load_all_frameworks_with_repo(config_manager)
        assert all("_repo_name" in fw for fw in frameworks)

    def test_框架总数等于所有仓库框架之和(self, config_manager):
        """main 有 2 个，local-docs 有 2 个，共 4 个"""
        frameworks = _load_all_frameworks_with_repo(config_manager)
        assert len(frameworks) == 4

    def test_repo字段正确标注来源仓库(self, config_manager):
        """xstatic 应来自 main，xnet 应来自 local-docs"""
        frameworks = _load_all_frameworks_with_repo(config_manager)
        repo_map = {fw["name"]: fw["_repo_name"] for fw in frameworks if fw["name"] != "ximage"}
        assert repo_map["xstatic"] == "main"
        assert repo_map["xnet"] == "local-docs"

    def test_无gitlist文件时抛出Abort(self, tmp_path):
        """没有任何 gitlist.json 时应 Abort"""
        import click

        # 创建空配置
        config = {
            "version": "2",
            "repos": [],
            "default_commit_message": "",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(json.dumps(config))
        cm = ConfigManager(tmp_path)
        with pytest.raises(click.Abort):
            _load_all_frameworks_with_repo(cm)

    def test_跳过模板条目(self, tmp_path):
        """名称为 '框架名称' 的条目应被跳过"""
        config = {
            "version": "2",
            "repos": [
                {
                    "name": "main",
                    "type": "remote",
                    "url": "https://github.com/example/main",
                    "path": "ai-driving/main",
                    "local_path": None,
                }
            ],
            "default_commit_message": "",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(json.dumps(config))
        fw_dir = tmp_path / "ai-driving" / "main" / "frameworks"
        fw_dir.mkdir(parents=True)
        gitlist = [
            {"name": "框架名称", "project_name": "template", "url": "", "module": "", "sources": []},
            {"name": "real-fw", "project_name": "real", "url": "https://x.com/r", "module": "m", "sources": []},
        ]
        (fw_dir / "gitlist.json").write_text(json.dumps(gitlist))
        cm = ConfigManager(tmp_path)
        frameworks = _load_all_frameworks_with_repo(cm)
        names = [fw["name"] for fw in frameworks]
        assert "框架名称" not in names
        assert "real-fw" in names


# ==================== _resolve_framework_name 测试 ====================


class TestResolveFrameworkName:
    """测试 _resolve_framework_name 辅助函数"""

    def test_普通名称精确匹配(self, config_manager):
        """xstatic 只在 main 中，应直接返回"""
        all_fw = _load_all_frameworks_with_repo(config_manager)
        fw, repo = _resolve_framework_name("xstatic", all_fw)
        assert fw["name"] == "xstatic"
        assert repo == "main"

    def test_repo斜杠格式精确指定(self, config_manager):
        """main/ximage 应返回 main 仓库的 ximage"""
        all_fw = _load_all_frameworks_with_repo(config_manager)
        fw, repo = _resolve_framework_name("main/ximage", all_fw)
        assert fw["name"] == "ximage"
        assert repo == "main"
        assert fw["project_name"] == "ximage"

    def test_repo斜杠格式指定local仓库(self, config_manager):
        """local-docs/ximage 应返回 local-docs 仓库的 ximage"""
        all_fw = _load_all_frameworks_with_repo(config_manager)
        fw, repo = _resolve_framework_name("local-docs/ximage", all_fw)
        assert fw["name"] == "ximage"
        assert repo == "local-docs"
        assert fw["project_name"] == "ximage-local"

    def test_同名冲突时抛出Abort(self, config_manager):
        """ximage 在两个仓库中都有，应 Abort"""
        import click

        all_fw = _load_all_frameworks_with_repo(config_manager)
        with pytest.raises(click.Abort):
            _resolve_framework_name("ximage", all_fw)

    def test_未找到框架时抛出Abort(self, config_manager):
        """不存在的框架名应 Abort"""
        import click

        all_fw = _load_all_frameworks_with_repo(config_manager)
        with pytest.raises(click.Abort):
            _resolve_framework_name("nonexistent", all_fw)

    def test_repo斜杠格式未找到时抛出Abort(self, config_manager):
        """main/nonexistent 应 Abort"""
        import click

        all_fw = _load_all_frameworks_with_repo(config_manager)
        with pytest.raises(click.Abort):
            _resolve_framework_name("main/nonexistent", all_fw)


# ==================== framework list 命令测试 ====================


class TestFrameworkList:
    """测试 framework list 子命令"""

    def test_列表包含所有框架(self, runner, project_with_two_repos):
        """framework list 应显示所有仓库的框架"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list"])
        assert result.exit_code == 0
        assert "xstatic" in result.output
        assert "xnet" in result.output

    def test_列表包含repo列(self, runner, project_with_two_repos):
        """framework list 应显示 repo 列（仓库名称）"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list"])
        assert result.exit_code == 0
        assert "main" in result.output
        assert "local-docs" in result.output

    def test_json格式输出包含repo字段(self, runner, project_with_two_repos):
        """--json 输出中每个框架应包含 repo 字段"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "frameworks" in data
        for fw in data["frameworks"]:
            assert "repo" in fw

    def test_指定框架名过滤(self, runner, project_with_two_repos):
        """指定框架名时只显示该框架"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list", "xstatic"])
        assert result.exit_code == 0
        assert "xstatic" in result.output

    def test_同名框架冲突时退出(self, runner, project_with_two_repos):
        """ximage 在两个仓库中都有，应提示冲突"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list", "ximage"])
        # 应该以非零退出码退出（Abort）
        assert result.exit_code != 0

    def test_json格式输出不含内部字段(self, runner, project_with_two_repos):
        """--json 输出中不应包含 _repo_name 等内部字段"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fw in data["frameworks"]:
            assert "_repo_name" not in fw


# ==================== framework install 命令测试 ====================


class TestFrameworkInstall:
    """测试 framework install 子命令"""

    def test_安装不存在的框架报错(self, runner, project_with_two_repos):
        """安装不存在的框架应报错"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "install", "nonexistent"])
        assert result.exit_code != 0

    def test_同名冲突时提示使用repo格式(self, runner, project_with_two_repos):
        """同名框架冲突时应提示使用 repo/name 格式"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "install", "ximage"])
        assert result.exit_code != 0
        # 应包含冲突提示
        assert "ximage" in result.output

    @patch("driving_cli.commands.framework.clone_repository")
    def test_使用repo斜杠格式安装(self, mock_clone, runner, project_with_two_repos):
        """使用 repo/name 格式应安装到对应仓库的 submodules 目录"""
        mock_clone.return_value = None
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "install", "main/xstatic"])
        # clone_repository 应被调用，目标路径在 main 仓库的 submodules 下
        if mock_clone.called:
            call_args = mock_clone.call_args
            install_path = str(call_args[0][1])
            assert "main" in install_path
            assert "submodules" in install_path

    def test_本地框架跳过安装(self, runner, project_with_two_repos):
        """本地项目框架（__local__）应跳过安装"""
        # 在 main 仓库添加一个本地框架
        main_fw_dir = project_with_two_repos / "ai-driving" / "main" / "frameworks"
        gitlist = json.loads((main_fw_dir / "gitlist.json").read_text(encoding="utf-8"))
        gitlist.append({
            "name": "local-fw",
            "project_name": "__local__",
            "url": "__local__",
            "branch": "__local__",
            "module": "local",
            "sources": ["src/*"],
            "description": "本地框架",
            "creator": "测试",
            "date": "2024-01-01",
        })
        (main_fw_dir / "gitlist.json").write_text(json.dumps(gitlist, ensure_ascii=False), encoding="utf-8")

        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "install", "local-fw"])
        assert result.exit_code == 0
        assert "跳过" in result.output


# ==================== framework sources 命令测试 ====================


class TestFrameworkSources:
    """测试 framework sources 子命令"""

    def test_sources路径基于对应仓库submodules(self, runner, project_with_two_repos):
        """sources 路径应包含对应仓库名称和 submodules"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "xstatic"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # 路径应包含 main 仓库的 submodules 目录
        assert any("main" in s and "submodules" in s for s in data["sources"])

    def test_sources使用repo斜杠格式(self, runner, project_with_two_repos):
        """使用 repo/name 格式时路径应基于指定仓库"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "local-docs/ximage"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # 路径应包含 local-docs 仓库的 submodules 目录
        assert any("local-docs" in s and "submodules" in s for s in data["sources"])

    def test_sources输出不含内部字段(self, runner, project_with_two_repos):
        """sources 输出不应包含 _repo_name 等内部字段"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "xstatic"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_repo_name" not in data

    def test_sources同名冲突时报错(self, runner, project_with_two_repos):
        """同名框架冲突时应报错"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "ximage"])
        assert result.exit_code != 0

    def test_sources输出包含gitlist的categories(self, runner, project_with_two_repos):
        """gitlist 条目的 categories 字段应在 sources 输出中暴露，供文档生成注入"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "xstatic"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("categories") == ["ui-page"]

    def test_sources无categories字段时不输出(self, runner, project_with_two_repos):
        """gitlist 条目未配置 categories 时，sources 输出不含该字段"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "sources", "local-docs/ximage"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "categories" not in data


# ==================== framework checkout/pull 命令测试 ====================


class TestFrameworkCheckoutPull:
    """测试 framework checkout 和 pull 子命令"""

    def test_checkout未安装框架报错(self, runner, project_with_two_repos):
        """checkout 未安装的框架应报错"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "checkout", "xstatic", "develop"])
        assert result.exit_code != 0

    def test_pull未安装框架报错(self, runner, project_with_two_repos):
        """pull 未安装的框架应报错"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "pull", "xstatic"])
        assert result.exit_code != 0

    def test_checkout不存在框架报错(self, runner, project_with_two_repos):
        """checkout 不存在的框架应报错"""
        with patch("driving_cli.commands.framework.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["framework", "checkout", "nonexistent", "main"])
        assert result.exit_code != 0


# ==================== cli 集成测试 ====================


class TestFrameworkLoad:
    """测试 driving framework load 命令"""

    @pytest.fixture
    def project_with_framework_docs(self, tmp_path):
        """创建包含 FRAMEWORK.md 的项目结构"""
        config = {
            "version": "2",
            "repos": [
                {
                    "name": "main",
                    "type": "remote",
                    "url": "https://github.com/example/main",
                    "path": "ai-driving/main",
                    "local_path": None,
                },
            ],
            "default_commit_message": "update by driving",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        frameworks_dir = tmp_path / "ai-driving" / "main" / "frameworks"

        # xstatic：有 FRAMEWORK.md
        xstatic_dir = frameworks_dir / "xstatic"
        xstatic_dir.mkdir(parents=True)
        (xstatic_dir / "FRAMEWORK.md").write_text(
            "---\nname: xstatic\ndescription: Activity/Fragment 基础封装框架\n---\n# xstatic\n",
            encoding="utf-8",
        )

        # ximage：有 FRAMEWORK.md
        ximage_dir = frameworks_dir / "ximage"
        ximage_dir.mkdir(parents=True)
        (ximage_dir / "FRAMEWORK.md").write_text(
            "---\nname: ximage\ndescription: 图片加载框架\ncategory: ui-component\n---\n# ximage\n",
            encoding="utf-8",
        )

        # xnet：没有 FRAMEWORK.md，应被跳过
        xnet_dir = frameworks_dir / "xnet"
        xnet_dir.mkdir(parents=True)

        # gitlist.json（load 命令不依赖它，但保持目录完整）
        (frameworks_dir / "gitlist.json").write_text("[]", encoding="utf-8")

        return tmp_path

    def test_返回所有有文档的框架(self, runner, project_with_framework_docs):
        """load 应返回所有存在 FRAMEWORK.md 的框架"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [fw["name"] for fw in data["frameworks"]]
        assert "xstatic" in names
        assert "ximage" in names

    def test_跳过没有FRAMEWORK_md的目录(self, runner, project_with_framework_docs):
        """没有 FRAMEWORK.md 的目录应被跳过"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [fw["name"] for fw in data["frameworks"]]
        assert "xnet" not in names

    def test_返回字段包含name_description_path(self, runner, project_with_framework_docs):
        """每个框架条目应包含 name、description、path 三个字段"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fw in data["frameworks"]:
            assert "name" in fw
            assert "description" in fw
            assert "path" in fw

    def test_path为相对路径(self, runner, project_with_framework_docs):
        """path 字段应为相对路径，格式为 ai-driving/<repo>/frameworks/<name>"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for fw in data["frameworks"]:
            assert fw["path"].startswith("ai-driving/")
            assert not Path(fw["path"]).is_absolute()

    def test_指定框架名过滤(self, runner, project_with_framework_docs):
        """指定框架名时只返回该框架"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "xstatic"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["frameworks"]) == 1
        assert data["frameworks"][0]["name"] == "xstatic"

    def test_多个框架名同时匹配(self, runner, project_with_framework_docs):
        """传入多个框架名时返回所有匹配框架"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "xstatic", "ximage"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [fw["name"] for fw in data["frameworks"]]
        assert "xstatic" in names
        assert "ximage" in names
        assert len(data["frameworks"]) == 2

    def test_仓库名命中返回整个仓库(self, runner, project_with_framework_docs):
        """传入仓库名时返回该仓库下所有框架"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "main"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [fw["name"] for fw in data["frameworks"]]
        assert "xstatic" in names
        assert "ximage" in names

    def test_不存在的关键词返回空列表(self, runner, project_with_framework_docs):
        """不匹配任何框架或仓库时返回空列表（与 skill load 行为一致）"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "nonexistent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["frameworks"] == []

    def test_description从frontmatter读取(self, runner, project_with_framework_docs):
        """description 应从 YAML front-matter 中读取"""
        with runner.isolated_filesystem():
            import os
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "xstatic"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["frameworks"][0]["description"] == "Activity/Fragment 基础封装框架"

    def test_category字段从frontmatter读取(self, runner, project_with_framework_docs):
        with runner.isolated_filesystem():
            import os; os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        cat = {fw["name"]: fw["category"] for fw in data["frameworks"]}
        # category 归一化为列表：单值 → 单元素列表，缺失 → 空列表
        assert cat["ximage"] == ["ui-component"]
        assert cat["xstatic"] == []

    def test_category过滤只返回匹配项(self, runner, project_with_framework_docs):
        with runner.isolated_filesystem():
            import os; os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "--category", "ui-component"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [fw["name"] for fw in data["frameworks"]] == ["ximage"]

    def test_category过滤大小写不敏感(self, runner, project_with_framework_docs):
        with runner.isolated_filesystem():
            import os; os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "--category", "UI-COMPONENT"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [fw["name"] for fw in data["frameworks"]] == ["ximage"]

    def test_category无匹配返回空(self, runner, project_with_framework_docs):
        with runner.isolated_filesystem():
            import os; os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "load", "--category", "nope"])
        assert result.exit_code == 0
        assert json.loads(result.output)["frameworks"] == []

    def test_category与关键词组合过滤(self, runner, project_with_framework_docs):
        """关键词 + --category 取交集：先按关键词过滤，再按 category 过滤"""
        with runner.isolated_filesystem():
            import os; os.chdir(project_with_framework_docs)
            # ximage 命中关键词且 category=ui-component → 保留
            r1 = runner.invoke(cli, ["framework", "load", "ximage", "--category", "ui-component"])
            # xstatic 命中关键词但无 ui-component 分类 → 被 category 过滤掉
            r2 = runner.invoke(cli, ["framework", "load", "xstatic", "--category", "ui-component"])
        assert r1.exit_code == 0
        assert [fw["name"] for fw in json.loads(r1.output)["frameworks"]] == ["ximage"]
        assert r2.exit_code == 0
        assert json.loads(r2.output)["frameworks"] == []

    def test_categories命令列出分类描述与数量(self, runner, project_with_framework_docs):
        """framework categories 列出分类：名称+描述（来自 gitlist.json 注册表）+ 数量（扫描 frontmatter）"""
        import os
        # 在 main 仓库的 gitlist.json 写入新格式对象（含 categories 注册表）
        gitlist = project_with_framework_docs / "ai-driving" / "main" / "frameworks" / "gitlist.json"
        gitlist.write_text(
            json.dumps(
                {"gitlist": [], "categories": [{"name": "ui-component", "description": "UI 组件库"}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with runner.isolated_filesystem():
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "categories"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        cats = {c["name"]: c for c in data["categories"]}
        assert "ui-component" in cats
        assert cats["ui-component"]["description"] == "UI 组件库"
        assert cats["ui-component"]["count"] == 1  # 仅 ximage 标了 category

    def test_categories命令注册表为空时仍从frontmatter发现(self, runner, project_with_framework_docs):
        """没有注册表时，category 仍能从框架 frontmatter 扫描出来（描述为空）"""
        import os
        with runner.isolated_filesystem():
            os.chdir(project_with_framework_docs)
            result = runner.invoke(cli, ["framework", "categories"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        cats = {c["name"]: c for c in data["categories"]}
        assert "ui-component" in cats
        assert cats["ui-component"]["count"] == 1
        assert cats["ui-component"]["description"] == ""

    def test_category多值数组解析(self, runner, tmp_path):
        """FRAMEWORK.md 的 category 支持数组 [a, b]，归一化为列表"""
        import os

        config = {
            "version": "2",
            "repos": [{"name": "main", "type": "remote", "url": "u", "path": "ai-driving/main"}],
            "default_commit_message": "x",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        fw_dir = tmp_path / "ai-driving" / "main" / "frameworks" / "xmulti"
        fw_dir.mkdir(parents=True)
        (fw_dir / "FRAMEWORK.md").write_text(
            "---\nname: xmulti\ndescription: 多分类框架\ncategory: [ui-component, network]\n---\n# xmulti\n",
            encoding="utf-8",
        )
        with runner.isolated_filesystem():
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["framework", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        fw = {f["name"]: f for f in data["frameworks"]}["xmulti"]
        assert fw["category"] == ["ui-component", "network"]

    def test_多值category被任一分类命中(self, runner, tmp_path):
        """多分类框架可被其任一分类的 --category 过滤命中"""
        import os

        config = {
            "version": "2",
            "repos": [{"name": "main", "type": "remote", "url": "u", "path": "ai-driving/main"}],
            "default_commit_message": "x",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        fw_dir = tmp_path / "ai-driving" / "main" / "frameworks" / "xmulti"
        fw_dir.mkdir(parents=True)
        (fw_dir / "FRAMEWORK.md").write_text(
            "---\nname: xmulti\ndescription: 多分类框架\ncategory: [ui-component, network]\n---\n# xmulti\n",
            encoding="utf-8",
        )
        with runner.isolated_filesystem():
            os.chdir(tmp_path)
            r1 = runner.invoke(cli, ["framework", "load", "--category", "network"])
            r2 = runner.invoke(cli, ["framework", "load", "--category", "UI-COMPONENT"])
        assert [f["name"] for f in json.loads(r1.output)["frameworks"]] == ["xmulti"]
        assert [f["name"] for f in json.loads(r2.output)["frameworks"]] == ["xmulti"]

    def test_categories注册表从gitlist新格式读取(self, runner, tmp_path):
        """新格式 gitlist.json（对象 {gitlist, categories}）提供分类描述"""
        import os

        config = {
            "version": "2",
            "repos": [{"name": "main", "type": "remote", "url": "u", "path": "ai-driving/main"}],
            "default_commit_message": "x",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        frameworks_dir = tmp_path / "ai-driving" / "main" / "frameworks"
        fw_dir = frameworks_dir / "ximage"
        fw_dir.mkdir(parents=True)
        (fw_dir / "FRAMEWORK.md").write_text(
            "---\nname: ximage\ndescription: 图片框架\ncategory: ui-component\n---\n# ximage\n",
            encoding="utf-8",
        )
        # 新格式 gitlist.json：对象内含 gitlist 数组 + categories 注册表
        gitlist_obj = {
            "gitlist": [
                {"name": "ximage", "description": "图片框架", "project_name": "ximage"}
            ],
            "categories": [{"name": "ui-component", "description": "UI 组件库"}],
        }
        (frameworks_dir / "gitlist.json").write_text(
            json.dumps(gitlist_obj, ensure_ascii=False), encoding="utf-8"
        )
        with runner.isolated_filesystem():
            os.chdir(tmp_path)
            cat_result = runner.invoke(cli, ["framework", "categories"])
            list_result = runner.invoke(cli, ["framework", "list"])
        # categories 描述来自 gitlist.json
        assert cat_result.exit_code == 0
        cats = {c["name"]: c for c in json.loads(cat_result.output)["categories"]}
        assert cats["ui-component"]["description"] == "UI 组件库"
        assert cats["ui-component"]["count"] == 1
        # framework list 仍能从新格式对象的 gitlist 数组解析框架
        assert list_result.exit_code == 0
        names = [f["name"] for f in json.loads(list_result.output)["frameworks"]]
        assert "ximage" in names

    def test_gitlist旧数组格式仍兼容(self, runner, tmp_path):
        """旧格式 gitlist.json（纯数组）继续可被 framework list 解析"""
        import os

        config = {
            "version": "2",
            "repos": [{"name": "main", "type": "remote", "url": "u", "path": "ai-driving/main"}],
            "default_commit_message": "x",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        frameworks_dir = tmp_path / "ai-driving" / "main" / "frameworks"
        frameworks_dir.mkdir(parents=True)
        gitlist_arr = [{"name": "ximage", "description": "图片框架", "project_name": "ximage"}]
        (frameworks_dir / "gitlist.json").write_text(
            json.dumps(gitlist_arr, ensure_ascii=False), encoding="utf-8"
        )
        with runner.isolated_filesystem():
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["framework", "list"])
        assert result.exit_code == 0
        names = [f["name"] for f in json.loads(result.output)["frameworks"]]
        assert "ximage" in names


class TestCliIntegration:
    """测试 cli.py 中 framework 子命令组的挂载"""

    def test_framework_group已挂载到cli(self, runner):
        """framework 子命令组应已挂载到 cli"""
        result = runner.invoke(cli, ["framework", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "install" in result.output
        assert "checkout" in result.output
        assert "pull" in result.output
        assert "sources" in result.output
        assert "load" in result.output




# ==================== 属性测试（Property 6） ====================

from hypothesis import given, settings
from hypothesis import strategies as st


# 生成合法框架名称的策略（字母数字下划线，非空）
_fw_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
    min_size=1,
    max_size=20,
).filter(lambda s: s[0].isalnum())

# 生成单个框架 dict 的策略
def _make_framework_strategy(repo_name: str):
    return st.fixed_dictionaries({
        "name": _fw_name_strategy,
        "project_name": _fw_name_strategy,
        "url": st.just("https://github.com/example/repo"),
        "module": st.just("module"),
        "sources": st.lists(st.just("src/*"), min_size=0, max_size=2),
        "description": st.just("描述"),
        "creator": st.just("测试"),
        "date": st.just("2024-01-01"),
        "_repo_name": st.just(repo_name),
    })


@settings(max_examples=100)
@given(
    repo1_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True),
    repo2_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True),
    repo1_count=st.integers(min_value=0, max_value=5),
    repo2_count=st.integers(min_value=0, max_value=5),
)
def test_property6_框架列表聚合完整性(repo1_name, repo2_name, repo1_count, repo2_count):
    """Property 6：框架列表聚合完整性

    # Feature: multi-repo-support, Property 6: 框架列表聚合完整性
    对于任意包含若干仓库的配置，每个仓库有若干不重名的框架，
    Framework_Manager 聚合后返回的框架总数应等于所有仓库框架数之和，
    且每个框架的 _repo_name 字段正确标注来源仓库名称。

    **Validates: Requirements 5.1**
    """
    # 两个仓库名称相同时跳过（避免歧义）
    if repo1_name == repo2_name:
        return

    # 构造两个仓库各自的框架列表（名称不重复）
    def make_unique_frameworks(repo_name: str, count: int, prefix: str) -> List[Dict]:
        return [
            {
                "name": f"{prefix}-fw-{i}",
                "project_name": f"{prefix}-proj-{i}",
                "url": "https://github.com/example/repo",
                "module": "module",
                "sources": ["src/*"],
                "description": "描述",
                "creator": "测试",
                "date": "2024-01-01",
                "_repo_name": repo_name,
            }
            for i in range(count)
        ]

    repo1_frameworks = make_unique_frameworks(repo1_name, repo1_count, "r1")
    repo2_frameworks = make_unique_frameworks(repo2_name, repo2_count, "r2")
    all_frameworks = repo1_frameworks + repo2_frameworks

    # 验证聚合总数等于各仓库框架数之和
    assert len(all_frameworks) == repo1_count + repo2_count

    # 验证每个框架的 _repo_name 字段正确标注来源仓库
    for fw in repo1_frameworks:
        assert fw["_repo_name"] == repo1_name
    for fw in repo2_frameworks:
        assert fw["_repo_name"] == repo2_name

    # 验证通过名称可以正确区分来源仓库
    for fw in all_frameworks:
        matched = [f for f in all_frameworks if f["name"] == fw["name"]]
        # 每个框架名称在聚合列表中唯一（因为我们用了不同前缀）
        assert len(matched) == 1
        assert matched[0]["_repo_name"] == fw["_repo_name"]
