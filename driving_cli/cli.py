"""Driving CLI Tool - 命令行入口"""

import click

from driving_cli import __version__
import driving_cli.commands.agent as agent
import driving_cli.commands.check as check
import driving_cli.commands.feature as feature
import driving_cli.commands.framework as framework
import driving_cli.commands.gate as gate
import driving_cli.commands.ide as ide
import driving_cli.commands.load as load
import driving_cli.commands.power as power
import driving_cli.commands.refine as refine
import driving_cli.commands.repo as repo
import driving_cli.commands.rule as rule
import driving_cli.commands.skill as skill
import driving_cli.commands.update as update
from driving_cli.utils.help_formatter import patch_click_help


# 全局替换 Click 的 help 渲染，所有命令自动生效
patch_click_help()


@click.group()
@click.version_option(version=__version__)
def cli():
    """Driving CLI Tool - AI Coding 工程化管理工具

    """
    pass


# 注册 agent 子命令组（多仓库 agent 管理）
cli.add_command(agent.agent_group)

# 注册 repo 子命令组（多仓库管理）
cli.add_command(repo.repo_group)

# 注册 power 子命令组（power 配置管理）
cli.add_command(power.power_group)

# 注册 framework 子命令组（多仓库框架管理）
cli.add_command(framework.framework_group)

# 注册 IDE 配置管理命令（暂未重构，不对外暴露）
# cli.add_command(ide.ide_list)
# cli.add_command(ide.ide_sync)

# 注册 skill 子命令组（多仓库 skill 管理）
cli.add_command(skill.skill_group)

# 注册 rule 子命令组（多仓库规则管理）
cli.add_command(rule.rule_group)

# 注册 gate 子命令组（门禁规则管理）
cli.add_command(gate.gate_group)

# 注册 feature 子命令组（多仓库需求功能管理）
cli.add_command(feature.feature_group)

# 注册 refine 子命令组（refine 提案管理）
cli.add_command(refine.refine_group)

# 注册更新命令
cli.add_command(update.update)

# 注册 check 命令
cli.add_command(check.check)

# 注册 load 命令
cli.add_command(load.load)



if __name__ == "__main__":
    cli()
