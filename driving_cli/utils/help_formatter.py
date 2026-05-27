"""Click help formatter - 保留 docstring 原始换行，不做段落重排"""

import click
from click import HelpFormatter


class PreserveNewlineFormatter(HelpFormatter):
    """保留 docstring 中所有换行，不做段落重排"""

    def write_paragraph(self) -> None:
        if self.buffer:
            self.write("\n")

    def write_text(self, text: str) -> None:
        for line in text.splitlines():
            self.write(f"{'  ' * self.current_indent}{line}\n")


def _preserve_get_help(self: click.BaseCommand, ctx: click.Context) -> str:
    """替换 click.BaseCommand.get_help，使用 PreserveNewlineFormatter"""
    formatter = PreserveNewlineFormatter(
        width=ctx.terminal_width,
        max_width=ctx.max_content_width,
    )
    self.format_help(ctx, formatter)
    return formatter.getvalue()


def patch_click_help() -> None:
    """全局替换 Click 所有命令的 get_help，一次调用，全局生效"""
    click.BaseCommand.get_help = _preserve_get_help  # type: ignore[method-assign]
    click.Command.get_help = _preserve_get_help      # type: ignore[method-assign]
