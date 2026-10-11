"""
xplane.py - Find X-Plane 12 installs, read the version, and find the original sky files.

X-Plane writes the list of its installs to:
    Windows  %LOCALAPPDATA%/x-plane_install_12.txt
    Linux    ~/.x-plane/x-plane_install_12.txt
The first line of <X-Plane>/Log.txt has the version, for example:
    Log.txt for X-Plane 12.4.4-b4-fbbdaacd (build 124414 Intel 64-bit, Vulkan ...)
"""
import os
import re
import sys
from dataclasses import dataclass

from urania.engine import night_sky, spirv

MIN_VERSION = (12, 4, 4)
XSA_REL = os.path.join("Resources", "shaders", "bin", "spv", "astronomical.xsa")
DAT_REL = os.path.join("Resources", "default data", "earth_astro.dat")
PLUGIN_REL = os.path.join("Resources", "plugins", "Urania")
CUSTOM_DAT_REL = os.path.join("Custom Data", "earth_astro.dat")
EXECUTABLES = ("X-Plane.exe", "X-Plane-x86_64", "X-Plane.app")

_VERSION_RE = re.compile(r"X-Plane (\d+)\.(\d+)\.(\d+)(?:-(\S+))?\s+\(build (\d+)")


@dataclass(frozen=True)
class XPVersion:
    major: int
    minor: int
    patch: int
    tag: str            # "r1", "b4-fbbdaacd", ...
    build: int

    @property
    def tuple(self):
        return self.major, self.minor, self.patch

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.patch}" + (f"-{self.tag}" if self.tag else "")


def install_list_file():
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA", "")
        return os.path.join(base, "x-plane_install_12.txt") if base else None
    return os.path.join(os.path.expanduser("~"), ".x-plane", "x-plane_install_12.txt")


def parse_install_list(text):
    """Return the folder paths in the text of x-plane_install_12.txt (one per line)."""
    out = []
    for line in text.splitlines():
        p = line.strip().rstrip("/\\")
        if p:
            out.append(os.path.normpath(p))
    return out


def is_xplane_root(path):
    if not path or not os.path.isdir(os.path.join(path, "Resources")):
        return False
    return any(os.path.exists(os.path.join(path, e)) for e in EXECUTABLES)


def find_installs(list_file=None):
    """Return the X-Plane 12 folders that exist, in the order of the install list."""
    list_file = list_file or install_list_file()
    if not list_file or not os.path.isfile(list_file):
        return []
    with open(list_file, encoding="utf-8", errors="replace") as f:
        return [p for p in parse_install_list(f.read()) if is_xplane_root(p)]


def parse_version(first_line):
    m = _VERSION_RE.search(first_line or "")
    if not m:
        return None
    return XPVersion(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "", int(m.group(5)))


def read_version(root):
    """Return the X-Plane version from Log.txt, or None if Log.txt is missing or unknown."""
    try:
        with open(os.path.join(root, "Log.txt"), encoding="utf-8", errors="replace") as f:
            return parse_version(f.readline())
    except OSError:
        return None


def version_ok(version):
    return version is not None and version.tuple >= MIN_VERSION


# --- Original sky files ------------------------------------------------------------------

def xsa_is_original(path):
    """True if the file is an X-Plane astronomical.xsa that is not patched."""
    try:
        return os.path.isfile(path) and not spirv.is_patched(path)
    except Exception:          # not a zip, no stage 7, ...
        return False


def dat_is_original(path):
    """True if the file is an X-Plane star file without haze rows (not changed by Urania)."""
    try:
        if not os.path.isfile(path):
            return False
        lines = night_sky.read_lines(path)
        if not any(l.strip() == "99" for l in lines):
            return False
        check = night_sky.verify(path)
        return check.stars > 0 and check.haze == 0
    except (OSError, ValueError):
        return False


@dataclass
class Found:
    path: str = None           # the original file, or None
    source: str = ""           # "installed", "Urania backup", ...
    note: str = ""             # text for the user


def _candidates(root, rel, extra_suffixes):
    base = os.path.join(root, rel)
    name = os.path.basename(rel)
    yield base, "installed file"
    yield os.path.join(root, PLUGIN_REL, "backup", name), "Urania backup"
    for suffix in extra_suffixes:
        yield base + suffix, f"backup {name}{suffix}"


def find_original_xsa(root):
    for path, source in _candidates(root, XSA_REL, (".original", ".before_urania", ".before_nightsky")):
        if xsa_is_original(path):
            return Found(path, source)
    return Found(None, "", "The installed astronomical.xsa is already changed and no backup of the original "
                           "was found. Drop the original file, or run the X-Plane installer > "
                           "\"Update X-Plane\" to restore it.")


def find_original_dat(root):
    for path, source in _candidates(root, DAT_REL, (".original",)):
        if dat_is_original(path):
            return Found(path, source)
    return Found(None, "", "The installed earth_astro.dat is already changed and no backup of the original "
                           "was found. Drop the original file, or run the X-Plane installer > "
                           "\"Update X-Plane\" to restore it.")


def custom_data_warning(root):
    """Return a warning text if Custom Data has its own earth_astro.dat, else ''."""
    p = os.path.join(root, CUSTOM_DAT_REL)
    if os.path.isfile(p):
        return (f"There is a file {CUSTOM_DAT_REL}. If X-Plane reads it, it hides the Urania star file. "
                "If the stars look unchanged after the install, move that file away.")
    return ""
