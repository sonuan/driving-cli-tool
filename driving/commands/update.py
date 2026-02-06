"""更新命令 - 检查和安装新版本"""

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import click

from driving import __version__
from driving.utils.config import DRIVING_UPDATE_VERSION_URL, update_env_file
from driving.utils.logger import log_error, log_info, log_success, log_warning


def get_current_version() -> str:
    """获取当前安装的版本号

    Returns:
        str: 当前版本号
    """
    return __version__


def fetch_version_info(version_url: str) -> Optional[Dict[str, Any]]:
    """从服务器获取最新版本信息

    Args:
        version_url: version.json 文件的完整 URL

    Returns:
        Optional[Dict]: 版本信息字典，失败返回 None
    """
    try:
        log_info(f"正在检查更新: {version_url}")

        with urllib.request.urlopen(version_url, timeout=10) as response:
            data = response.read()
            version_info = json.loads(data.decode("utf-8"))
            return version_info

    except urllib.error.URLError as e:
        log_error(f"无法连接到更新服务器: {e.reason}")
        return None
    except json.JSONDecodeError as e:
        log_error(f"版本信息格式错误: {str(e)}")
        return None
    except Exception as e:
        log_error(f"获取版本信息失败: {str(e)}")
        return None


def compare_versions(current: str, latest: str) -> int:
    """比较两个版本号

    Args:
        current: 当前版本号，如 "2.2.2"
        latest: 最新版本号，如 "2.3.0"

    Returns:
        int: -1 表示 current < latest，0 表示相等，1 表示 current > latest
    """
    try:
        current_parts = [int(x) for x in current.split(".")]
        latest_parts = [int(x) for x in latest.split(".")]

        # 补齐长度
        max_len = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_len - len(current_parts)))
        latest_parts.extend([0] * (max_len - len(latest_parts)))

        for c, l in zip(current_parts, latest_parts):
            if c < l:
                return -1
            elif c > l:
                return 1

        return 0
    except Exception:
        return 0


@click.command("version")
@click.option("--check", is_flag=True, help="检查是否有新版本可用")
@click.option("--url", default=None, help="自定义 version.json 文件的完整 URL")
def version(check: bool, url: str = None):
    """显示当前版本或检查更新

    参数：
        --url: 自定义 version.json 文件的完整 URL（优先级：参数 > 环境变量 > .env 文件 > 默认值）

    示例：
        driving version              # 显示当前版本
        driving version --check      # 检查是否有新版本
        driving version --check --url http://your-server.com/path/version.json
    """
    current_version = get_current_version()

    if not check:
        # 只显示当前版本
        log_info(f"Driving CLI Tool 版本: {current_version}")
        return

    # 确定使用的 version.json URL（优先级：命令行参数 > 环境变量 > .env 文件 > 默认值）
    version_url = url if url else DRIVING_UPDATE_VERSION_URL

    # 检查更新
    log_info(f"当前版本: {current_version}")
    log_info(f"版本文件: {version_url}")

    version_info = fetch_version_info(version_url)
    if not version_info:
        log_warning("无法检查更新，请稍后重试")
        return

    latest_version = version_info.get("version", "unknown")
    log_info(f"最新版本: {latest_version}")

    comparison = compare_versions(current_version, latest_version)

    if comparison < 0:
        log_warning(f"\n🎉 发现新版本: {latest_version}")

        # 显示更新日志
        changelog = version_info.get("changelog", [])
        if changelog:
            log_info("\n更新内容:")
            for item in changelog:
                log_info(f"  • {item}")

        log_info("\n执行以下命令更新:")
        log_info("  driving update")

    elif comparison == 0:
        log_success("\n✓ 已是最新版本")
    else:
        log_info("\n当前版本高于服务器版本")


@click.command("update")
@click.option("--force", is_flag=True, help="强制重新安装当前版本")
@click.option("--yes", "-y", is_flag=True, help="跳过确认提示")
@click.option(
    "--url", default=None, help="自定义 version.json 文件的完整 URL（自动保存到 .env 文件）"
)
def update(force: bool, yes: bool, url: str = None):
    """从服务器更新 driving CLI 工具

    参数：
        --url: 自定义 version.json 文件的完整 URL，会自动保存到项目根目录的 .env 文件
               （优先级：参数 > 环境变量 > .env 文件 > 默认值）

    配置方式：
        1. 使用 --url 参数（推荐，会自动保存）：
           driving update --url http://your-server.com/path/version.json
        2. 设置环境变量 DRIVING_UPDATE_VERSION_URL：
           export DRIVING_UPDATE_VERSION_URL=http://your-server.com/path/version.json
        3. 在项目根目录创建 .env 文件并添加：
           DRIVING_UPDATE_VERSION_URL=http://your-server.com/path/version.json
        4. 默认值：https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json

    注意：
    - 使用 --url 参数时，会自动将地址保存到 .env 文件，下次无需再指定
    - URL 应该是 version.json 文件的完整路径

    示例：
        driving update               # 使用默认 URL 检查并安装更新
        driving update --url http://your-server.com/path/version.json  # 使用自定义 URL
        driving update --force       # 强制重新安装
        driving update -y            # 跳过确认提示
    """
    import os
    import shutil
    import stat
    import sys
    import tempfile

    # 确定使用的 version.json URL（优先级：命令行参数 > 环境变量 > .env 文件 > 默认值）
    version_url = url if url else DRIVING_UPDATE_VERSION_URL

    current_version = get_current_version()
    log_info(f"当前版本: {current_version}")
    log_info(f"版本文件: {version_url}")

    # 如果使用了自定义 URL，保存到 .env 文件
    if url:
        # 使用当前运行目录
        current_dir = Path.cwd()

        log_info(f"保存自定义版本文件 URL 到 {current_dir}/.env")
        update_env_file(current_dir, "DRIVING_UPDATE_VERSION_URL", url)
        log_success(f"已将 DRIVING_UPDATE_VERSION_URL={url} 保存到 .env 文件")

    # 获取最新版本信息
    version_info = fetch_version_info(version_url)
    if not version_info:
        log_error("无法获取版本信息，更新失败")
        return

    latest_version = version_info.get("version", "unknown")
    download_url = version_info.get("download_url", "")

    if not download_url:
        log_error("版本信息中缺少下载地址")
        return

    # 检查是否需要更新
    comparison = compare_versions(current_version, latest_version)

    if comparison >= 0 and not force:
        log_success("已是最新版本，无需更新")
        log_info("如需重新安装，请使用 --force 选项")
        return

    # 显示更新信息
    if comparison < 0:
        log_warning(f"\n准备更新到版本: {latest_version}")

        changelog = version_info.get("changelog", [])
        if changelog:
            log_info("\n更新内容:")
            for item in changelog:
                log_info(f"  • {item}")
    else:
        log_info(f"\n准备重新安装版本: {latest_version}")

    # 确认更新
    if not yes:
        log_info("")
        if not click.confirm("是否继续？"):
            log_info("已取消更新")
            return

    # 下载并安装二进制文件
    try:
        log_info(f"\n正在下载: {download_url}")

        # 下载到系统临时目录
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=tempfile.gettempdir())

        try:
            with urllib.request.urlopen(download_url, timeout=30) as response:
                # 显示下载进度
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                with os.fdopen(tmp_fd, "wb") as tmp_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        tmp_file.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            # 使用 print 显示进度，覆盖同一行
                            print(
                                f"\r[INFO] 下载进度: {percent:.1f}% ({downloaded}/{total_size} bytes)",
                                end="",
                                flush=True,
                            )

                    # 确保所有数据都写入磁盘
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())

            print()  # 换行
            log_info("下载完成")

        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            log_error(f"下载失败: {str(e)}")
            return

        # 获取当前可执行文件路径
        current_exe = None

        # 首先尝试查找已安装的 driving 命令
        result = subprocess.run(["which", "driving"], capture_output=True, text=True)
        if result.returncode == 0:
            current_exe = result.stdout.strip()

        # 如果没有找到，检查是否是直接运行的可执行文件
        if not current_exe:
            if not sys.argv[0].endswith(".py"):
                current_exe = os.path.abspath(sys.argv[0])

        if not current_exe:
            log_error("无法找到 driving 命令的安装位置")
            log_info("请确保:")
            log_info("  1. 已通过 pip 安装: pip3 install -e .")
            log_info("  2. 或使用可执行文件: ./dist/driving update")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return

        log_info(f"安装位置: {current_exe}")

        # 验证下载的文件是否是有效的可执行文件
        try:
            file_size = os.path.getsize(tmp_path)
            if file_size < 1024:  # 小于 1KB 肯定不对
                log_error(f"下载的文件太小 ({file_size} bytes)，可能下载不完整")
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return
            log_info(f"下载文件大小: {file_size / 1024 / 1024:.2f} MB")
        except Exception as e:
            log_error(f"无法验证下载文件: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return

        # 替换可执行文件
        try:
            # 在 Unix 系统上，正在运行的可执行文件可以被删除和替换
            # 使用 rename/move 而不是 copy，这样更安全和原子化

            # 先删除旧文件（正在运行的进程仍然可以继续执行）
            if os.path.exists(current_exe):
                os.unlink(current_exe)

            # 移动新文件到目标位置（比复制更原子化）
            shutil.move(tmp_path, current_exe)

            # 设置执行权限 (755: rwxr-xr-x)
            os.chmod(
                current_exe,
                stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
            )

            log_success(f"\n✓ 更新成功！当前版本: {latest_version}")
            log_info("\n提示: 更新将在下次运行 driving 命令时生效")
            log_info("请运行 'driving --version' 验证更新")

        except PermissionError:
            log_error("权限不足，无法替换文件")
            log_info("请尝试使用 sudo 运行:")
            log_info(f"  sudo driving update {'-y' if yes else ''}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return
        except Exception as e:
            log_error(f"安装失败: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return

    except Exception as e:
        log_error(f"更新过程出错: {str(e)}")


if __name__ == "__main__":
    version()
