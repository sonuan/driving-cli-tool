"""Repo 子命令组 - 多仓库管理命令

提供 driving repo <subcommand> 系列命令，用于安装、列出、卸载仓库，
以及对远程仓库执行 git pull/commit/push 操作。
"""

from pathlib import Path
from typing import Optional

import click
import git

from driving_cli.models.config import RepoConfig
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.git_helper import (
    checkout_branch_after_install as _checkout_branch_after_install_impl,
    ensure_submodule_initialized,
    find_git_root,
    push_with_upstream,
)
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning
from driving_cli.utils.validators import (
    infer_repo_name_from_url,
    validate_git_url,
    validate_repo_name,
)


@click.group(name="repo")
def repo_group():
    """AI Coding 规范仓库管理（安装、列出、卸载、git 操作）

    支持远程仓库（git submodule）和本地仓库（软链接或普通目录）。

    示例：
        driving repo install --url https://github.com/org/repo
        driving repo install --local /path/to/local
        driving repo list
        driving repo uninstall my-repo
        driving repo pull
        driving repo push
    """
    pass


# ==================== repo install ====================

@repo_group.command(name="install")
@click.option("--url", default=None, help="远程 Git 仓库地址")
@click.option("--local", "local_path", default=None, is_flag=False, flag_value="", help="注册本地仓库（可选路径）")
@click.option("--name", "repo_name", default=None, help="自定义仓库名称")
@click.option("--description", "description", default=None, help="仓库描述，用于 AI 关键词匹配")
@click.option("--desc", "desc", default=None, help="仓库描述（--description 的简写）")
@click.option("--tag", "tags", multiple=True, help="新增仓库标签（可多次指定，如 --tag base --tag features）")
@click.option("--module", "modules", multiple=True, metavar="NAME:DESCRIPTION", help="新增业务模块（格式：name:description，可多次指定）")
@click.option("--force", is_flag=True, default=False, help="强制覆盖已存在的同名仓库")
@click.option("--power", "power_name", default=None, help="Power 模式下指定写入哪个 power 的 driving.config.json")
@click.option("--branch", default=None, help="指定分支（安装后自动 checkout；未配置时缺少 driving.config.json 会给出警告）")
def install(url: Optional[str], local_path: Optional[str], repo_name: Optional[str], description: Optional[str], desc: Optional[str], tags: tuple, modules: tuple, force: bool, power_name: Optional[str], branch: Optional[str]):
    """安装仓库

    无参数：读取配置初始化所有未初始化的远程仓库。\n
    --url：将远程 Git 仓库作为 submodule 安装。\n
    --local [path]：注册本地仓库（有路径则创建软链接，无路径则创建普通目录）。\n
    --tag <tag>：新增仓库标签（可多次指定）。\n
    --desc <desc>：仓库描述（--description 的简写）。\n
    --module <name:description>：新增业务模块（可多次指定）。\n
    --power <name>：Power 模式下指定写入哪个 power 的配置文件（不指定则写入第一个 power）。\n
    --branch <branch>：指定仓库分支，安装后自动 checkout；未配置时若缺少 driving.config.json 会给出警告。\n
    """
    from driving_cli.utils.config_manager import PowerManager
    project_root = find_project_root()

    # --desc 是 --description 的简写，优先使用 --description
    effective_description = description if description is not None else desc

    # 解析 --module name:description 参数
    from driving_cli.models.config import ModuleConfig
    parsed_modules = []
    for mod_str in modules:
        if ":" in mod_str:
            mod_name, mod_desc = mod_str.split(":", 1)
        else:
            mod_name, mod_desc = mod_str, ""
        mod_name = mod_name.strip()
        mod_desc = mod_desc.strip()
        if mod_name:
            parsed_modules.append(ModuleConfig(name=mod_name, description=mod_desc))

    # 解析写入目标 ConfigManager
    pm = PowerManager(project_root)
    if pm.exists():
        # Power 模式：路由到指定 power 或默认 power
        try:
            if power_name:
                config_mgr = pm.get_config_manager_for(power_name)
            else:
                config_mgr = pm.get_default_config_manager()
                default_entry = pm.load_power_config().powers[0]
                log_info(f"Power 模式：写入 power '{default_entry.name}'（{default_entry.path}/driving.config.json）")
                log_info("如需写入其他 power，请使用 --power <name> 指定")
        except ValueError as e:
            from driving_cli.utils.logger import log_error
            log_error(str(e))
            raise click.Abort()
    else:
        # 传统模式
        config_mgr = ConfigManager(project_root)

    # 无参数模式：初始化所有未初始化的远程仓库
    if url is None and local_path is None:
        _install_all_uninitialized(config_mgr, project_root)
        return

    # 安装远程仓库
    if url is not None:
        _install_remote(config_mgr, project_root, url, repo_name, force, effective_description,
                        list(tags) or None, parsed_modules or None, branch=branch)
        return

    # 注册本地仓库（local_path 为 "" 表示 --local 无值，为具体路径表示有值）
    _install_local(config_mgr, project_root, local_path, repo_name, force, effective_description,
                   list(tags) or None, parsed_modules or None)


def _set_submodule_config(git_root: Path, submodule_path: str, key: str, value: str):
    """在 .gitmodules 中为指定 submodule 设置任意 key = value

    若该 key 已存在则跳过（幂等），不存在则追加到 section 末尾。
    缩进风格自动跟随文件现有风格。
    """
    gitmodules_path = git_root / ".gitmodules"
    if not gitmodules_path.exists():
        return

    lines = gitmodules_path.read_text(encoding="utf-8").splitlines(keepends=True)

    # 定位目标 submodule 块
    section_header = None
    for i, line in enumerate(lines):
        if line.strip().startswith("[submodule") and submodule_path in line:
            section_header = i
            break

    if section_header is None:
        log_warning(f"未在 .gitmodules 中找到 submodule '{submodule_path}'，跳过 {key} 设置")
        return

    # 扫描 section 内容，检查 key 是否已存在
    i = section_header + 1
    insert_pos = len(lines)
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("["):
            insert_pos = i
            break
        # key 匹配：去掉空格后以 "key" 或 "key=" 开头
        if stripped == key or stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            log_info(f"submodule '{submodule_path}' 已有 {key} 配置，跳过")
            return
        i += 1

    # 检测缩进风格
    indent = "\t"
    for j in range(section_header + 1, insert_pos):
        if lines[j].strip() and not lines[j].startswith("["):
            indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
            break

    lines.insert(insert_pos, f"{indent}{key} = {value}\n")
    gitmodules_path.write_text("".join(lines), encoding="utf-8")
    log_info(f"已为 submodule '{submodule_path}' 设置 {key} = {value}")


def _set_submodule_ignore(git_root: Path, submodule_path: str):
    """为 submodule 设置 ignore = all 和 fetchRecurseSubmodules = false

    - ignore = all：主项目 git status/diff 不显示 submodule 变更
    - fetchRecurseSubmodules = false：主项目 fetch/pull 不自动拉取 submodule 远端
    """
    _set_submodule_config(git_root, submodule_path, "ignore", "all")
    _set_submodule_config(git_root, submodule_path, "fetchRecurseSubmodules", "false")


def _cleanup_stale_git_modules(git_root: Path, submodule_path: str):
    """清理残留的 .git/modules 数据

    当 submodule 的工作目录不存在，但 .git/modules 中有残留数据时，
    自动清理以避免 git submodule add 报错。

    清理规则：
    - .git/modules/ai-driving 存在但 ai-driving/ 不存在 → 清理整个 modules/ai-driving
    - .git/modules/ai-driving/<name> 存在但 ai-driving/<name>/ 不存在 → 只清理该子目录
    """
    import shutil

    modules_dir = git_root / ".git" / "modules"
    parts = Path(submodule_path).parts  # e.g. ('ai-driving', 'driving')

    # 从最深层往上检查，找到需要清理的最小范围
    for depth in range(len(parts), 0, -1):
        partial_path = Path(*parts[:depth])
        modules_path = modules_dir / partial_path
        work_path = git_root / partial_path

        # 工作目录不存在，或存在但为空（视为未初始化）
        work_dir_empty = not work_path.exists() or (work_path.is_dir() and not any(work_path.iterdir()))
        if modules_path.exists() and work_dir_empty:
            log_warning(f"检测到残留 git modules 数据：{modules_path}，正在清理...")
            shutil.rmtree(modules_path)
            log_info(f"已清理：{modules_path}")
            break  # 清理最小范围后停止


def _checkout_branch_after_install(repo_dir: Path, repo_name: str, branch: str):
    """submodule 安装/初始化后切换到指定分支（委托给 git_helper.checkout_branch_after_install）"""
    _checkout_branch_after_install_impl(repo_dir, repo_name, branch)


def _install_all_uninitialized(config_mgr: ConfigManager, project_root: Path):
    """无参数 install：初始化所有未初始化的远程仓库"""
    try:
        repos = config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    # 过滤出 remote 类型仓库
    remote_repos = [r for r in repos if r.type == "remote"]

    if not remote_repos:
        log_info("配置中没有远程仓库，无需初始化")
        return

    # 查找 git 根目录
    try:
        git_root = find_git_root(project_root)
    except git.exc.InvalidGitRepositoryError:
        log_error("当前目录不在 Git 仓库中，请先执行 git init")
        raise click.Abort()

    initialized_count = 0
    skipped_count = 0

    for repo_cfg in remote_repos:
        repo_dir = project_root / repo_cfg.path
        # 检查目录是否已初始化（非空目录）
        if repo_dir.exists() and any(repo_dir.iterdir()):
            log_info(f"仓库 '{repo_cfg.name}' 已初始化，跳过")
            skipped_count += 1
            continue

        log_info(f"正在初始化仓库 '{repo_cfg.name}'...")

        # 计算相对于 git 根目录的 submodule 路径
        try:
            submodule_path = str((project_root / repo_cfg.path).relative_to(git_root))
        except ValueError:
            submodule_path = repo_cfg.path

        ok = ensure_submodule_initialized(
            project_root=project_root,
            git_root=git_root,
            rel_path=submodule_path,
            url=repo_cfg.url or "",
            branch=repo_cfg.branch or "",
            label=f"仓库 '{repo_cfg.name}'",
        )
        # ensure_submodule_initialized 内部对 submodule add 后会调用 git_helper 的 checkout；
        # 但 ignore 设置需要在此补充（repo 语义特有）
        if ok:
            _set_submodule_ignore(git_root, submodule_path)
            initialized_count += 1

    log_info(f"完成：初始化 {initialized_count} 个，跳过 {skipped_count} 个")


def _migrate_local_to_remote(config_mgr: ConfigManager, project_root: Path, repo_cfg: "RepoConfig", remote_url: str):
    """将本地仓库迁移到远程：添加 remote origin 并推送，再清理本地目录

    迁移步骤：
    1. 找到本地仓库目录（软链接指向的真实路径或普通目录）
    2. 添加 remote origin（若已存在则跳过）
    3. 推送当前分支到远程
    4. 仅推送成功后才删除本地目录，为后续 submodule add 腾出位置
    """
    # 确定本地仓库的真实路径
    if repo_cfg.local_path:
        local_dir = Path(repo_cfg.local_path)
    else:
        local_dir = project_root / repo_cfg.path
        if local_dir.is_symlink():
            local_dir = local_dir.resolve()

    if not local_dir.exists():
        log_warning(f"本地仓库目录不存在：{local_dir}，跳过推送步骤")
        return

    try:
        local_repo = git.Repo(local_dir)
    except git.exc.InvalidGitRepositoryError:
        # 不是 git 仓库，自动初始化并提交所有内容
        log_info(f"'{local_dir}' 不是 git 仓库，自动执行 git init + commit...")
        try:
            local_repo = git.Repo.init(local_dir)
            # 写入 .gitignore 排除嵌套 .git 目录，避免 GitLab fsck 拒绝
            gitignore = local_dir / ".gitignore"
            ignore_content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
            if ".git" not in ignore_content:
                with open(gitignore, "a", encoding="utf-8") as f:
                    f.write("\n# auto-added by driving\n**/.git\n")
            files_to_add = [
                str(p.relative_to(local_dir))
                for p in local_dir.rglob("*")
                if p.is_file() and ".git" not in p.parts
            ]
            if files_to_add:
                local_repo.index.add(files_to_add)
            local_repo.index.commit("init by driving cli")
            log_success("已自动初始化并提交本地内容")
        except Exception as e:
            log_error(f"自动初始化失败: {e}")
            raise click.Abort()

    # 添加或更新 remote origin
    try:
        if "origin" in [r.name for r in local_repo.remotes]:
            local_repo.remotes.origin.set_url(remote_url)
            log_info(f"已更新 remote origin：{remote_url}")
        else:
            local_repo.create_remote("origin", remote_url)
            log_info(f"已添加 remote origin：{remote_url}")
    except Exception as e:
        log_error(f"设置 remote 失败: {e}")
        raise click.Abort()

    # 推送当前分支
    if local_repo.head.is_detached or not local_repo.head.is_valid():
        log_error("本地仓库无有效分支，无法推送，请先提交内容后再迁移")
        raise click.Abort()

    try:
        branch = local_repo.active_branch.name
        log_info(f"正在推送分支 '{branch}' 到远程，请稍候...")
        push_infos = local_repo.remotes.origin.push(refspec=f"{branch}:{branch}", set_upstream=True)
        # 检查推送结果，gitpython 在某些错误下不抛异常，需手动检查 flags
        for info in push_infos:
            if info.flags & info.ERROR:
                log_error(f"推送失败：{info.summary.strip()}")
                raise click.Abort()
        log_success(f"推送成功：{branch} → {remote_url}")
    except git.exc.GitCommandError as e:
        log_error(f"推送失败: {e}")
        raise click.Abort()

    # 仅推送成功后才清理本地目录/软链接，为 submodule add 腾出位置
    install_dir = project_root / repo_cfg.path
    if install_dir.is_symlink():
        install_dir.unlink()
    elif install_dir.exists():
        import shutil
        shutil.rmtree(install_dir)
    log_info(f"已清理本地目录：{repo_cfg.path}")


def _install_remote(config_mgr: ConfigManager, project_root: Path, url: str, repo_name: Optional[str], force: bool, description: Optional[str] = None, tags: Optional[list] = None, modules: Optional[list] = None, branch: Optional[str] = None):
    """安装远程 Git 仓库（submodule）"""
    # 校验 Git URL 格式
    if not validate_git_url(url):
        log_error(f"Git URL 格式不合法：{url}")
        raise click.Abort()

    # 推断或校验仓库名称
    if repo_name is None:
        repo_name = infer_repo_name_from_url(url)
        log_info(f"自动推断仓库名称：{repo_name}")
    else:
        if not validate_repo_name(repo_name):
            log_error("仓库名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
            raise click.Abort()

    # 检查名称是否已存在
    existing = config_mgr.get_repo(repo_name)
    if existing is not None:
        if existing.type == "local" and not force:
            # 本地仓库迁移到远程：提示用户确认
            log_info(f"检测到本地仓库 '{repo_name}'，将推送内容到远程并切换为 submodule")
            confirmed = click.confirm("是否继续？", default=False)
            if not confirmed:
                raise click.Abort()
            _migrate_local_to_remote(config_mgr, project_root, existing, url)
        elif not force:
            log_error(f"仓库 '{repo_name}' 已存在，使用 --force 覆盖")
            raise click.Abort()
        else:
            log_warning(f"强制覆盖已存在的仓库 '{repo_name}'")
        try:
            config_mgr.remove_repo(repo_name)
        except ValueError:
            pass

    # 查找 git 根目录
    try:
        git_root = find_git_root(project_root)
    except git.exc.InvalidGitRepositoryError:
        log_error("当前目录不在 Git 仓库中，请先执行 git init")
        raise click.Abort()

    git_repo = git.Repo(git_root)
    install_path = f"ai-driving/{repo_name}"

    # 计算相对于 git 根目录的路径（submodule 路径需相对于 git 根目录）
    try:
        rel_to_git = (project_root / "ai-driving" / repo_name).relative_to(git_root)
        submodule_path = str(rel_to_git)
    except ValueError:
        submodule_path = install_path

    log_info(f"正在添加远程仓库 '{repo_name}'...")
    log_info(f"仓库地址：{url}")

    # 清理残留的工作目录，避免 "destination path already exists" 报错
    abs_install_path = project_root / "ai-driving" / repo_name
    if abs_install_path.exists() and not abs_install_path.is_symlink():
        import shutil
        log_warning(f"检测到残留工作目录：{submodule_path}，正在清理...")
        shutil.rmtree(abs_install_path)
        log_info(f"已清理：{submodule_path}")

    # 清理残留的 .git/modules 数据（需在工作目录清理后执行，确保触发条件满足）
    _cleanup_stale_git_modules(git_root, submodule_path)

    log_info("正在 clone 远程仓库，请稍候...")
    try:
        git_repo.git.submodule("add", "--force", url, submodule_path)
    except git.exc.GitCommandError as e:
        err_str = str(e)
        # 主仓库尚无 commit 时，checkout 步骤会失败，但 clone 和 .gitmodules 写入已完成。
        # 检查 .gitmodules 中是否已有该 submodule 条目来判断 add 是否实际成功。
        if "yet to be born" in err_str or "unable to checkout" in err_str:
            gitmodules_path = git_root / ".gitmodules"
            if gitmodules_path.exists() and submodule_path in gitmodules_path.read_text(encoding="utf-8"):
                log_warning("主仓库尚无 commit，submodule 已注册但暂未 checkout，后续执行 'driving repo install' 可完成初始化")
            else:
                log_error(f"添加 submodule 失败: {e}")
                raise click.Abort()
        else:
            log_error(f"添加 submodule 失败: {e}")
            raise click.Abort()

    # 补充 ignore = all，让主项目忽略 submodule 内部变更
    _set_submodule_ignore(git_root, submodule_path)

    # 写入配置
    repo_cfg = RepoConfig(
        name=repo_name,
        type="remote",
        url=url,
        path=install_path,
        local_path=None,
        description=description,
        tags=tags if tags is not None else [],
        modules=modules,
        branch=branch,
    )
    try:
        config_mgr.add_repo(repo_cfg)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"远程仓库 '{repo_name}' 安装成功！")
    log_info(f"安装路径：{install_path}")

    # 安装后自动切换到指定分支
    if branch:
        _checkout_branch_after_install(project_root / install_path, repo_name, branch)

    log_info("下一步：")
    log_info(f"  git add .gitmodules {submodule_path}")
    log_info(f"  git commit -m 'Add repo {repo_name}'")


def _install_local(config_mgr: ConfigManager, project_root: Path, local_path: str, repo_name: Optional[str], force: bool, description: Optional[str] = None, tags: Optional[list] = None, modules: Optional[list] = None):
    """注册本地仓库（软链接或普通目录）"""
    # 确定仓库名称
    if repo_name is None:
        if local_path:
            # 从路径推断名称
            repo_name = Path(local_path).name
            # 清理非法字符
            import re
            repo_name = re.sub(r'[^a-zA-Z0-9_-]', '-', repo_name).strip('-')
            if not repo_name or not validate_repo_name(repo_name):
                repo_name = "local"
            log_info(f"自动推断仓库名称：{repo_name}")
        else:
            log_error("注册本地仓库时，请通过 --name 指定仓库名称，或提供本地路径")
            raise click.Abort()

    if not validate_repo_name(repo_name):
        log_error("仓库名称只允许字母、数字、连字符和下划线，且必须以字母或数字开头")
        raise click.Abort()

    # 检查名称是否已存在
    existing = config_mgr.get_repo(repo_name)
    if existing is not None:
        if not force:
            log_error(f"仓库 '{repo_name}' 已存在，使用 --force 覆盖")
            raise click.Abort()
        log_warning(f"强制覆盖已存在的仓库 '{repo_name}'")
        try:
            config_mgr.remove_repo(repo_name)
        except ValueError:
            pass

    install_dir = project_root / "ai-driving" / repo_name
    install_path = f"ai-driving/{repo_name}"

    if local_path:
        # 有路径：验证路径存在，创建软链接
        src_path = Path(local_path).resolve()
        if not src_path.exists():
            log_error(f"本地路径不存在：{local_path}")
            raise click.Abort()

        # 如果目标已存在，先删除
        if install_dir.exists() or install_dir.is_symlink():
            if install_dir.is_symlink():
                install_dir.unlink()
            else:
                import shutil
                shutil.rmtree(install_dir)

        # 确保父目录存在
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        install_dir.symlink_to(src_path)
        log_success(f"已创建软链接：{install_path} → {src_path}")
        stored_local_path = str(src_path)
    else:
        # 无路径：创建普通目录
        install_dir.mkdir(parents=True, exist_ok=True)
        log_success(f"已创建本地仓库目录：{install_path}")
        stored_local_path = None

    # 写入配置
    repo_cfg = RepoConfig(
        name=repo_name,
        type="local",
        url=None,
        path=install_path,
        local_path=stored_local_path,
        description=description,
        tags=tags if tags is not None else [],
        modules=modules,
    )
    try:
        config_mgr.add_repo(repo_cfg)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"本地仓库 '{repo_name}' 注册成功！")


# ==================== repo list ====================

@repo_group.command(name="list")
def repo_list():
    """查看已安装的仓库列表（JSON 格式输出）"""
    import json as _json
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    try:
        repos = config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    result = []
    for repo in repos:
        entry = {
            "name": repo.name,
            "type": repo.type,
            "description": repo.description or "",
            "path": repo.path,
        }
        result.append(entry)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


# ==================== repo uninstall ====================

@repo_group.command(name="uninstall")
@click.argument("repo_name")
def uninstall(repo_name: str):
    """卸载指定仓库

    移除远程仓库的 git submodule 或本地仓库的软链接/目录，并更新配置。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    # 查找仓库配置
    repo_cfg = config_mgr.get_repo(repo_name)
    if repo_cfg is None:
        log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
        raise click.Abort()

    repo_dir = project_root / repo_cfg.path

    if repo_cfg.type == "remote":
        # 移除 git submodule
        try:
            git_root = find_git_root(project_root)
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中")
            raise click.Abort()

        git_repo = git.Repo(git_root)

        # 计算相对于 git 根目录的 submodule 路径
        try:
            submodule_path = str((project_root / repo_cfg.path).relative_to(git_root))
        except ValueError:
            submodule_path = repo_cfg.path

        # 查找并移除 submodule
        submodule = None
        for sm in git_repo.submodules:
            if sm.path == submodule_path:
                submodule = sm
                break

        if submodule:
            log_info(f"正在移除 submodule '{repo_name}'...")
            try:
                submodule.remove()
                log_success(f"submodule '{repo_name}' 已移除")
            except Exception as e:
                log_warning(f"移除 submodule 时出现警告: {e}")
                # 尝试手动清理目录
                if repo_dir.exists():
                    import shutil
                    shutil.rmtree(repo_dir)
        else:
            log_warning(f"未找到 submodule '{submodule_path}'，尝试直接删除目录")
            if repo_dir.exists():
                import shutil
                shutil.rmtree(repo_dir)
                log_info(f"已删除目录：{repo_cfg.path}")

    elif repo_cfg.type == "local":
        # 移除软链接或目录
        if repo_dir.is_symlink():
            repo_dir.unlink()
            log_success(f"已移除软链接：{repo_cfg.path}")
        elif repo_dir.exists():
            import shutil
            shutil.rmtree(repo_dir)
            log_success(f"已删除目录：{repo_cfg.path}")
        else:
            log_warning(f"目录不存在，仅从配置中移除：{repo_cfg.path}")

    # 从配置中移除
    try:
        config_mgr.remove_repo(repo_name)
    except ValueError as e:
        log_error(str(e))
        raise click.Abort()

    log_success(f"仓库 '{repo_name}' 已卸载")


# ==================== repo pull ====================

@repo_group.command(name="pull")
@click.argument("repo_name", required=False, default=None)
def pull(repo_name: Optional[str]):
    """从远程拉取更新

    指定仓库名则只对该仓库执行；不指定则对所有 remote 仓库执行。
    local 类型仓库会跳过并给出提示。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    repos = _resolve_repos(config_mgr, repo_name, operation="pull")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 pull 操作")
            continue
        _git_pull(repo_cfg, project_root)


def _git_pull(repo_cfg: RepoConfig, project_root: Path):
    """对指定远程仓库执行 git pull"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        log_info("请先执行 'driving repo install' 初始化仓库")
        return

    log_info(f"正在拉取仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if repo.is_dirty(untracked_files=True):
            log_warning(f"仓库 '{repo_cfg.name}' 存在未提交的修改，请先提交后再拉取")
            return
        if not repo.remotes:
            log_error(f"仓库 '{repo_cfg.name}' 未配置远程仓库")
            return
        # 处理 detached HEAD
        if repo.head.is_detached:
            log_warning(f"仓库 '{repo_cfg.name}' 处于 detached HEAD 状态，尝试切换到 main/master")
            for branch in ("main", "master"):
                try:
                    repo.git.checkout(branch)
                    break
                except git.exc.GitCommandError:
                    continue
            else:
                log_error(f"无法切换分支，请手动处理仓库 '{repo_cfg.name}'")
                return

        current_branch = repo.active_branch.name
        repo.remotes.origin.pull(current_branch)
        log_success(f"仓库 '{repo_cfg.name}' 拉取成功")
    except git.exc.GitCommandError as e:
        log_error(f"仓库 '{repo_cfg.name}' 拉取失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 拉取失败: {e}")


# ==================== repo commit ====================

@repo_group.command(name="commit")
@click.argument("repo_name", required=False, default=None)
@click.argument("message", required=False, default=None)
def commit(repo_name: Optional[str], message: Optional[str]):
    """提交仓库修改

    指定仓库名则只对该仓库执行；不指定则对所有有未提交修改的 remote 仓库执行。
    local 类型仓库会跳过并给出提示。

    示例：
        driving repo commit my-repo "fix: update config"
        driving repo commit "fix: update all"
        driving repo commit
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    # 判断第一个参数是仓库名还是提交信息
    # 如果 repo_name 不是已知仓库名，则视为提交信息
    actual_repo_name = repo_name
    actual_message = message

    if repo_name is not None:
        existing = config_mgr.get_repo(repo_name)
        if existing is None:
            # repo_name 不是仓库名，视为提交信息
            actual_message = repo_name
            actual_repo_name = None

    # 获取默认提交信息
    if actual_message is None:
        try:
            cfg = config_mgr.load()
            actual_message = cfg.default_commit_message
        except ValueError:
            actual_message = "update by driving"

    repos = _resolve_repos(config_mgr, actual_repo_name, operation="commit")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 commit 操作")
            continue
        _git_commit(repo_cfg, project_root, actual_message)


def _git_commit(repo_cfg: RepoConfig, project_root: Path, message: str):
    """对指定远程仓库执行 git commit"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        return

    log_info(f"正在提交仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if not repo.is_dirty(untracked_files=True):
            log_info(f"仓库 '{repo_cfg.name}' 没有需要提交的修改，跳过")
            return
        repo.git.add(A=True)
        repo.index.commit(message)
        log_success(f"仓库 '{repo_cfg.name}' 提交成功：{message}")
    except git.exc.GitCommandError as e:
        log_error(f"仓库 '{repo_cfg.name}' 提交失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 提交失败: {e}")


# ==================== repo push ====================

@repo_group.command(name="push")
@click.argument("repo_name", required=False, default=None)
def push(repo_name: Optional[str]):
    """推送仓库到远程

    指定仓库名则只对该仓库执行；不指定则对所有 remote 仓库执行。
    local 类型仓库会跳过并给出提示。
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    repos = _resolve_repos(config_mgr, repo_name, operation="push")
    if repos is None:
        raise click.Abort()

    for repo_cfg in repos:
        if repo_cfg.type == "local":
            log_warning(f"仓库 '{repo_cfg.name}' 是本地仓库，跳过 push 操作")
            continue
        _git_push(repo_cfg, project_root)


def _git_push(repo_cfg: RepoConfig, project_root: Path):
    """对指定远程仓库执行 git push，自动处理无 upstream 分支的情况"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        return

    log_info(f"正在推送仓库 '{repo_cfg.name}'...")
    try:
        repo = git.Repo(repo_dir)
        if not repo.remotes:
            log_error(f"仓库 '{repo_cfg.name}' 未配置远程仓库")
            return
        ok, err = push_with_upstream(repo)
        if ok:
            log_success(f"仓库 '{repo_cfg.name}' 推送成功")
        else:
            log_error(f"仓库 '{repo_cfg.name}' 推送失败：{err}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 推送失败: {e}")


# ==================== repo checkout ====================

@repo_group.command(name="checkout")
@click.argument("repo_name")
@click.argument("branch")
def checkout(repo_name: str, branch: str):
    """切换仓库分支

    对指定仓库执行 git checkout <branch>，切换到目标分支。
    如果本地不存在该分支，会尝试从远程拉取。

    示例：
        driving repo checkout driving main
        driving repo checkout driving feature/new-skill
    """
    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    repo_cfg = config_mgr.get_repo(repo_name)
    if repo_cfg is None:
        log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
        raise click.Abort()

    if repo_cfg.type == "local":
        log_warning(f"仓库 '{repo_name}' 是本地仓库，跳过 checkout 操作")
        return

    _git_checkout(repo_cfg, project_root, branch)


def _git_checkout(repo_cfg: RepoConfig, project_root: Path, branch: str):
    """对指定远程仓库执行 git checkout"""
    repo_dir = project_root / repo_cfg.path
    if not repo_dir.exists():
        log_error(f"仓库 '{repo_cfg.name}' 目录不存在：{repo_cfg.path}")
        log_info("请先执行 'driving repo install' 初始化仓库")
        return

    log_info(f"正在切换仓库 '{repo_cfg.name}' 到分支 '{branch}'...")
    try:
        repo = git.Repo(repo_dir)
        if repo.is_dirty(untracked_files=True):
            log_warning(f"仓库 '{repo_cfg.name}' 存在未提交的修改，请先提交或暂存后再切换分支")
            return

        # 先尝试 fetch，确保远程分支信息最新
        if repo.remotes:
            try:
                repo.remotes.origin.fetch()
            except git.exc.GitCommandError as e:
                log_warning(f"仓库 '{repo_cfg.name}' fetch 失败，将使用本地分支信息（{e.stderr.strip() if e.stderr else str(e)}）")

        # 执行 checkout
        repo.git.checkout(branch)
        log_success(f"仓库 '{repo_cfg.name}' 已切换到分支 '{branch}'")
    except git.exc.GitCommandError as e:
        if "did not match any" in str(e) or "pathspec" in str(e):
            log_error(f"分支 '{branch}' 不存在，请检查分支名称")
        else:
            log_error(f"仓库 '{repo_cfg.name}' 切换分支失败: {e}")
    except Exception as e:
        log_error(f"仓库 '{repo_cfg.name}' 切换分支失败: {e}")


# ==================== repo load ====================

@repo_group.command(name="load")
@click.argument("keywords", nargs=-1, required=False)
def load(keywords: tuple):
    """输出仓库列表（JSON 格式），支持按 repo-name 关键词过滤

    不传参数时输出所有仓库；传入关键词时只输出匹配的仓库。

    示例：
        driving repo load
        driving repo load my-repo
        driving repo load repo-a repo-b
    """
    import json as _json
    from driving_cli.utils.match import normalize_keywords
    keywords = normalize_keywords(keywords)

    result = collect_repos(keywords)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


def collect_repos(keywords: tuple = ()) -> list:
    """收集仓库列表，供 repo load 和 driving load 复用。

    不传关键词时，返回所有仓库。
    传入关键词时，按 repo.name 精确匹配或 repo.description 模糊匹配（不区分大小写，取并集）。
    """
    from driving_cli.utils.match import fuzzy_match

    project_root = find_project_root()
    config_mgr = ConfigManager(project_root)

    try:
        repos = config_mgr.get_all_repos()
    except ValueError:
        return []

    if not keywords:
        matched = repos
    else:
        kw_lower = tuple(k.lower() for k in keywords)
        matched = [
            r for r in repos
            if r.name.lower() in kw_lower or fuzzy_match(r.description or "", keywords)
        ]

    return [
        {
            "name": r.name,
            "type": r.type,
            "description": r.description or "",
            "path": r.path,
        }
        for r in matched
    ]


# ==================== 辅助函数 ====================

def _resolve_repos(config_mgr: ConfigManager, repo_name: Optional[str], operation: str):
    """解析要操作的仓库列表

    若指定了 repo_name，返回该仓库（不存在则报错返回 None）。
    若未指定，返回所有仓库（pull/push/commit 时包含 local，由调用方跳过）。

    Returns:
        list[RepoConfig] 或 None（出错时）
    """
    try:
        if repo_name is not None:
            repo_cfg = config_mgr.get_repo(repo_name)
            if repo_cfg is None:
                log_error(f"仓库 '{repo_name}' 不存在，使用 'driving repo list' 查看已安装仓库")
                return None
            return [repo_cfg]
        else:
            return config_mgr.get_all_repos()
    except ValueError as e:
        log_error(str(e))
        return None
