# -*- mode: python ; coding: utf-8 -*-
# VectorForge v0.5 — PyInstaller one-file Windows build
#   pyinstaller --noconfirm VectorForge.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'vtracer',
        'rembg',
        'rembg.sessions',
        'rembg.sessions.u2net',
        'onnxruntime',
        'cv2',
        'numpy',
        'PIL._tkinter_finder',
        'customtkinter',
        'vectorforge',
        'vectorforge.engine',
        'vectorforge.engine.preprocess',
        'vectorforge.engine.vectorize',
        'vectorforge.engine.bg_remove',
        'vectorforge.engine.presets',
        'vectorforge.engine.memory',
        'vectorforge.engine.image_ops',
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

try:
    from PyInstaller.utils.hooks import collect_all
    tmp_ret = collect_all('customtkinter')
    a.datas += tmp_ret[0]
    a.binaries += tmp_ret[1]
    a.hiddenimports += tmp_ret[2]
except Exception as e:
    print('warn: customtkinter collect_all failed', e)

try:
    from PyInstaller.utils.hooks import collect_dynamic_libs
    a.binaries += collect_dynamic_libs('cv2')
except Exception as e:
    print('warn: cv2 libs collect failed', e)

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
