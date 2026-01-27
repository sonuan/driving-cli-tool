"""IDE 配置管理命令"""

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Set, Tuple

import click
import git

from driving.utils.config import SENSITIVE_KEYWORDS, get_driving_dir
from driving.utils.git_helper import find_git_root
from driving.utils.logger import log_error, log_info, log_success, log_warning


def _is_sensitive_key(key: str) -> bool:
    """判断键名是否为敏感字段

    Args:
        key: 键名

    Returns:
        bool: 是否为敏感字段
    """
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in SENSITIVE_KEYWORDS)


def _extract_env_vars(
    data: Any, prefix: str = "", env_vars: Dict[str, str] = None
) -> Tuple[Any, Dict[str, str]]:
    """递归提取敏感环境变量

    Args:
        data: JSON 数据
        prefix: 环境变量前缀（不使用，保留参数以保持兼容性）
        env_vars: 已提取的环境变量字典

    Returns:
        Tuple[Any, Dict[str, str]]: (处理后的数据, 环境变量字典)
    """
    if env_vars is None:
        env_vars = {}

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # 检查是否为敏感字段
            if isinstance(value, str) and _is_sensitive_key(key) and value:
                # 使用原始的 key 名称（转大写，替换特殊字符为下划线）
                env_key = key.upper()
                env_key = re.sub(r"[^A-Z0-9_]", "_", env_key)

                # 存储环境变量
                env_vars[env_key] = value

                # 替换为环境变量引用
                result[key] = f"${{{env_key}}}"
            elif isinstance(value, (dict, list)):
                # 递归处理嵌套结构（不传递 prefix）
                result[key], env_vars = _extract_env_vars(value, "", env_vars)
            else:
                result[key] = value
        return result, env_vars
    elif isinstance(data, list):
        result = []
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                new_item, env_vars = _extract_env_vars(item, "", env_vars)
                result.append(new_item)
            else:
                result.append(item)
        return result, env_vars
    else:
        return data, env_vars


def _process_mcp_json(file_path: Path, target_dir: Path) -> Set[str]:
    """处理 mcp.json 文件，提取敏感信息到 .env

    Args:
        file_path: mcp.json 文件路径
        target_dir: 目标目录（项目根目录）

    Returns:
        Set[str]: 提取的环境变量名集合
    """
    try:
        # 读取 mcp.json
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # 移除 JSON 注释
            content = re.sub(r"//.*?\n|/\*.*?\*/", "", content, flags=re.DOTALL)
            data = json.loads(content)

        # 提取环境变量
        processed_data, env_vars = _extract_env_vars(data)

        if not env_vars:
            return set()

        # 写回处理后的 mcp.json
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(processed_data, f, indent=2, ensure_ascii=False)

        # 更新 .env.local 文件（敏感信息）
        env_local_file = target_dir / ".env.local"
        existing_env = {}

        if env_local_file.exists():
            # 读取现有的 .env.local 文件
            with open(env_local_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        existing_env[key.strip()] = value.strip()

        # 合并新的环境变量
        existing_env.update(env_vars)

        # 写入 .env.local 文件
        with open(env_local_file, "w", encoding="utf-8") as f:
            f.write("# IDE 配置环境变量（敏感信息）\n")
            f.write("# 此文件包含敏感信息，请勿提交到 Git 仓库\n")
            f.write("# 优先级：.env.local > .env\n\n")
            for key, value in sorted(existing_env.items()):
                f.write(f"{key}={value}\n")

        # 更新 .gitignore
        gitignore_file = target_dir / ".gitignore"
        gitignore_content = ""

        if gitignore_file.exists():
            gitignore_content = gitignore_file.read_text(encoding="utf-8")

        # 确保 .env.local 在 .gitignore 中
        if ".env.local" not in gitignore_content:
            # 添加 .env.local 到 .gitignore
            if gitignore_content and not gitignore_content.endswith("\n"):
                gitignore_content += "\n"
            gitignore_content += "\n# IDE 配置环境变量文件（敏感信息）\n.env.local\n"
            gitignore_file.write_text(gitignore_content, encoding="utf-8")
            log_info("已将 .env.local 添加到 .gitignore")

        return set(env_vars.keys())

    except Exception as e:
        log_warning(f"处理 mcp.json 失败: {e}")
        return set()


def _copy_directory_incremental(
    source_dir: Path, target_dir: Path, project_root: Path
) -> tuple[int, int, int, Set[str]]:
    """增量复制目录，只覆盖同名文件，保留目标目录中的其他文件

    Args:
        source_dir: 源目录
        target_dir: 目标目录
        project_root: 项目根目录

    Returns:
        tuple[int, int, int, Set[str]]: (新增文件数, 更新文件数, 跳过文件数, 提取的环境变量集合)
    """
    added_count = 0
    updated_count = 0
    skipped_count = 0
    all_env_vars = set()

    # 确保目标目录存在
    target_dir.mkdir(parents=True, exist_ok=True)

    # 遍历源目录
    for source_path in source_dir.rglob("*"):
        if source_path.is_file():
            # 计算相对路径
            relative_path = source_path.relative_to(source_dir)
            target_path = target_dir / relative_path

            # 确保目标文件的父目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 检查文件是否存在
            if target_path.exists():
                # 比较文件内容是否相同
                if source_path.read_bytes() == target_path.read_bytes():
                    skipped_count += 1
                else:
                    # 文件内容不同，覆盖
                    shutil.copy2(source_path, target_path)
                    updated_count += 1
            else:
                # 文件不存在，新增
                shutil.copy2(source_path, target_path)
                added_count += 1

            # 如果是 mcp.json 文件，处理敏感信息
            if target_path.name == "mcp.json":
                env_vars = _process_mcp_json(target_path, project_root)
                if env_vars:
                    all_env_vars.update(env_vars)
                    log_info(f"已从 {relative_path} 提取 {len(env_vars)} 个环境变量到 .env")

    return added_count, updated_count, skipped_count, all_env_vars


@click.command(name="ide-list")
def ide_list():
    """列出可用的 IDE 配置

    显示 install 目录下所有可用的 IDE 配置名称。
    """
    try:
        driving_dir = get_driving_dir()
        install_dir = driving_dir / "install"

        if not install_dir.exists():
            log_error(f"install 目录不存在: {install_dir}")
            raise click.Abort()

        # 查找所有以 . 开头的目录（IDE 配置目录）
        ide_dirs = [
            d.name
            for d in install_dir.iterdir()
            if d.is_dir() and d.name.startswith(".") and d.name != ".DS_Store"
        ]

        if not ide_dirs:
            log_warning("未找到任何 IDE 配置")
            return

        log_info("可用的 IDE 配置：")
        for ide_name in sorted(ide_dirs):
            # 移除开头的点号显示
            display_name = ide_name[1:]
            log_info(f"  - {display_name}")

        log_info(f"\n使用 'driving ide-sync <ide名称>' 同步配置到项目")

    except Exception as e:
        log_error(f"列出 IDE 配置失败: {e}")
        raise click.Abort()


@click.command(name="ide-sync")
@click.argument("ide_name")
def ide_sync(ide_name: str):
    """同步 IDE 配置到当前工作目录

    将 install 目录下对应的 IDE 配置增量同步到当前工作目录。
    只会覆盖同名文件，不会删除目标目录中的其他文件。
    自动提取 mcp.json 中的敏感信息（API Key、Token 等）到 .env.local 文件。

    Args:
        ide_name: IDE 名称（如 kiro、claude、cursor）

    示例:
        driving ide-sync kiro  # 将 install/.kiro 增量同步到当前工作目录/.kiro
    """
    try:
        # 查找项目根目录
        try:
            project_root = find_git_root()
            log_info(f"项目根目录: {project_root}")
        except git.exc.InvalidGitRepositoryError:
            log_error("当前目录不在 Git 仓库中")
            raise click.Abort()

        driving_dir = get_driving_dir()
        install_dir = driving_dir / "install"

        if not install_dir.exists():
            log_error(f"install 目录不存在: {install_dir}")
            raise click.Abort()

        # 构建源目录和目标目录路径
        # IDE 配置目录以 . 开头
        source_dir = install_dir / f".{ide_name}"
        # target_dir 使用当前工作目录
        target_dir = Path.cwd() / f".{ide_name}"

        if not source_dir.exists():
            log_error(f"IDE 配置不存在: {source_dir}")
            log_info(f"使用 'driving ide-list' 查看可用的 IDE 配置")
            raise click.Abort()

        # 增量复制目录
        log_info(f"正在同步 IDE 配置...")
        log_info(f"源目录: {source_dir}")
        log_info(f"目标目录: {target_dir}")

        added_count, updated_count, skipped_count, env_vars = _copy_directory_incremental(
            source_dir, target_dir, Path.cwd()
        )

        log_success(f"IDE 配置同步成功！")
        log_info(f"配置已同步到: {target_dir}")
        log_info(f"新增文件: {added_count}, 更新文件: {updated_count}, 跳过文件: {skipped_count}")

        if env_vars:
            log_success(f"已提取 {len(env_vars)} 个敏感环境变量到 {Path.cwd()}/.env.local")
            log_warning("请检查 .env.local 文件并填写正确的值")
            log_info("提示：.env.local 包含敏感信息，已自动添加到 .gitignore")

        if target_dir.exists():
            # 统计目标目录中的其他文件
            target_files = set(
                p.relative_to(target_dir) for p in target_dir.rglob("*") if p.is_file()
            )
            source_files = set(
                p.relative_to(source_dir) for p in source_dir.rglob("*") if p.is_file()
            )
            extra_files = target_files - source_files

            if extra_files:
                log_info(f"保留的自定义文件: {len(extra_files)} 个")

    except Exception as e:
        log_error(f"同步 IDE 配置失败: {e}")
        raise click.Abort()
