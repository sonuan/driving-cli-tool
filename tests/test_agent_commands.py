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
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
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
        _make_memory(agents_dir / "with-mem", {"facts.md": "一些事实"})
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
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_load输出包含必需字段(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ("name", "description", "role", "skills",
                          "path", "has_soul", "has_memory"):
                assert field in item

    def test_load_path格式正确(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            assert item["path"].startswith("ai-driving/")
            assert item["path"].endswith("/")
            assert "/agents/" in item["path"]

    def test_load_has_soul标记正确(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        agent_map = {a["name"]: a for a in data}
        assert agent_map["agent-a"]["has_soul"] is True
        assert agent_map["agent-b"]["has_soul"] is False

    def test_load无agents目录时返回空数组(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "empty", "type": "local", "path": "ai-driving/empty", "local_path": None},
        ])
        with patch("driving.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_load遵守disabled配置(self, runner, tmp_path):
        _make_config(tmp_path, [{
            "name": "my-local", "type": "local",
            "path": "ai-driving/my-local", "local_path": None,
            "agents": {"enabled": [], "disabled": ["agent-b"]},
        }])
        agents_dir = tmp_path / "ai-driving" / "my-local" / "agents"
        _make_agents_md(agents_dir / "agent-a", "agent-a", "描述 A")
        _make_agents_md(agents_dir / "agent-b", "agent-b", "描述 B")

        with patch("driving.commands.agent.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["agent", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = {a["name"] for a in data}
        assert "agent-a" in names
        assert "agent-b" not in names


# ==================== agent list 命令 ====================


class TestAgentListCommand:
    def test_list显示agent列表(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "agent-a" in result.output
        assert "agent-b" in result.output

    def test_list显示启用标记(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_list显示soul标记(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
            result = runner.invoke(cli, ["agent", "list"])
        assert result.exit_code == 0
        assert "[soul]" in result.output

    def test_list_repo过滤不存在的仓库报错(self, runner, project_with_agents):
        with patch("driving.commands.agent.find_project_root", return_value=project_with_agents):
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
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "append",
                                         "test-agent", "facts", "新事实"])
        assert result.exit_code == 0
        facts_file = agent_dir / "memory" / "facts.md"
        content = facts_file.read_text(encoding="utf-8")
        assert "新事实" in content
        assert "<!--" in content
        assert "-->" in content

    def test_memory_set覆盖已有内容需要force(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"context.md": "旧内容"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "context", "新内容"], input="n\n")
        context_file = agent_dir / "memory" / "context.md"
        assert "旧内容" in context_file.read_text(encoding="utf-8")

    def test_memory_set_force强制覆盖(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"context.md": "旧内容"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "context", "新内容", "--force"])
        assert result.exit_code == 0
        context_file = agent_dir / "memory" / "context.md"
        content = context_file.read_text(encoding="utf-8")
        assert "新内容" in content
        assert "<!--" in content

    def test_memory_set写入文件(self, runner, project_with_agent_memory):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "set",
                                         "test-agent", "facts", "用户偏好简洁风格"])
        assert result.exit_code == 0
        facts_file = (project_with_agent_memory / "ai-driving" / "my-local" /
                      "agents" / "test-agent" / "memory" / "facts.md")
        assert facts_file.exists()
        assert "用户偏好简洁风格" in facts_file.read_text(encoding="utf-8")

    def test_memory_get读取文件(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"facts.md": "已知事实内容"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "test-agent", "facts"])
        assert result.exit_code == 0
        assert "已知事实内容" in result.output

    def test_memory_get无key时返回JSON(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"facts.md": "事实", "context.md": "上下文"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "test-agent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "facts" in data
        assert "context" in data

    def test_memory_append追加内容(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"facts.md": "第一行\n"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "append",
                                         "test-agent", "facts", "第二行"])
        assert result.exit_code == 0
        facts_file = agent_dir / "memory" / "facts.md"
        content = facts_file.read_text(encoding="utf-8")
        assert "第一行" in content
        assert "第二行" in content

    def test_memory_clear指定key删除文件(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"facts.md": "内容", "context.md": "上下文"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "clear",
                                         "test-agent", "facts", "--yes"])
        assert result.exit_code == 0
        assert not (agent_dir / "memory" / "facts.md").exists()
        assert (agent_dir / "memory" / "context.md").exists()

    def test_memory_clear全部删除memory目录(self, runner, project_with_agent_memory):
        agent_dir = (project_with_agent_memory / "ai-driving" / "my-local" /
                     "agents" / "test-agent")
        _make_memory(agent_dir, {"facts.md": "内容", "context.md": "上下文"})

        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "clear", "test-agent", "--yes"])
        assert result.exit_code == 0
        assert not (agent_dir / "memory").exists()

    def test_memory_get不存在的agent报错(self, runner, project_with_agent_memory):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "nonexistent-agent"])
        assert result.exit_code != 0

    def test_memory_get无memory目录返回空JSON(self, runner, project_with_agent_memory):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get", "test-agent"])
        assert result.exit_code == 0
        assert json.loads(result.output) == {}

    def test_memory_get不存在的key返回空字符串(self, runner, project_with_agent_memory):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_agent_memory):
            result = runner.invoke(cli, ["agent", "memory", "get",
                                         "test-agent", "nonexistent"])
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
    """创建包含完整 agent（AGENTS.md + SOUL.md + memory）的测试项目"""
    _make_config(tmp_path, [
        {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
    ])
    agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "test-agent"
    _make_agents_md(agent_dir, "test-agent", "测试 agent 描述",
                    role="reviewer", skills=["code-reviews"])
    _make_soul_md(agent_dir)
    _make_memory(agent_dir, {
        "facts.md": "<!-- 2026-04-02T10:00:00+08:00 | user -->\n用户偏好简洁风格\n",
        "context.md": "<!-- 2026-04-02T11:00:00+08:00 | user -->\n正在审查 PR #1\n",
    })
    return tmp_path


class TestAgentExportCommand:
    def test_export_kiro生成json文件(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent",
                                         "--tool", "kiro", "--no-memory"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".kiro" / "agents" / "test-agent.json"
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["name"] == "test-agent"
        assert "prompt" in data
        assert data["prompt"].startswith("file://")

    def test_export_claude_code生成md文件(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent",
                                         "--tool", "claude-code", "--no-memory"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        assert out.exists()
        # --no-memory 时应为软链接
        assert out.is_symlink()

    def test_export_claude_code带记忆生成独立文件(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent",
                                         "--tool", "claude-code"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        assert out.exists()
        # 有记忆时应为独立文件，不是软链接
        assert not out.is_symlink()
        content = out.read_text(encoding="utf-8")
        assert "测试 agent 描述" in content

    def test_export_cursor生成mdc文件(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent",
                                         "--tool", "cursor", "--no-memory"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".cursor" / "rules" / "test-agent.mdc"
        assert out.exists()
        # test-agent 的 AGENTS.md 没有 alwaysApply 字段，降级为独立文件
        assert not out.is_symlink()
        content = out.read_text(encoding="utf-8")
        assert "alwaysApply: false" in content

    def test_export_windsurf生成md文件(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "test-agent",
                                         "--tool", "windsurf", "--no-memory"])
        assert result.exit_code == 0
        out = project_with_full_agent / ".windsurf" / "rules" / "test-agent.md"
        assert out.exists()
        # test-agent 的 AGENTS.md 没有 trigger 字段，降级为独立文件
        assert not out.is_symlink()
        content = out.read_text(encoding="utf-8")
        assert "trigger: manual" in content

    def test_export_cursor含alwaysApply字段时生成软链接(self, runner, tmp_path):
        """AGENTS.md 含 alwaysApply 字段时，cursor export 生成软链接"""
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
        ])
        agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "symlink-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text(
            "---\nname: symlink-agent\ndescription: 测试\nalwaysApply: false\n---\n\n内容\n",
            encoding="utf-8"
        )
        runner_inst = CliRunner()
        with patch("driving.commands.agent.find_project_root", return_value=tmp_path):
            result = runner_inst.invoke(cli, ["agent", "export", "symlink-agent",
                                              "--tool", "cursor", "--no-memory"])
        assert result.exit_code == 0
        out = tmp_path / ".cursor" / "rules" / "symlink-agent.mdc"
        assert out.is_symlink()

    def test_export_windsurf含trigger字段时生成软链接(self, runner, tmp_path):
        """AGENTS.md 含 trigger 字段时，windsurf export 生成软链接"""
        _make_config(tmp_path, [
            {"name": "my-local", "type": "local", "path": "ai-driving/my-local", "local_path": None},
        ])
        agent_dir = tmp_path / "ai-driving" / "my-local" / "agents" / "symlink-agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text(
            "---\nname: symlink-agent\ndescription: 测试\ntrigger: manual\n---\n\n内容\n",
            encoding="utf-8"
        )
        runner_inst = CliRunner()
        with patch("driving.commands.agent.find_project_root", return_value=tmp_path):
            result = runner_inst.invoke(cli, ["agent", "export", "symlink-agent",
                                              "--tool", "windsurf", "--no-memory"])
        assert result.exit_code == 0
        out = tmp_path / ".windsurf" / "rules" / "symlink-agent.md"
        assert out.is_symlink()

    def test_export包含soul内容(self, runner, project_with_full_agent):
        # soul 内容只在独立文件（带记忆）模式下嵌入
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "claude-code"])
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        content = out.read_text(encoding="utf-8")
        assert "Soul" in content

    def test_export包含memory内容(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent",
                                "--tool", "claude-code"])
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        content = out.read_text(encoding="utf-8")
        assert "背景知识" in content
        assert "用户偏好简洁风格" in content

    def test_export_no_memory不包含记忆(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent",
                                "--tool", "claude-code", "--no-memory"])
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        content = out.read_text(encoding="utf-8")
        assert "背景知识" not in content
        assert "用户偏好简洁风格" not in content

    def test_export_kiro包含agentSpawn_hook(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent", "--tool", "kiro"])
        out = project_with_full_agent / ".kiro" / "agents" / "test-agent.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "hooks" in data
        assert "agentSpawn" in data["hooks"]
        assert any("memory get" in h["command"] for h in data["hooks"]["agentSpawn"])

    def test_export_kiro_no_memory也含hook(self, runner, project_with_full_agent):
        # Kiro 始终通过 agentSpawn hook 动态注入记忆，--no-memory 不影响 hook
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent",
                                "--tool", "kiro", "--no-memory"])
        out = project_with_full_agent / ".kiro" / "agents" / "test-agent.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "hooks" in data
        assert "agentSpawn" in data["hooks"]

    def test_export不存在的agent报错(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            result = runner.invoke(cli, ["agent", "export", "nonexistent",
                                         "--tool", "kiro"])
        assert result.exit_code != 0

    def test_export_claude_code包含关联技能(self, runner, project_with_full_agent):
        with patch("driving.commands.agent.find_project_root",
                   return_value=project_with_full_agent):
            runner.invoke(cli, ["agent", "export", "test-agent",
                                "--tool", "claude-code", "--no-memory"])
        out = project_with_full_agent / ".claude" / "agents" / "test-agent.md"
        content = out.read_text(encoding="utf-8")
        assert "code-reviews" in content
