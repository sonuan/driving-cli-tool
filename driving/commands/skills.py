"""Skills 管理命令"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import click

from driving.utils.config import is_local_mode
from driving.utils.logger import log_error, log_info, log_success, log_warning

# 尝试导入 yaml，如果失败则使用简单解析器
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    # 警告信息延迟到实际使用时输出，避免影响 JSON 输出


def parse_yaml_simple(yaml_content: str) -> Optional[Dict[str, str]]:
    """简化的 YAML 解析器，仅支持 name 和 description 字段

    支持的格式：
    1. name: value
    2. description: value
    3. description: |
         multiline
         value

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

            # 多行 description (使用 |)
            if value == "|":
                desc_lines = []
                i += 1
                # 读取缩进的行
                while i < len(lines):
                    next_line = lines[i]
                    # 如果是缩进的行，添加到 description
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


def find_skills_dir() -> Optional[Path]:
    """查找 ai-docs/skills 目录

    Returns:
        Path: skills 目录路径，如果不存在则返回 None
    """
    current_dir = Path.cwd()

    # 本地模式：直接在当前目录查找
    if is_local_mode():
        skills_dir = current_dir / "ai-docs" / "skills"
        if skills_dir.exists():
            return skills_dir
        return None

    # 标准模式：在 ai-driving 目录查找
    driving_dir = current_dir / "ai-driving"
    if driving_dir.exists():
        skills_dir = driving_dir / "ai-docs" / "skills"
        if skills_dir.exists():
            return skills_dir

    return None


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
                # 降级到简化解析器
                return parse_yaml_simple(yaml_content)
        else:
            # 使用简化解析器
            return parse_yaml_simple(yaml_content)

    except Exception as e:
        log_warning(f"解析 {skill_md_path} 失败: {e}")
        return None


def scan_skills(skills_dir: Path) -> List[Dict[str, str]]:
    """扫描 skills 目录下的所有技能

    Args:
        skills_dir: skills 目录路径

    Returns:
        List[Dict]: 技能列表，每个技能包含 name 和 description（仅包含 description 不为空的技能）
    """
    skills = []
    skipped_empty_desc = []

    # 遍历 skills 目录下的所有子目录
    for skill_dir in skills_dir.iterdir():
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
                skipped_empty_desc.append(skill_info["name"])
                log_warning(f"跳过技能 {skill_info['name']}：description 为空")
                continue

            skills.append(skill_info)
            log_info(f"发现技能: {skill_info['name']}")
        else:
            log_warning(f"跳过 {skill_dir.name}：YAML 头信息不完整")

    # 汇总跳过的技能
    if skipped_empty_desc:
        log_info("")
        log_info(f"⚠️  跳过 {len(skipped_empty_desc)} 个 description 为空的技能:")
        for name in skipped_empty_desc:
            log_info(f"  - {name}")
        log_info("提示：请为这些技能补充 description 后重新运行 skills-sync")

    return skills


def generate_available_skills_content(skills: List[Dict[str, str]]) -> str:
    """生成 available_skills 标签内部的内容（不包含标签本身）

    Args:
        skills: 技能列表

    Returns:
        str: available_skills 标签内部的内容
    """
    # 按技能名称排序
    sorted_skills = sorted(skills, key=lambda x: x["name"])

    # 生成技能列表
    skills_content = ""

    for skill in sorted_skills:
        skills_content += f"""
<skill>
<name>{skill['name']}</name>
<description>{skill['description']}</description>
<location>project</location>
</skill>
"""

    return skills_content


def generate_full_skills_system_content(skills: List[Dict[str, str]]) -> str:
    """生成完整的 skills_system 标签内的内容（用于新建文件或不存在标签时）

    Args:
        skills: 技能列表

    Returns:
        str: skills_system 标签内的完整内容
    """
    # 固定的 usage 部分
    usage_section = """<usage>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Load skill content from `ai-docs/skills/{skill-name}/SKILL.md`
- The skill content will load with detailed instructions on how to complete the task
- Base directory provided in output for resolving bundled resources (references/, scripts/, assets/)

Usage notes:
- Only use skills listed in <available_skills> below
- Do not reload a skill that is already loaded in your context
- Each skill invocation is stateless and independent
</usage>"""

    # 生成 available_skills 部分（包含标签）
    available_skills_inner = generate_available_skills_content(skills)
    available_skills = f"\n<available_skills>{available_skills_inner}\n</available_skills>"

    # 组合完整内容（仅包含 skills_system 内部内容）
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
        # 如果文件不存在，创建基础结构
        original_content = """# AGENTS


"""

    # 检查是否存在 skills_system 标签
    skills_system_pattern = r'<skills_system priority="1">(.*?)</skills_system>'

    if re.search(skills_system_pattern, original_content, re.DOTALL):
        # 存在 skills_system 标签，只更新 available_skills 部分
        # 使用更精确的正则表达式：匹配换行符后的 <available_skills> 标签
        # 这样可以避免匹配到 usage 文本中的 "<available_skills>"
        available_skills_pattern = r"\n<available_skills>.*?</available_skills>"

        # 生成新的 available_skills 内容（包含标签）
        new_available_skills_inner = generate_available_skills_content(skills)
        new_available_skills_full = (
            f"\n<available_skills>{new_available_skills_inner}\n</available_skills>"
        )

        # 检查是否存在 available_skills 标签
        if re.search(available_skills_pattern, original_content, re.DOTALL):
            # 替换整个 available_skills 标签及其内容
            new_content = re.sub(
                available_skills_pattern,
                new_available_skills_full,
                original_content,
                flags=re.DOTALL,
            )
        else:
            # 如果不存在 available_skills，在 skills_system 标签内添加
            # 这种情况理论上不应该发生，但为了健壮性还是处理一下
            full_content = generate_full_skills_system_content(skills)
            new_content = re.sub(
                skills_system_pattern,
                f'<skills_system priority="1">{full_content}\n</skills_system>',
                original_content,
                flags=re.DOTALL,
            )
    else:
        # 不存在 skills_system 标签，插入完整的 skills_system 内容
        full_content = generate_full_skills_system_content(skills)
        new_content = (
            original_content.rstrip()
            + f'\n\n<skills_system priority="1">{full_content}\n</skills_system>\n'
        )

    # 写入文件
    agents_md_path.write_text(new_content, encoding="utf-8")


@click.command(name="skills-sync")
def skills_sync():
    """同步技能列表到 AGENTS.md 文件

    扫描 ai-docs/skills 目录下的所有技能，读取每个技能的 SKILL.md 文件的 YAML 头信息，
    然后更新 AGENTS.md 文件中的 <skills_system> 部分，保留其他内容不变。

    支持两种工作模式：
    - 标准模式：从 ai-driving/ai-docs/skills 读取技能，更新根目录的 AGENTS.md
    - 本地模式：从 ai-docs/skills 读取技能，更新根目录的 AGENTS.md
    """
    try:
        # 在命令执行时输出 PyYAML 警告
        if not HAS_YAML:
            log_warning("PyYAML 未安装，将使用简化的 YAML 解析器")
            log_warning("建议安装 PyYAML 以获得更好的兼容性: pip3 install PyYAML")

        current_dir = Path.cwd()

        # 查找 skills 目录
        skills_dir = find_skills_dir()
        if not skills_dir:
            log_error("未找到 ai-docs/skills 目录")
            log_info("请先执行 'driving install' 安装 driving 配置")
            raise click.Abort()

        log_info(f"扫描技能目录: {skills_dir}")

        # 扫描技能
        skills = scan_skills(skills_dir)

        if not skills:
            log_warning("未找到任何有效的技能")
            return

        log_success(f"找到 {len(skills)} 个技能")

        # 确定 AGENTS.md 文件路径（在项目根目录）
        agents_md_path = current_dir / "AGENTS.md"

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

    except Exception as e:
        log_error(f"同步技能列表失败: {e}")
        raise click.Abort()
