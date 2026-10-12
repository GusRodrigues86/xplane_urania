"""
bundle.py - Put the built shader, the star data and the Urania plugin into one zip file.

The zip file has the same folder layout as X-Plane 12. The user extracts it into the
X-Plane 12 folder (the folder that contains "Resources"):

    Resources/shaders/bin/spv/astronomical.xsa          the night sky shader (built here)
    Resources/default data/earth_astro.dat              the star data (built here)
    Resources/plugins/Urania/win_x64/Urania.xpl         the plugin (Windows)
    Resources/plugins/Urania/lin_x64/Urania.xpl         the plugin (Linux)
    Resources/plugins/Urania/backup/astronomical.xsa    the user's original files: the plugin menu
    Resources/plugins/Urania/backup/earth_astro.dat     "Restore X-Plane stock sky" copies them back
    Resources/plugins/Urania/install.txt                what this zip installed (the plugin checks it)
    Resources/plugins/Urania/Urania_README.txt          install, restore, credits
    Resources/plugins/Urania/licenses/*.txt             third-party licenses

2 runs with the same input files give the same zip file (fixed dates, sorted entries).
"""
import hashlib
import os
import zipfile
from dataclasses import dataclass
from importlib import resources

from urania import __version__, paths
from urania.engine import night_sky, spirv
from urania.errors import UraniaError

ZIP_DATE = (2026, 10, 11, 0, 0, 0)       # fixed date for all zip entries: same input -> same zip
PATH_XSA = "Resources/shaders/bin/spv/astronomical.xsa"
PATH_DAT = "Resources/default data/earth_astro.dat"
PLUGIN_ROOT = "Resources/plugins/Urania"
PATH_BACKUP_XSA = f"{PLUGIN_ROOT}/backup/astronomical.xsa"
PATH_BACKUP_DAT = f"{PLUGIN_ROOT}/backup/earth_astro.dat"
PATH_MANIFEST = f"{PLUGIN_ROOT}/install.txt"
PATH_README = f"{PLUGIN_ROOT}/Urania_README.txt"
PATH_LICENSES = f"{PLUGIN_ROOT}/licenses"

# Licenses that go with the files in the zip (the plugin contains Dear ImGui).
LICENSE_FILES = ("d3-celestial-LICENSE.txt", "imgui-LICENSE.txt", "NASA-SVS-credit.txt")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def license_text(name):
    return resources.files("urania").joinpath("licenses", name).read_text(encoding="utf-8")


README = """URANIA {version} - NIGHT SKY FOR X-PLANE 12
==========================================

Urania changes the X-Plane 12 night sky:
- Stars have their real colors and sizes.
- The Milky Way, nebulae and galaxies show as soft light.
- Moonlit sky: the sky glows around the moon (brightest near the moon and the horizon), the glow
  follows the moon phase and height, and the moon crescent stays bright up to its edge.
- The Urania plugin (menu Plugins > Urania) sets the cloud moonlight and the sky darkness.

This build:
- Moonlit sky: {moon}
- Screen height: {viewport_h} px
- Star brightness (STAR_GAIN): {star_gain}
- Milky Way brightness (MW_GAIN): {mw_gain}
- Nebula brightness (NEBULA_GAIN): {nebula_gain}
- Galaxy brightness (GALAXY_GAIN): {galaxy_gain}
- Data file: {stars} stars, {haze} haze rows, airglow: {airglow}
- Made from your X-Plane files: astronomical.xsa {sha_in_xsa_short}, earth_astro.dat {sha_in_dat_short}


REQUIREMENTS
------------
- X-Plane 12.4.4 or newer on Windows or Linux (Vulkan).
- X-Plane 12 for macOS uses Metal. Urania does not work on macOS. Do not install it there.
- The haze size is correct for a screen height of {viewport_h} px. On a different screen
  height, run Urania again with your screen height.


INSTALL
-------
1. Close X-Plane.
2. Extract this zip file into the X-Plane 12 folder (the folder that contains the "Resources" folder).
3. If the system asks, replace the existing files.
4. Start X-Plane. The menu Plugins > Urania opens the settings window.

Windows (PowerShell). Change the folder to your X-Plane folder:

    Expand-Archive -Path "{zip_name}" -DestinationPath "C:\\X-Plane 12" -Force

Linux (terminal):

    unzip -o "{zip_name}" -d "$HOME/X-Plane 12"

Check: the file "Resources\\default data\\earth_astro.dat" must now have a size of about
{dat_kb} KB. If you find a new folder "Resources" in the wrong place, you extracted into the
wrong folder. Delete the wrong folder and do step 2 again.


REMOVE URANIA (BACK TO THE X-PLANE SKY)
--------------------------------------
Easy way: in X-Plane, menu Plugins > Urania > "Restore X-Plane stock sky". Restart X-Plane.
Then delete the folder Resources/plugins/Urania.

By hand: copy the 2 files in Resources/plugins/Urania/backup back to their places:
    backup/astronomical.xsa  ->  Resources/shaders/bin/spv/astronomical.xsa
    backup/earth_astro.dat   ->  Resources/default data/earth_astro.dat
Or run the X-Plane installer, select "Update X-Plane", and let it restore the modified files.


AFTER AN X-PLANE UPDATE
-----------------------
An X-Plane update can replace the shader and the star file with new original files.
The Urania plugin then shows a note in its window. Run the Urania app again with the new
original files and extract the new zip.


CREDITS AND LICENSES
--------------------
- Milky Way brightness: NASA/Goddard Space Flight Center Scientific Visualization Studio,
  Deep Star Maps 2020 (https://svs.gsfc.nasa.gov/4851). Gaia DR2: ESA/Gaia/DPAC.
- Star colors (B-V): d3-celestial by Olaf Frohn, Hipparcos/Tycho data (BSD-3-Clause).
- Star positions and the original star file: Laminar Research (X-Plane 12).
- Plugin window: Dear ImGui (MIT license).
- The license texts are in Resources/plugins/Urania/licenses.
- astronomical.xsa and earth_astro.dat contain X-Plane code and data by Laminar Research
  with changes. Personal use only. Do not upload this zip to public sites.
  Laminar Research does not support shader changes.

SHA-256:
{sha_xsa}  {path_xsa}
{sha_dat}  {path_dat}
"""


@dataclass
class BundleResult:
    zip_path: str
    entries: list
    sha256: str


def _entry(name, executable=False):
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if executable else 0o644) << 16
    return info


def _setting(settings, name):
    if name not in settings:
        return "unknown"
    v = settings[name].value
    if name == "VIEWPORT_H":
        return str(int(v))
    return f"{v:g}"


def make_bundle(xsa, dat, original_xsa, original_dat, settings, out_zip, plugins=None):
    """Write the install zip. Return a BundleResult.

    xsa, dat                     the built files
    original_xsa, original_dat   the user's original X-Plane files (backup for restore)
    settings                     the shader settings (shaders.resolve_settings())
    plugins                      {platform: Urania.xpl path}; default: the bundled plugin binaries
    """
    if not spirv.is_patched(xsa):
        raise UraniaError(f"{xsa} is the X-Plane original, not the Urania shader.")
    if spirv.is_patched(original_xsa):
        raise UraniaError(f"{original_xsa} is not the X-Plane original (it is a patched shader).")
    check = night_sky.verify(dat)
    if check.haze == 0:
        raise UraniaError(f"{dat} has no haze rows. It is not the Urania star file.")
    if check.errors:
        raise UraniaError(f"{dat} has {len(check.errors)} bad rows, for example: {check.errors[0]}")
    plugins = paths.plugin_binaries() if plugins is None else plugins
    if not plugins:
        raise UraniaError("The Urania plugin binaries are missing from this Urania installation. "
                          "Download Urania again.")

    moon = spirv.has_moon(xsa)
    airglow = sum(1 for ln in night_sky.read_lines(dat) if ln.split()[3:4] == ["SKY"])
    sha_xsa, sha_dat = sha256_file(xsa), sha256_file(dat)
    sha_in_xsa, sha_in_dat = sha256_file(original_xsa), sha256_file(original_dat)
    text = README.format(
        version=__version__, moon="yes" if moon else "no (X-Plane moon)",
        viewport_h=_setting(settings, "VIEWPORT_H"), star_gain=_setting(settings, "STAR_GAIN"),
        mw_gain=_setting(settings, "MW_GAIN"), nebula_gain=_setting(settings, "NEBULA_GAIN"),
        galaxy_gain=_setting(settings, "GALAXY_GAIN"),
        stars=check.stars, haze=check.haze, airglow=f"yes ({airglow} rows)" if airglow else "no",
        sha_in_xsa_short=sha_in_xsa[:12], sha_in_dat_short=sha_in_dat[:12],
        zip_name=os.path.basename(out_zip), dat_kb=round(os.path.getsize(dat) / 1024),
        sha_xsa=sha_xsa, sha_dat=sha_dat, path_xsa=PATH_XSA, path_dat=PATH_DAT)
    readme = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")   # CRLF: Windows Notepad

    # install.txt: the plugin reads it to see if an X-Plane update replaced the files.
    manifest = "\n".join([
        f"urania {__version__}",
        f"xsa_sha256 {sha_xsa}",
        f"xsa_size {os.path.getsize(xsa)}",
        f"dat_sha256 {sha_dat}",
        f"dat_size {os.path.getsize(dat)}",
        f"moon {1 if moon else 0}",
        f"original_xsa_sha256 {sha_in_xsa}",
        f"original_dat_sha256 {sha_in_dat}",
    ]) + "\n"

    files = {
        PATH_XSA: ("file", xsa, False),
        PATH_DAT: ("file", dat, False),
        PATH_BACKUP_XSA: ("file", original_xsa, False),
        PATH_BACKUP_DAT: ("file", original_dat, False),
        PATH_MANIFEST: ("bytes", manifest.encode("utf-8"), False),
        PATH_README: ("bytes", readme, False),
    }
    for name in LICENSE_FILES:
        files[f"{PATH_LICENSES}/{name}"] = ("bytes", license_text(name).encode("utf-8"), False)
    for plat, path in plugins.items():
        files[f"{PLUGIN_ROOT}/{plat}/Urania.xpl"] = ("file", path, True)

    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    tmp = out_zip + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for name in sorted(files):
            kind, src, exe = files[name]
            if kind == "file":
                with open(src, "rb") as f:
                    data = f.read()
            else:
                data = src
            z.writestr(_entry(name, exe), data)
    os.replace(tmp, out_zip)
    return BundleResult(out_zip, sorted(files), sha256_file(out_zip))
