"""Rule 子命令组

提供 `driving rule load` 和 `driving rule list` 命令，
扫描所有已安装仓库的 rules/ 目录，管理规则的启用/禁用状态。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click

from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _parse_frontmatter_simple(yaml_content: str) -> Optional[Dict]:
    """简化的 YAML 解析器，仅支持 name 和 description 字段

    Args:
        yaml_content: YAML 内容字符串

    Returns:
        Dict: 包含 name 和 description 的字典，缺少 name 则返回 None
    """
    result = {}
    lines = yaml_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("#"):
            i += 1
            continue

        if line.startswith("name:"):
            result["name"] = line[5:].strip()
            i += 1
            continue

        if line.startswith("description:"):
            value = line[12:].strip()
            if value and value != "|":
                result["description"] = value
                i += 1
                continue
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
            result["description"] = ""
            i += 1
            continue

        i += 1

    if "name" not in result:
        return None
    if "description" not in result:
        result["description"] = ""
    return result


def parse_rule_yaml(rule_md_path: Path, header_only: bool = False) -> Optional[Dict]:
    """解析规则 .md 文件的 YAML frontmatter

    提取 name、description 字段；header_only=False 时还提取正文作为 content。
    header_only=True 时逐行读取到第二个 --- 即停止，避免读取大文件正文。

    Args:
        rule_md_path: 规则 .md 文件路径
        header_only: True 时只解析 frontmatter，不读取正文（更快）

    Returns:
        Dict: {"name": ..., "description": ...} 或含 "content" 的完整字典，
              缺少 name 字段或无 frontmatter 则返回 None
    """
    try:
        if header_only:
            yaml_lines = []
            with rule_md_path.open(encoding="utf-8") as f:
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
            markdown_body = None
        else:
            content = rule_md_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None
            lines = content.split("\n")
            end_idx = None
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    end_idx = i
                    break
            if end_idx is None:
                return None
            yaml_content = "\n".join(lines[1:end_idx]).strip()
            body_lines = lines[end_idx + 1:]
            while body_lines and not body_lines[0].strip():
                body_lines = body_lines[1:]
            markdown_body = "\n".join(body_lines)

        # 优先使用 PyYAML 解析
        if HAS_YAML:
            try:
                yaml_data = yaml.safe_load(yaml_content)
                if not yaml_data or "name" not in yaml_data:
                    return None
                result = {
                    "name": str(yaml_data.get("name", "")),
                    "description": str(yaml_data.get("description", "") or ""),
                }
                if not header_only:
                    result["content"] = markdown_body
                return result
            except Exception as e:
                log_warning(f"PyYAML 解析失败，尝试使用简化解析器: {e}")
                parsed = _parse_frontmatter_simple(yaml_content)
        else:
            parsed = _parse_frontmatter_simple(yaml_content)

        if parsed is None:
            return None

        result = {
            "name": parsed["name"],
            "description": parsed.get("description", ""),
        }
        if not header_only:
            result["content"] = markdown_body
        return result

    except Exception as e:
        log_warning(f"解析 {rule_md_path} 失败: {e}")
        return None


def scan_rules_from_dir(repo_name: str, rules_dir: Path, quiet: bool = False, header_only: bool = False) -> List[Dict]:
    """扫描单个仓库的 rules/ 目录，返回规则列表

    Args:
        repo_name: 仓库名称
        rules_dir: rules 目录路径
        quiet: 静默模式，不输出日志
        header_only: True 时只解析 frontmatter，不读取正文（更快）

    Returns:
        List[Dict]: 规则列表，每条包含 name、description、path、content 字段
    """
    rules = []

    for rule_file in sorted(rules_dir.iterdir()):
        if not rule_file.is_file() or rule_file.suffix != ".md":
            continue

        rule_info = parse_rule_yaml(rule_file, header_only=header_only)
        if rule_info is None:
            if not quiet:
                log_warning(f"跳过 {rule_file.name}：缺少 YAML frontmatter 或 name 字段")
            continue

        file_stem = rule_file.stem
        rule_info["path"] = f"ai-driving/{repo_name}/rules/{file_stem}.md"
        rules.append(rule_info)

        if not quiet:
            log_info(f"发现规则: {rule_info['name']} (来自仓库 {repo_name})")

    return rules


def _load_manifest_rules(repo_dir: Path) -> Optional[dict]:
    """读取仓库 manifest.json 中的 rules 配置，作为仓库级默认值"""
    manifest_path = repo_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = json_module.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("rules") or None
    except Exception:
        return None


def _scan_rules_with_filter(
    repo_name: str,
    rules_dir: Path,
    enabled: List[str],
    disabled: List[str],
    quiet: bool = True,
) -> List[Dict]:
    """扫描规则目录，enabled 白名单时只读对应文件，减少文件 IO。"""
    if enabled:
        rules = []
        enabled_set = set(enabled)
        for rule_name in sorted(enabled_set):
            rule_file = rules_dir / f"{rule_name}.md"
            if not rule_file.exists():
                continue
            rule_info = parse_rule_yaml(rule_file, header_only=True)
            if rule_info:
                rule_info["path"] = f"ai-driving/{repo_name}/rules/{rule_name}.md"
                rules.append(rule_info)
        return rules

    all_rules = scan_rules_from_dir(repo_name, rules_dir, quiet=quiet, header_only=True)
    if disabled:
        disabled_set = set(disabled)
        all_rules = [r for r in all_rules if r["name"] not in disabled_set]
    return all_rules


def filter_rules_by_config(rules: List[Dict], repo_config: RepoConfig) -> List[Dict]:
    """根据仓库的 rules 配置过滤规则列表

    - rules 字段为 None：返回全部规则
    - enabled 列表非空：白名单模式，只返回 enabled 中的规则
    - enabled 为空且 disabled 非空：黑名单模式，排除 disabled 中的规则

    Args:
        rules: 规则列表
        repo_config: 仓库配置对象

    Returns:
        List[Dict]: 过滤后的规则列表
    """
    if repo_config.rules is None:
        return rules

    enabled = repo_config.rules.get("enabled") or []
    disabled = repo_config.rules.get("disabled") or []

    if enabled:
        # 白名单模式：只保留 enabled 列表中的规则
        return [r for r in rules if r["name"] in enabled]
    elif disabled:
        # 黑名单模式：排除 disabled 列表中的规则
        return [r for r in rules if r["name"] not in disabled]

    return rules


@click.group(name="rule")
def rule_group():
    """规则管理

    - 支持扫描多个仓库的 rules/ 目录\n
    - 管理多个仓库规则的启用和禁用\n
    - 获取多个仓库可用规则的完整内容加载到上下文
    """
    pass


def collect_rules(keywords: tuple = ()) -> list:
    """收集可用规则列表，供 rule load 和 driving load 复用。"""

    project_root = find_project_root()
    config_manager = ConfigManager(project_root)

    rules_dirs = config_manager.get_all_rules_dirs()
    if not rules_dirs:
        return []

    repo_configs = config_manager.get_all_repos()
    repo_config_map = {r.name: r for r in repo_configs}

    # 优化 1：无关键词时只扫描 base 仓库
    if not keywords:
        rules_dirs = [
            (n, d) for n, d in rules_dirs
            if "base" in ((repo_config_map.get(n) and repo_config_map[n].tags) or [])
        ]

    all_rules_by_repo: dict = {}
    for repo_name, rules_dir in rules_dirs:
        rc = repo_config_map.get(repo_name)
        if not keywords:
            # 优先级：driving.config.json > manifest.json > 全量加载
            effective_rules = (rc.rules if rc and rc.rules is not None
                               else _load_manifest_rules(rules_dir.parent))
            enabled = (effective_rules or {}).get("enabled") or []
            disabled = (effective_rules or {}).get("disabled") or []
            # 优化 2：enabled 白名单时提前过滤文件
            repo_rules = _scan_rules_with_filter(repo_name, rules_dir, enabled, disabled)
        else:
            repo_rules = scan_rules_from_dir(repo_name, rules_dir, quiet=True, header_only=True)
        all_rules_by_repo[repo_name] = repo_rules

    result: list = []
    seen: set = set()

    def _add(rules: list):
        for r in rules:
            if r["path"] not in seen:
                seen.add(r["path"])
                result.append(r)

    if not keywords:
        for repo_name, repo_rules in all_rules_by_repo.items():
            _add(repo_rules)
    else:
        from driving_cli.utils.match import fuzzy_match_any
        kw_lower = tuple(k.lower() for k in keywords)
        for repo_name, repo_rules in all_rules_by_repo.items():
            if repo_name.lower() in kw_lower:
                _add(repo_rules)
                continue
            matched = [r for r in repo_rules
                       if fuzzy_match_any((r["name"], r.get("description", "")), keywords)]
            _add(matched)

    return [
        {"name": r["name"], "description": r["description"], "path": r["path"]}
        for r in result
    ]


@rule_group.command(name="load")
@click.argument("keywords", nargs=-1, required=False)
def rule_load(keywords: tuple):
    """输出所有已启用规则的完整内容，供 AI 会话注入上下文

    不传关键词时，只加载 tags 含 "base" 的仓库的规则。
    传入关键词时，在 base 仓库基础上，额外匹配 repo.name 或 rule.name 的规则（取并集）。
    支持多个关键词：driving rule load f-message f-qucall

    示例：
        driving rule load
        driving rule load f-message
        driving rule load f-message f-qucall
        driving rule load code-style
    """
    try:
        output = collect_rules(keywords)
        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        log_error(f"加载规则列表失败: {e}")
        raise click.Abort()


@rule_group.command(name="list")
@click.option("--repo", "repo_name", default=None, help="只显示指定仓库的规则")
@click.option("--edit", is_flag=True, default=False, help="进入交互模式，勾选/取消规则")
@click.option("--mode", type=click.Choice(["auto", "enable", "disable"]), default="auto",
              help="保存模式：auto 自动选择（默认），enable 强制写 enabled，disable 强制写 disabled")
def rule_list(repo_name: Optional[str], edit: bool, mode: str):
    """列出所有规则，按仓库分组显示启用状态，支持编辑模式

    使用 --edit 进入交互模式，通过空格勾选/取消规则，回车保存。
    --mode 控制保存字段：auto 自动选最短，enable 强制写 enabled，disable 强制写 disabled。

    示例：
        driving rule list
        driving rule list --repo my-local
        driving rule list --edit
        driving rule list --edit --mode enable
        driving rule list --edit --mode disable
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
            rules_dirs = [(repo_name, config_manager.get_repo_dir(repo_name) / "rules")]
            rules_dirs = [(n, d) for n, d in rules_dirs if d.exists()]
            target_repos = [repo_cfg]
        else:
            rules_dirs = config_manager.get_all_rules_dirs()
            target_repos = config_manager.get_all_repos()

        if not rules_dirs:
            log_info("未找到任何规则目录")
            return

        repo_config_map = {r.name: r for r in target_repos}

        # 扫描所有规则（不过滤，展示完整状态）
        all_rules_by_repo: Dict[str, List[Dict]] = {}
        repo_dir_map: Dict[str, Path] = {}
        for rname, rdir in rules_dirs:
            all_rules_by_repo[rname] = scan_rules_from_dir(rname, rdir, quiet=True)
            repo_dir_map[rname] = rdir.parent

        def _is_enabled(rc: Optional[RepoConfig], rule_name: str, repo_dir: Path) -> bool:
            rules_cfg = (rc.rules if rc and rc.rules is not None
                         else _load_manifest_rules(repo_dir))
            if rules_cfg is None:
                return True
            enabled = rules_cfg.get("enabled") or []
            disabled = rules_cfg.get("disabled") or []
            if enabled:
                return rule_name in enabled
            return rule_name not in disabled

        if edit:
            # ── 交互模式 ──────────────────────────────────────────
            from prompt_toolkit.shortcuts import checkboxlist_dialog
            from prompt_toolkit.styles import Style as PTStyle

            clean_style = PTStyle.from_dict({
                "dialog":                        "bg:#1e1e1e",
                "dialog.body":                   "bg:#1e1e1e fg:#ffffff",
                "dialog.body checkbox":          "fg:#888888",
                "dialog.body checkbox-selected": "fg:#00cc00 bold",
                "dialog.body checkbox-checked":  "fg:#00cc00",
                "button":                        "bg:#333333 fg:#ffffff",
                "button.focused":                "bg:#00cc00 fg:#000000",
            })

            for rname, rules in all_rules_by_repo.items():
                if not rules:
                    continue
                rc = repo_config_map.get(rname)
                repo_dir = repo_dir_map.get(rname, Path("."))
                values = [(r["name"], r["name"]) for r in rules]
                default_checked = [r["name"] for r in rules if _is_enabled(rc, r["name"], repo_dir)]

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

                all_names = [r["name"] for r in rules]
                checked = set(result)
                unchecked = set(all_names) - checked

                if rc is None:
                    continue

                # 计算变更内容：对比有效状态（config 或 manifest）
                prev_rules = rc.rules if rc.rules is not None else _load_manifest_rules(repo_dir)
                old_disabled = set((prev_rules or {}).get("disabled") or [])
                if prev_rules and (prev_rules.get("enabled") or []):
                    old_enabled_set = set(prev_rules["enabled"])
                    old_disabled = {n for n in all_names if n not in old_enabled_set}

                newly_enabled = sorted(old_disabled - unchecked)
                newly_disabled = sorted(unchecked - old_disabled)

                if not unchecked:
                    rc.rules = None
                elif not checked:
                    rc.rules = {"enabled": [], "disabled": []}
                elif mode == "enable":
                    rc.rules = {"enabled": sorted(checked), "disabled": []}
                elif mode == "disable":
                    rc.rules = {"enabled": [], "disabled": sorted(unchecked)}
                else:
                    if len(checked) <= len(unchecked):
                        rc.rules = {"enabled": sorted(checked), "disabled": []}
                    else:
                        rc.rules = {"enabled": [], "disabled": sorted(unchecked)}
                config_manager.update_repo(rc)

                if not newly_enabled and not newly_disabled:
                    log_info(f"仓库 '{rname}' 无变更")
                else:
                    log_success(f"仓库 '{rname}' 规则配置已保存")
                    for name in newly_enabled:
                        click.echo(f"  + {name}  （已启用）")
                    for name in newly_disabled:
                        click.echo(f"  - {name}  （已禁用）")
        else:
            # ── 只读展示模式 ──────────────────────────────────────
            total = 0
            for rname, rules in all_rules_by_repo.items():
                rc = repo_config_map.get(rname)
                repo_dir = repo_dir_map.get(rname, Path("."))
                click.echo(f"\n仓库：{rname}")
                for r in rules:
                    rname_rule = r["name"]
                    mark = "✓" if _is_enabled(rc, rname_rule, repo_dir) else "✗"
                    click.echo(f"  [{mark}] {rname_rule}")
                    total += 1
            click.echo(f"\n共 {total} 条规则  （使用 --edit 进入编辑模式）")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出规则失败: {e}")
        raise click.Abort()
