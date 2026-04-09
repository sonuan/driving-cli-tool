"""日志模块 - 使用 Rich 实现彩色日志输出"""

import sys

from rich.console import Console

console = Console()
error_console = Console(stderr=True)

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
