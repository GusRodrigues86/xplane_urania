"""
inputs.py - The input files of Urania: what each one is, where the user gets it, how to check it.

Each InputSpec has a validator: validate(path) -> Check(ok, message). The GUI shows the
"where" text and the link next to each drop zone.
"""
import json
import os
import tarfile
from dataclasses import dataclass, field

from urania import xplane
from urania.engine import night_sky, shaders
from urania.errors import UraniaError

D3_URL = "https://registry.npmjs.org/d3-celestial/-/d3-celestial-0.7.35.tgz"
D3_MEMBER = "package/data/stars.8.json"
NASA_URL = "https://svs.gsfc.nasa.gov/4851"


@dataclass
class Check:
    ok: bool
    message: str
    warning: str = ""


@dataclass
class InputSpec:
    key: str
    title: str
    file_name: str            # usual name ("" for a folder)
    where: str                # where to get it (text for the user)
    url: str = ""
    is_folder: bool = False
    extensions: tuple = field(default_factory=tuple)

    def validate(self, path):
        return VALIDATORS[self.key](path)


SPECS = [
    InputSpec("xplane", "X-Plane 12 folder", "", is_folder=True,
              where="The folder that contains \"Resources\" and the X-Plane program. Urania finds it "
                    "automatically if X-Plane 12 is installed. X-Plane 12.4.4 or newer."),
    InputSpec("xsa", "Original shader", "astronomical.xsa", extensions=(".xsa",),
              where="From your X-Plane folder: Resources/shaders/bin/spv/astronomical.xsa. Urania takes it "
                    "automatically. It must be the X-Plane original (not changed by a sky mod)."),
    InputSpec("dat", "Original star file", "earth_astro.dat", extensions=(".dat",),
              where="From your X-Plane folder: Resources/default data/earth_astro.dat. Urania takes it "
                    "automatically. It must be the X-Plane original (not changed by a sky mod)."),
    InputSpec("stars", "Star catalog", "stars.8.json", url=D3_URL, extensions=(".json", ".tgz"),
              where="d3-celestial 0.7.35 (BSD-3-Clause). Download the .tgz file from the link. Drop the .tgz "
                    "itself, or the file package/data/stars.8.json from inside it."),
    InputSpec("milkyway", "Milky Way map", "milkyway_2020_4k.exr", url=NASA_URL, extensions=(".exr",),
              where="NASA SVS 4851 \"Deep Star Maps 2020\". Open the link in a web browser and download "
                    "milkyway_2020_4k.exr (about 36 MB)."),
]
SPEC_BY_KEY = {s.key: s for s in SPECS}


# --- Validators --------------------------------------------------------------------------

def validate_xplane(path):
    if not xplane.is_xplane_root(path):
        return Check(False, "This is not an X-Plane folder (no Resources folder and X-Plane program).")
    v = xplane.read_version(path)
    warn = xplane.custom_data_warning(path)
    if v is None:
        return Check(True, "X-Plane folder (version unknown: no Log.txt; start X-Plane 1 time to make it).",
                     warning="Urania needs X-Plane 12.4.4 or newer. Urania cannot check the version." +
                             (" " + warn if warn else ""))
    if not xplane.version_ok(v):
        return Check(False, f"X-Plane {v} is too old. Urania needs X-Plane 12.4.4 or newer. Update X-Plane.")
    return Check(True, f"X-Plane {v} (build {v.build})", warning=warn)


def validate_xsa(path):
    if not os.path.isfile(path):
        return Check(False, "File not found.")
    try:
        zin, _ = shaders.open_stock(path)
        zin.close()
    except UraniaError as e:
        return Check(False, str(e))
    return Check(True, "X-Plane original shader (9 stages)")


def validate_dat(path):
    if not os.path.isfile(path):
        return Check(False, "File not found.")
    if not xplane.dat_is_original(path):
        try:
            haze = night_sky.verify(path).haze
        except (OSError, ValueError):
            haze = 0
        if haze:
            return Check(False, "This star file is already changed by a sky mod (it has haze rows). "
                                "Use the X-Plane original.")
        return Check(False, "This is not an X-Plane earth_astro.dat file.")
    n = night_sky.verify(path).stars
    return Check(True, f"X-Plane original star file ({n} stars)")


def _check_catalog_json(data):
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list) or not feats:
        return None
    with_bv = sum(1 for f in feats if isinstance(f, dict) and f.get("properties", {}).get("bv") not in (None, ""))
    return len(feats), with_bv


def validate_stars(path):
    if not os.path.isfile(path):
        return Check(False, "File not found.")
    try:
        if path.lower().endswith((".tgz", ".tar.gz")):
            with tarfile.open(path, "r:gz") as t:
                f = t.extractfile(D3_MEMBER)
                if f is None:
                    raise KeyError(D3_MEMBER)
                data = json.load(f)
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
    except KeyError:
        return Check(False, f"The .tgz file has no {D3_MEMBER}. Use d3-celestial 0.7.35.")
    except (OSError, ValueError, tarfile.TarError) as e:
        return Check(False, f"Cannot read the catalog ({e}).")
    counts = _check_catalog_json(data)
    if not counts or counts[1] == 0:
        return Check(False, "This is not the d3-celestial star catalog (no stars with a B-V color).")
    return Check(True, f"Star catalog: {counts[0]} stars, {counts[1]} with color")


def validate_milkyway(path):
    if not os.path.isfile(path):
        return Check(False, "File not found.")
    try:
        import OpenEXR
        with OpenEXR.File(path, header_only=True) as f:
            header = f.header()
        if "dataWindow" in header:                 # fast: the header only (the NASA file has it)
            (x0, y0), (x1, y1) = header["dataWindow"]
            w, h = int(x1 - x0 + 1), int(y1 - y0 + 1)
        else:                                      # some writers: read the image size from the pixels
            with OpenEXR.File(path) as f:
                h, w = f.channels()["RGB"].pixels.shape[:2]
    except Exception as e:                     # OpenEXR raises several error types
        return Check(False, f"This is not an OpenEXR image ({e}).")
    if w != 2 * h or h % 16:
        return Check(False, f"The map must be 2:1 (for example 4096 x 2048), not {w} x {h}.")
    return Check(True, f"Milky Way map {w} x {h}")


VALIDATORS = {"xplane": validate_xplane, "xsa": validate_xsa, "dat": validate_dat,
              "stars": validate_stars, "milkyway": validate_milkyway}


def extract_stars(path, work_dir):
    """Return the path of stars.8.json. A .tgz is extracted into work_dir (only that 1 file)."""
    if not path.lower().endswith((".tgz", ".tar.gz")):
        return path
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir, "stars.8.json")
    with tarfile.open(path, "r:gz") as t:
        f = t.extractfile(D3_MEMBER)
        if f is None:
            raise UraniaError(f"{path} has no {D3_MEMBER}")
        with open(out, "wb") as o:
            o.write(f.read())
    return out


def autodetect(xplane_root):
    """Return {key: (path or None, note)} for the files that Urania takes from the X-Plane folder."""
    xsa = xplane.find_original_xsa(xplane_root)
    dat = xplane.find_original_dat(xplane_root)
    return {"xsa": (xsa.path, xsa.source or xsa.note), "dat": (dat.path, dat.source or dat.note)}
