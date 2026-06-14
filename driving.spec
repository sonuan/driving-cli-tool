# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec 文件 - 确保所有 driving_cli.commands 子模块被正确打包

hiddenimports = [
    'driving_cli',
    'driving_cli.commands',
    'driving_cli.commands.agent',
    'driving_cli.commands.check',
    'driving_cli.commands.feature',
    'driving_cli.commands.framework',
    'driving_cli.commands.gate',
    'driving_cli.commands.ide',
    'driving_cli.commands.load',
    'driving_cli.commands.power',
    'driving_cli.commands.refine',
    'driving_cli.commands.repo',
    'driving_cli.commands.rule',
    'driving_cli.commands.skill',
    'driving_cli.commands.update',
    'driving_cli.utils',
    'driving_cli.utils.config_manager',
    'driving_cli.utils.logger',
    'driving_cli.utils.op_reporter',
    'driving_cli.utils.help_formatter',
    'driving_cli.utils.git_helper',
    'driving_cli.utils.match',
]

a = Analysis(
    ['driving_cli/cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='driving',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
