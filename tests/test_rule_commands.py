"""rule 子命令组单元测试

覆盖 driving rule load / rule list 的主要功能，包括：
- parse_rule_yaml：完整 frontmatter、缺少 name、无 frontmatter、content 提取
- scan_rules_from_dir：location 格式、跳过无效文件
- filter_rules_by_config：rules=None（全量）、白名单、黑名单
- RepoConfig.rules 字段序列化 round-trip（Property 8）
- rule 输出字段完整性（Property 5）
- content 不含 frontmatter（Property 6）
- 规则启用/禁用过滤正确性（Property 7）
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.rule import (
    filter_rules_by_config,
    parse_rule_yaml,
    scan_rules_from_dir,
)
from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager


# ==================== Helpers ====================


def _make_rule_md(path: Path, name: str, description: str = "", body: str = "") -> None:
    """在指定路径创建带 YAML frontmatter 的规则 .md 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\n"
    if description:
        content += f"description: {description}\n"
    content += f"---\n\n{body}"
    path.write_text(content, encoding="utf-8")


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


# ==================== parse_rule_yaml ====================


class TestParseRuleYaml:
    def test_完整frontmatter解析(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\nname: my-rule\ndescription: 规则描述\n---\n\n正文内容", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is not None
        assert result["name"] == "my-rule"
        assert result["description"] == "规则描述"

    def test_content提取正确(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\nname: r\ndescription: d\n---\n\n# 标题\n\n正文", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is not None
        assert "# 标题" in result["content"]
        assert "正文" in result["content"]

    def test_content不含frontmatter分隔符(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\nname: r\n---\n\n正文", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is not None
        # content 不应包含 frontmatter 的 --- 分隔符行
        assert result["content"].strip() == "正文"

    def test_缺少name返回None(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\ndescription: 只有描述\n---\n\n正文", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is None

    def test_无frontmatter返回None(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("# 没有 frontmatter 的文件\n\n内容", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is None

    def test_缺少description时默认空字符串(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\nname: r\n---\n\n正文", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is not None
        assert result["description"] == ""

    def test_frontmatter未闭合返回None(self, tmp_path):
        f = tmp_path / "rule.md"
        f.write_text("---\nname: r\ndescription: d\n正文（没有结束 ---）", encoding="utf-8")
        result = parse_rule_yaml(f)
        assert result is None


# ==================== scan_rules_from_dir ====================


class TestScanRulesFromDir:
    def test_扫描返回正确规则列表(self, tmp_path):
        rules_dir = tmp_path / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "描述 A", "正文 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "描述 B", "正文 B")

        result = scan_rules_from_dir("my-repo", rules_dir)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"rule-a", "rule-b"}

    def test_location格式正确(self, tmp_path):
        rules_dir = tmp_path / "rules"
        _make_rule_md(rules_dir / "nav.md", "navigation", "导航规则", "内容")

        result = scan_rules_from_dir("my-local", rules_dir)
        assert len(result) == 1
        assert result[0]["path"] == "ai-driving/my-local/rules/nav.md"

    def test_location包含仓库名(self, tmp_path):
        rules_dir = tmp_path / "rules"
        _make_rule_md(rules_dir / "code.md", "code-rules", "代码规则", "内容")

        result = scan_rules_from_dir("driving", rules_dir)
        assert result[0]["path"].startswith("ai-driving/driving/")

    def test_跳过无frontmatter文件(self, tmp_path):
        rules_dir = tmp_path / "rules"
        # 无 frontmatter 的文件
        (rules_dir / "no-fm.md").parent.mkdir(parents=True, exist_ok=True)
        (rules_dir / "no-fm.md").write_text("# 没有 frontmatter", encoding="utf-8")
        _make_rule_md(rules_dir / "valid.md", "valid-rule", "有效规则", "内容")

        result = scan_rules_from_dir("repo", rules_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["name"] == "valid-rule"

    def test_跳过缺少name的文件(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "no-name.md").write_text(
            "---\ndescription: 没有 name\n---\n\n内容", encoding="utf-8"
        )
        _make_rule_md(rules_dir / "valid.md", "valid-rule", "有效", "内容")

        result = scan_rules_from_dir("repo", rules_dir, quiet=True)
        assert len(result) == 1

    def test_跳过非md文件(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "readme.txt").write_text("文本文件", encoding="utf-8")
        _make_rule_md(rules_dir / "rule.md", "my-rule", "规则", "内容")

        result = scan_rules_from_dir("repo", rules_dir, quiet=True)
        assert len(result) == 1

    def test_输出包含content字段(self, tmp_path):
        rules_dir = tmp_path / "rules"
        _make_rule_md(rules_dir / "r.md", "r", "desc", "这是正文内容")

        result = scan_rules_from_dir("repo", rules_dir, quiet=True)
        assert len(result) == 1
        assert "content" in result[0]
        assert "这是正文内容" in result[0]["content"]


# ==================== filter_rules_by_config ====================


class TestFilterRulesByConfig:
    def _make_rules(self, names):
        return [{"name": n, "description": "", "path": f"ai-driving/r/rules/{n}.md", "content": ""} for n in names]

    def _make_repo_config(self, rules_cfg):
        return RepoConfig(name="repo", type="local", path="ai-driving/repo", rules=rules_cfg)

    def test_rules为None时返回全部(self):
        rules = self._make_rules(["a", "b", "c"])
        rc = self._make_repo_config(None)
        result = filter_rules_by_config(rules, rc)
        assert len(result) == 3

    def test_白名单模式只返回enabled中的规则(self):
        rules = self._make_rules(["a", "b", "c"])
        rc = self._make_repo_config({"enabled": ["a", "c"], "disabled": []})
        result = filter_rules_by_config(rules, rc)
        assert {r["name"] for r in result} == {"a", "c"}

    def test_黑名单模式排除disabled中的规则(self):
        rules = self._make_rules(["a", "b", "c"])
        rc = self._make_repo_config({"enabled": [], "disabled": ["b"]})
        result = filter_rules_by_config(rules, rc)
        assert {r["name"] for r in result} == {"a", "c"}

    def test_enabled和disabled都为空时返回全部(self):
        rules = self._make_rules(["a", "b"])
        rc = self._make_repo_config({"enabled": [], "disabled": []})
        result = filter_rules_by_config(rules, rc)
        assert len(result) == 2

    def test_白名单优先于黑名单(self):
        """enabled 非空时，disabled 被忽略"""
        rules = self._make_rules(["a", "b", "c"])
        rc = self._make_repo_config({"enabled": ["a"], "disabled": ["a", "b"]})
        result = filter_rules_by_config(rules, rc)
        # enabled 非空，白名单模式，只返回 a
        assert {r["name"] for r in result} == {"a"}

    def test_白名单中不存在的规则被忽略(self):
        rules = self._make_rules(["a", "b"])
        rc = self._make_repo_config({"enabled": ["a", "x"], "disabled": []})
        result = filter_rules_by_config(rules, rc)
        assert {r["name"] for r in result} == {"a"}


# ==================== RepoConfig.rules 序列化 ====================


class TestRepoConfigRulesSerialization:
    def test_rules为None时不写入JSON(self):
        rc = RepoConfig(name="r", type="local", path="ai-driving/r", rules=None)
        d = rc.to_dict()
        assert "rules" not in d

    def test_rules有值时写入JSON(self):
        rc = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            rules={"enabled": ["a"], "disabled": []}
        )
        d = rc.to_dict()
        assert "rules" in d
        assert d["rules"]["enabled"] == ["a"]

    def test_round_trip_rules有值(self):
        rc = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            rules={"enabled": ["x", "y"], "disabled": []}
        )
        restored = RepoConfig.from_dict(rc.to_dict())
        assert restored.rules == rc.rules

    def test_round_trip_rules为None(self):
        rc = RepoConfig(name="r", type="local", path="ai-driving/r", rules=None)
        restored = RepoConfig.from_dict(rc.to_dict())
        assert restored.rules is None


# ==================== CLI 集成测试 ====================


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_with_rules(tmp_path):
    """创建包含规则文件的测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None, "tags": ["base"]},
    ])
    rules_dir = tmp_path / "ai-driving" / "my-local" / "rules"
    _make_rule_md(rules_dir / "rule-a.md", "rule-a", "规则 A 描述", "规则 A 正文")
    _make_rule_md(rules_dir / "rule-b.md", "rule-b", "规则 B 描述", "规则 B 正文")
    return tmp_path


class TestRuleLoadCommand:
    def test_load输出JSON数组(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_load输出包含必需字段(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert "name" in item
            assert "description" in item
            assert "path" in item
            assert "content" not in item  # rule load 不返回正文

    def test_load_location格式正确(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert item["path"].startswith("ai-driving/")
            assert item["path"].endswith(".md")

    def test_load无规则目录时返回空数组(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "empty-repo", "type": "local", "path": "ai-driving/empty-repo", "local_path": None},
        ])
        with patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["rule", "load"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_load遵守黑名单配置(self, runner, tmp_path):
        _make_config(tmp_path, [
            {
                "name": "my-local", "type": "local",
                "path": "ai-driving/my-local", "local_path": None,
                "tags": ["base"],
                "rules": {"enabled": [], "disabled": ["rule-b"]},
            },
        ])
        rules_dir = tmp_path / "ai-driving" / "my-local" / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "A", "正文 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "B", "正文 B")

        with patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["rule", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {r["name"] for r in data}
        assert "rule-a" in names
        assert "rule-b" not in names

    def test_带关键词时忽略enabled白名单(self, runner, tmp_path):
        _make_config(tmp_path, [
            {
                "name": "my-local", "type": "local",
                "path": "ai-driving/my-local", "local_path": None,
                "tags": ["base"],
                "rules": {"enabled": ["rule-a"], "disabled": []},
            },
        ])
        rules_dir = tmp_path / "ai-driving" / "my-local" / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "A", "正文 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "B", "正文 B")

        with patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["rule", "load", "rule-b"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {r["name"] for r in data}
        assert "rule-b" in names

    def test_带关键词时忽略disabled黑名单(self, runner, tmp_path):
        _make_config(tmp_path, [
            {
                "name": "my-local", "type": "local",
                "path": "ai-driving/my-local", "local_path": None,
                "tags": ["base"],
                "rules": {"enabled": [], "disabled": ["rule-b"]},
            },
        ])
        rules_dir = tmp_path / "ai-driving" / "my-local" / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "A", "正文 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "B", "正文 B")

        with patch("driving_cli.commands.rule.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["rule", "load", "rule-b"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {r["name"] for r in data}
        assert "rule-b" in names


class TestRuleListCommand:
    def test_list显示规则列表(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "list"])
        assert result.exit_code == 0
        assert "rule-a" in result.output
        assert "rule-b" in result.output

    def test_list显示启用标记(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "list"])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_list_repo过滤不存在的仓库报错(self, runner, project_with_rules):
        with patch("driving_cli.commands.rule.find_project_root", return_value=project_with_rules):
            result = runner.invoke(cli, ["rule", "list", "--repo", "nonexistent"])
        assert result.exit_code != 0

    def test_rule_group已挂载到cli(self, runner):
        result = runner.invoke(cli, ["rule", "--help"])
        assert result.exit_code == 0
        assert "load" in result.output
        assert "list" in result.output


# ==================== manifest.json 支持 rules 配置测试 ====================


class TestRuleManifestFallback:
    """测试 manifest.json rules 字段作为仓库级默认值"""

    def _make_project(self, tmp_path, config_rules=None):
        repos_entry = {
            "name": "main", "type": "remote",
            "url": "https://example.com/main",
            "path": "ai-driving/main", "local_path": None, "tags": ["base"],
        }
        if config_rules is not None:
            repos_entry["rules"] = config_rules
        _make_config(tmp_path, [repos_entry])
        rules_dir = tmp_path / "ai-driving" / "main" / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "规则 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "规则 B")
        _make_rule_md(rules_dir / "rule-c.md", "rule-c", "规则 C")
        return tmp_path

    def test_manifest_enabled白名单生效(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        manifest = {"rules": {"enabled": ["rule-a"], "disabled": []}}
        (project / "ai-driving" / "main" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            result = runner.invoke(cli, ["rule", "load"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "rule-a"

    def test_manifest_disabled黑名单生效(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        manifest = {"rules": {"enabled": [], "disabled": ["rule-b"]}}
        (project / "ai-driving" / "main" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            result = runner.invoke(cli, ["rule", "load"])
        data = json.loads(result.output)
        names = {r["name"] for r in data}
        assert "rule-b" not in names
        assert {"rule-a", "rule-c"} == names

    def test_config优先级高于manifest(self, runner, tmp_path):
        project = self._make_project(tmp_path, config_rules={"enabled": ["rule-c"], "disabled": []})
        manifest = {"rules": {"enabled": ["rule-a"], "disabled": []}}
        (project / "ai-driving" / "main" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            result = runner.invoke(cli, ["rule", "load"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "rule-c"

    def test_list只读模式感知manifest(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        manifest = {"rules": {"enabled": [], "disabled": ["rule-b"]}}
        (project / "ai-driving" / "main" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            result = runner.invoke(cli, ["rule", "list"])
        assert "[✗] rule-b" in result.output
        assert "[✓] rule-a" in result.output


class TestRuleEditSaveMode:
    """测试 rule list --edit 保存模式"""

    def _make_project(self, tmp_path, config_rules=None):
        repos_entry = {
            "name": "main", "type": "remote",
            "url": "https://example.com/main",
            "path": "ai-driving/main", "local_path": None, "tags": ["base"],
        }
        if config_rules is not None:
            repos_entry["rules"] = config_rules
        _make_config(tmp_path, [repos_entry])
        rules_dir = tmp_path / "ai-driving" / "main" / "rules"
        _make_rule_md(rules_dir / "rule-a.md", "rule-a", "规则 A")
        _make_rule_md(rules_dir / "rule-b.md", "rule-b", "规则 B")
        _make_rule_md(rules_dir / "rule-c.md", "rule-c", "规则 C")
        return tmp_path

    def _fake_dialog(self, checked):
        def fake(**kwargs):
            class R:
                def run(self): return checked
            return R()
        return fake

    def test_auto_开启少时写enabled(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            with patch("prompt_toolkit.shortcuts.checkboxlist_dialog",
                       side_effect=self._fake_dialog(["rule-a"])):
                runner.invoke(cli, ["rule", "list", "--edit"])
        from driving_cli.utils.config_manager import ConfigManager
        cfg = ConfigManager(project).get_repo("main")
        assert cfg.rules["enabled"] == ["rule-a"]
        assert cfg.rules["disabled"] == []

    def test_auto_禁用少时写disabled(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            with patch("prompt_toolkit.shortcuts.checkboxlist_dialog",
                       side_effect=self._fake_dialog(["rule-a", "rule-b"])):
                runner.invoke(cli, ["rule", "list", "--edit"])
        from driving_cli.utils.config_manager import ConfigManager
        cfg = ConfigManager(project).get_repo("main")
        assert cfg.rules["disabled"] == ["rule-c"]
        assert cfg.rules["enabled"] == []

    def test_mode_enable强制写enabled(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            with patch("prompt_toolkit.shortcuts.checkboxlist_dialog",
                       side_effect=self._fake_dialog(["rule-a", "rule-b"])):
                runner.invoke(cli, ["rule", "list", "--edit", "--mode", "enable"])
        from driving_cli.utils.config_manager import ConfigManager
        cfg = ConfigManager(project).get_repo("main")
        assert sorted(cfg.rules["enabled"]) == ["rule-a", "rule-b"]
        assert cfg.rules["disabled"] == []

    def test_mode_disable强制写disabled(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            with patch("prompt_toolkit.shortcuts.checkboxlist_dialog",
                       side_effect=self._fake_dialog(["rule-a"])):
                runner.invoke(cli, ["rule", "list", "--edit", "--mode", "disable"])
        from driving_cli.utils.config_manager import ConfigManager
        cfg = ConfigManager(project).get_repo("main")
        assert cfg.rules["disabled"] == ["rule-b", "rule-c"]
        assert cfg.rules["enabled"] == []

    def test_全选时清空rules(self, runner, tmp_path):
        project = self._make_project(tmp_path)
        with patch("driving_cli.commands.rule.find_project_root", return_value=project):
            with patch("prompt_toolkit.shortcuts.checkboxlist_dialog",
                       side_effect=self._fake_dialog(["rule-a", "rule-b", "rule-c"])):
                runner.invoke(cli, ["rule", "list", "--edit"])
        from driving_cli.utils.config_manager import ConfigManager
        cfg = ConfigManager(project).get_repo("main")
        assert cfg.rules is None


# ==================== 属性测试 ====================

from hypothesis import given, settings
from hypothesis import strategies as st

_rule_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=20,
).filter(lambda s: s[0].isalpha())

_repo_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True)

_description_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _-",
    min_size=0,
    max_size=50,
)

_body_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 \n#",
    min_size=0,
    max_size=100,
).filter(lambda s: not s.startswith("---"))


# Feature: feature-and-rule-commands, Property 5: rule 输出字段完整性
@settings(max_examples=100)
@given(
    repo_name=_repo_name_st,
    rule_names=st.lists(_rule_name_st, min_size=1, max_size=5, unique=True),
    descriptions=st.lists(_description_st, min_size=1, max_size=5),
    bodies=st.lists(_body_st, min_size=1, max_size=5),
)
def test_property5_rule输出字段完整性(
    tmp_path_factory, repo_name, rule_names, descriptions, bodies
):
    """Property 5: rule 输出字段完整性

    对于任意包含有效 YAML frontmatter 的规则文件，scan_rules_from_dir 的输出中
    每条记录都应包含 name、description、location、content 四个字段，
    且 location 格式为 ai-driving/{repo}/rules/{name}.md。

    **Validates: Requirements 2.3, 2.4**
    """
    tmp_path = tmp_path_factory.mktemp("prop5")
    rules_dir = tmp_path / "rules"

    for i, name in enumerate(rule_names):
        desc = descriptions[i] if i < len(descriptions) else ""
        body = bodies[i] if i < len(bodies) else ""
        _make_rule_md(rules_dir / f"{name}.md", name, desc, body)

    result = scan_rules_from_dir(repo_name, rules_dir, quiet=True)

    assert len(result) == len(rule_names)
    for item in result:
        assert "name" in item
        assert "description" in item
        assert "path" in item
        assert "content" in item
        # location 格式验证
        assert item["path"].startswith(f"ai-driving/{repo_name}/rules/")
        assert item["path"].endswith(".md")


# Feature: feature-and-rule-commands, Property 6: content 不含 frontmatter
@settings(max_examples=100)
@given(
    name=_rule_name_st,
    description=_description_st,
    body=_body_st,
)
def test_property6_content不含frontmatter(tmp_path_factory, name, description, body):
    """Property 6: content 不含 frontmatter

    对于任意包含 YAML frontmatter 的规则文件，parse_rule_yaml 解析出的 content
    字段不应包含 --- 分隔符和 frontmatter 内容，只包含 frontmatter 之后的 markdown 正文。

    **Validates: Requirements 2.5**
    """
    tmp_path = tmp_path_factory.mktemp("prop6")
    f = tmp_path / "rule.md"
    _make_rule_md(f, name, description, body)

    result = parse_rule_yaml(f)
    assert result is not None

    content = result["content"]
    # content 不应包含 frontmatter 中的字段行
    assert f"name: {name}" not in content
    # content 不应以 --- 开头
    assert not content.startswith("---")
    # 如果 body 非空，content 应包含 body
    if body.strip():
        assert body.strip() in content


# Feature: feature-and-rule-commands, Property 7: 规则启用/禁用过滤正确性
@settings(max_examples=100)
@given(
    rule_names=st.lists(_rule_name_st, min_size=0, max_size=8, unique=True),
    enabled=st.lists(_rule_name_st, min_size=0, max_size=4, unique=True),
    disabled=st.lists(_rule_name_st, min_size=0, max_size=4, unique=True),
)
def test_property7_规则过滤正确性(rule_names, enabled, disabled):
    """Property 7: 规则启用/禁用过滤正确性

    对于任意规则列表和仓库配置：
    - 当 rules=None 时，filter_rules_by_config 返回全部规则
    - 当 enabled 非空时，返回结果是 enabled 列表与全集的交集
    - 当 enabled 为空且 disabled 非空时，返回结果是全集减去 disabled 列表

    **Validates: Requirements 2.6, 4.2, 4.3, 4.4**
    """
    rules = [
        {"name": n, "description": "", "path": f"ai-driving/r/rules/{n}.md", "content": ""}
        for n in rule_names
    ]
    rule_name_set = set(rule_names)

    # Case 1: rules=None → 返回全部
    rc_none = RepoConfig(name="r", type="local", path="ai-driving/r", rules=None)
    result_none = filter_rules_by_config(rules, rc_none)
    assert len(result_none) == len(rules)

    # Case 2: enabled 非空 → 白名单
    if enabled:
        rc_wl = RepoConfig(name="r", type="local", path="ai-driving/r",
                           rules={"enabled": enabled, "disabled": []})
        result_wl = filter_rules_by_config(rules, rc_wl)
        result_names = {r["name"] for r in result_wl}
        expected = rule_name_set & set(enabled)
        assert result_names == expected

    # Case 3: enabled 为空，disabled 非空 → 黑名单
    if disabled:
        rc_bl = RepoConfig(name="r", type="local", path="ai-driving/r",
                           rules={"enabled": [], "disabled": disabled})
        result_bl = filter_rules_by_config(rules, rc_bl)
        result_names = {r["name"] for r in result_bl}
        expected = rule_name_set - set(disabled)
        assert result_names == expected


# Feature: feature-and-rule-commands, Property 8: RepoConfig rules 字段序列化 round-trip
@settings(max_examples=100)
@given(
    enabled=st.lists(_rule_name_st, min_size=0, max_size=5, unique=True),
    disabled=st.lists(_rule_name_st, min_size=0, max_size=5, unique=True),
    use_none=st.booleans(),
)
def test_property8_repoconfig_rules_round_trip(enabled, disabled, use_none):
    """Property 8: RepoConfig rules 字段序列化 round-trip

    对于任意包含 rules 字段的 RepoConfig 对象，执行 to_dict() 再 from_dict()
    应得到等价的对象；当 rules=None 时，to_dict() 的结果不应包含 rules 键。

    **Validates: Requirements 4.1, 4.5**
    """
    rules_val = None if use_none else {"enabled": enabled, "disabled": disabled}
    rc = RepoConfig(name="test-repo", type="local", path="ai-driving/test-repo", rules=rules_val)

    d = rc.to_dict()

    if use_none:
        assert "rules" not in d
    else:
        assert "rules" in d

    restored = RepoConfig.from_dict(d)
    assert restored.rules == rc.rules
    assert restored.name == rc.name
