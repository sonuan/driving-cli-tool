"""Skill 子命令组

提供 `driving skill sync` 命令，扫描所有已安装仓库的 skills/ 目录并同步到 AGENTS.md。
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning

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
    """解析 SKILL.md 文件的 YAML 头信息，逐行读取到第二个 --- 即停止

    Args:
        skill_md_path: SKILL.md 文件路径

    Returns:
        Dict: 包含 name 和 description 的字典，如果解析失败则返回 None
    """
    try:
        yaml_lines = []
        with skill_md_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f):
                if lineno == 0:
                    if line.rstrip("\n") != "---":
                        return None
                    continue
                if line.strip() == "---":
                    break
                yaml_lines.append(line)
            else:
                return None  # 未找到结束 ---

        yaml_content = "".join(yaml_lines).strip()

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


def scan_skills_from_dir(repo_name: str, skills_dir: Path, quiet: bool = False) -> List[Dict[str, str]]:
    """扫描单个仓库的 skills 目录，返回技能列表

    每个技能的 path 字段为完整路径：ai-driving/<repo-name>/skills/<skill-name>/

    Args:
        repo_name: 仓库名称
        skills_dir: skills 目录路径
        quiet: 静默模式，不输出日志（用于机器读取场景）

    Returns:
        List[Dict]: 技能列表，每个技能包含 name、description、path 字段
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
            if not quiet:
                log_warning(f"跳过 {skill_dir.name}：未找到 SKILL.md 文件")
            continue

        # 解析 YAML 头
        skill_info = parse_skill_yaml(skill_md)
        if skill_info:
            # 检查 description 是否为空
            if not skill_info["description"] or not skill_info["description"].strip():
                if not quiet:
                    log_warning(f"跳过技能 {skill_info['name']}：description 为空")
                continue

            skill_info["path"] = f"ai-driving/{repo_name}/skills/{skill_dir.name}/"
            skills.append(skill_info)
            if not quiet:
                log_info(f"发现技能: {skill_info['name']} (来自仓库 {repo_name})")
        else:
            if not quiet:
                log_warning(f"跳过 {skill_dir.name}：YAML 头信息不完整")

    return skills


def merge_skills_from_all_repos(
    skills_dirs: List[Tuple[str, Path]],
    quiet: bool = False,
    repo_configs: Optional[List] = None,
) -> List[Dict[str, str]]:
    """合并所有仓库的技能列表，同名技能按仓库顺序去重

    按配置文件中仓库顺序（先配置的优先），同名技能只保留第一个，并记录警告。

    Args:
        skills_dirs: [(repo_name, skills_dir_path), ...] 列表

    Returns:
        List[Dict]: 合并后的技能列表，每个技能包含 name、description、path 字段
    """
    merged: Dict[str, Dict[str, str]] = {}  # skill_name -> skill_info
    result: List[Dict[str, str]] = []

    # 构建 repo_name -> RepoConfig 的映射，用于过滤
    repo_config_map = {}
    if repo_configs:
        for rc in repo_configs:
            repo_config_map[rc.name] = rc

    for repo_name, skills_dir in skills_dirs:
        repo_skills = scan_skills_from_dir(repo_name, skills_dir, quiet=quiet)

        # 按仓库的 skills.enabled / skills.disabled 过滤
        rc = repo_config_map.get(repo_name)
        if rc is not None and rc.skills is not None:
            enabled = rc.skills.get("enabled") or []
            disabled = rc.skills.get("disabled") or []
            if enabled:
                repo_skills = [s for s in repo_skills if s["name"] in enabled]
            elif disabled:
                repo_skills = [s for s in repo_skills if s["name"] not in disabled]

        for skill in repo_skills:
            skill_name = skill["name"]
            if skill_name in merged:
                existing_path = merged[skill_name]["path"]
                if not quiet:
                    log_warning(
                        f"技能 '{skill_name}' 在多个仓库中存在，"
                        f"使用 {existing_path}（跳过 {skill['path']}）"
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
<path>{skill['path']}</path>
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
    """技能管理

    - 支持扫描多个仓库的 skills/ 目录\n
    - 管理多个仓库技能的启用和禁用\n
    - 获取多个仓库可用技能的信息加载到上下文
    """
    pass


@skill_group.command(name="sync")
def skill_sync():
    """【废弃】扫描所有仓库 skills/ 并同步到 AGENTS.md

    遍历 driving.config.json 中所有已安装仓库的 skills/ 目录，
    读取每个技能的 SKILL.md 文件的 YAML 头信息，
    然后更新 AGENTS.md 文件中的 <skills_system> 部分，保留其他内容不变。

    同名技能按仓库在配置文件中的顺序去重（先配置的优先）。
    path 字段为完整路径：ai-driving/<repo-name>/skills/<skill-name>/
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

        # 合并所有仓库的技能列表（同名去重，遵守启用/禁用配置）
        repo_configs = config_manager.get_all_repos()
        skills = merge_skills_from_all_repos(skills_dirs, repo_configs=repo_configs)

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
            log_info(f"    📁 {skill['path']}")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"同步技能列表失败: {e}")
        raise click.Abort()


@skill_group.command(name="load")
@click.argument("keywords", nargs=-1, required=False)
def skill_load(keywords: tuple):
    """输出当前所有可用技能的完整信息，供 AI 会话注入上下文

    不传关键词时，只加载 tags 含 "base" 的仓库的技能。
    传入关键词时，在 base 仓库基础上，额外匹配 repo.name 或 skill.name 的技能（取并集）。
    支持多个关键词：driving skill load f-message f-qucall

    示例：
        driving skill load
        driving skill load f-message
        driving skill load f-message f-qucall
        driving skill load code-review
    """
    import json as json_module

    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        skills_dirs = config_manager.get_all_skills_dirs()
        if not skills_dirs:
            click.echo("[]")
            return

        repo_configs = config_manager.get_all_repos()
        repo_config_map = {r.name: r for r in repo_configs}

        # 扫描所有仓库的全量技能（quiet 模式，遵守 enabled/disabled 配置）
        all_skills_by_repo: dict = {}
        for repo_name, skills_dir in skills_dirs:
            rc = repo_config_map.get(repo_name)
            repo_skills = scan_skills_from_dir(repo_name, skills_dir, quiet=True)
            # 应用仓库的 enabled/disabled 过滤
            if rc is not None and rc.skills is not None:
                enabled = rc.skills.get("enabled") or []
                disabled = rc.skills.get("disabled") or []
                if enabled:
                    repo_skills = [s for s in repo_skills if s["name"] in enabled]
                elif disabled:
                    repo_skills = [s for s in repo_skills if s["name"] not in disabled]
            all_skills_by_repo[repo_name] = repo_skills

        result_skills: list = []
        seen_paths: set = set()

        def _add_skills(skills: list):
            for s in skills:
                if s["path"] not in seen_paths:
                    seen_paths.add(s["path"])
                    result_skills.append(s)

        if not keywords:
            # 无关键词：只加载 tag=base 的仓库
            for repo_name, repo_skills in all_skills_by_repo.items():
                rc = repo_config_map.get(repo_name)
                tags = rc.tags if rc and rc.tags else []
                if "base" in tags:
                    _add_skills(repo_skills)
        else:
            # 有关键词：忽略 tags，只按 repo.name 或 skill.name 精确匹配
            kw_set = set(keywords)

            for repo_name, repo_skills in all_skills_by_repo.items():
                # repo.name 匹配任意关键词 → 整个仓库的 skills 全部加载
                if repo_name in kw_set:
                    _add_skills(repo_skills)
                    continue

                # skill.name 匹配任意关键词 → 只加载匹配的 skill
                matched = [s for s in repo_skills if s["name"] in kw_set]
                _add_skills(matched)

        output = [
            {"name": s["name"], "description": s["description"], "path": s["path"]}
            for s in sorted(result_skills, key=lambda x: x["name"])
        ]
        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        log_error(f"加载技能列表失败: {e}")
        raise click.Abort()


@skill_group.command(name="list")
@click.option("--repo", "repo_name", default=None, help="只显示指定仓库的技能")
@click.option("--edit", is_flag=True, default=False, help="进入交互模式，勾选/取消技能")
def skill_list(repo_name: Optional[str], edit: bool):
    """列出所有可用技能，按仓库分组显示启用状态，支持编辑模式

    使用 --edit 进入交互模式，通过空格勾选/取消技能，回车保存。

    示例：
        driving skill list
        driving skill list --repo driving
        driving skill list --edit
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        # 确定要扫描的仓库范围
        if repo_name:
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            skills_dirs = [(repo_name, config_manager.get_repo_dir(repo_name) / "skills")]
            skills_dirs = [(n, d) for n, d in skills_dirs if d.exists()]
            target_repos = [repo_cfg]
        else:
            skills_dirs = config_manager.get_all_skills_dirs()
            target_repos = config_manager.get_all_repos()

        if not skills_dirs:
            log_info("未找到任何技能目录")
            return

        repo_config_map = {r.name: r for r in target_repos}

        # 扫描所有技能（不过滤，展示完整状态）
        all_skills_by_repo: Dict[str, List[Dict]] = {}
        for rname, sdir in skills_dirs:
            all_skills_by_repo[rname] = scan_skills_from_dir(rname, sdir, quiet=True)

        def _is_enabled(rc, sname: str) -> bool:
            if rc is None or rc.skills is None:
                return True
            enabled = rc.skills.get("enabled") or []
            disabled = rc.skills.get("disabled") or []
            if enabled:
                return sname in enabled
            return sname not in disabled

        if edit:
            # ── 交互模式 ──────────────────────────────────────────
            from prompt_toolkit.shortcuts import checkboxlist_dialog
            from prompt_toolkit.styles import Style as PTStyle

            # 干净样式：选中绿色，光标行无背景，只加下划线区分
            clean_style = PTStyle.from_dict({
                "dialog":                    "bg:#1e1e1e",
                "dialog.body":               "bg:#1e1e1e fg:#ffffff",
                "dialog.body checkbox":      "fg:#888888",
                "dialog.body checkbox-selected": "fg:#00cc00 bold",
                "dialog.body checkbox-checked":  "fg:#00cc00",
                "button":                    "bg:#333333 fg:#ffffff",
                "button.focused":            "bg:#00cc00 fg:#000000",
            })

            for rname, skills in all_skills_by_repo.items():
                if not skills:
                    continue
                rc = repo_config_map.get(rname)
                values = [(s["name"], s["name"]) for s in skills]
                default_checked = [s["name"] for s in skills if _is_enabled(rc, s["name"])]

                click.echo(f"\n仓库：{rname}")
                result = checkboxlist_dialog(
                    title=f"仓库：{rname}",
                    text="空格勾选/取消，Tab 切换到 OK，回车确认",
                    values=values,
                    default_values=default_checked,
                    style=clean_style,
                ).run()

                if result is None:
                    continue

                all_names = [s["name"] for s in skills]
                new_disabled = [n for n in all_names if n not in result]

                if rc is None:
                    continue

                # 计算变更内容
                old_disabled = set((rc.skills or {}).get("disabled") or [])
                new_disabled_set = set(new_disabled)
                newly_enabled = sorted(old_disabled - new_disabled_set)   # 原来禁用，现在启用
                newly_disabled = sorted(new_disabled_set - old_disabled)  # 原来启用，现在禁用

                rc.skills = None if not new_disabled else {"enabled": [], "disabled": sorted(new_disabled)}
                config_manager.update_repo(rc)

                if not newly_enabled and not newly_disabled:
                    log_info(f"仓库 '{rname}' 无变更")
                else:
                    log_success(f"仓库 '{rname}' 技能配置已保存")
                    for name in newly_enabled:
                        click.echo(f"  + {name}  （已启用）")
                    for name in newly_disabled:
                        click.echo(f"  - {name}  （已禁用）")
        else:
            # ── 只读展示模式 ──────────────────────────────────────
            total = 0
            for rname, skills in all_skills_by_repo.items():
                rc = repo_config_map.get(rname)
                click.echo(f"\n仓库：{rname}")
                for s in skills:
                    sname = s["name"]
                    mark = "✓" if _is_enabled(rc, sname) else "✗"
                    click.echo(f"  [{mark}] {sname}")
                    total += 1
            click.echo(f"\n共 {total} 个技能  （使用 --edit 进入编辑模式）")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出技能失败: {e}")
        raise click.Abort()


@skill_group.command(name="enable")
@click.argument("skill_spec")
def skill_enable(skill_spec: str):
    """【废弃】启用指定技能，使用 list --edit 代替

    将技能加入对应仓库的白名单（skills_enabled）。
    支持 <repo-name>/<skill-name> 格式指定仓库，否则在所有仓库中查找。

    示例：
        driving skill enable code-review
        driving skill enable driving/code-review
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        repo_name, skill_name = _parse_skill_spec(skill_spec, config_manager)
        if repo_name is None:
            raise click.Abort()

        repo_cfg = config_manager.get_repo(repo_name)

        # 确保 skills 字段存在
        if repo_cfg.skills is None:
            repo_cfg.skills = {"enabled": [], "disabled": []}
        enabled = repo_cfg.skills.setdefault("enabled", [])
        disabled = repo_cfg.skills.setdefault("disabled", [])

        # 从黑名单中移除（如果存在）
        if skill_name in disabled:
            disabled.remove(skill_name)

        # 加入白名单（如果已有白名单模式）
        if enabled:
            if skill_name not in enabled:
                enabled.append(skill_name)
                enabled.sort()
        else:
            # 白名单为空表示全部启用，检查技能是否存在即可
            skills_dir = config_manager.get_repo_dir(repo_name) / "skills"
            if not (skills_dir / skill_name).exists():
                log_error(f"技能 '{skill_name}' 在仓库 '{repo_name}' 中不存在")
                raise click.Abort()
            # 清理空的 skills 字段
            if not enabled and not disabled:
                repo_cfg.skills = None
            log_success(f"技能 '{skill_name}'（仓库：{repo_name}）已处于启用状态（默认全部启用）")
            config_manager.update_repo(repo_cfg)
            return

        config_manager.update_repo(repo_cfg)
        log_success(f"已启用技能 '{skill_name}'（仓库：{repo_name}）")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"启用技能失败: {e}")
        raise click.Abort()


@skill_group.command(name="disable")
@click.argument("skill_spec")
def skill_disable(skill_spec: str):
    """【废弃】禁用指定技能，使用 list --edit 代替

    将技能加入对应仓库的黑名单（skills_disabled）。
    支持 <repo-name>/<skill-name> 格式指定仓库，否则在所有仓库中查找。

    示例：
        driving skill disable refactor
        driving skill disable driving/refactor
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        repo_name, skill_name = _parse_skill_spec(skill_spec, config_manager)
        if repo_name is None:
            raise click.Abort()

        repo_cfg = config_manager.get_repo(repo_name)

        # 确保 skills 字段存在
        if repo_cfg.skills is None:
            repo_cfg.skills = {"enabled": [], "disabled": []}
        enabled = repo_cfg.skills.setdefault("enabled", [])
        disabled = repo_cfg.skills.setdefault("disabled", [])

        # 从白名单中移除（如果存在）
        if skill_name in enabled:
            enabled.remove(skill_name)

        # 加入黑名单
        if skill_name not in disabled:
            disabled.append(skill_name)
            disabled.sort()

        config_manager.update_repo(repo_cfg)
        log_success(f"已禁用技能 '{skill_name}'（仓库：{repo_name}）")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"禁用技能失败: {e}")
        raise click.Abort()


def _parse_skill_spec(skill_spec: str, config_manager: ConfigManager):
    """解析 skill_spec，支持 <repo>/<skill> 或 <skill> 格式

    Returns:
        (repo_name, skill_name) 或 (None, None) 表示出错
    """
    if "/" in skill_spec:
        repo_name, skill_name = skill_spec.split("/", 1)
        if config_manager.get_repo(repo_name) is None:
            log_error(f"仓库 '{repo_name}' 不存在")
            return None, None
        return repo_name, skill_name

    # 未指定仓库：在所有仓库中查找该技能
    matches = []
    for repo_name, skills_dir in config_manager.get_all_skills_dirs():
        if (skills_dir / skill_spec).exists():
            matches.append(repo_name)

    if not matches:
        log_error(f"技能 '{skill_spec}' 在任何仓库中都不存在")
        return None, None

    if len(matches) > 1:
        log_error(f"技能 '{skill_spec}' 存在于多个仓库：{', '.join(matches)}")
        log_error(f"请使用 '<repo-name>/{skill_spec}' 格式指定仓库")
        return None, None

    return matches[0], skill_spec
