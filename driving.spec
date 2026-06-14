# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec 文件 - 确保所有 driving_cli 子模块被正确打包

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 强制收集 driving_cli 下所有子模块，不依赖静态分析
all_hidden = collect_submodules('driving_cli')

a = Analysis(
    ['driving_cli/cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=all_hidden,
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
