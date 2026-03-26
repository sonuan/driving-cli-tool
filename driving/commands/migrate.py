"""迁移命令

将旧版 .env.driving 配置迁移到新的 driving.config.json 格式。
"""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import click

from driving.models.config import DrivingConfig, RepoConfig
from driving.utils.config_manager import (
    CONFIG_FILE_NAME,
    DEFAULT_COMMIT_MESSAGE,
    DEFAULT_UPDATE_VERSION_URL,
    ConfigManager,
    find_project_root,
)
from driving.utils.validators import infer_repo_name_from_url

# .env.driving 文件名
ENV_FILE_NAME = ".env.driving"

# 可自动迁移的配置项映射：env 键 → 说明
MIGRATABLE_KEYS = {
    "DRIVING_REPO_URL": "repos[0].url（远程仓库地址）",
    "DRIVING_DEFAULT_COMMIT_MESSAGE": "default_commit_message（默认提交信息）",
    "DRIVING_UPDATE_VERSION_URL": "update_version_url（版本更新检查 URL）",
}

# 无法自动迁移的配置项：env 键 → 说明
NON_MIGRATABLE_KEYS = {
    "DRIVING_LOCAL_MODE": "本地模式已废弃，请改用 'driving repo install --local <path>' 注册本地仓库",
    "DRIVING_REPO_PATH": "仓库路径现由 driving.config.json 中的 repos[].path 管理",
    "DRIVING_BRANCH": "分支信息请通过 git 命令直接管理",
}


def parse_env_file(env_file: Path) -> Dict[str, str]:
    """解析 .env.driving 文件，返回键值对字典

    忽略注释行（以 # 开头）和空行。

    Args:
        env_file: .env.driving 文件路径

    Returns:
        Dict[str, str]: 配置键值对
    """
    result = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # 跳过空行和注释行
        if not line or line.startswith("#"):
            continue
        # 解析 KEY=VALUE 格式
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def build_config_from_env(env_vars: Dict[str, str]) -> Tuple[DrivingConfig, list, list]:
    """根据 env 变量构建 DrivingConfig 对象

    Args:
        env_vars: 从 .env.driving 解析出的键值对

    Returns:
        Tuple[DrivingConfig, list, list]:
            - 构建好的 DrivingConfig 对象
            - 已迁移的配置项列表（(key, description) 元组）
            - 无法迁移的配置项列表（(key, description) 元组）
    """
    migrated = []
    non_migratable = []

    # 处理 DRIVING_REPO_URL → repos[0]
    repos = []
    repo_url = env_vars.get("DRIVING_REPO_URL", "").strip()
    if repo_url:
        repo_name = infer_repo_name_from_url(repo_url)
        repos.append(
            RepoConfig(
                name=repo_name,
                type="remote",
                url=repo_url,
                path=f"ai-driving/{repo_name}",
                local_path=None,
            )
        )
        migrated.append(("DRIVING_REPO_URL", f"→ repos[0]（name={repo_name}, type=remote）"))

    # 处理 DRIVING_DEFAULT_COMMIT_MESSAGE → default_commit_message
    commit_message = env_vars.get("DRIVING_DEFAULT_COMMIT_MESSAGE", "").strip()
    if not commit_message:
        commit_message = DEFAULT_COMMIT_MESSAGE
    else:
        migrated.append(("DRIVING_DEFAULT_COMMIT_MESSAGE", f"→ default_commit_message（值：{commit_message}）"))

    # 处理 DRIVING_UPDATE_VERSION_URL → update_version_url
    update_url = env_vars.get("DRIVING_UPDATE_VERSION_URL", "").strip()
    if not update_url:
        update_url = DEFAULT_UPDATE_VERSION_URL
    else:
        migrated.append(("DRIVING_UPDATE_VERSION_URL", f"→ update_version_url（值：{update_url}）"))

    # 检测无法自动迁移的配置项
    for key, description in NON_MIGRATABLE_KEYS.items():
        if key in env_vars:
            non_migratable.append((key, description))

    # 检测其他未知配置项
    known_keys = set(MIGRATABLE_KEYS.keys()) | set(NON_MIGRATABLE_KEYS.keys())
    for key in env_vars:
        if key not in known_keys:
            non_migratable.append((key, "未知配置项，无法自动迁移，请手动处理"))

    config = DrivingConfig(
        version="2",
        repos=repos,
        default_commit_message=commit_message,
        update_version_url=update_url,
    )

    return config, migrated, non_migratable


def check_migration_needed(project_root: Optional[Path] = None) -> bool:
    """检测是否需要迁移

    当 .env.driving 存在但 driving.config.json 不存在时，返回 True。

    Args:
        project_root: 项目根目录，None 时自动查找

    Returns:
        bool: 需要迁移时返回 True
    """
    if project_root is None:
        project_root = find_project_root()

    env_file = project_root / ENV_FILE_NAME
    config_file = project_root / CONFIG_FILE_NAME

    return env_file.exists() and not config_file.exists()


@click.command(name="migrate")
@click.option("--dry-run", is_flag=True, default=False, help="仅预览迁移结果，不实际写入文件")
def migrate(dry_run: bool):
    """将 .env.driving 配置迁移到 driving.config.json

    读取当前项目的 .env.driving 文件，将可迁移的配置项转换为
    driving.config.json 格式，并列出无法自动迁移的配置项。

    迁移完成后，.env.driving 文件不会被自动删除，
    确认迁移无误后可手动删除。
    """
    project_root = find_project_root()
    env_file = project_root / ENV_FILE_NAME
    config_file = project_root / CONFIG_FILE_NAME

    # 检查 .env.driving 是否存在
    if not env_file.exists():
        click.echo(f"未找到 {ENV_FILE_NAME} 文件，无需迁移。")
        return

    # 检查 driving.config.json 是否已存在
    if config_file.exists() and not dry_run:
        click.echo(
            click.style(f"警告：{CONFIG_FILE_NAME} 已存在。", fg="yellow")
        )
        if not click.confirm("是否覆盖现有配置文件？", default=False):
            click.echo("迁移已取消。")
            return

    # 解析 .env.driving
    click.echo(f"正在读取 {env_file} ...")
    try:
        env_vars = parse_env_file(env_file)
    except Exception as e:
        click.echo(click.style(f"读取 {ENV_FILE_NAME} 失败：{e}", fg="red"))
        return

    if not env_vars:
        click.echo(f"{ENV_FILE_NAME} 文件为空或仅包含注释，无配置项可迁移。")
        return

    # 构建新配置
    config, migrated, non_migratable = build_config_from_env(env_vars)

    # 展示迁移预览
    click.echo("\n" + click.style("=== 迁移预览 ===", bold=True))

    if migrated:
        click.echo(click.style("\n✓ 可自动迁移的配置项：", fg="green"))
        for key, desc in migrated:
            click.echo(f"  {key} {desc}")
    else:
        click.echo(click.style("\n未找到可自动迁移的配置项。", fg="yellow"))

    if non_migratable:
        click.echo(click.style("\n⚠ 无法自动迁移的配置项（需手动处理）：", fg="yellow"))
        for key, desc in non_migratable:
            click.echo(f"  {key}：{desc}")

    # dry-run 模式：仅预览，不写入
    if dry_run:
        click.echo(click.style("\n[dry-run 模式] 未写入任何文件。", fg="cyan"))
        return

    # 写入 driving.config.json
    click.echo(f"\n正在写入 {config_file} ...")
    try:
        manager = ConfigManager(project_root)
        manager.save(config)
    except Exception as e:
        click.echo(click.style(f"写入 {CONFIG_FILE_NAME} 失败：{e}", fg="red"))
        return

    click.echo(click.style(f"\n✓ 迁移完成！配置已写入 {CONFIG_FILE_NAME}", fg="green"))
    click.echo(
        click.style(
            f"\n提示：{ENV_FILE_NAME} 文件未被删除。\n"
            f"确认新配置无误后，可手动删除该文件：\n"
            f"  rm {env_file}",
            fg="cyan",
        )
    )
