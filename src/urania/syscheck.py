"""
syscheck.py - Check this computer before a build. Each check tells the user how to fix a problem.

Frozen app: Python and the packages are inside the app. The checks are: system, bundled tools,
plugin files, disk space, write access.
Source mode (python -m urania): also the Python version and the Python packages.
"""
import importlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from urania import paths, tools
from urania.errors import ToolMissing

OK, WARN, FAIL = "ok", "warn", "fail"
MIN_FREE_MB = 500
MIN_GLIBC = (2, 35)            # the Linux app and tools are built on Ubuntu 22.04
PY_MIN, PY_MAX = (3, 9), (3, 14)
PACKAGES = (("numpy", "numpy"), ("OpenEXR", "OpenEXR>=3.3"), ("tkinterdnd2", "tkinterdnd2"))


@dataclass
class Item:
    name: str
    status: str               # ok / warn / fail
    detail: str
    fix: str = ""             # what the user must do (empty if nothing)
    fix_command: list = None  # a command that Urania can run for the user (pip install), or None


def check_system():
    tag = tools.platform_tag()
    if tag in ("win_x64", "lin_x64"):
        return Item("System", OK, f"{platform.system()} {platform.release()} ({platform.machine()})")
    if sys.platform == "darwin":
        return Item("System", FAIL, "macOS: X-Plane uses Metal there. Urania works only with Vulkan.",
                    "Use Urania on Windows or Linux.")
    return Item("System", FAIL, f"Unsupported system: {tag}", "Use Windows or Linux on a 64-bit x86 computer.")


def check_glibc():
    if not sys.platform.startswith("linux"):
        return None
    name, ver = platform.libc_ver()
    try:
        parts = tuple(int(x) for x in ver.split(".")[:2])
    except ValueError:
        parts = ()
    if name != "glibc" or not parts:
        return Item("C library", WARN, f"{name or 'unknown'} {ver}: Urania is built for glibc {MIN_GLIBC[0]}."
                    f"{MIN_GLIBC[1]} or newer.")
    if parts < MIN_GLIBC:
        return Item("C library", FAIL, f"glibc {ver} is too old.",
                    f"Urania needs glibc {MIN_GLIBC[0]}.{MIN_GLIBC[1]} or newer (Ubuntu 22.04, Fedora 36 or newer).")
    return Item("C library", OK, f"glibc {ver}")


def check_python():
    if paths.is_frozen():
        return None
    v = sys.version_info[:2]
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    if bits != 64 or not (PY_MIN <= v <= PY_MAX):
        return Item("Python", FAIL, f"Python {platform.python_version()} {bits}-bit",
                    "Install Python 3.9 to 3.14, 64-bit (Windows: winget install -e --id Python.Python.3.13).")
    return Item("Python", OK, f"Python {platform.python_version()} 64-bit")


def check_packages():
    if paths.is_frozen():
        return []
    items = []
    missing = []
    for module, req in PACKAGES:
        try:
            m = importlib.import_module(module)
            if module == "OpenEXR" and not hasattr(m, "File"):
                raise ImportError("OpenEXR older than 3.3")
            items.append(Item(f"Package {module}", OK, getattr(m, "__version__", "installed")))
        except ImportError as e:
            missing.append(req)
            items.append(Item(f"Package {module}", FAIL, f"not installed ({e})"))
    if missing:
        cmd = [sys.executable, "-m", "pip", "install"] + missing
        for it in items:
            if it.status == FAIL:
                it.fix = "Install the Python packages: " + " ".join(f'"{c}"' if " " in c or ">" in c else c
                                                                    for c in cmd)
                it.fix_command = cmd
    return items


def check_tools(tools_dir=None):
    items = []
    for name in tools.TOOL_NAMES:
        try:
            path = tools.find_tool(name, tools_dir)
        except ToolMissing:
            items.append(Item(name, FAIL, "not found", tools.install_hint()))
            continue
        if os.name != "nt" and not os.access(path, os.X_OK):
            items.append(Item(name, FAIL, f"{path} is not executable", f"Run: chmod +x \"{path}\""))
            continue
        version = tools.tool_version(path, name)
        if version == "unknown":
            items.append(Item(name, FAIL, f"{path} does not run", tools.install_hint()))
        else:
            where = "bundled" if os.path.dirname(path) == tools.bundled_dir() else path
            items.append(Item(name, OK, f"{version} ({where})"))
    return items


def check_plugin():
    found = paths.plugin_binaries()
    missing = [p for p in paths.PLUGIN_PLATFORMS if p not in found]
    if not found:
        return Item("Urania plugin", FAIL, "plugin files not found", "Download Urania again (the app is not complete).")
    if missing:
        return Item("Urania plugin", WARN, f"only {', '.join(found)}; missing {', '.join(missing)}",
                    "The zip works only on the systems that have a plugin file.")
    return Item("Urania plugin", OK, ", ".join(found))


def check_output_dir(out_dir):
    out_dir = out_dir or os.getcwd()
    probe_dir = out_dir
    while probe_dir and not os.path.isdir(probe_dir):
        parent = os.path.dirname(probe_dir)
        if parent == probe_dir:
            break
        probe_dir = parent
    try:
        free_mb = shutil.disk_usage(probe_dir).free // (1 << 20)
    except OSError as e:
        return [Item("Output folder", FAIL, f"{out_dir}: {e}", "Choose another output folder.")]
    items = []
    if free_mb < MIN_FREE_MB:
        items.append(Item("Disk space", FAIL, f"{free_mb} MB free in {probe_dir}",
                          f"Free at least {MIN_FREE_MB} MB, or choose another output folder."))
    else:
        items.append(Item("Disk space", OK, f"{free_mb} MB free"))
    try:
        with tempfile.NamedTemporaryFile(dir=probe_dir, prefix=".urania_write_test"):
            pass
        items.append(Item("Output folder", OK, f"writable: {out_dir}"))
    except OSError as e:
        items.append(Item("Output folder", FAIL, f"cannot write in {probe_dir} ({e})", "Choose another output folder."))
    return items


def run_all(out_dir=None, tools_dir=None):
    """Return the list of check Items."""
    items = [check_system()]
    for extra in (check_glibc(), check_python()):
        if extra:
            items.append(extra)
    items += check_packages()
    items += check_tools(tools_dir)
    items.append(check_plugin())
    items += check_output_dir(out_dir)
    return items


def blocking(items):
    return [i for i in items if i.status == FAIL]


def run_fix(item):
    """Run the fix command of an item (pip install). Return (ok, output text)."""
    if not item.fix_command:
        return False, "No automatic fix. " + item.fix
    try:
        r = subprocess.run(item.fix_command, capture_output=True, text=True, **tools._no_window())
    except OSError as e:
        return False, str(e)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 and "externally-managed-environment" in out:
        out += ("\n\nThis Python does not allow pip installs. Make a virtual environment:\n"
                "  python3 -m venv .venv  then  .venv/bin/python -m pip install -e .  then  .venv/bin/urania")
    return r.returncode == 0, out
