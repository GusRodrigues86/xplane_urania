#!/usr/bin/env python3
"""
build_tools.py - Build the 3 Vulkan tools that Urania bundles, from source, on this computer.

    glslangValidator   (KhronosGroup/glslang)
    spirv-val          (KhronosGroup/SPIRV-Tools, needs SPIRV-Headers)
    spirv-cross        (KhronosGroup/SPIRV-Cross)

All 4 repositories are cloned at the same Vulkan SDK tag (SDK_TAG). The tools are linked
statically (Windows: static MSVC runtime; Linux: static libstdc++), so the user needs nothing else.

Output: vendor/tools/<win_x64|lin_x64>/ with the 3 programs and their license files.

Needs: git, CMake 3.21+, and a C++ compiler (Visual Studio 2022 Build Tools on Windows, g++ on Linux).

USAGE
    python scripts/build_tools.py            build for this computer
    python scripts/build_tools.py --clean    remove the old source and build folders first
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from urania.tools import platform_tag  # noqa: E402

SDK_TAG = "vulkan-sdk-1.4.363.0"
REPOS = {
    "SPIRV-Headers": "https://github.com/KhronosGroup/SPIRV-Headers.git",
    "SPIRV-Tools": "https://github.com/KhronosGroup/SPIRV-Tools.git",
    "glslang": "https://github.com/KhronosGroup/glslang.git",
    "SPIRV-Cross": "https://github.com/KhronosGroup/SPIRV-Cross.git",
}
LICENSES = {"glslang": "LICENSE.txt", "SPIRV-Tools": "LICENSE", "SPIRV-Headers": "LICENSE", "SPIRV-Cross": "LICENSE"}


def sh(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def cmake_common():
    args = ["-DCMAKE_BUILD_TYPE=Release"]
    if os.name == "nt":
        args += ["-A", "x64", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
                 "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW"]
    else:
        args += ["-DCMAKE_EXE_LINKER_FLAGS=-static-libgcc -static-libstdc++"]
    return args


def build(src, bld, extra, targets):
    sh(["cmake", "-S", src, "-B", bld] + cmake_common() + extra)
    for t in targets:
        sh(["cmake", "--build", bld, "--config", "Release", "--target", t, "--parallel"])


def find_exe(bld, name):
    exe = name + (".exe" if os.name == "nt" else "")
    for dirpath, _, files in os.walk(bld):
        if exe in files:
            return os.path.join(dirpath, exe)
    sys.exit(f"ERROR: {exe} not found in {bld}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", action="store_true", help="remove the old source and build folders first")
    args = ap.parse_args()

    tag = platform_tag()
    if tag not in ("win_x64", "lin_x64"):
        sys.exit(f"ERROR: unsupported system {tag}")
    work = os.path.join(ROOT, "build", "tools", tag)
    srcs = os.path.join(ROOT, "build", "tools", "src")
    out = os.path.join(ROOT, "vendor", "tools", tag)
    if args.clean:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(srcs, ignore_errors=True)
    os.makedirs(srcs, exist_ok=True)

    for name, url in REPOS.items():
        d = os.path.join(srcs, name)
        if not os.path.isdir(d):
            sh(["git", "-c", "advice.detachedHead=false", "clone", "--depth", "1", "--branch", SDK_TAG, url, d])

    headers = os.path.join(srcs, "SPIRV-Headers").replace("\\", "/")   # CMake reads \ as an escape
    build(os.path.join(srcs, "SPIRV-Tools"), os.path.join(work, "spirv-tools"),
          [f"-DSPIRV-Headers_SOURCE_DIR={headers}", "-DSPIRV_SKIP_TESTS=ON", "-DSPIRV_WERROR=OFF",
           "-DSPIRV_TOOLS_BUILD_STATIC=ON", "-DBUILD_SHARED_LIBS=OFF"],
          ["spirv-val"])
    build(os.path.join(srcs, "glslang"), os.path.join(work, "glslang"),
          ["-DENABLE_OPT=OFF", "-DGLSLANG_TESTS=OFF", "-DENABLE_HLSL=OFF", "-DBUILD_SHARED_LIBS=OFF",
           "-DGLSLANG_ENABLE_INSTALL=OFF"],
          ["glslang-standalone"])
    build(os.path.join(srcs, "SPIRV-Cross"), os.path.join(work, "spirv-cross"),
          ["-DSPIRV_CROSS_CLI=ON", "-DSPIRV_CROSS_ENABLE_TESTS=OFF", "-DSPIRV_CROSS_SHARED=OFF"],
          ["spirv-cross"])

    os.makedirs(out, exist_ok=True)
    ext = ".exe" if os.name == "nt" else ""
    copies = {"glslangValidator": find_exe(os.path.join(work, "glslang"), "glslang"),
              "spirv-val": find_exe(os.path.join(work, "spirv-tools"), "spirv-val"),
              "spirv-cross": find_exe(os.path.join(work, "spirv-cross"), "spirv-cross")}
    for name, path in copies.items():
        dst = os.path.join(out, name + ext)
        shutil.copy2(path, dst)
        os.chmod(dst, 0o755)
        print(f"  {dst}")
    lic = os.path.join(out, "licenses")
    os.makedirs(lic, exist_ok=True)
    for repo, f in LICENSES.items():
        shutil.copy2(os.path.join(srcs, repo, f), os.path.join(lic, f"{repo}-LICENSE.txt"))
    with open(os.path.join(out, "VERSION.txt"), "w", newline="\n") as f:
        f.write(f"Built from source by scripts/build_tools.py at tag {SDK_TAG} ({tag}).\n")
    print(f"Done: {out}")


if __name__ == "__main__":
    main()
