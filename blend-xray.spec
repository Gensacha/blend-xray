# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""PyInstaller spec for the portable Blend X-Ray window.

Build it with (from a checkout, inside the project venv):

    python -m pip install "pyinstaller>=6.6"
    python -m PyInstaller --noconfirm --clean blend-xray.spec

The result is ``dist/BlendXRay.exe``: one file, no installer, no registry
write, no admin rights. It is **unsigned** -- see the README for what Windows
SmartScreen does about that on first run.

Three things in here are load-bearing and easy to lose in a "cleanup":

1. ``copy_metadata("blender-asset-tracer")``. ``scanner.assert_bat_version()``
   reads the installed distribution metadata to refuse BAT 2.x. A frozen build
   without that metadata raises PackageNotFoundError and the tool refuses to
   run at all -- the version guard fails closed, which is correct, but it makes
   the exe useless. The metadata must ship.
2. ``upx=False``. UPX-compressed executables are a well-known antivirus
   heuristic trigger. An unsigned security tool that also looks packed is a
   tool nobody gets to run.
3. ``blend_xray/known_scripts.json``. PyInstaller collects code, not data
   files. Without this line the frozen build still runs, but its known-script
   database is empty, every recognised release is reported as an unrecognised
   script again, and the only symptom is a line in the report saying the
   database was not found -- which is easy to read past.
4. The blender-asset-tracer sweep is scoped to ``.blendfile`` and must stay
   scoped. See the comment on ``BAT_PACKAGE`` below.
"""

import ast
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

#: Only subpackage of blender-asset-tracer this project uses. The whole symbol
#: surface is ``blender_asset_tracer.blendfile.BlendFile`` (blend_xray/
#: scanner.py). Sweeping the top-level package instead pulled in ``pack.shaman``
#: -- BAT's *upload* client -- and with it requests, urllib3, certifi, idna,
#: _socket.pyd, _ssl.pyd, libssl-3.dll and libcrypto-3.dll: a complete HTTP and
#: TLS stack, in an offline inspection tool that documents itself as making no
#: network calls. The behaviour was always true; the bundle contradicted it,
#: and a bundled OpenSSL is a discrepancy that gets published rather than
#: reported. Widen this only for a symbol this project actually imports.
BAT_PACKAGE = "blender_asset_tracer.blendfile"


def _project_version() -> str:
    """Read ``__version__`` out of the package source without importing it.

    The spec runs before anything is built and must not depend on the project
    being importable from the build directory; parsing the assignment keeps
    ``blend_xray/_version.py`` the one place a version number is written.

    It is ``_version.py`` and not ``__init__.py`` because setuptools' static
    ``attr:`` lookup finds the double-click launcher ``blend_xray.py`` at the
    repo root first, reads no version from it, then falls back to importing it
    and raises. A dedicated module is the one path with no ambiguity.
    """
    source = (Path(SPECPATH) / "blend_xray" / "_version.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(getattr(t, "id", None) == "__version__" for t in node.targets):
                return str(node.value.value)
    raise SystemExit("blend_xray/_version.py no longer defines __version__")


VERSION = _project_version()
#: Windows VERSIONINFO wants exactly four integers.
VERSION_TUPLE = tuple((list(map(int, re.findall(r"\d+", VERSION))) + [0, 0, 0, 0])[:4])


def _version_resource():
    """A VERSIONINFO resource, or None when this PyInstaller cannot build one.

    Properties > Details on an unsigned executable that is blank there reads as
    one more reason not to trust it -- to precisely the cautious user this tool
    is for, and who was told to check the file before running it. It is also
    the only way a zip user can answer SECURITY.md's "which version".
    """
    try:
        from PyInstaller.utils.win32.versioninfo import (
            FixedFileInfo,
            StringFileInfo,
            StringStruct,
            StringTable,
            VarFileInfo,
            VarStruct,
            VSVersionInfo,
        )
    except ImportError:  # pragma: no cover - non-Windows build host
        return None
    strings = [
        StringStruct("CompanyName", "Sacha Geneviève"),
        StringStruct("FileDescription", "Blend X-Ray -- inspect a .blend file for embedded code"),
        StringStruct("FileVersion", VERSION),
        StringStruct("InternalName", "BlendXRay"),
        StringStruct("LegalCopyright", "GPL-3.0-or-later"),
        StringStruct("OriginalFilename", "BlendXRay.exe"),
        StringStruct("ProductName", "Blend X-Ray"),
        StringStruct("ProductVersion", VERSION),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
        kids=[
            StringFileInfo([StringTable("040904B0", strings)]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )


datas = []
hiddenimports = []

# See note 1 in the module docstring. Do not remove.
datas += copy_metadata("blender-asset-tracer")
# See note 4 and the comment on BAT_PACKAGE. Do not widen.
hiddenimports += collect_submodules(BAT_PACKAGE)

# See note 3 in the module docstring. Do not remove.
datas += [("blend_xray/known_scripts.json", "blend_xray")]

# Drag-and-drop is optional: tkinterdnd2 ships a Tcl library that has to be
# collected as data. If it is not installed we simply build without it, and
# the window falls back to its "Choose a file..." buttons at runtime.
try:
    datas += collect_data_files("tkinterdnd2")
    hiddenimports += collect_submodules("tkinterdnd2")
except Exception:  # noqa: BLE001 - absence is a supported configuration
    pass

a = Analysis(
    ["blend_xray_gui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "setuptools", "pip"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BlendXRay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # See note 2 in the module docstring.
    runtime_tmpdir=None,
    console=False,  # A window, not a console. The CLI is a separate entry point.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_version_resource(),
)
