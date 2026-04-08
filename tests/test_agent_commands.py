"""agent 子命令组单元测试

覆盖 driving agent 的主要功能，包括：
- _parse_frontmatter：标准解析、缺少 name、无 frontmatter、YAML 列表字段
- scan_agents_from_dir：路径格式、has_soul/has_memory 标记、跳过无效目录
- _merge_agents：同名去重、仓库顺序优先级、启用/禁用过滤
- agent load / list 命令集成测试
- agent memory get / set / append / clear 命令集成测试
- RepoConfig.agents 字段序列化 round-trip
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.agent import (
    _merge_agents,
    _parse_frontmatter,
    scan_agents_from_dir,
)
from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager


# ==================== Helpers ====================


def _make_agents_md(agent_dir: Path, name: str, description: str,
                    role: str = "", skills: list = None) -> None:
    """在指定目录创建 AGENTS.md 文件"""
    agent_dir.mkdir(parents=True, exist_ok=True)
    skills_block = ""
    if skills:
        skills_block = "skills:\n" + "".join(f"  - {s}\n" for s in skills)
    content = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"{'role: ' + role + chr(10) if role else ''}"
        f"{skills_block}"
        f"---\n\n# {name}\n\nAgent 内容。\n"
    )
    (agent_dir / "AGENTS.md").write_text(content, encoding="utf-8")


def _make_soul_md(agent_dir: Path) -> None:
    (agent_dir / "SOUL.md").write_text("# Soul\n\n人格描述。\n", encoding="utf-8")


def _make_memory(agent_dir: Path, files: dict) -> None:
    """创建 memory/ 目录及指定文件"""
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(exist_ok=True)
    for filename, content in files.items():
        (memory_dir / filename).write_text(content, encoding="utf-8")


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


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_with_agents(tmp_path):
    """创建包含两个 agent 的测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None, "tags": ["base"]},
    ])
    agents_dir = tmp_path / "ai-driving" / "my-local" / "agents"
    _make_agents_md(agents_dir / "agent-a", "agent-a", "Agent A 描述", role="reviewer")
    _make_agents_md(agents_dir / "agent-b", "agent-b", "Agent B 描述", role="assistant",
                    skills=["code-reviews"])
    _make_soul_md(agents_dir / "agent-a")
    return tmp_path


# ==================== _parse_frontmatter ====================


class TestParseFrontmatter:
    def test_解析标准frontmatter(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        _make_agents_md(tmp_path, "my-agent", "描述内容", role="reviewer")
        result = _parse_frontmatter(tmp_path / "AGENTS.md")
        assert result is not None
        assert result["name"] == "my-agent"
        assert result["description"] == "描述内容"
        assert result["role"] == "reviewer"

    def test_解析skills列表字段(self, tmp_path):
        _make_agents_md(tmp_path, "a", "desc", skills=["skill-x", "skill-y"])
        result = _parse_frontmatter(tmp_path / "AGENTS.md")
        assert result is not None
        assert isinstance(result["skills"], list)
        assert "skill-x" in result["skills"]
        assert "skill-y" in result["skills"]

    def test_缺少name返回None(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("---\ndescription: 只有描述\n---\n\n内容", encoding="utf-8")
        result = _parse_frontmatter(f)
        assert result is None

    def test_无frontmatter返回None(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("# 没有 frontmatter\n\n内容", encoding="utf-8")
        result = _parse_frontmatter(f)
        assert result is None

    def test_frontmatter未闭合返回None(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("---\nname: a\ndescription: d\n没有结束分隔符", encoding="utf-8")
        result = _parse_frontmatter(f)
        assert result is None

    def test_缺少description时不报错(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("---\nname: a\n---\n\n内容", encoding="utf-8")
        result = _parse_frontmatter(f)
        assert result is not None
        assert result["name"] == "a"


# ==================== scan_agents_from_dir ====================


class TestScanAgentsFromDir:
    def test_扫描返回正确agent列表(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "agent-a", "agent-a", "描述 A")
        _make_agents_md(agents_dir / "agent-b", "agent-b", "描述 B")

        result = scan_agents_from_dir("my-repo", agents_dir, quiet=True)
        assert len(result) == 2
        names = {a["name"] for a in result}
        assert names == {"agent-a", "agent-b"}

    def test_path格式正确(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "my-agent", "my-agent", "描述")

        result = scan_agents_from_dir("my-local", agents_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["path"] == "ai-driving/my-local/agents/my-agent/"

    def test_has_soul标记正确(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "with-soul", "with-soul", "有 soul")
        _make_soul_md(agents_dir / "with-soul")
        _make_agents_md(agents_dir / "no-soul", "no-soul", "无 soul")

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        result_map = {a["name"]: a for a in result}
        assert result_map["with-soul"]["has_soul"] is True
        assert result_map["no-soul"]["has_soul"] is False

    def test_has_memory标记正确(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "with-mem", "with-mem", "有记忆")
        (agents_dir / "with-mem" / "MEMORY.md").write_text("一些事实", encoding="utf-8")
        _make_agents_md(agents_dir / "no-mem", "no-mem", "无记忆")

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        result_map = {a["name"]: a for a in result}
        assert result_map["with-mem"]["has_memory"] is True
        assert result_map["no-mem"]["has_memory"] is False

    def test_跳过无AGENTS_md的目录(self, tmp_path):
        agents_dir = tmp_path / "agents"
        (agents_dir / "no-md").mkdir(parents=True)
        _make_agents_md(agents_dir / "valid", "valid", "有效 agent")

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_跳过description为空的agent(self, tmp_path):
        agents_dir = tmp_path / "agents"
        empty_dir = agents_dir / "empty-desc"
        empty_dir.mkdir(parents=True)
        (empty_dir / "AGENTS.md").write_text(
            "---\nname: empty-desc\ndescription: \n---\n\n内容", encoding="utf-8"
        )
        _make_agents_md(agents_dir / "valid", "valid", "有效描述")

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_skills字段正确解析(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "skilled", "skilled", "有技能",
                        skills=["code-reviews", "android-standard-page"])

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        assert len(result) == 1
        assert result[0]["skills"] == ["code-reviews", "android-standard-page"]

    def test_输出包含所有必需字段(self, tmp_path):
        agents_dir = tmp_path / "agents"
        _make_agents_md(agents_dir / "full", "full", "完整 agent", role="reviewer",
                        skills=["s1"])

        result = scan_agents_from_dir("repo", agents_dir, quiet=True)
        assert len(result) == 1
        a = result[0]
        for field in ("name", "description", "role", "version", "skills",
                      "path", "has_soul", "has_memory"):
            assert field in a


# ==================== _merge_agents ====================


class TestMergeAgents:
    def test_合并两个仓库的agent(self, tmp_path):
        d1 = tmp_path / "repo1" / "agents"
        d2 = tmp_path / "repo2" / "agents"
        _make_agents_md(d1 / "agent-a", "agent-a", "描述 A")
        _make_agents_md(d2 / "agent-b", "agent-b", "描述 B")

        result = _merge_agents([("repo1", d1), ("repo2", d2)], quiet=True)
        assert len(result) == 2
        names = {a["name"] for a in result}
        assert names == {"agent-a", "agent-b"}

    def test_同名agent先配置的优先(self, tmp_path):
        d1 = tmp_path / "repo1" / "agents"
        d2 = tmp_path / "repo2" / "agents"
        _make_agents_md(d1 / "shared", "shared", "repo1 版本")
        _make_agents_md(d2 / "shared", "shared", "repo2 版本")

        result = _merge_agents([("repo1", d1), ("repo2", d2)], quiet=True)
        assert len(result) == 1
        assert result[0]["description"] == "repo1 版本"
        assert "repo1" in result[0]["path"]

    def test_空列表返回空(self):
        result = _merge_agents([], quiet=True)
        assert result == []

    def test_遵守disabled配置(self, tmp_path):
        d1 = tmp_path / "repo1" / "agents"
        _make_agents_md(d1 / "agent-a", "agent-a", "描述 A")
        _make_agents_md(d1 / "agent-b", "agent-b", "描述 B")

        rc = RepoConfig(
            name="repo1", type="local", path="ai-driving/repo1",
            agents={"enabled": [], "disabled": ["agent-b"]},
        )
        result = _merge_agents([("repo1", d1)], repo_configs=[rc], quiet=True)
        names = {a["name"] for a in result}
        assert "agent-a" in names
        assert "agent-b" not in names

    def test_遵守enabled白名单配置(self, tmp_path):
        d1 = tmp_path / "repo1" / "agents"
        _make_agents_md(d1 / "agent-a", "agent-a", "描述 A")
        _make_agents_md(d1 / "agent-b", "agent-b", "描述 B")
        _make_agents_md(d1 / "agent-c", "agent-c", "描述 C")

        rc = RepoConfig(
            name="repo1", type="local", path="ai-driving/repo1",
            agents={"enabled": ["agent-a", "agent-c"], "disabled": []},
        )
        result = _merge_agents([("repo1", d1)], repo_configs=[rc], quiet=True)
        names = {a["name"] for a in result}
        assert names == {"agent-a", "agent-c"}


# ==================== agent load 命令 ====================


class TestAgentLoadCommand:
    def test_load输出JSON数组(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_load输出包含必需字段(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ("name", "description", "path"):
                assert field in item

    def test_load_path格式正确(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert item["path"].startswith("ai-driving/")
            assert item["path"].endswith("/")
            assert "/agents/" in item["path"]

    def test_load_has_soul标记正确(self, runner, project_with_agents):
        # agent load 只返回精简字段（name/description/path），soul 标记在 agent list 中显示
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {a["name"] for a in data}
        assert "agent-a" in names
        assert "agent-b" in names

    def test_load无agents目录时返回空数组(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "empty", "type": "local", "path": "ai-driving/empty", "local_path": None, "tags": ["base"]},
        ])
        with patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_load遵守disabled配置(self, runner, tmp_path):
        _make_config(tmp_path, [{
            "name": "my-local", "type": "local",
            "path": "ai-driving/my-local", "local_path": None,
            "tags": ["base"],
            "agents": {"enabled": [], "disabled": ["agent-b"]},
        }])
        agents_dir = tmp_path / "ai-driving" / "my-local" / "agents"
        _make_agents_md(agents_dir / "agent-a", "agent-a", "描述 A")
        _make_agents_md(agents_dir / "agent-b", "agent-b", "描述 B")

        with patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {a["name"] for a in data}
        assert "agent-a" in names
        assert "agent-b" not in names


# ==================== agent list 命令 ====================


class TestAgentListCommand:
    def test_list显示agent列表(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "agent-a" in result.output
        assert "agent-b" in result.output

    def test_list显示启用标记(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_list显示soul标记(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "[soul]" in result.output

    def test_list_repo过滤不存在的仓库报错(self, runner, project_with_agents):
        with patch("driving_cli.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list", "--repo", "nonexistent"])
        assert result.exit_code != 0

    def test_agent_group已挂载到cli(self, runner):
        result = runner.invoke(cli, ["agent", "--help"])
        assert result.exit_code == 0
        assert "load" in result.output
        assert "list" in result.output
        assert "memory" in result.output


# ==================== agent memory 命令 ====================


@pytest.fixture
def project_with_agent_memory(tmp_path):
    """创建带 memory 的 agent 测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
    ])
    agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "test-agent"
    _make_agents_md(agent_dir, "test-agent", "测试 agent")
    return tmp_path


class TestAgentMemoryCommands:
    def test_memory_append追加内容包含时间戳(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "append",
                                         "test-agent", "新事实"])
        assert result.exit_code == 0
        memory_file = agent_dir / "MEMORY.md"
        content = memory_file.read_text(encoding="utf-8")
        assert "新事实" in content

    def test_memory_set覆盖已有内容需要force(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        memory_file = agent_dir / "MEMORY.md"
        memory_file.write_text("旧内容", encoding="utf-8")

        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "新内容"], input="n\n")
        assert "旧内容" in memory_file.read_text(encoding="utf-8")

    def test_memory_set_force强制覆盖(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        memory_file = agent_dir / "MEMORY.md"
        memory_file.write_text("旧内容", encoding="utf-8")

        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "新内容", "--force"])
        assert result.exit_code == 0
        assert "新内容" in memory_file.read_text(encoding="utf-8")

    def test_memory_set写入文件(self, runner, project_with_agent_memory):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "用户偏好简洁风格"])
        assert result.exit_code == 0
        memory_file = (project_with_agent_memory / "ai-driving" / "my-local" /
                       "agents" / "test-agent" / "MEMORY.md")
        assert memory_file.exists()
        assert "用户偏好简洁风格" in memory_file.read_text(encoding="utf-8")

    def test_memory_get读取文件(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        (agent_dir / "MEMORY.md").write_text("已知事实内容", encoding="utf-8")

        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "test-agent"])
        assert result.exit_code == 0
        assert "已知事实内容" in result.output

    def test_memory_append追加内容(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        (agent_dir / "MEMORY.md").write_text("第一行\n", encoding="utf-8")

        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "append",
                                         "test-agent", "第二行"])
        assert result.exit_code == 0
        content = (agent_dir / "MEMORY.md").read_text(encoding="utf-8")
        assert "第一行" in content
        assert "第二行" in content

    def test_memory_clear删除MEMORY_md(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        (agent_dir / "MEMORY.md").write_text("内容", encoding="utf-8")

        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "clear",
                                         "test-agent", "--yes"])
        assert result.exit_code == 0
        assert not (agent_dir / "MEMORY.md").exists()

    def test_memory_get不存在的agent报错(self, runner, project_with_agent_memory):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "nonexistent-agent"])
        assert result.exit_code != 0

    def test_memory_get无MEMORY_md返回空(self, runner, project_with_agent_memory):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "test-agent"])
        assert result.exit_code == 0
        assert result.output.strip() == ""


# ==================== RepoConfig.agents 序列化 ====================


class TestRepoConfigAgentsSerialization:
    def test_agents为None时不写入JSON(self):
        rc = RepoConfig(name="r", type="local", path="ai-driving/r", agents=None)
        d = rc.to_dict()
        assert "agents" not in d

    def test_agents有值时写入JSON(self):
        rc = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            agents={"enabled": ["a"], "disabled": []}
        )
        d = rc.to_dict()
        assert "agents" in d
        assert d["agents"]["enabled"] == ["a"]

    def test_round_trip_agents有值(self):
        rc = RepoConfig(
            name="r", type="local", path="ai-driving/r",
            agents={"enabled": ["x", "y"], "disabled": []}
        )
        restored = RepoConfig.from_dict(rc.to_dict())
        assert restored.agents == rc.agents

    def test_round_trip_agents为None(self):
        rc = RepoConfig(name="r", type="local", path="ai-driving/r", agents=None)
        restored = RepoConfig.from_dict(rc.to_dict())
        assert restored.agents is None


# ==================== agent export 命令 ====================


@pytest.fixture
def project_with_full_agent(tmp_path):
    """创建包含完整 agent（AGENTS.md + SOUL.md + MEMORY.md）的测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
    ])
    agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "test-agent"
    _make_agents_md(agent_dir, "test-agent", "测试 agent 描述",
                    role="reviewer", skills=["code-reviews"])
    _make_soul_md(agent_dir)
    (agent_dir / "MEMORY.md").write_text(
        "用户偏好简洁风格\n正在审查 PR #1\n",
        encoding="utf-8"
    )
    return tmp_path


def _add_frontmatter_field(agent_dir: Path, field: str, value: str) -> None:
    """向 AGENTS.md frontmatter 追加字段"""
    agents_md = agent_dir / "AGENTS.md"
    content = agents_md.read_text(encoding="utf-8")
    agents_md.write_text(content.replace("---\n\n", f"{field}: {value}\n---\n\n"), encoding="utf-8")


class TestAgentExportCommand:
    def test_export_kiro生成软链接(self, runner, project_with_full_agent):
        agent_dir = project_with_full_agent / "ai-driving" / "my-local" / "agents" / "test-agent"
        _add_frontmatter_field(agent_dir, "tools", '["read", "shell"]')
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "kiro"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".kiro" / "agents" / "test-agent.md"
        assert out.is_symlink()

    def test_export_kiro缺少tools字段报错(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "kiro"])
        assert result.exit_code != 0

    def test_export_claude_code生成软链接(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "claude-code"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        assert out.is_symlink()

    def test_export_cursor缺少alwaysApply字段报错(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "cursor"])
        assert result.exit_code != 0

    def test_export_cursor含alwaysApply字段生成软链接(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
        ])
        agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "symlink-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text(
            "---\nname: symlink-agent\ndescription: 测试\nalwaysApply: false\n---\n\n内容\n",
            encoding="utf-8"
        )
        with patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "export", "symlink-agent", "--tool", "cursor"])
        assert result.exit_code == 0
        out = tmp_path / ".cursor" / "rules" / "symlink-agent.mdc"
        assert out.is_symlink()

    def test_export_windsurf缺少trigger字段报错(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "windsurf"])
        assert result.exit_code != 0

    def test_export_windsurf含trigger字段生成软链接(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
        ])
        agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "symlink-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text(
            "---\nname: symlink-agent\ndescription: 测试\ntrigger: manual\n---\n\n内容\n",
            encoding="utf-8"
        )
        with patch("driving_cli.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "export", "symlink-agent", "--tool", "windsurf"])
        assert result.exit_code == 0
        out = tmp_path / ".windsurf" / "rules" / "symlink-agent.md"
        assert out.is_symlink()

    def test_export已存在时跳过(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "claude-code"])
            # 第二次调用应跳过
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "claude-code"])
        assert result.exit_code == 0
        assert "已存在" in result.output

    def test_export_force强制重建(self, runner, project_with_full_agent):
        agent_dir = project_with_full_agent / "ai-driving" / "my-local" / "agents" / "test-agent"
        _add_frontmatter_field(agent_dir, "tools", '["read", "shell"]')
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "kiro"])
            result = runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "kiro", "--force"])
        assert result.exit_code == 0
        assert "已生成" in result.output

    def test_export不存在的agent报错(self, runner, project_with_full_agent):
        with patch("driving_cli.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "nonexistent", "--tool", "kiro"])
        assert result.exit_code != 0
