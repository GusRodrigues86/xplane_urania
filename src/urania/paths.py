"""
paths.py - Where Urania finds the files that it bundles.

Frozen app (PyInstaller):  <app>/tools/...        <app>/plugin/Urania/<win_x64|lin_x64>/Urania.xpl
Source tree:               vendor/tools/<plat>/  vendor/plugin/Urania/<win_x64|lin_x64>/Urania.xpl
"""
import os
import sys

PLUGIN_NAME = "Urania"
PLUGIN_PLATFORMS = ("win_x64", "lin_x64")


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def app_root():
    """The folder that holds the bundled files."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vendor"))


def repo_root():
    """The source tree root (only meaningful when not frozen)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def bundled_tools_dir(platform_tag):
    if is_frozen():
        return os.path.join(app_root(), "tools")
    return os.path.join(app_root(), "tools", platform_tag)


def plugin_dir():
    """Folder with <platform>/Urania.xpl for each platform."""
    return os.path.join(app_root(), "plugin", PLUGIN_NAME)


def plugin_binaries(base=None):
    """Return {platform: path} for the plugin binaries that exist."""
    base = base or plugin_dir()
    found = {}
    for plat in PLUGIN_PLATFORMS:
        p = os.path.join(base, plat, PLUGIN_NAME + ".xpl")
        if os.path.isfile(p):
            found[plat] = p
    return found
