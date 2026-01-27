"""Driving CLI Tool - 命令行入口"""

import click

from driving import __version__
from driving.commands import framework, ide, link, repo, skills, update


@click.group()
@click.version_option(version=__version__)
def cli():
    """Driving CLI Tool - 管理开发框架文档和代码仓库

    支持两种工作模式：
    - 标准模式：使用 .driving/ 目录（Git submodule）
    - 本地模式：直接在当前目录操作（当前目录存在 gitlist.json）

    使用 driving <command> 来执行各种操作。
    使用 driving <command> --help 查看具体命令的帮助信息。
    """
    pass


# 注册 Driving 仓库管理命令
cli.add_command(repo.pull)
cli.add_command(repo.commit)
cli.add_command(repo.push)

# 注册 Driving 管理命令
cli.add_command(link.install)
cli.add_command(link.uninstall)

# 注册框架仓库管理命令
cli.add_command(framework.git_list)
cli.add_command(framework.git_install)
cli.add_command(framework.git_checkout)
cli.add_command(framework.git_pull)
cli.add_command(framework.git_sources)

# 注册 IDE 配置管理命令
cli.add_command(ide.ide_list)
cli.add_command(ide.ide_sync)

# 注册 Skills 管理命令
cli.add_command(skills.skills_sync)

# 注册更新命令
cli.add_command(update.version)
cli.add_command(update.update)


if __name__ == "__main__":
    cli()
