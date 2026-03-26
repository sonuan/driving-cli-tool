"""Driving CLI Tool - 命令行入口"""

import click

from driving import __version__
from driving.commands import framework, ide, migrate, repo, skill, update
from driving.commands.migrate import check_migration_needed


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx):
    """Driving CLI Tool - 管理开发框架文档和代码仓库

    支持多仓库管理模式，使用 ai-driving/<repo-name>/ 目录结构。
    配置存储在 driving.config.json 文件中。

    使用 driving <command> 来执行各种操作。
    使用 driving <command> --help 查看具体命令的帮助信息。
    """
    # 当执行的不是 migrate 命令时，检测是否需要迁移
    if ctx.invoked_subcommand != "migrate":
        try:
            if check_migration_needed():
                click.echo(
                    click.style(
                        "\n⚠ 检测到 .env.driving 文件，但尚未迁移到 driving.config.json。\n"
                        "  请运行 'driving migrate' 完成配置迁移。\n",
                        fg="yellow",
                    )
                )
        except Exception:
            # 迁移检测失败不影响正常命令执行
            pass


# 注册迁移命令
cli.add_command(migrate.migrate)

# 注册 repo 子命令组（多仓库管理）
cli.add_command(repo.repo_group)

# 注册 framework 子命令组（多仓库框架管理）
cli.add_command(framework.framework_group)

# 保留旧的 git-* 框架命令（向后兼容）
cli.add_command(framework.git_list)
cli.add_command(framework.git_install)
cli.add_command(framework.git_checkout)
cli.add_command(framework.git_pull)
cli.add_command(framework.git_sources)

# 注册 IDE 配置管理命令
cli.add_command(ide.ide_list)
cli.add_command(ide.ide_sync)

# 注册 skill 子命令组（多仓库 skill 管理）
cli.add_command(skill.skill_group)

# 注册更新命令
cli.add_command(update.version)
cli.add_command(update.update)


if __name__ == "__main__":
    cli()
