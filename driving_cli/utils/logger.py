"""日志模块 - 使用 Rich 实现彩色日志输出"""

import sys

from rich.console import Console

console = Console()
error_console = Console(stderr=True)


def log_info(message: str):
    """输出信息日志（蓝色）

    Args:
        message: 日志信息
    """
    console.print(f"[blue][INFO][/blue] {message}")


def log_success(message: str):
    """输出成功日志（绿色）

    Args:
        message: 日志信息
    """
    console.print(f"[green][SUCCESS][/green] {message}")


def log_error(message: str):
    """输出错误日志（红色）

    Args:
        message: 日志信息
    """
    error_console.print(f"[red][ERROR][/red] {message}")


def log_warning(message: str):
    """输出警告日志（黄色）

    Args:
        message: 日志信息
    """
    console.print(f"[yellow][WARNING][/yellow] {message}")
