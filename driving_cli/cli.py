"""Driving CLI Tool - 命令行入口"""

import click

from driving_cli import __version__
from driving_cli.commands import agent, check, feature, framework, gate, ide, load, refine, repo, rule, skill, update


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
