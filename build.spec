# -*- mode: python ; coding: utf-8 -*-
"""
BossKey build spec - 修复版
显式收集所有 PyQt5 依赖，确保 Qt 平台插件被包含
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None

# 显式收集 PyQt5 所有数据（包括 plugins/platforms/qwindows.dll）
datas, binaries, hiddenimports = collect_all('PyQt5')

# 补充 pywin32
pywin32_data, pywin32_bin, pywin32_hidden = collect_all('win32gui')
datas += pywin32_data
binaries += pywin32_bin
hiddenimports += pywin32_hidden

hiddenimports += [
    'win32con', 'win32process', 'win32api',
]

# 添加项目自身的数据文件
datas += [
    ('assets/icon.ico', 'assets'),
]

print(f"[INFO] 共收集 {len(datas)} 个数据文件")
print(f"[INFO] 共收集 {len(binaries)} 个二进制文件")
print(f"[INFO] 共收集 {len(hiddenimports)} 个隐藏导入")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BossKey',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    uac_admin=True,
)
