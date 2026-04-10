"""refine 子命令组单元测试

覆盖 driving refine list / refine load 的主要功能：
- _parse_refine_frontmatter：完整 frontmatter、缺少 target_type、无 frontmatter
- _scan_refines：type_filter 过滤、文件名匹配
- refine list：按类型分组展示、--type 过滤、--repo 过滤
- refine load：全量输出、name 模糊匹配、--type 过滤、返回字段完整性
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.refine import _parse_refine_frontmatter, _scan_refines


# ==================== Helpers ====================


def _make_refine_md(
    path: Path,
    target_type: str = "skill",
    target_name: str = "test-skill",
    description: str = "测试描述",
    status: str = "pending",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n"
        f"date: 2026-04-10\n"
        f"target_type: {target_type}\n"
        f"target_name: {target_name}\n"
        f"target_file: ai-driving/driving/skills/{target_name}/SKILL.md\n"
        f"description: {description}\n"
        f"operator: test\n"
        f"status: {status}\n"
        f"---\n\n# 变更内容\n\n测试内容\n",
        encoding="utf-8",
    )


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


# ==================== _parse_refine_frontmatter ====================


class TestParseRefineFrontmatter:
    def test_完整frontmatter解析(self, tmp_path):
        f = tmp_path / "refine.md"
        _make_refine_md(f, target_type="skill", target_name="my-skill", description="测试")
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["target_type"] == "skill"
        assert result["target_name"] == "my-skill"
        assert result["description"] == "测试"
        assert result["status"] == "pending"

    def test_缺少target_type返回None(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text("---\ndate: 2026-04-10\nstatus: pending\n---\n\n内容", encoding="utf-8")
        assert _parse_refine_frontmatter(f) is None

    def test_无frontmatter返回None(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text("# 普通 markdown\n\n没有 frontmatter", encoding="utf-8")
        assert _parse_refine_frontmatter(f) is None

    def test_description缺失时返回空字符串(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text(
            "---\ndate: 2026-04-10\ntarget_type: rule\ntarget_name: x\nstatus: pending\n---\n",
            encoding="utf-8",
        )
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["description"] == ""


# ==================== _scan_refines ====================


class TestScanRefines:
    def test_扫描返回正确条目(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo")
        _make_refine_md(tmp_path / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar")
        items = _scan_refines("driving", tmp_path)
        assert len(items) == 2

    def test_type_filter过滤(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md", target_type="skill")
        _make_refine_md(tmp_path / "2026-04-10-rule-bar.md", target_type="rule")
        items = _scan_refines("driving", tmp_path, type_filter="skill")
        assert len(items) == 1
        assert items[0]["target_type"] == "skill"

    def test_path字段格式正确(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md")
        items = _scan_refines("my-repo", tmp_path)
        assert items[0]["path"] == "ai-driving/my-repo/refines/2026-04-10-skill-foo.md"

    def test_跳过非md文件(self, tmp_path):
        (tmp_path / "notes.txt").write_text("not a refine", encoding="utf-8")
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md")
        items = _scan_refines("driving", tmp_path)
        assert len(items) == 1


# ==================== driving refine list ====================


class TestRefineList:
    def _setup(self, tmp_path):
        _make_config(tmp_path, [{"name": "driving", "type": "local", "path": "ai-driving/driving"}])
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        _make_refine_md(refines_dir / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo", description="技能描述")
        _make_refine_md(refines_dir / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar", description="规则描述")
        return tmp_path

    def test_列出所有refine(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "list"])
        assert result.exit_code == 0
        assert "skill" in result.output
        assert "rule" in result.output
        assert "共 2 条 refine" in result.output

    def test_type过滤只显示skill(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "list", "--type", "skill"])
        assert result.exit_code == 0
        assert "skill" in result.output
        assert "rule" not in result.output
        assert "共 1 条 refine" in result.output

    def test_description显示在输出中(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "list"])
        # description 字段应出现在输出中（非空）
        assert "(pending)" in result.output
        # 输出中应包含 description 内容（不只是 target_name）
        lines = [l for l in result.output.splitlines() if "(pending)" in l]
        assert len(lines) > 0
        for line in lines:
            parts = line.strip().split("  ")
            assert len(parts) >= 3  # date, target_name, description, status


# ==================== driving refine load ====================


class TestRefineLoad:
    def _setup(self, tmp_path):
        _make_config(tmp_path, [{"name": "driving", "type": "local", "path": "ai-driving/driving"}])
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        _make_refine_md(refines_dir / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo", description="技能描述")
        _make_refine_md(refines_dir / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar", description="规则描述")
        return tmp_path

    def test_全量输出两条(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    def test_返回字段完整(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "load"])
        data = json.loads(result.output)
        for item in data:
            assert "name" in item
            assert "description" in item
            assert "path" in item

    def test_name模糊匹配(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "load", "skill"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert "skill" in data[0]["name"]

    def test_type过滤(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "load", "--type", "rule"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert "rule" in data[0]["name"]

    def test_无匹配返回空数组(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "load", "nonexistent"])
        data = json.loads(result.output)
        assert data == []
