"""
tools.py - Find and run the Vulkan tools: glslangValidator, spirv-val, spirv-cross.

Search order:
  1. the folder that the caller gives (--tools);
  2. the tools bundled with Urania (frozen app: <app>/tools; source tree: vendor/tools/<platform>);
  3. %VULKAN_SDK%/Bin (Windows) or $VULKAN_SDK/bin;
  4. PATH.
"""
import os
import platform
import shutil
import subprocess
import sys

from urania import paths
from urania.errors import ToolMissing

TOOL_NAMES = ("glslangValidator", "spirv-val", "spirv-cross")

# The command that prints the version of each tool.
VERSION_ARGS = {"glslangValidator": ["--version"], "spirv-val": ["--version"], "spirv-cross": ["--revision"]}


def platform_tag():
    """Return 'win_x64', 'lin_x64' or a short text for an unsupported system."""
    machine = platform.machine().lower()
    x64 = machine in ("amd64", "x86_64")
    if sys.platform.startswith("win") and x64:
        return "win_x64"
    if sys.platform.startswith("linux") and x64:
        return "lin_x64"
    return f"{sys.platform}_{machine}"


def bundled_dir():
    """Return the folder of the bundled tools (may not exist)."""
    return paths.bundled_tools_dir(platform_tag())


def search_dirs(tools_dir=None):
    dirs = [tools_dir] if tools_dir else []
    dirs.append(bundled_dir())
    sdk = os.environ.get("VULKAN_SDK")
    if sdk:
        dirs += [os.path.join(sdk, "Bin"), os.path.join(sdk, "bin")]
    return dirs


def find_tool(name, tools_dir=None):
    """Return the full path of a tool. Raise ToolMissing if the tool is not found."""
    exe_names = (name + ".exe", name) if os.name == "nt" else (name,)
    for d in search_dirs(tools_dir):
        for exe in exe_names:
            p = os.path.join(d, exe)
            if os.path.isfile(p):
                return p
    found = shutil.which(name)
    if found:
        return found
    raise ToolMissing(f"{name} not found. {install_hint()}")


def install_hint():
    """Return the install command for the Vulkan tools on this system."""
    if os.name == "nt":
        return ("Install the Vulkan SDK (PowerShell: winget install -e --id KhronosGroup.VulkanSDK), "
                "then restart Urania.")
    return ("Install the tools with your package manager, then restart Urania. "
            "Ubuntu/Debian: sudo apt install glslang-tools spirv-tools spirv-cross   "
            "Fedora: sudo dnf install glslang spirv-tools spirv-cross   "
            "Arch: sudo pacman -S glslang spirv-tools spirv-cross")


def run(cmd):
    """Run a tool. Return stdout. Raise ToolMissing with the tool output if it fails."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **_no_window())
    except OSError as e:
        raise ToolMissing(f"cannot run {cmd[0]} ({e}). {install_hint()}") from e
    if r.returncode != 0:
        raise ToolMissing(f"error in: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}".rstrip())
    return r.stdout


def tool_version(path, name=None):
    """Return the first line of the version text of a tool, or 'unknown'."""
    name = name or os.path.splitext(os.path.basename(path))[0]
    try:
        r = subprocess.run([path] + VERSION_ARGS.get(name, ["--version"]), capture_output=True, text=True,
                           timeout=20, **_no_window())
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "unknown"


def _no_window():
    """On Windows, do not open a console window for each tool (the GUI app has no console)."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}
