"""更新命令 - 检查和安装新版本"""

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import click

from driving_cli import __version__
from driving_cli.utils.config_manager import ConfigManager, find_project_root
from driving_cli.utils.logger import log_error, log_info, log_success, log_warning

# 默认更新检查 URL
_DEFAULT_UPDATE_VERSION_URL = (
    "https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json"
)


def _get_update_version_url() -> str:
    """从 driving.config.json 读取更新检查 URL，不存在则返回默认值"""
    try:
        config = ConfigManager(find_project_root()).load()
        if config.update_version_url:
            return config.update_version_url
    except Exception:
        pass
    return _DEFAULT_UPDATE_VERSION_URL


def _save_update_version_url(url: str) -> None:
    """将更新检查 URL 保存到 driving.config.json"""
    try:
        manager = ConfigManager(find_project_root())
        config = manager.load()
        config.update_version_url = url
        manager.save(config)
    except Exception as e:
        log_warning(f"保存更新 URL 失败: {e}")


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


@click.command("update")
@click.option("--check", is_flag=True, help="仅检查是否有新版本，不安装")
@click.option("--force", is_flag=True, help="强制重新安装当前版本")
@click.option("--yes", "-y", is_flag=True, help="跳过确认提示")
@click.option("--url", default=None, help="自定义 version.json 文件的完整 URL")
def update(check: bool, force: bool, yes: bool, url: str = None):
    """更新管理

    示例：
        driving update               # 检查并安装更新
        driving update --check       # 仅检查是否有新版本
        driving update --force       # 强制重新安装
        driving update -y            # 跳过确认提示
        driving update --url http://your-server.com/path/version.json
    """
    import os
    import stat
    import sys
    import tempfile

    # 确定使用的 version.json URL（优先级：命令行参数 > driving.config.json > 默认值）
    version_url = url if url else _get_update_version_url()

    current_version = get_current_version()
    log_info(f"当前版本: {current_version}")

    # --check 模式：仅检查版本，不安装
    if check:
        version_info = fetch_version_info(version_url)
        if not version_info:
            log_warning("无法检查更新，请稍后重试")
            return
        latest_version = version_info.get("version", "unknown")
        log_info(f"最新版本: {latest_version}")
        comparison = compare_versions(current_version, latest_version)
        if comparison < 0:
            log_warning(f"\n🎉 发现新版本: {latest_version}")
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
        return

    log_info(f"版本文件: {version_url}")

    # 如果使用了自定义 URL，保存到 driving.config.json
    if url:
        log_info(f"保存自定义版本文件 URL 到 driving.config.json")
        _save_update_version_url(url)
        log_success(f"已将更新 URL 保存到 driving.config.json")

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

        # 确定安装目标路径（提前计算，供下载临时目录使用）
        user_install_dir_early = Path.home() / ".driving-cli"
        user_install_path_early = user_install_dir_early / "driving"

        # 临时文件与目标放在同一目录，确保 os.rename 是原子操作（避免跨设备 copy）
        if user_install_path_early.exists():
            tmp_dir = str(user_install_dir_early)
            os.makedirs(tmp_dir, exist_ok=True)
        else:
            tmp_dir = tempfile.gettempdir()

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=tmp_dir)

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

        # 确定安装目标路径
        # 优先使用 ~/.driving-cli/driving（用户目录，无需 sudo）
        # 回退到 which driving 的结果（兼容旧版本或 pip 安装方式）
        #
        # sudo 执行时 Path.home() 返回 /root，需通过 SUDO_USER 还原真实用户 home
        sudo_user = os.environ.get("SUDO_USER", "")
        if sudo_user:
            import pwd as _pwd
            try:
                real_home = Path(_pwd.getpwnam(sudo_user).pw_dir)
            except KeyError:
                real_home = Path.home()
        else:
            real_home = Path.home()

        user_install_dir = real_home / ".driving-cli"
        user_install_path = user_install_dir / "driving"
        symlink_path = Path("/usr/local/bin/driving")

        if user_install_path.exists():
            # 新方案：二进制在用户目录，直接更新，无需 sudo
            current_exe = str(user_install_path)
            migrate = False
        else:
            # 兼容旧方案：通过 which 查找
            result = subprocess.run(["which", "driving"], capture_output=True, text=True)
            if result.returncode == 0:
                resolved = Path(result.stdout.strip()).resolve()
                current_exe = str(resolved)
            elif not sys.argv[0].endswith(".py"):
                current_exe = os.path.abspath(sys.argv[0])
            else:
                current_exe = None

            # 检测是否为旧安装方式（/usr/local/bin/driving 是真实文件而非符号链接）
            migrate = (
                current_exe is not None
                and symlink_path.exists()
                and not symlink_path.is_symlink()
            )
            if migrate:
                log_info("检测到旧版安装方式，本次更新将自动迁移到 ~/.driving-cli/driving")
                log_info("迁移完成后，后续 driving update 无需 sudo")
                # 目标改为新目录，安装完成后再建符号链接
                current_exe = str(user_install_path)

        if not current_exe:
            log_error("无法找到 driving 命令的安装位置")
            log_info("请确保:")
            log_info("  1. 已通过安装脚本安装（推荐）")
            log_info("  2. 或通过 pip 安装: pip3 install -e .")
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
        def _do_install(src: str, dest: str) -> None:
            """将 src 原子替换到 dest 并设置执行权限（755）。目标目录不存在时自动创建。"""
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # os.replace 是原子操作，同设备下等价于 rename，不会有跨设备 copy 权限问题
            os.replace(src, dest)
            os.chmod(
                dest,
                stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
            )

        def _do_install_with_sudo(src: str, dest: str) -> bool:
            """使用 sudo mv + chmod 替换文件，返回是否成功。"""
            log_info("需要管理员权限完成安装，请输入密码：")
            result = subprocess.run(
                ["sudo", "sh", "-c", f"mv {src!r} {dest!r} && chmod 755 {dest!r}"]
            )
            return result.returncode == 0

        try:
            # 在 Unix 系统上，正在运行的可执行文件可以被删除和替换
            # 使用 rename/move 而不是 copy，这样更安全和原子化
            try:
                _do_install(tmp_path, current_exe)
            except PermissionError:
                # 无写权限时自动 fallback 到 sudo，用户只需输入一次密码
                if not _do_install_with_sudo(tmp_path, current_exe):
                    log_error("安装失败：sudo 执行出错")
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    return

            # 旧安装方式迁移收尾：删除旧真实文件，建立符号链接
            if migrate:
                def _do_migrate_symlink() -> bool:
                    """删除 /usr/local/bin/driving 真实文件，创建指向新目录的符号链接"""
                    try:
                        if symlink_path.exists() and not symlink_path.is_symlink():
                            symlink_path.unlink()
                        symlink_path.symlink_to(current_exe)
                        return True
                    except PermissionError:
                        return False

                migrated = _do_migrate_symlink()
                if not migrated:
                    # 需要 sudo 建符号链接
                    log_info("创建符号链接需要管理员权限，请输入密码：")
                    r = subprocess.run(
                        ["sudo", "sh", "-c",
                         f"rm -f {str(symlink_path)!r} && ln -sf {current_exe!r} {str(symlink_path)!r}"]
                    )
                    migrated = r.returncode == 0

                if migrated:
                    log_success("✓ 已迁移到新安装方式，后续 driving update 无需 sudo")
                else:
                    log_warning("符号链接创建失败，但二进制已更新到 ~/.driving-cli/driving")
                    log_info(f"可手动执行：sudo ln -sf {current_exe} {symlink_path}")

            # sudo 执行时将安装目录所有权归还真实用户，避免 root 权限问题
            if sudo_user and user_install_dir.exists():
                try:
                    subprocess.run(
                        ["chown", "-R", sudo_user, str(user_install_dir)],
                        check=True
                    )
                except Exception:
                    pass  # chown 失败不影响主流程

            log_success(f"\n✓ 更新成功！当前版本: {latest_version}")
            log_info("\n提示: 更新将在下次运行 driving 命令时生效")
            log_info("请运行 'driving --version' 验证更新")

            # 上报：driving update 手动更新 CLI 成功
            try:
                from driving_cli.utils.op_reporter import report_op_event
                report_op_event(
                    operation="update_completed",
                    description=f"driving update 手动更新 CLI：{current_version} → {latest_version}",
                    cli_version=latest_version,
                    extra={"from_version": current_version, "to_version": latest_version},
                )
            except Exception:
                pass  # 上报失败不影响更新成功的用户体验

        except Exception as e:
            log_error(f"安装失败: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return

    except Exception as e:
        log_error(f"更新过程出错: {str(e)}")


if __name__ == "__main__":
    update()
