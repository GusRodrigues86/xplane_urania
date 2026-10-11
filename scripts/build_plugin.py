#!/usr/bin/env python3
"""
build_plugin.py - Build and test the Urania plugin on this computer (Windows or Linux).

Before the first build, put the third-party code in place (it is not in the repository):
    plugin/SDK/                    X-Plane SDK 4.4   (see plugin/SDK/PUT_THE_SDK_HERE.txt)
    plugin/third_party/imgui/      Dear ImGui 1.92+  (see plugin/third_party/imgui/PUT_IMGUI_HERE.txt)

Steps: cmake configure -> build -> ctest -> copy Urania.xpl to vendor/plugin/Urania/<platform>/.
The Urania app bundles the files in vendor/plugin.

USAGE
    python scripts/build_plugin.py
    python scripts/build_plugin.py --sdk "D:/path/to/SDK"     (use an SDK folder in another place)
    python scripts/build_plugin.py --dev                      (URANIA_DEV=ON: test parts in the window)
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN = os.path.join(ROOT, "plugin")
sys.path.insert(0, os.path.join(ROOT, "src"))
from urania.tools import platform_tag  # noqa: E402

IMGUI_FILES = ("imgui.cpp", "imgui.h", "imgui_draw.cpp", "imgui_internal.h", "imgui_tables.cpp",
               "imgui_widgets.cpp", "imconfig.h", "imstb_rectpack.h", "imstb_textedit.h", "imstb_truetype.h",
               "LICENSE.txt")


def sh(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=PLUGIN, check=True)


def check_third_party(sdk):
    problems = []
    if not os.path.isfile(os.path.join(sdk, "CHeaders", "XPLM", "XPLMPanelGraphics.h")):
        problems.append(f"X-Plane SDK 4.4 not found in {sdk}\n    see plugin/SDK/PUT_THE_SDK_HERE.txt")
    imgui = os.path.join(PLUGIN, "third_party", "imgui")
    missing = [f for f in IMGUI_FILES if not os.path.isfile(os.path.join(imgui, f))]
    if missing:
        problems.append(f"Dear ImGui files missing in {imgui}: {', '.join(missing)}\n"
                        "    see plugin/third_party/imgui/PUT_IMGUI_HERE.txt")
    if problems:
        sys.exit("ERROR: third-party code is missing:\n  " + "\n  ".join(problems))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdk", default=os.path.join(PLUGIN, "SDK"), help="X-Plane SDK folder (CHeaders, Libraries)")
    ap.add_argument("--dev", action="store_true", help="build with URANIA_DEV=ON (test parts in the window)")
    args = ap.parse_args()

    tag = platform_tag()
    preset = {"win_x64": "windows", "lin_x64": "linux"}.get(tag)
    if not preset:
        sys.exit(f"ERROR: unsupported system {tag}. Build on Windows or Linux (x86_64).")
    sdk = os.path.abspath(args.sdk)
    check_third_party(sdk)

    sh(["cmake", "--preset", preset, f"-DXPLANE_SDK_DIR={sdk.replace(os.sep, '/')}",
        f"-DURANIA_DEV={'ON' if args.dev else 'OFF'}"])
    sh(["cmake", "--build", "--preset", preset])
    sh(["ctest", "--preset", preset])

    src = os.path.join(PLUGIN, "dist", "Urania", tag, "Urania.xpl")
    dst_dir = os.path.join(ROOT, "vendor", "plugin", "Urania", tag)
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(dst_dir, "Urania.xpl"))
    print(f"Done: {os.path.join(dst_dir, 'Urania.xpl')}")


if __name__ == "__main__":
    main()
