"""skill 子命令组单元测试

覆盖 driving skill sync 的主要功能，包括：
- 多仓库 skills 目录扫描
- 同名技能去重（按仓库顺序）
- location 字段路径生成
- AGENTS.md 更新逻辑
- 属性测试（Property 10）
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.skill import (
    generate_available_skills_content,
    merge_skills_from_all_repos,
    parse_skill_yaml,
    parse_yaml_simple,
    scan_skills_from_dir,
    update_agents_md,
)
from driving_cli.utils.config_manager import ConfigManager


# ==================== Fixtures ====================


@pytest.fixture
def runner():
    """Click 测试 runner"""
    return CliRunner()


def _make_skill_md(skill_dir: Path, name: str, description: str) -> None:
    """在指定目录创建 SKILL.md 文件"""
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"""---
name: {name}
description: {description}
---

# {name}

技能内容。
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


@pytest.fixture
def project_with_two_repos(tmp_path):
    """创建包含两个仓库的项目结构，每个仓库有独立的 skills 目录"""
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

    # main 仓库：两个技能
    _make_skill_md(
        tmp_path / "ai-driving" / "main" / "skills" / "code-review",
        "code-review",
        "代码审查技能，帮助发现代码问题",
    )
    _make_skill_md(
        tmp_path / "ai-driving" / "main" / "skills" / "refactor",
        "refactor",
        "代码重构技能，提升代码质量",
    )

    # local-docs 仓库：两个技能（其中 code-review 与 main 同名）
    _make_skill_md(
        tmp_path / "ai-driving" / "local-docs" / "skills" / "code-review",
        "code-review",
        "本地代码审查技能（应被 main 仓库覆盖）",
    )
    _make_skill_md(
        tmp_path / "ai-driving" / "local-docs" / "skills" / "doc-writer",
        "doc-writer",
        "文档编写技能，生成高质量文档",
    )

    return tmp_path


@pytest.fixture
def config_manager(project_with_two_repos):
    """返回指向测试项目的 ConfigManager"""
    return ConfigManager(project_with_two_repos)


# ==================== parse_yaml_simple 测试 ====================


class TestParseYamlSimple:
    """测试简化 YAML 解析器"""

    def test_解析基本name和description(self):
        yaml_content = "name: my-skill\ndescription: 这是描述"
        result = parse_yaml_simple(yaml_content)
        assert result is not None
        assert result["name"] == "my-skill"
        assert result["description"] == "这是描述"

    def test_缺少name时返回None(self):
        yaml_content = "description: 只有描述"
        result = parse_yaml_simple(yaml_content)
        assert result is None

    def test_缺少description时默认为空字符串(self):
        yaml_content = "name: my-skill"
        result = parse_yaml_simple(yaml_content)
        assert result is not None
        assert result["description"] == ""

    def test_多行description(self):
        yaml_content = "name: my-skill\ndescription: |\n  第一行\n  第二行"
        result = parse_yaml_simple(yaml_content)
        assert result is not None
        assert "第一行" in result["description"]
        assert "第二行" in result["description"]

    def test_跳过注释行(self):
        yaml_content = "# 注释\nname: my-skill\n# 另一个注释\ndescription: 描述"
        result = parse_yaml_simple(yaml_content)
        assert result is not None
        assert result["name"] == "my-skill"


# ==================== parse_skill_yaml 测试 ====================


class TestParseSkillYaml:
    """测试 SKILL.md YAML 头解析"""

    def test_解析标准SKILL_md(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        _make_skill_md(skill_dir, "my-skill", "技能描述")
        result = parse_skill_yaml(skill_dir / "SKILL.md")
        assert result is not None
        assert result["name"] == "my-skill"
        assert result["description"] == "技能描述"

    def test_无YAML头返回None(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# 没有 YAML 头的文件", encoding="utf-8")
        result = parse_skill_yaml(skill_md)
        assert result is None

    def test_不完整YAML头返回None(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription: 没有 name\n---\n内容", encoding="utf-8")
        result = parse_skill_yaml(skill_md)
        assert result is None


# ==================== scan_skills_from_dir 测试 ====================


class TestScanSkillsFromDir:
    """测试单仓库 skills 目录扫描"""

    def test_扫描返回正确技能列表(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _make_skill_md(skills_dir / "skill-a", "skill-a", "技能 A 描述")
        _make_skill_md(skills_dir / "skill-b", "skill-b", "技能 B 描述")

        result = scan_skills_from_dir("main", skills_dir)
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"skill-a", "skill-b"}

    def test_location字段为完整路径(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _make_skill_md(skills_dir / "my-skill", "my-skill", "描述")

        result = scan_skills_from_dir("main", skills_dir)
        assert len(result) == 1
        assert result[0]["path"] == "ai-driving/main/skills/my-skill/"

    def test_location路径包含仓库名(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _make_skill_md(skills_dir / "test-skill", "test-skill", "描述")

        result = scan_skills_from_dir("local-docs", skills_dir)
        assert result[0]["path"] == "ai-driving/local-docs/skills/test-skill/"

    def test_跳过无SKILL_md的目录(self, tmp_path):
        skills_dir = tmp_path / "skills"
        # 创建没有 SKILL.md 的目录
        (skills_dir / "no-skill-md").mkdir(parents=True)
        _make_skill_md(skills_dir / "valid-skill", "valid-skill", "有效技能")

        result = scan_skills_from_dir("main", skills_dir)
        assert len(result) == 1
        assert result[0]["name"] == "valid-skill"

    def test_跳过description为空的技能(self, tmp_path):
        skills_dir = tmp_path / "skills"
        # 创建 description 为空的技能
        skill_dir = skills_dir / "empty-desc"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: empty-desc\ndescription: \n---\n内容", encoding="utf-8"
        )
        _make_skill_md(skills_dir / "valid-skill", "valid-skill", "有效描述")

        result = scan_skills_from_dir("main", skills_dir)
        assert len(result) == 1
        assert result[0]["name"] == "valid-skill"

    def test_跳过特殊目录other(self, tmp_path):
        skills_dir = tmp_path / "skills"
        # 创建 other 目录（应被跳过）
        _make_skill_md(skills_dir / "other", "other-skill", "应被跳过")
        _make_skill_md(skills_dir / "real-skill", "real-skill", "真实技能")

        result = scan_skills_from_dir("main", skills_dir)
        assert len(result) == 1
        assert result[0]["name"] == "real-skill"


# ==================== merge_skills_from_all_repos 测试 ====================


class TestMergeSkillsFromAllRepos:
    """测试多仓库技能合并逻辑"""

    def test_合并两个仓库的技能(self, tmp_path):
        # 创建两个仓库的 skills 目录
        main_skills = tmp_path / "main" / "skills"
        local_skills = tmp_path / "local" / "skills"
        _make_skill_md(main_skills / "skill-a", "skill-a", "技能 A")
        _make_skill_md(local_skills / "skill-b", "skill-b", "技能 B")

        result = merge_skills_from_all_repos([("main", main_skills), ("local", local_skills)])
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"skill-a", "skill-b"}

    def test_同名技能先配置的优先(self, tmp_path):
        """同名技能应保留先配置仓库的版本"""
        main_skills = tmp_path / "main" / "skills"
        local_skills = tmp_path / "local" / "skills"
        _make_skill_md(main_skills / "code-review", "code-review", "main 版本描述")
        _make_skill_md(local_skills / "code-review", "code-review", "local 版本描述")

        result = merge_skills_from_all_repos([("main", main_skills), ("local", local_skills)])
        assert len(result) == 1
        assert result[0]["description"] == "main 版本描述"
        assert result[0]["path"] == "ai-driving/main/skills/code-review/"

    def test_同名技能后配置的被跳过(self, tmp_path):
        """后配置仓库的同名技能应被跳过，location 应指向先配置的仓库"""
        main_skills = tmp_path / "main" / "skills"
        local_skills = tmp_path / "local" / "skills"
        _make_skill_md(main_skills / "shared", "shared", "main 版本")
        _make_skill_md(local_skills / "shared", "shared", "local 版本")

        result = merge_skills_from_all_repos([("main", main_skills), ("local", local_skills)])
        assert len(result) == 1
        assert "main" in result[0]["path"]

    def test_空仓库列表返回空列表(self):
        result = merge_skills_from_all_repos([])
        assert result == []

    def test_合并后技能总数不超过各仓库之和(self, tmp_path):
        """合并后技能总数 <= 各仓库技能数之和（同名去重）"""
        main_skills = tmp_path / "main" / "skills"
        local_skills = tmp_path / "local" / "skills"
        _make_skill_md(main_skills / "skill-a", "skill-a", "技能 A")
        _make_skill_md(main_skills / "skill-b", "skill-b", "技能 B")
        _make_skill_md(local_skills / "skill-b", "skill-b", "技能 B 重复")
        _make_skill_md(local_skills / "skill-c", "skill-c", "技能 C")

        result = merge_skills_from_all_repos([("main", main_skills), ("local", local_skills)])
        # main 有 2 个，local 有 2 个，但 skill-b 重复，合并后应有 3 个
        assert len(result) == 3
        assert len(result) <= 2 + 2  # 不超过各仓库之和


# ==================== generate_available_skills_content 测试 ====================


class TestGenerateAvailableSkillsContent:
    """测试 available_skills 内容生成"""

    def test_生成包含技能名称和描述(self):
        skills = [
            {"name": "skill-a", "description": "描述 A", "path": "ai-driving/main/skills/skill-a/"},
        ]
        content = generate_available_skills_content(skills)
        assert "skill-a" in content
        assert "描述 A" in content
        assert "ai-driving/main/skills/skill-a/" in content

    def test_location字段出现在输出中(self):
        skills = [
            {"name": "my-skill", "description": "描述", "path": "ai-driving/repo/skills/my-skill/"},
        ]
        content = generate_available_skills_content(skills)
        assert "<path>ai-driving/repo/skills/my-skill/</path>" in content

    def test_技能按名称排序(self):
        skills = [
            {"name": "z-skill", "description": "Z 技能", "path": "ai-driving/main/skills/z-skill/"},
            {"name": "a-skill", "description": "A 技能", "path": "ai-driving/main/skills/a-skill/"},
        ]
        content = generate_available_skills_content(skills)
        # a-skill 应在 z-skill 之前
        assert content.index("a-skill") < content.index("z-skill")


# ==================== update_agents_md 测试 ====================


class TestUpdateAgentsMd:
    """测试 AGENTS.md 更新逻辑"""

    def test_新建AGENTS_md时插入skills_system(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        skills = [
            {"name": "skill-a", "description": "描述 A", "path": "ai-driving/main/skills/skill-a/"},
        ]
        update_agents_md(agents_md, skills)
        content = agents_md.read_text(encoding="utf-8")
        assert "skills_system" in content
        assert "skill-a" in content
        assert "ai-driving/main/skills/skill-a/" in content

    def test_更新已有skills_system标签(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            '# AGENTS\n\n<skills_system priority="1">\n<available_skills>\n<skill><name>old</name></skill>\n</available_skills>\n</skills_system>\n',
            encoding="utf-8",
        )
        skills = [
            {"name": "new-skill", "description": "新技能", "path": "ai-driving/main/skills/new-skill/"},
        ]
        update_agents_md(agents_md, skills)
        content = agents_md.read_text(encoding="utf-8")
        assert "new-skill" in content
        # 旧技能应被替换
        assert "<name>old</name>" not in content

    def test_保留AGENTS_md其他内容(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# AGENTS\n\n## 其他内容\n\n保留这段文字。\n", encoding="utf-8")
        skills = [
            {"name": "skill-a", "description": "描述", "path": "ai-driving/main/skills/skill-a/"},
        ]
        update_agents_md(agents_md, skills)
        content = agents_md.read_text(encoding="utf-8")
        assert "保留这段文字。" in content
        assert "skill-a" in content

    def test_location字段写入AGENTS_md(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        skills = [
            {"name": "my-skill", "description": "描述", "path": "ai-driving/repo/skills/my-skill/"},
        ]
        update_agents_md(agents_md, skills)
        content = agents_md.read_text(encoding="utf-8")
        assert "ai-driving/repo/skills/my-skill/" in content


# ==================== skill sync 命令集成测试 ====================


class TestSkillSyncCommand:
    """测试 skill sync 子命令"""

    def test_sync成功更新AGENTS_md(self, runner, project_with_two_repos):
        """skill sync 应成功扫描并更新 AGENTS.md"""
        with patch("driving.commands.skill.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["skill", "sync"])
        assert result.exit_code == 0
        agents_md = project_with_two_repos / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert "code-review" in content
        assert "refactor" in content
        assert "doc-writer" in content

    def test_sync同名技能只保留先配置仓库(self, runner, project_with_two_repos):
        """code-review 在 main 和 local-docs 都有，应只保留 main 的版本"""
        with patch("driving.commands.skill.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["skill", "sync"])
        assert result.exit_code == 0
        agents_md = project_with_two_repos / "AGENTS.md"
        content = agents_md.read_text(encoding="utf-8")
        # location 应指向 main 仓库
        assert "ai-driving/main/skills/code-review/" in content
        # local-docs 的 code-review 不应出现
        assert "ai-driving/local-docs/skills/code-review/" not in content

    def test_sync_location字段为完整路径(self, runner, project_with_two_repos):
        """location 字段应为 ai-driving/<repo-name>/skills/<skill-name>/ 格式"""
        with patch("driving.commands.skill.find_project_root", return_value=project_with_two_repos):
            result = runner.invoke(cli, ["skill", "sync"])
        assert result.exit_code == 0
        agents_md = project_with_two_repos / "AGENTS.md"
        content = agents_md.read_text(encoding="utf-8")
        # 验证完整路径格式
        assert "ai-driving/main/skills/refactor/" in content
        assert "ai-driving/local-docs/skills/doc-writer/" in content

    def test_无skills目录时报错(self, runner, tmp_path):
        """没有任何 skills 目录时应报错"""
        config = {
            "version": "2",
            "repos": [],
            "default_commit_message": "",
            "update_version_url": "",
        }
        (tmp_path / "driving.config.json").write_text(json.dumps(config))
        with patch("driving.commands.skill.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["skill", "sync"])
        assert result.exit_code != 0

    def test_skill_group已挂载到cli(self, runner):
        """skill 子命令组应已挂载到 cli"""
        result = runner.invoke(cli, ["skill", "--help"])
        assert result.exit_code == 0
        assert "sync" in result.output


# ==================== 属性测试（Property 10） ====================

from hypothesis import given, settings
from hypothesis import strategies as st


# 生成合法技能名称的策略
_skill_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=20,
).filter(lambda s: s[0].isalpha())

# 生成合法仓库名称的策略
_repo_name_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True)


@settings(max_examples=100)
@given(
    repo1_name=_repo_name_strategy,
    repo2_name=_repo_name_strategy,
    repo1_skill_names=st.lists(_skill_name_strategy, min_size=0, max_size=5, unique=True),
    repo2_skill_names=st.lists(_skill_name_strategy, min_size=0, max_size=5, unique=True),
)
def test_property10_skill合并路径标注(
    tmp_path_factory, repo1_name, repo2_name, repo1_skill_names, repo2_skill_names
):
    """Property 10：Skill 列表合并保留路径标注

    # Feature: multi-repo-support, Property 10: Skill 列表合并保留路径标注
    对于任意来自多个仓库的技能列表，Skill_Manager 合并后，
    每个技能的 location 字段应等于该技能在文件系统中的完整路径
    （ai-driving/<repo-name>/skills/<skill-name>/），
    且合并后的技能总数不超过各仓库技能数之和（同名技能按优先级去重）。

    **Validates: Requirements 6.2, 6.3**
    """
    # 两个仓库名称相同时跳过（避免歧义）
    if repo1_name == repo2_name:
        return

    tmp_path = tmp_path_factory.mktemp("skill_test")

    # 创建两个仓库的 skills 目录
    repo1_skills_dir = tmp_path / repo1_name / "skills"
    repo2_skills_dir = tmp_path / repo2_name / "skills"

    for skill_name in repo1_skill_names:
        _make_skill_md(repo1_skills_dir / skill_name, skill_name, f"{skill_name} 描述")

    for skill_name in repo2_skill_names:
        _make_skill_md(repo2_skills_dir / skill_name, skill_name, f"{skill_name} 描述")

    # 执行合并
    skills_dirs = []
    if repo1_skill_names:
        skills_dirs.append((repo1_name, repo1_skills_dir))
    if repo2_skill_names:
        skills_dirs.append((repo2_name, repo2_skills_dir))

    result = merge_skills_from_all_repos(skills_dirs)

    # 验证：合并后技能总数不超过各仓库技能数之和
    total_input = len(repo1_skill_names) + len(repo2_skill_names)
    assert len(result) <= total_input

    # 验证：每个技能的 location 字段格式正确
    for skill in result:
        location = skill["path"]
        # location 必须以 ai-driving/ 开头
        assert location.startswith("ai-driving/")
        # location 必须以 / 结尾
        assert location.endswith("/")
        # location 必须包含 /skills/
        assert "/skills/" in location
        # location 格式：ai-driving/<repo-name>/skills/<skill-name>/
        parts = location.split("/")
        assert parts[0] == "ai-driving"
        assert parts[2] == "skills"
        assert len(parts) == 5  # ['ai-driving', repo_name, 'skills', skill_name, '']

    # 验证：同名技能只出现一次
    skill_names = [s["name"] for s in result]
    assert len(skill_names) == len(set(skill_names))

    # 验证：同名技能优先使用先配置仓库（repo1 优先于 repo2）
    common_names = set(repo1_skill_names) & set(repo2_skill_names)
    for name in common_names:
        matched = [s for s in result if s["name"] == name]
        assert len(matched) == 1
        # 应来自 repo1（先配置的）
        assert matched[0]["path"] == f"ai-driving/{repo1_name}/skills/{name}/"
