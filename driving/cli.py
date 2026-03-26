"""Driving CLI Tool - 命令行入口"""

import click

from driving import __version__
from driving.commands import framework, ide, repo, skill, update


@click.group()
@click.version_option(version=__version__)
def cli():
    """Driving CLI Tool - AI Coding 工程化管理工具

    """
    pass


# 注册 repo 子命令组（多仓库管理）
cli.add_command(repo.repo_group)

# 注册 framework 子命令组（多仓库框架管理）
cli.add_command(framework.framework_group)

# 注册 IDE 配置管理命令（暂未重构，不对外暴露）
# cli.add_command(ide.ide_list)
# cli.add_command(ide.ide_sync)

# 注册 skill 子命令组（多仓库 skill 管理）
cli.add_command(skill.skill_group)

# 注册更新命令
cli.add_command(update.update)



if __name__ == "__main__":
    cli()
