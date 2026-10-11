# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Urania app. Run through scripts/build_app.py (it checks vendor/ first).
#
# Output: dist/Urania/ with
#   Urania(.exe)        the window (Windows: no console)
#   urania-cli(.exe)    the same program with a console, for the command line
#   _internal/          Python, numpy, OpenEXR, Tk, tkdnd, urania package data
#       tools/          glslangValidator, spirv-val, spirv-cross (+ licenses)
#       plugin/Urania/  win_x64/Urania.xpl, lin_x64/Urania.xpl
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from urania.tools import platform_tag  # noqa: E402

TAG = platform_tag()
TOOLS = os.path.join(ROOT, "vendor", "tools", TAG)
PLUGIN = os.path.join(ROOT, "vendor", "plugin", "Urania")
TKDND_DIRS = {"win_x64": ("win-x64", "win-x64-tcl9"), "lin_x64": ("linux-x64", "linux-x64-tcl9")}[TAG]

datas = collect_data_files("urania")                       # shader_src/*.glsl, licenses/*.txt
datas += [(os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "LICENSES.md"), ".")]

# tkdnd: only the folders for this platform (the package has all platforms).
import tkinterdnd2  # noqa: E402
tkdnd_root = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
for d in TKDND_DIRS:
    src = os.path.join(tkdnd_root, d)
    if os.path.isdir(src):
        datas.append((src, os.path.join("tkinterdnd2", "tkdnd", d)))

binaries = collect_dynamic_libs("OpenEXR")
for name in os.listdir(TOOLS):
    p = os.path.join(TOOLS, name)
    if os.path.isfile(p):
        binaries.append((p, "tools"))
datas.append((os.path.join(TOOLS, "licenses"), os.path.join("tools", "licenses")))
for plat in ("win_x64", "lin_x64"):
    xpl = os.path.join(PLUGIN, plat, "Urania.xpl")
    if os.path.isfile(xpl):
        datas.append((xpl, os.path.join("plugin", "Urania", plat)))

a = Analysis(
    [os.path.join(ROOT, "packaging", "urania_entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["urania.gui", "urania.cli", "tkinterdnd2", "OpenEXR"],
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(ROOT, "packaging", "urania.ico") if TAG == "win_x64" else None
icon = icon if icon and os.path.isfile(icon) else None

gui_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Urania", console=False, icon=icon,
              upx=False, strip=False)
cli_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="urania-cli", console=True, icon=icon,
              upx=False, strip=False)
coll = COLLECT(gui_exe, cli_exe, a.binaries, a.datas, name="Urania", upx=False, strip=False)
