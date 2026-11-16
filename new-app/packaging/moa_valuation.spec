# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for MOA Valuation (Windows).

Run from new-app/:
  pyinstaller packaging/moa_valuation.spec
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPEC is injected by PyInstaller when this file is executed.
SPECDIR = Path(SPEC).resolve().parent
APP_ROOT = SPECDIR.parent

datas = [
    (str(APP_ROOT / "config"), "config"),
    (str(APP_ROOT / "templates"), "templates"),
    (str(APP_ROOT / "logs-updation.xlsx"), "."),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "multipart",
    "pymupdf",
    "fitz",
    "openpyxl",
    "yaml",
    "pydantic",
    "anyio",
    "anyio._backends._asyncio",
    "h11",
    "sniffio",
    "click",
]

# Pull transitive modules that PyInstaller often misses for these stacks.
for pkg in ("uvicorn", "fastapi", "starlette", "pydantic", "openpyxl"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

# PyMuPDF ships binary + data files.
try:
    tmp_ret = collect_all("pymupdf")
    datas += tmp_ret[0]
    hiddenimports += tmp_ret[1]
    # binaries handled via Analysis.binaries below
    _pymupdf_binaries = tmp_ret[2]
except Exception:
    _pymupdf_binaries = []

block_cipher = None

a = Analysis(
    [str(APP_ROOT / "main.py")],
    pathex=[str(APP_ROOT)],
    binaries=_pymupdf_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MOA_Valuation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MOA_Valuation",
)
