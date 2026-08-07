# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for VectorForge Windows .exe
# Build on Windows:
#   pyinstaller --noconfirm VectorForge.spec
#
# More defensive against TOC / collect_all edge cases on newer Python.

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

def _safe_collect_all(package_name):
    """Return (datas, binaries, hiddenimports) with only valid 3-tuples."""
    try:
        from PyInstaller.utils.hooks import collect_all
        datas, binaries, hiddenimports = collect_all(package_name)
    except Exception as e:
        print(f"warn: collect_all({package_name}) failed: {e}")
        return [], [], []

    def _clean(entries):
        cleaned = []
        for item in entries:
            if isinstance(item, (list, tuple)) and len(item) == 3:
                cleaned.append(tuple(item))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                # Some hooks return 2-tuples; treat as (src, dest) data
                cleaned.append((item[0], item[1], "DATA"))
            else:
                print(f"warn: skipping malformed TOC entry: {item!r}")
        return cleaned

    return _clean(datas), _clean(binaries), list(hiddenimports or [])


a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "vtracer",
        "rembg",
        "rembg.sessions",
        "rembg.sessions.u2net",
        "onnxruntime",
        "PIL._tkinter_finder",
        "customtkinter",
        "vectorforge",
        "vectorforge.engine",
        "vectorforge.ui",
        "vectorforge.ui.app",
        "vectorforge.cli",
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

# Bundle customtkinter assets safely
try:
    ct_datas, ct_binaries, ct_hidden = _safe_collect_all("customtkinter")
    a.datas += ct_datas
    a.binaries += ct_binaries
    a.hiddenimports += ct_hidden
except Exception as e:
    print("warn: customtkinter collect failed", e)

# Also try to pull any extra data from rembg if present
try:
    rb_datas, rb_binaries, rb_hidden = _safe_collect_all("rembg")
    a.datas += rb_datas
    a.binaries += rb_binaries
    a.hiddenimports += rb_hidden
except Exception:
    pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VectorForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can cause issues with some native libs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # set True for debug builds to see crashes
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
