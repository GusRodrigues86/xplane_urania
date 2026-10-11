#!/usr/bin/env python3
"""
build_app.py - Freeze the Urania app with PyInstaller (on this computer: Windows or Linux).

Needs (in vendor/, made by the other scripts):
    vendor/tools/<platform>/          python scripts/build_tools.py
    vendor/plugin/Urania/<platform>/  python scripts/build_plugin.py   (on Windows AND Linux, for the zip)

Output: dist/Urania/  (Urania + urania-cli programs, with everything inside)
Then a quick test: urania-cli --version and urania-cli check run from dist/.

USAGE
    python scripts/build_app.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from urania.tools import TOOL_NAMES, platform_tag  # noqa: E402


def main():
    tag = platform_tag()
    tools = os.path.join(ROOT, "vendor", "tools", tag)
    ext = ".exe" if os.name == "nt" else ""
    missing = [n for n in TOOL_NAMES if not os.path.isfile(os.path.join(tools, n + ext))]
    if missing:
        sys.exit(f"ERROR: {', '.join(missing)} missing in {tools}. Run: python scripts/build_tools.py")
    plugins = [p for p in ("win_x64", "lin_x64")
               if os.path.isfile(os.path.join(ROOT, "vendor", "plugin", "Urania", p, "Urania.xpl"))]
    if not plugins:
        sys.exit("ERROR: no plugin in vendor/plugin. Run: python scripts/build_plugin.py")
    if len(plugins) < 2:
        print(f"WARNING: only the {plugins[0]} plugin is in vendor/plugin. The zips made by this app will "
              "work only on that system. Build the plugin on the other system too (see README).")

    work = os.path.join(ROOT, "build", "pyinstaller")
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(os.path.join(dist, "Urania"), ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--workpath", work,
                    "--distpath", dist, os.path.join(ROOT, "packaging", "urania.spec")], check=True)

    cli = os.path.join(dist, "Urania", "urania-cli" + ext)
    subprocess.run([cli, "--version"], check=True)
    r = subprocess.run([cli, "check", "--out", dist], capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        sys.exit("ERROR: the frozen app found a problem (see above).")
    print(f"Done: {os.path.join(dist, 'Urania')}")


if __name__ == "__main__":
    main()
