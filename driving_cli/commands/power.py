"""Power 子命令组 - 管理 driving.power.json

提供 driving power <subcommand> 系列命令，用于安装、卸载、列出、更新 power 条目。
Power 模式允许将多个目录下的 driving.config.json 合并使用，解决多分支配置冲突问题。
"""

import json as _json
from typing import Optional

import click

from driving_cli.models.power_config import PowerEntry
from driving_cli.utils.config_manager import PowerManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning
from driving_cli.utils.validators import infer_repo_name_from_url, validate_git_url, validate_repo_name


@click.group(name="power")
def power_group():
    """Power 配置管理（合并多个 driving.config.json）

    Power 模式：在项目根目录创建 driving.power.json，列出多个包含
    driving.config.json 的目录，driving-cli 运行时自动合并所有配置。

    适用场景：项目有多个分支，各分支有独立的 driving.config.json，
    通过 power 合并后无需跨分支合并配置文件。

    示例：
        driving power install --url https://git.xxx.com/config.git
        driving power install --url https://git.xxx.com/config.git --name feature
        driving power install --name main --path ai-driving/my-local
        driving power install
        driving power pull
        driving power list
        driving power uninstall feature
    """
    pass


# ==================== power install ====================

@power_group.command(name="install")
@click.option("--url", default=None, help="远程 Git 仓库地址（作为 submodule 安装）")
@click.option("--name", "power_name", default=None, help="Power 名称（唯一标识，不指定则从 URL 推断）")
@click.option("--path", "power_path", default=None, help="本地目录路径（--url 时可选，默认 ai-driving/<name>；本地模式时必填）")
@click.option("--description", default=None, help="Power 描述")
@click.option("--force", is_flag=True, default=False, help="强制覆盖已存在的同名 power（仅有参数时有效）")
def power_install(url: Optional[str], power_name: Optional[str], power_path: Optional[str], description: Optional[str], force: bool):
    """安装 power 条目

    无参数：读取 driving.power.json，初始化所有未就绪的 power。\n
    --url：将远程仓库作为 git submodule 安装，仓库根目录须包含 driving.config.json。\n
    --path：注册已存在的本地目录，目录下须包含 driving.config.json。\n

    示例：
        driving power install
        driving power install --url https://git.xxx.com/config.git
        driving power install --url https://git.xxx.com/config.git --name feature
        driving power install --url https://git.xxx.com/config.git --force
        driving power install --name main --path ai-driving/my-local
    """
    project_root = find_project_root()
    pm = PowerManager(project_root)

    # ---- 无参数模式：初始化所有未就绪的 power ----
    if url is None and power_path is None:
        if not pm.exists():
            log_error("driving.power.json 不存在，当前未启用 Power 模式")
            log_info("如需安装远程 power，请使用 --url 参数：driving power install --url <url>")
            raise click.Abort()
        _install_all_uninitialized(pm, project_root)
        return

    # ---- 远程模式 ----
    if url is not None:
        if not validate_git_url(url):
            log_error(f"Git URL 格式不合法：{url}")
            raise click.Abort()

        # 推断 name
        if power_name is None:
            power_name = infer_repo_name_from_url(url)
            log_info(f"自动推断 power 名称：{power_name}")
        elif not validate_repo_name(power_name):
            log_error("Power 名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
            raise click.Abort()

        # 推断安装路径
        install_path = power_path if power_path else f"ai-driving/{power_name}"
        abs_install_path = project_root / install_path
        config_json_path = abs_install_path / "driving.config.json"

        # 判断当前状态，决定执行路径
        dir_exists = abs_install_path.exists() and abs_install_path.is_dir() and any(abs_install_path.iterdir())
        already_registered = False
        if pm.exists():
            try:
                existing_cfg = pm.load_power_config()
                already_registered = any(p.name == power_name for p in existing_cfg.powers)
            except ValueError:
                pass

        # 情况 4：目录存在 + 已注册 + 有 driving.config.json → 已完整安装
        if dir_exists and already_registered and config_json_path.exists():
            if not force:
                log_info(f"Power '{power_name}' 已完整安装（路径：{install_path}）")
                log_info("如需重新安装，请使用 --force")
                return
            # --force：移除注册记录，重新走安装流程
            log_warning(f"--force：重新安装 power '{power_name}'")
            try:
                pm.remove_power(power_name)
            except ValueError:
                pass

        # 查找 git 根目录（clone 和注册都需要）
        try:
            from driving_cli.utils.git_helper import find_git_root
            git_root = find_git_root(project_root)
        except Exception:
            log_error("当前目录不在 Git 仓库中，请先执行 git init")
            raise click.Abort()

        entry = PowerEntry(name=power_name, path=install_path, url=url, description=description)

        # 情况 1：目录不存在 → clone
        if not dir_exists:
            log_info(f"正在安装远程 power '{power_name}'...")
            log_info(f"仓库地址：{url}")
            log_info("正在 clone 远程仓库，请稍候...")
            try:
                pm.add_power_remote(entry, git_root)
            except ValueError as e:
                log_error(str(e))
                raise click.Abort()
            log_success(f"远程 power '{power_name}' clone 成功！")
            log_info(f"安装路径：{install_path}")
            try:
                submodule_path = str(abs_install_path.relative_to(git_root))
            except ValueError:
                submodule_path = install_path
            log_info("下一步提交 submodule：")
            log_info(f"  git add .gitmodules {submodule_path}")
            log_info(f"  git commit -m 'Add power {power_name}'")
            # clone 完成后检查 driving.config.json
            if config_json_path.exists():
                log_success("driving.config.json 已就绪，power 配置完整 ✓")
                return
            # 没有 driving.config.json，fall through 到情况 3 提示

        # 情况 2：目录存在但未注册 → 注册到 driving.power.json
        elif not already_registered:
            log_info(f"检测到本地目录 '{install_path}'，注册为 power '{power_name}'...")
            try:
                if pm.exists():
                    power_cfg = pm.load_power_config()
                else:
                    from driving_cli.models.power_config import PowerConfig
                    power_cfg = PowerConfig(powers=[])
                power_cfg.powers.append(entry)
                pm.save_power_config(power_cfg)
            except ValueError as e:
                log_error(str(e))
                raise click.Abort()
            log_success(f"Power '{power_name}' 已注册到 driving.power.json")
            if config_json_path.exists():
                log_success("driving.config.json 已就绪，power 配置完整 ✓")
                return
            # 没有 driving.config.json，fall through 到情况 3 提示

        # 情况 3：已注册但无 driving.config.json → 提示用户运行 repo install
        log_warning(f"Power '{power_name}' 已注册，但 '{install_path}/driving.config.json' 不存在")
        log_info("请运行以下命令安装仓库并生成配置文件：")
        log_info(f"  driving repo install --power {power_name}")
        return

    # ---- 本地模式 ----
    if power_name is None:
        log_error("本地模式下请通过 --name 指定 power 名称")
        raise click.Abort()
    if not validate_repo_name(power_name):
        log_error("Power 名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
        raise click.Abort()

    entry = PowerEntry(name=power_name, path=power_path, url=None, description=description)

    try:
        pm.add_power_local(entry)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"本地 power '{power_name}' 已安装（路径：{power_path}）")


def _install_all_uninitialized(pm: PowerManager, project_root):
    """无参数 power install：初始化所有未就绪的 power"""
    import git

    try:
        power_cfg = pm.load_power_config()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    if not power_cfg.powers:
        log_info("driving.power.json 中没有配置任何 power")
        return

    # remote power 需要 git 根目录
    has_remote = any(p.type == "remote" for p in power_cfg.powers)
    git_root = None
    if has_remote:
        try:
            from driving_cli.utils.git_helper import find_git_root
            git_root = find_git_root(project_root)
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中，请先执行 git init")
            raise click.Abort()

    initialized_count = 0
    skipped_count = 0

    for entry in power_cfg.powers:
        power_dir = project_root / entry.path

        # ---- local power ----
        if entry.type == "local":
            if power_dir.exists():
                log_info(f"Power '{entry.name}'（本地）已就绪，跳过")
                skipped_count += 1
            else:
                log_warning(f"Power '{entry.name}'（本地）目录不存在：{entry.path}，跳过")
                skipped_count += 1
            continue

        # ---- remote power ----
        dir_initialized = power_dir.exists() and power_dir.is_dir() and any(power_dir.iterdir())

        if dir_initialized:
            log_info(f"Power '{entry.name}' 已初始化，跳过")
            skipped_count += 1
            continue

        log_info(f"正在初始化 power '{entry.name}'...")

        # 计算相对于 git 根目录的 submodule 路径
        try:
            submodule_path = str((project_root / entry.path).relative_to(git_root))
        except (ValueError, TypeError):
            submodule_path = entry.path

        git_repo = git.Repo(git_root)

        # 优先 update --init（.gitmodules 中已注册的情况）
        try:
            git_repo.git.submodule("update", "--init", submodule_path)
            log_success(f"Power '{entry.name}' 初始化成功")
            initialized_count += 1
            continue
        except git.exc.GitCommandError as e:
            stderr_msg = e.stderr.strip() if e.stderr else str(e)
            log_info(f"submodule update --init 失败，尝试重新添加（原因：{stderr_msg}）")

        # 降级：submodule add（首次添加）
        if not entry.url:
            log_error(f"Power '{entry.name}' 缺少 URL，无法添加 submodule")
            continue

        from driving_cli.utils.config_manager import PowerManager as _PM
        # 复用 config_manager 里的清理逻辑
        pm._cleanup_stale_git_modules(git_root, submodule_path)
        try:
            (git_root / submodule_path).parent.mkdir(parents=True, exist_ok=True)
            from driving_cli.commands.repo import _set_submodule_ignore
            git_repo.git.submodule("add", "--force", entry.url, submodule_path)
            _set_submodule_ignore(git_root, submodule_path)
            log_success(f"Power '{entry.name}' 添加并初始化成功")
            initialized_count += 1
        except git.exc.GitCommandError as e:
            stderr_msg = e.stderr.strip() if e.stderr else str(e)
            log_error(f"Power '{entry.name}' 初始化失败：{stderr_msg}")

    log_info(f"完成：初始化 {initialized_count} 个，跳过 {skipped_count} 个")


# ==================== power pull ====================

@power_group.command(name="pull")
@click.argument("power_name", required=False, default=None)
def power_pull(power_name: Optional[str]):
    """拉取远程 power 的最新内容

    不指定名称则更新所有远程 power。
    本地 power 会跳过并给出提示。

    示例：
        driving power pull
        driving power pull feature
    """
    project_root = find_project_root()
    pm = PowerManager(project_root)

    if not pm.exists():
        log_error("driving.power.json 不存在，当前未启用 Power 模式")
        raise click.Abort()

    try:
        power_cfg = pm.load_power_config()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    targets = power_cfg.powers
    if power_name is not None:
        targets = [p for p in targets if p.name == power_name]
        if not targets:
            log_error(f"Power '{power_name}' 不存在，使用 'driving power list' 查看已配置的 power")
            raise click.Abort()

    for entry in targets:
        if entry.type == "local":
            log_warning(f"Power '{entry.name}' 是本地 power，跳过 pull 操作")
            continue
        log_info(f"正在拉取 power '{entry.name}'...")
        try:
            ok = pm.pull_power(entry.name)
            if ok:
                log_success(f"Power '{entry.name}' 拉取成功")
            else:
                log_warning(f"Power '{entry.name}' 目录不存在，跳过")
        except ValueError as e:
            log_error(str(e))


# ==================== power uninstall ====================

@power_group.command(name="uninstall")
@click.argument("power_name")
def power_uninstall(power_name: str):
    """卸载一个 power 条目（仅修改 driving.power.json，不删除目录或 submodule）

    示例：
        driving power uninstall feature
    """
    project_root = find_project_root()
    pm = PowerManager(project_root)

    if not pm.exists():
        log_error("driving.power.json 不存在，当前未启用 Power 模式")
        raise click.Abort()

    try:
        pm.remove_power(power_name)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"Power '{power_name}' 已卸载")
    log_info("注意：submodule 目录和 .gitmodules 条目未删除，如需完全移除请手动执行 git submodule deinit")


# ==================== power list ====================

@power_group.command(name="list")
def power_list():
    """列出所有已配置的 power 条目

    示例：
        driving power list
    """
    project_root = find_project_root()
    pm = PowerManager(project_root)

    if not pm.exists():
        log_info("driving.power.json 不存在，当前使用传统模式（直接读取 driving.config.json）")
        return

    try:
        power_cfg = pm.load_power_config()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    if not power_cfg.powers:
        log_info("driving.power.json 中没有配置任何 power")
        return

    result = []
    for entry in power_cfg.powers:
        config_path = project_root / entry.path / "driving.config.json"
        result.append({
            "name": entry.name,
            "type": entry.type,
            "url": entry.url or "",
            "path": entry.path,
            "description": entry.description or "",
            "config_exists": config_path.exists(),
        })

    print(_json.dumps(result, ensure_ascii=False, indent=2))
