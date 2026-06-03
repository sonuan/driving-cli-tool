"""Refine 子命令组

提供 `driving refine list`、`driving refine load`、`driving refine commit`
和 `driving refine log` 命令，扫描所有已安装仓库的 refines/ 目录，
管理和加载 pending 状态的优化提案，以及维护 REFINE_LOG.md 变更记录。
"""

import json as json_module
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import git

from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.git_helper import get_git_user, push_with_upstream
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning
from driving_cli.utils.reporter_utils import do_post, now_timestamp

VALID_TYPES = ("skill", "rule", "agent", "framework")


def _parse_trigger_block(file_path: Path) -> Optional[Dict]:
    """从 refine 文件 frontmatter 中手动提取 trigger 嵌套字典。

    用于 PyYAML 不可用时 _parse_simple 无法解析嵌套字典的兜底处理。
    只提取 source 和 reason 两个字段。

    Returns:
        {"source": ..., "reason": ...} 或 None（trigger 块不存在时）
    """
    try:
        in_frontmatter = False
        in_trigger = False
        result: Dict = {}
        with file_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f):
                stripped = line.rstrip("\n")
                if lineno == 0:
                    if stripped.strip() == "---":
                        in_frontmatter = True
                    continue
                if not in_frontmatter:
                    break
                if stripped.strip() == "---":
                    break
                if stripped.strip() == "trigger:":
                    in_trigger = True
                    continue
                if in_trigger:
                    # 缩进行属于 trigger 块
                    if stripped.startswith("  ") or stripped.startswith("\t"):
                        kv = stripped.strip()
                        if ":" in kv:
                            k, _, v = kv.partition(":")
                            result[k.strip()] = v.strip()
                    else:
                        # 非缩进行，trigger 块结束
                        in_trigger = False
        return result if result else None
    except Exception:
        return None


def _parse_refine_frontmatter(file_path: Path) -> Optional[Dict]:
    """解析 refine 文件的 YAML frontmatter。

    提取 date、target_type、target_name、target_file、description、operator、trigger、status 字段。
    逐行读取到第二个 --- 即停止，避免读取大文件正文。

    Returns:
        Dict 或 None（无 frontmatter / 缺少必填字段）
    """
    from driving_cli.utils.yaml_parser import parse_frontmatter

    try:
        data = parse_frontmatter(file_path, required_fields=["target_type"])
        if data is None:
            return None

        return {
            "date": str(data.get("date", "")),
            "target_type": str(data.get("target_type", "")),
            "target_name": str(data.get("target_name", "")),
            "target_file": str(data.get("target_file", "")),
            "description": str(data.get("description", "")),
            "operator": str(data.get("operator", "")),
            "trigger": data.get("trigger") if isinstance(data.get("trigger"), dict) else _parse_trigger_block(file_path),
            "status": str(data.get("status", "pending")),
        }
    except Exception as e:
        log_warning(f"解析 {file_path.name} 失败: {e}")
        return None


def _scan_refines(repo_name: str, refines_dir: Path, type_filter: Optional[str] = None) -> List[Dict]:
    """扫描单个仓库的 refines/ 目录，返回 refine 信息列表。"""
    results = []
    for f in sorted(refines_dir.iterdir()):
        if not f.is_file() or f.suffix != ".md":
            continue
        meta = _parse_refine_frontmatter(f)
        if meta is None:
            continue
        if type_filter and meta["target_type"] != type_filter:
            continue
        results.append({
            "name": f.stem,
            "description": meta["description"],
            "path": f"ai-driving/{repo_name}/refines/{f.name}",
            "date": meta["date"],
            "target_type": meta["target_type"],
            "target_name": meta["target_name"],
            "status": meta["status"],
            "_file": f,  # 内部用，load 时读取正文
        })
    return results


def _get_all_refines_dirs(config_manager: ConfigManager) -> List[Tuple[str, Path]]:
    """返回所有仓库的 refines/ 目录（仅存在的）。"""
    result = []
    for repo in config_manager.get_all_repos():
        d = config_manager.get_repo_dir(repo.name) / "refines"
        if d.exists():
            result.append((repo.name, d))
    return result


_REFINE_LOG_HEADER = "# Refine Log\n# 记录所有已生效的规范变更，refines 合并后由 AI 追加。\n"


def _report_to_webhook(
    webhook_url: str,
    repo_name: str,
    file_path: Path,
    meta: dict,
    event: str = "refine.committed",
) -> None:
    """上报 refine 提案事件到 webhook。

    失败时静默处理，不影响主流程。

    Args:
        webhook_url: 目标 webhook 地址
        repo_name: 仓库名称
        file_path: refine 文件路径（用于取文件名）
        meta: 由 _parse_refine_frontmatter 返回的 frontmatter 字典
        event: 事件类型，refine.committed（提交）或 refine.merged（合并）
    """
    trigger = meta.get("trigger") or {}

    git_user = get_git_user()

    payload: Dict = {
        "event": event,
        "at": now_timestamp(),
        "repo": repo_name,
        "file": file_path.name,
        "date": meta.get("date", ""),
        "target_type": meta.get("target_type", ""),
        "target_name": meta.get("target_name", ""),
        "target_file": meta.get("target_file", ""),
        "description": meta.get("description", ""),
        "operator": meta.get("operator", ""),
        "actor": git_user["name"],
        "status": meta.get("status", "pending"),
        "trigger_source": trigger.get("source", ""),
        "trigger_reason": trigger.get("reason", ""),
    }

    do_post(webhook_url, payload)


def _get_refine_log_path(config_manager: ConfigManager, repo_name: str) -> Path:
    """返回指定仓库的 REFINE_LOG.md 绝对路径。"""
    return config_manager.get_repo_dir(repo_name) / "REFINE_LOG.md"


@click.group(name="refine")
def refine_group():
    """Refine 提案管理

    - 列出所有仓库的 pending refine 提案\n
    - 加载 refine 内容供 AI 检索历史优化经验\n
    - 提交 pending refine 到 git（add + commit + push）\n
    - 维护 REFINE_LOG.md 变更记录
    """
    pass


@refine_group.command(name="list")
@click.option("--type", "type_filter", type=click.Choice(VALID_TYPES), default=None,
              help="只显示指定类型的 refine（skill/rule/agent/framework）")
@click.option("--repo", "repo_name", default=None, help="只显示指定仓库的 refine")
def refine_list(type_filter: Optional[str], repo_name: Optional[str]):
    """列出所有 pending 状态的 refine 提案，按类型分组显示。

    示例：
        driving refine list
        driving refine list --type skill
        driving refine list --repo driving
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        if repo_name:
            repo_cfg = config_manager.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在")
                raise click.Abort()
            refines_dirs = [(repo_name, config_manager.get_repo_dir(repo_name) / "refines")]
            refines_dirs = [(n, d) for n, d in refines_dirs if d.exists()]
        else:
            refines_dirs = _get_all_refines_dirs(config_manager)

        if not refines_dirs:
            log_info("未找到任何 refines 目录")
            return

        total = 0
        for rname, rdir in refines_dirs:
            items = _scan_refines(rname, rdir, type_filter=type_filter)
            if not items:
                continue

            click.echo(f"\n仓库：{rname}")

            # 按 target_type 分组
            by_type: Dict[str, List[Dict]] = {}
            for item in items:
                by_type.setdefault(item["target_type"], []).append(item)

            type_groups = sorted(by_type.items())
            for i, (ttype, group) in enumerate(type_groups):
                click.echo(f"  [{ttype}]")
                for item in group:
                    desc = item["description"] or "-"
                    click.echo(f"    {item['date']}  {item['target_name']}  {desc}  ({item['status']})")
                    total += 1
                if i < len(type_groups) - 1:
                    click.echo("")
        if total == 0:
            log_info("没有找到符合条件的 refine 提案")
        else:
            click.echo(f"\n共 {total} 条 refine")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"列出 refine 失败: {e}")
        raise click.Abort()


@refine_group.command(name="load")
@click.argument("names", nargs=-1, required=False)
@click.option("--type", "type_filter", type=click.Choice(VALID_TYPES), default=None,
              help="只加载指定类型的 refine（skill/rule/agent/framework）")
def refine_load(names: tuple, type_filter: Optional[str]):
    """输出 refine 提案内容，供 AI 注入上下文检索历史优化经验。

    不传 name 时输出所有 pending 的 refine。
    传入 name 时按文件名模糊匹配（包含即命中），支持多个。

    示例：
        driving refine load
        driving refine load self-refine
        driving refine load self-refine code-style
        driving refine load --type skill
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)
        refines_dirs = _get_all_refines_dirs(config_manager)

        output = []
        for rname, rdir in refines_dirs:
            items = _scan_refines(rname, rdir, type_filter=type_filter)
            for item in items:
                # 名称过滤：文件名包含任意一个关键词即命中
                if names and not any(n in item["name"] for n in names):
                    continue
                output.append({
                    "name": item["name"],
                    "description": item["description"],
                    "path": item["path"],
                })

        click.echo(json_module.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        log_error(f"加载 refine 失败: {e}")
        raise click.Abort()


@refine_group.command(name="commit")
@click.argument("repo_name")
@click.option("--no-push", is_flag=True, default=False, help="只 commit，不执行 push（离线场景）")
@click.option("--file", "file_paths", multiple=True, required=True,
              help="要提交的文件路径（相对于仓库根目录），可多次指定")
def refine_commit(repo_name: str, no_push: bool, file_paths: tuple):
    """提交指定文件到 git（add + commit + push）

    --file 为必填项，接受相对于仓库根目录的路径，可多次指定。
    只提交未被 git 追踪的文件（新增未提交），已追踪文件自动跳过。

    示例：
        driving refine commit driving --file refines/2026-05-xx-rule-foo.md
        driving refine commit driving --file REFINE_LOG.md
        driving refine commit driving --file agents/xxx/MEMORY.md --file refines/2026-05-xx-rule-foo.md
        driving refine commit driving --file refines/2026-05-xx-rule-foo.md --no-push
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        # 校验仓库
        repo_cfg = config_manager.get_repo(repo_name)
        if repo_cfg is None:
            log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
            raise click.Abort()

        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_name}' 是本地仓库，跳过 git 操作")
            raise click.Abort()

        repo_dir = config_manager.get_repo_dir(repo_name)
        try:
            repo = git.Repo(repo_dir)
        except git.exc.InvalidGitRepositoryError:
            log_error(f"仓库 '{repo_name}' 目录不是有效的 git 仓库：{repo_dir}")
            raise click.Abort()

        # 校验文件存在，并过滤掉无变更的文件
        # 有效文件 = 未追踪的新文件 OR 已追踪但有修改的文件
        untracked = set(repo.untracked_files)
        # 已追踪且工作区有修改（unstaged）
        unstaged = {item.a_path for item in repo.index.diff(None)}
        # 已暂存但未提交（staged）
        staged = {item.a_path for item in repo.index.diff("HEAD")}
        changed = untracked | unstaged | staged

        valid_files = []
        for fp in file_paths:
            abs_path = repo_dir / fp
            if not abs_path.exists():
                log_warning(f"文件不存在，跳过：{fp}")
                continue
            if fp not in changed:
                log_warning(f"文件无变更，跳过：{fp}")
                continue
            valid_files.append(fp)

        if not valid_files:
            log_info("没有需要提交的新增文件，退出")
            return

        # 展示待提交清单
        click.echo(f"\n待提交文件（共 {len(valid_files)} 个）：")
        for fp in valid_files:
            click.echo(f"  {fp}")

        click.echo("")
        confirmed = click.confirm("确认提交以上文件？", default=True)
        if not confirmed:
            log_info("已取消")
            return

        # 自动生成 commit message
        file_names = [Path(fp).name for fp in valid_files]
        summary = "; ".join(file_names[:3])
        if len(file_names) > 3:
            summary += f" 等 {len(file_names)} 个文件"
        commit_message = f"refine({repo_name}): {summary}"

        # git add
        try:
            repo.index.add(valid_files)
            log_info(f"已暂存 {len(valid_files)} 个文件")
        except Exception as e:
            log_error(f"git add 失败: {e}")
            raise click.Abort()

        # git commit
        try:
            repo.index.commit(commit_message)
            log_success(f"已提交：{commit_message}")
        except Exception as e:
            log_error(f"git commit 失败: {e}")
            raise click.Abort()

        # git push
        if no_push:
            log_info("已跳过 push（--no-push）")
            # commit 成功即上报
            _trigger_refine_webhook(config_manager, repo_name, repo_dir, valid_files, "refine.committed")
            return

        if not repo.remotes:
            log_warning(f"仓库 '{repo_name}' 未配置远程仓库，跳过 push")
            return

        # push 前检查远端是否有新提交，提示用户选择是否先 pull
        try:
            repo.remotes.origin.fetch()
            current_branch = repo.active_branch.name if not repo.head.is_detached else None
            if current_branch:
                local_commit = repo.head.commit
                remote_ref = f"origin/{current_branch}"
                try:
                    remote_commit = repo.commit(remote_ref)
                    # 检查远端是否有本地没有的提交
                    behind_commits = list(repo.iter_commits(f"{local_commit}..{remote_ref}"))
                    if behind_commits:
                        click.echo(f"\n远端有 {len(behind_commits)} 个新提交，建议先 pull 再 push。")
                        do_pull = click.confirm("是否先执行 pull？", default=True)
                        if do_pull:
                            repo.remotes.origin.pull(current_branch)
                            log_success(f"pull 成功")
                        else:
                            log_info("跳过 pull，继续 push（可能产生冲突）")
                except Exception:
                    pass  # 无法获取远端引用（如首次推送），忽略
        except git.exc.GitCommandError:
            log_warning("fetch 失败，跳过远端检查，直接 push")

        do_push = click.confirm("\n确认 push 到远端？", default=True)
        if not do_push:
            log_info("已跳过 push")
            return

        try:
            log_info(f"正在推送仓库 '{repo_name}'...")
            ok, err = push_with_upstream(repo)
            if ok:
                log_success(f"仓库 '{repo_name}' 推送成功")
                # push 成功后上报 webhook
                _trigger_refine_webhook(config_manager, repo_name, repo_dir, valid_files, "refine.committed")
            else:
                log_error(f"推送失败：{err}")
                raise click.Abort()
        except git.exc.GitCommandError as e:
            log_error(f"推送失败: {e}")
            raise click.Abort()

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"refine commit 失败: {e}")
        raise click.Abort()


# ---------------------------------------------------------------------------
# 内部辅助：规范化 refine 文件路径
# ---------------------------------------------------------------------------

def _normalize_refine_path(fp: str, repo_dir: Path) -> str:
    """将用户传入的路径规范化为相对于仓库根目录的路径。

    支持以下格式自动转换：
    - 绝对路径：/Users/.../ai-driving/driving-base/refines/xxx.md → refines/xxx.md
    - 含仓库前缀：ai-driving/driving-base/refines/xxx.md → refines/xxx.md
    - 仅文件名：xxx.md → refines/xxx.md
    - 已是正确格式：refines/xxx.md → 不变
    """
    p = Path(fp)

    # 如果是绝对路径或包含仓库根目录前缀，尝试取相对路径
    try:
        rel = p.relative_to(repo_dir)
        return str(rel)
    except ValueError:
        pass

    # 如果路径以 ai-driving/ 开头（含仓库名前缀），剥离到仓库根目录之后的部分
    parts = p.parts
    try:
        # 找到 repo_dir 最后一级目录名在 parts 中的位置
        repo_dirname = repo_dir.name
        idx = next(i for i, part in enumerate(parts) if part == repo_dirname)
        return str(Path(*parts[idx + 1:]))
    except StopIteration:
        pass

    # 如果只传了文件名（无目录），自动补充 refines/ 前缀
    if len(p.parts) == 1 and p.suffix == ".md":
        return f"refines/{fp}"

    return fp


# ---------------------------------------------------------------------------
# 内部辅助：批量上报 refine 文件到 webhook
# ---------------------------------------------------------------------------

def _trigger_refine_webhook(
    config_manager: "ConfigManager",
    repo_name: str,
    repo_dir: Path,
    file_paths: List[str],
    event: str,
) -> None:
    """读取 refine_webhook 配置，逐文件解析 meta 并上报。

    仅上报能成功解析 frontmatter 的文件，其余静默跳过。
    """
    webhook_url = config_manager.load().refine_webhook
    if not webhook_url:
        import sys
        print("⚠️ refine_webhook 未配置，refine 事件未上报。请在 driving.config.json 中设置 refine_webhook", file=sys.stderr)
        return
    for fp in file_paths:
        f_path = repo_dir / fp
        if not f_path.exists():
            continue
        meta = _parse_refine_frontmatter(f_path)
        if meta:
            _report_to_webhook(webhook_url, repo_name, f_path, meta, event)


# ---------------------------------------------------------------------------
# refine merge 命令
# ---------------------------------------------------------------------------

@refine_group.command(name="merge")
@click.argument("repo_name")
@click.option("--file", "file_paths", multiple=True, required=True,
              help="已合并的 refine 文件路径（相对于仓库根目录），可多次指定")
@click.option("--changed-file", "changed_files", multiple=True, default=[],
              help="实际被修改的正式文件路径（相对于仓库根目录），可多次指定。未传时降级使用 target_file")
@click.option("--operator", "operator", default="",
              help="操作者名称，写入 REFINE_LOG 记录，默认取 refine 文件的 operator 字段")
@click.option("--trigger-source", "trigger_source", default="",
              help="本次合并操作的触发来源（gate / self / manual），上报 webhook 时使用")
@click.option("--trigger-reason", "trigger_reason", default="",
              help="本次合并操作的触发原因，上报 webhook 时使用")
@click.option("--no-push", is_flag=True, default=False, help="只 commit，不执行 push")
def refine_merge(repo_name: str, file_paths: tuple, changed_files: tuple, operator: str,
                 trigger_source: str, trigger_reason: str, no_push: bool):
    """完成 refine 合并收尾：追加 REFINE_LOG → 上报 webhook → 删除 refine 文件 → commit/push。

    在 AI 将变更内容写入正式文件后调用本命令，完成合并流程的剩余步骤。
    使用 --changed-file 指定实际修改的文件（可多个），未指定时降级使用 refine 的 target_file。
    使用 --trigger-source / --trigger-reason 指定本次合并操作的触发来源和原因，上报 webhook 时使用。

    示例：
        driving refine merge driving-base --file refines/2026-06-01-rule-gate-spec-trigger-field.md
        driving refine merge driving-base --file refines/2026-06-01-rule-a.md --file refines/2026-06-01-rule-b.md
        driving refine merge driving-base --file refines/2026-06-01-rule-a.md --changed-file skills/dev-design/references/dev-design.md
        driving refine merge driving-base --file refines/2026-06-01-rule-a.md --trigger-source manual --trigger-reason "用户主动合并"
        driving refine merge driving-base --file refines/2026-06-01-rule-a.md --no-push
    """
    import datetime as dt

    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        repo_cfg = config_manager.get_repo(repo_name)
        if repo_cfg is None:
            log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
            raise click.Abort()

        repo_dir = config_manager.get_repo_dir(repo_name)

        # 校验文件存在并解析 meta
        items: List[Dict] = []
        for fp in file_paths:
            fp = _normalize_refine_path(fp, repo_dir)
            f_path = repo_dir / fp
            if not f_path.exists():
                log_error(
                    f"文件不存在：{fp}\n"
                    f"  期望路径（相对于仓库根目录）：refines/<文件名>.md\n"
                    f"  实际查找路径：{f_path}"
                )
                raise click.Abort()
            meta = _parse_refine_frontmatter(f_path)
            if meta is None:
                log_error(f"无法解析 frontmatter，请检查文件格式：{fp}")
                raise click.Abort()
            items.append({"fp": fp, "f_path": f_path, "meta": meta})

        # 展示待处理清单
        click.echo(f"\n待合并 refine（共 {len(items)} 个）：")
        for item in items:
            click.echo(f"  {item['fp']}  [{item['meta']['target_type']}] {item['meta']['target_name']}")

        click.echo("")
        confirmed = click.confirm("确认执行合并收尾？", default=True)
        if not confirmed:
            log_info("已取消")
            return

        today = dt.date.today().strftime("%Y-%m-%d")
        log_file = _get_refine_log_path(config_manager, repo_name)

        # Step 1: 逐文件追加 REFINE_LOG
        for item in items:
            meta = item["meta"]
            op = operator or meta.get("operator", "AI")
            entry = (
                f"[{today}] [合并] "
                f"{meta['target_type']}:{meta['target_name']} — "
                f"{meta['description']} (operator: {op})"
            )
            if log_file.exists():
                existing = log_file.read_text(encoding="utf-8")
                separator = "" if existing.endswith("\n") else "\n"
                log_file.write_text(existing + separator + entry + "\n", encoding="utf-8")
            else:
                log_file.write_text(_REFINE_LOG_HEADER + "\n" + entry + "\n", encoding="utf-8")
                log_info(f"已创建 {repo_name}/REFINE_LOG.md")
            log_success(f"已追加 REFINE_LOG：{meta['target_name']}")

        # Step 2: 上报 webhook（删除文件前，此时文件仍存在）
        webhook_url = config_manager.load().refine_webhook
        if webhook_url:
            for item in items:
                # 用本次合并操作的触发信息覆盖提案生成时的 trigger
                merge_meta = dict(item["meta"])
                if trigger_source or trigger_reason:
                    merge_meta["trigger"] = {
                        "source": trigger_source,
                        "reason": trigger_reason,
                    }
                _report_to_webhook(webhook_url, repo_name, item["f_path"], merge_meta, "refine.merged")

        # Step 3: 删除 refine 文件
        for item in items:
            item["f_path"].unlink()
            log_info(f"已删除：{item['fp']}")

        # Step 4: git commit + push（跳过 local 仓库）
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_name}' 是本地仓库，跳过 git 操作")
            return

        try:
            repo = git.Repo(repo_dir)
        except git.exc.InvalidGitRepositoryError:
            log_error(f"仓库 '{repo_name}' 目录不是有效的 git 仓库：{repo_dir}")
            raise click.Abort()

        # 收集需要提交的文件：REFINE_LOG.md + --changed-file 指定的正式文件 + 已删除的 refine 文件
        # 仅使用 --changed-file 参数，未传时提示用户确认（期望必填）
        target_files = []
        if changed_files:
            for cf in changed_files:
                cf_norm = _normalize_refine_path(cf, repo_dir)
                abs_cf = repo_dir / cf_norm
                if abs_cf.exists():
                    target_files.append(cf_norm)
                else:
                    log_warning(f"--changed-file 指定的文件不存在，跳过：{cf_norm}")
        else:
            log_warning("未指定 --changed-file，正式文件将不会被 commit。")
            click.echo("  建议使用 --changed-file <path> 指定本次实际修改的文件（可多次指定）。")
            confirmed_skip = click.confirm("  确认不提交正式文件，继续执行？", default=False)
            if not confirmed_skip:
                log_info("已取消，请补充 --changed-file 参数后重试")
                return

        files_to_commit = ["REFINE_LOG.md"] + target_files + [item["fp"] for item in items]

        # git add（含已删除文件）
        try:
            add_files = ["REFINE_LOG.md"] + target_files
            if add_files:
                repo.index.add(add_files)
            # 已删除的文件用 git rm 从索引移除
            for item in items:
                try:
                    repo.index.remove([item["fp"]])
                except Exception:
                    pass  # 文件可能未被追踪，忽略
            if target_files:
                log_info(f"已暂存变更（含正式文件：{', '.join(target_files)}）")
            else:
                log_info(f"已暂存变更")
        except Exception as e:
            log_error(f"git add 失败: {e}")
            raise click.Abort()

        # 自动生成 commit message，格式：target_name: description
        parts = [
            f"{item['meta']['target_name']}: {item['meta']['description']}"
            if item["meta"].get("description")
            else item["meta"]["target_name"]
            for item in items
        ]
        summary = "; ".join(parts[:3])
        if len(parts) > 3:
            summary += f" 等 {len(parts)} 个"
        commit_message = f"refine(merge): {summary}"

        try:
            repo.index.commit(commit_message)
            log_success(f"已提交：{commit_message}")
        except Exception as e:
            log_error(f"git commit 失败: {e}")
            raise click.Abort()

        if no_push:
            log_info("已跳过 push（--no-push）")
            return

        if not repo.remotes:
            log_warning(f"仓库 '{repo_name}' 未配置远程仓库，跳过 push")
            return

        do_push = click.confirm("\n确认 push 到远端？", default=True)
        if not do_push:
            log_info("已跳过 push")
            return

        try:
            log_info(f"正在推送仓库 '{repo_name}'...")
            ok, err = push_with_upstream(repo)
            if ok:
                log_success(f"仓库 '{repo_name}' 推送成功")
            else:
                log_error(f"推送失败：{err}")
                raise click.Abort()
        except git.exc.GitCommandError as e:
            log_error(f"推送失败: {e}")
            raise click.Abort()

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"refine merge 失败: {e}")
        raise click.Abort()




@refine_group.group(name="log")
def refine_log_group():
    """管理 REFINE_LOG.md 变更记录

    - 追加一条已生效的变更记录\n
    - 读取当前记录内容
    """
    pass


@refine_log_group.command(name="append")
@click.argument("repo_name")
@click.argument("entry")
def refine_log_append(repo_name: str, entry: str):
    """追加一条变更记录到 REFINE_LOG.md。

    若文件不存在则自动创建并写入文件头。
    ENTRY 格式建议：

        [YYYY-MM-DD] [即时|合并] <target_type>:<target_name> — <描述> (operator: <触发者>)

    示例：

        driving refine log append driving "[2026-05-26] [即时] agent:android-review-workflow MEMORY — 沉淀 RecyclerView 嵌套滚动冲突处理经验 (operator: 张三)"

        driving refine log append driving-base "[2026-05-26] [合并] rule:code-style — 新增 Kotlin 协程异常处理规范 (operator: AI 自主发现)"
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        repo_cfg = config_manager.get_repo(repo_name)
        if repo_cfg is None:
            log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
            raise click.Abort()

        log_file = _get_refine_log_path(config_manager, repo_name)

        if log_file.exists():
            existing = log_file.read_text(encoding="utf-8")
            # 保证条目之间有换行分隔
            separator = "" if existing.endswith("\n") else "\n"
            log_file.write_text(existing + separator + entry.rstrip() + "\n", encoding="utf-8")
        else:
            # 首次创建：写入文件头再追加条目
            log_file.write_text(
                _REFINE_LOG_HEADER + "\n" + entry.rstrip() + "\n",
                encoding="utf-8",
            )
            log_info(f"已创建 {repo_name}/REFINE_LOG.md")

        log_success(f"已追加到 {repo_name}/REFINE_LOG.md")
        click.echo(f"file: REFINE_LOG.md")

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"追加 refine log 失败: {e}")
        raise click.Abort()


@refine_log_group.command(name="get")
@click.argument("repo_name")
def refine_log_get(repo_name: str):
    """读取指定仓库的 REFINE_LOG.md 内容。

    示例：
        driving refine log get driving
        driving refine log get driving-base
    """
    try:
        project_root = find_project_root()
        config_manager = ConfigManager(project_root)

        repo_cfg = config_manager.get_repo(repo_name)
        if repo_cfg is None:
            log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
            raise click.Abort()

        log_file = _get_refine_log_path(config_manager, repo_name)

        if not log_file.exists():
            click.echo("")
            return

        click.echo(log_file.read_text(encoding="utf-8"))

    except click.Abort:
        raise
    except Exception as e:
        log_error(f"读取 refine log 失败: {e}")
        raise click.Abort()
