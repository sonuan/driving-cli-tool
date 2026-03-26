"""Skill 子命令组

提供 `driving skill sync` 命令，扫描所有已安装仓库的 skills/ 目录并同步到 AGENTS.md。
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving.utils.config_manager import ConfigManager, find_project_root
from driving.utils.logger import log_error, log_info, log_success, log_warning

# 尝试导入 yaml，如果失败则使用简单解析器
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def parse_yaml_simple(yaml_content: str) -> Optional[Dict[str, str]]:
    """简化的 YAML 解析器，仅支持 name 和 description 字段

    Args:
        yaml_content: YAML 内容字符串

    Returns:
        Dict: 包含 name 和 description 的字典，如果解析失败则返回 None
    """
    result = {}
    lines = yaml_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # 跳过空行和注释
        if not line or line.startswith("#"):
            i += 1
            continue

        # 解析 name
        if line.startswith("name:"):
            value = line[5:].strip()
            result["name"] = value
            i += 1
            continue

        # 解析 description
        if line.startswith("description:"):
            value = line[12:].strip()

            # 单行 description
            if value and value != "|":
                result["description"] = value
                i += 1
                continue

            # 多行 description（使用 |）
            if value == "|":
                desc_lines = []
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if next_line.startswith("  ") or next_line.startswith("\t"):
                        desc_lines.append(next_line.strip())
                        i += 1
                    else:
                        break
                result["description"] = " ".join(desc_lines)
                continue

            # 空 description
            result["description"] = ""
            i += 1
            continue

        i += 1

    # 验证必需字段
    if "name" not in result:
        return None

    # 确保 description 存在（即使为空）
    if "description" not in result:
        result["description"] = ""

    return result


def parse_skill_yaml(skill_md_path: Path) -> Optional[Dict[str, str]]:
    """解析 SKILL.md 文件的 YAML 头信息

    Args:
        skill_md_path: SKILL.md 文件路径

    Returns:
        Dict: 包含 name 和 description 的字典，如果解析失败则返回 None
    """
    try:
        content = skill_md_path.read_text(encoding="utf-8")

        # 检查是否有 YAML 头
        if not content.startswith("---"):
            return None

        # 提取 YAML 头（在两个 --- 之间）
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        yaml_content = parts[1].strip()

        # 优先使用 PyYAML 解析
        if HAS_YAML:
            try:
                yaml_data = yaml.safe_load(yaml_content)

                if not yaml_data or "name" not in yaml_data:
                    return None

                return {
                    "name": yaml_data.get("name", ""),
                    "description": yaml_data.get("description", ""),
                }
            except Exception as e:
                log_warning(f"PyYAML 解析失败，尝试使用简化解析器: {e}")
                return parse_yaml_simple(yaml_content)
        else:
            return parse_yaml_simple(yaml_content)

    except Exception as e:
        log_warning(f"解析 {skill_md_path} 失败: {e}")
        return None


def scan_skills_from_dir(repo_name: str, skills_dir: Path) -> List[Dict[str, str]]:
    """扫描单个仓库的 skills 目录，返回技能列表

    每个技能的 location 字段为完整路径：ai-driving/<repo-name>/skills/<skill-name>/

    Args:
        repo_name: 仓库名称
        skills_dir: skills 目录路径

    Returns:
        List[Dict]: 技能列表，每个技能包含 name、description、location 字段
    """
    skills = []

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        # 跳过特殊目录
        if skill_dir.name in ["other", "__pycache__"]:
            continue

        # 查找 SKILL.md 文件
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            log_warning(f"跳过 {skill_dir.name}：未找到 SKILL.md 文件")
            continue

        # 解析 YAML 头
        skill_info = parse_skill_yaml(skill_md)
        if skill_info:
            # 检查 description 是否为空
            if not skill_info["description"] or not skill_info["description"].strip():
                log_warning(f"跳过技能 {skill_info['name']}：description 为空")
                continue

            # 设置完整路径作为 location
            skill_info["location"] = f"ai-driving/{repo_name}/skills/{skill_dir.name}/"
            skills.append(skill_info)
            log_info(f"发现技能: {skill_info['name']} (来自仓库 {repo_name})")
        else:
            log_warning(f"跳过 {skill_dir.name}：YAML 头信息不完整")

    return skills


def merge_skills_from_all_repos(
    skills_dirs: List[Tuple[str, Path]],
) -> List[Dict[str, str]]:
    """合并所有仓库的技能列表，同名技能按仓库顺序去重

    按配置文件中仓库顺序（先配置的优先），同名技能只保留第一个，并记录警告。

    Args:
        skills_dirs: [(repo_name, skills_dir_path), ...] 列表

    Returns:
        List[Dict]: 合并后的技能列表，每个技能包含 name、description、location 字段
    """
    merged: Dict[str, Dict[str, str]] = {}  # skill_name -> skill_info
    result: List[Dict[str, str]] = []

    for repo_name, skills_dir in skills_dirs:
        repo_skills = scan_skills_from_dir(repo_name, skills_dir)
        for skill in repo_skills:
            skill_name = skill["name"]
            if skill_name in merged:
                # 同名技能已存在，记录警告，跳过（先配置的优先）
                existing_location = merged[skill_name]["location"]
                log_warning(
                    f"技能 '{skill_name}' 在多个仓库中存在，"
                    f"使用 {existing_location}（跳过 {skill['location']}）"
                )
            else:
                merged[skill_name] = skill
                result.append(skill)

    return result


def generate_available_skills_content(skills: List[Dict[str, str]]) -> str:
    """生成 available_skills 标签内部的内容（不包含标签本身）

    Args:
        skills: 技能列表

    Returns:
        str: available_skills 标签内部的内容
    """
    # 按技能名称排序
    sorted_skills = sorted(skills, key=lambda x: x["name"])

    skills_content = ""
    for skill in sorted_skills:
        skills_content += f"""
<skill>
<name>{skill['name']}</name>
<description>{skill['description']}</description>
<location>{skill['location']}</location>
</skill>
"""

    return skills_content


def generate_full_skills_system_content(skills: List[Dict[str, str]]) -> str:
    """生成完整的 skills_system 标签内的内容

    Args:
        skills: 技能列表

    Returns:
        str: skills_system 标签内的完整内容
    """
    # 固定的 usage 部分
    usage_section = """<usage>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Load skill content from the path specified in <location>
- The skill content will load with detailed instructions on how to complete the task
- Base directory provided in output for resolving bundled resources (references/, scripts/, assets/)

Usage notes:
- Only use skills listed in <available_skills> below
- Do not reload a skill that is already loaded in your context
- Each skill invocation is stateless and independent
</usage>"""

    available_skills_inner = generate_available_skills_content(skills)
    available_skills = f"\n<available_skills>{available_skills_inner}\n</available_skills>"

    content = f"""
## Available Skills

<!-- SKILLS_TABLE_START -->
{usage_section}
{available_skills}
<!-- SKILLS_TABLE_END -->
"""

    return content


def update_agents_md(agents_md_path: Path, skills: List[Dict[str, str]]) -> None:
    """更新 AGENTS.md 文件中的 skills_system 部分

    Args:
        agents_md_path: AGENTS.md 文件路径
        skills: 技能列表
    """
    # 读取现有内容
    if agents_md_path.exists():
        original_content = agents_md_path.read_text(encoding="utf-8")
    else:
        original_content = """# AGENTS


"""

    # 检查是否存在 skills_system 标签
    skills_system_pattern = r'<skills_system priority="1">(.*?)</skills_system>'

    if re.search(skills_system_pattern, original_content, re.DOTALL):
        # 存在 skills_system 标签，只更新 available_skills 部分
        available_skills_pattern = r"\n<available_skills>.*?</available_skills>"

        new_available_skills_inner = generate_available_skills_content(skills)
        new_available_skills_full = (
            f"\n<available_skills>{new_available_skills_inner}\n</available_skills>"
        )

        if re.search(available_skills_pattern, original_content, re.DOTALL):
            new_content = re.sub(
                available_skills_pattern,
                new_available_skills_full,
                original_content,
                flags=re.DOTALL,
            )
        else:
            full_content = generate_full_skills_system_content(skills)
            new_content = re.sub(
                skills_system_pattern,
                f'<skills_system priority="1">{full_content}\n</skills_system>',
                original_content,
                flags=re.DOTALL,
            )
    else:
        # 不存在 skills_system 标签，插入完整内容
        full_content = generate_full_skills_system_content(skills)
        new_content = (
            original_content.rstrip()
            + f'\n\n<skills_system priority="1">{full_content}\n</skills_system>\n'
        )

    agents_md_path.write_text(new_content, encoding="utf-8")


@click.group(name="skill")
def skill_group():
    """Skill 管理命令组

    管理 driving 技能，支持扫描所有已安装仓库的 skills/ 目录并同步到 AGENTS.md。
    """
    pass


@skill_group.command(name="sync")
def skill_sync():
    """扫描所有仓库 skills/ 并同步到 AGENTS.md

    遍历 driving.config.json 中所有已安装仓库的 skills/ 目录，
    读取每个技能的 SKILL.md 文件的 YAML 头信息，
    然后更新 AGENTS.md 文件中的 <skills_system> 部分，保留其他内容不变。

    同名技能按仓库在配置文件中的顺序去重（先配置的优先）。
    <location> 字段为完整路径：ai-driving/<repo-name>/skills/<skill-name>/
    """
    try:
        # 在命令执行时输出 PyYAML 警告
        if not HAS_YAML:
            log_warning("PyYAML 未安装，将使用简化的 YAML 解析器")
            log_warning("建议安装 PyYAML 以获得更好的兼容性: pip3 install PyYAML")

        # 查找项目根目录并初始化 ConfigManager
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        # 获取所有仓库的 skills 目录
        skills_dirs = config_manager.get_all_skills_dirs()

        if not skills_dirs:
            log_error("未找到任何仓库的 skills 目录")
            log_info("请先执行 'driving repo install' 安装仓库")
            raise click.Abort()

        log_info(f"扫描 {len(skills_dirs)} 个仓库的 skills 目录...")

        # 合并所有仓库的技能列表（同名去重）
        skills = merge_skills_from_all_repos(skills_dirs)

        if not skills:
            log_warning("未找到任何有效的技能")
            return

        log_success(f"找到 {len(skills)} 个技能")

        # 确定 AGENTS.md 文件路径（在项目根目录）
        agents_md_path = project_root / "AGENTS.md"

        # 更新 AGENTS.md 文件
        update_agents_md(agents_md_path, skills)

        log_success(f"AGENTS.md 文件已更新: {agents_md_path}")
        log_info("")
        log_info("📝 技能列表：")
        for skill in skills:
            desc = (
                skill["description"][:50] + "..."
                if len(skill["description"]) > 50
                else skill["description"]
            )
            log_info(f"  - {skill['name']}: {desc}")
            log_info(f"    📁 {skill['location']}")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"同步技能列表失败: {e}")
        raise click.Abort()
