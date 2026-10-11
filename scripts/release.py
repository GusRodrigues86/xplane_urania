#!/usr/bin/env python3
"""
release.py - Test everything and pack the frozen app for users.

Steps:
    1. pytest (all tests, also the Vulkan-tool tests; -m real too if the inputs are present)
    2. ctest (plugin core tests)
    3. build_app.py (PyInstaller)
    4. dist/Urania-<version>-windows-x64.zip   or   dist/Urania-<version>-linux-x64.tar.gz

Before: build_tools.py and build_plugin.py on BOTH systems (the plugin of the other system goes
into vendor/plugin/Urania/<platform>/ by hand or by a shared folder), so the zips work everywhere.

USAGE
    python scripts/release.py
    python scripts/release.py --skip-tests
"""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from urania import __version__  # noqa: E402
from urania.tools import platform_tag  # noqa: E402

USER_README = """URANIA {version} - NIGHT SKY FOR X-PLANE 12.4.4+
==============================================

1. Start Urania: {start}
2. The window shows what you need. Urania finds X-Plane 12 and its original files.
   Download the 2 data files with the "Get it" buttons and drop them into the window:
     - d3-celestial-0.7.35.tgz (star colors)
     - milkyway_2020_4k.exr    (Milky Way, NASA SVS 4851)
3. Click "Build Urania zip".
4. Close X-Plane. Extract the zip into your X-Plane 12 folder (the folder with "Resources").
5. Start X-Plane. Menu Plugins > Urania.

Command line: {cli} --help

Remove: X-Plane menu Plugins > Urania > "Restore X-Plane stock sky...", restart X-Plane.

Urania is free software (MIT). See LICENSE and LICENSES.md.
The zip that Urania builds contains changed X-Plane files: it is for your personal use only.
"""


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    tag = platform_tag()
    name = {"win_x64": "windows-x64", "lin_x64": "linux-x64"}[tag]
    preset = {"win_x64": "windows", "lin_x64": "linux"}[tag]

    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "-m", "not real or real"])
        run(["ctest", "--preset", preset], cwd=os.path.join(ROOT, "plugin"))
    run([sys.executable, os.path.join(ROOT, "scripts", "build_app.py")])

    app = os.path.join(ROOT, "dist", "Urania")
    is_win = tag == "win_x64"
    with open(os.path.join(app, "README.txt"), "w", encoding="utf-8", newline="\r\n" if is_win else "\n") as f:
        f.write(USER_README.format(version=__version__,
                                   start="double-click Urania.exe" if is_win else "run ./Urania",
                                   cli="urania-cli.exe" if is_win else "./urania-cli"))
    base = os.path.join(ROOT, "dist", f"Urania-{__version__}-{name}")
    if is_win:
        out = base + ".zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for d, _, files in os.walk(app):
                for fn in sorted(files):
                    p = os.path.join(d, fn)
                    z.write(p, os.path.join("Urania", os.path.relpath(p, app)))
    else:
        out = base + ".tar.gz"                     # tar keeps the exec bits of the programs and tools
        with tarfile.open(out, "w:gz") as t:
            t.add(app, arcname="Urania")
    print(f"Done: {out} ({os.path.getsize(out) // (1 << 20)} MB)")


if __name__ == "__main__":
    main()
