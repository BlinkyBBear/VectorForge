# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for VectorForge Windows .exe (and other platforms).
# Build on Windows for a native .exe:
#   pyinstaller VectorForge.spec
#
# First-run rembg model downloads to %USERPROFILE%\.u2net\ (or U2NET_HOME).
# To fully offline-bundle the model, place u2net.onnx next to the exe and set
# U2NET_HOME in the runtime hook (optional — see scripts/hooks).

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'vtracer',
        'rembg',
        'rembg.sessions',
        'rembg.sessions.u2net',
        'onnxruntime',
        'PIL._tkinter_finder',
        'customtkinter',
        'vectorforge',
        'vectorforge.engine',
        'vectorforge.ui',
        'vectorforge.ui.app',
        'vectorforge.cli',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Bundle customtkinter assets
try:
    import customtkinter
    from PyInstaller.utils.hooks import collect_all

    tmp_ret = collect_all('customtkinter')
    a.datas += tmp_ret[0]
    a.binaries += tmp_ret[1]
    a.hiddenimports += tmp_ret[2]
except Exception as e:
    print('warn: customtkinter collect_all failed', e)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VectorForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app; use console=True for debug builds
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
