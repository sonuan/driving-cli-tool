"""日志模块 - 使用 Rich 实现彩色日志输出"""

import sys

from rich.console import Console

# Windows 编码兼容性：force_terminal 确保 Rich 正确处理终端输出
# 设置 UTF-8 编码避免中文和 emoji 在 GBK 终端下乱码
if sys.platform == "win32":
    # Windows 下强制设置 UTF-8 编码
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")

console = Console(force_terminal=True, force_interactive=True)
error_console = Console(stderr=True, force_terminal=True, force_interactive=True)

# 静默模式：True 时 log_info/log_warning 不输出（log_error 始终输出到 stderr）
_silent = False


def set_silent(silent: bool) -> None:
    """设置静默模式"""
    global _silent
    _silent = silent


def is_silent() -> bool:
    return _silent


def log_info(message: str):
    """输出信息日志（蓝色）"""
    if not _silent:
        console.print(f"[blue][INFO][/blue] {message}")


def log_success(message: str):
    """输出成功日志（绿色）"""
    if not _silent:
        console.print(f"[green][SUCCESS][/green] {message}")


def log_error(message: str):
    """输出错误日志（红色），始终输出到 stderr"""
    error_console.print(f"[red][ERROR][/red] {message}")


def log_warning(message: str):
    """输出警告日志（黄色）"""
    if not _silent:
        console.print(f"[yellow][WARNING][/yellow] {message}")
