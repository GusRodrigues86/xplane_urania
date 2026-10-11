"""
pipeline.py - The full Urania build: check the inputs -> star data -> shader -> zip -> self-check.

The GUI and the CLI both call run_build(). Progress goes to log(text) and step(n, total, title).
"""
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field

from urania import inputs, xplane
from urania.engine import bundle, night_sky, shaders, spirv
from urania.errors import UraniaError

STEPS = ("Check the input files", "Build the star data", "Build the shader", "Make the zip file", "Check the zip file")
DEFAULT_ZIP_NAME = "Urania_XP12.zip"


def _quiet(*_args):
    pass


@dataclass
class BuildRequest:
    stars: str
    milkyway: str
    out_zip: str
    xplane_root: str = None      # if given: version check, and the originals come from here
    xsa: str = None              # original astronomical.xsa (default: found in xplane_root)
    dat: str = None              # original earth_astro.dat (default: found in xplane_root)
    overrides: dict = field(default_factory=dict)   # shader settings {name: value}
    airglow: bool = False        # use earth_astro_airglow.dat (faint glow over the full sky)
    allow_any_version: bool = False
    tools_dir: str = None
    keep_work: bool = False      # keep the work folder (for debugging)


@dataclass
class BuildResult:
    zip_path: str
    zip_sha256: str
    report_path: str
    gains: dict
    warnings: list


def resolve_inputs(req):
    """Fill xsa and dat from the X-Plane folder if needed. Return a list of warnings."""
    warnings = []
    if req.xplane_root:
        check = inputs.validate_xplane(req.xplane_root)
        if not check.ok:
            if req.allow_any_version and xplane.is_xplane_root(req.xplane_root):
                warnings.append(check.message)
            else:
                raise UraniaError(check.message)
        if check.warning:
            warnings.append(check.warning)
        found = inputs.autodetect(req.xplane_root)
        if not req.xsa:
            req.xsa = found["xsa"][0]
            if not req.xsa:
                raise UraniaError(found["xsa"][1])
        if not req.dat:
            req.dat = found["dat"][0]
            if not req.dat:
                raise UraniaError(found["dat"][1])
    if not req.xsa or not req.dat:
        raise UraniaError("Give the X-Plane folder, or the original astronomical.xsa and earth_astro.dat.")
    for key, path in (("xsa", req.xsa), ("dat", req.dat), ("stars", req.stars), ("milkyway", req.milkyway)):
        spec = inputs.SPEC_BY_KEY[key]
        if not path:
            raise UraniaError(f"{spec.title} is missing. {spec.where}")
        check = spec.validate(path)
        if not check.ok:
            raise UraniaError(f"{spec.title} ({path}): {check.message}")
    return warnings


def self_check(zip_path, settings):
    """Open the zip like the user will, and check the shader and the star file in it."""
    tmp = tempfile.mkdtemp(prefix="urania_check_")
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise UraniaError(f"The zip file is damaged ({bad}).")
            z.extract(bundle.PATH_XSA, tmp)
            z.extract(bundle.PATH_DAT, tmp)
        gains = spirv.read_gains(os.path.join(tmp, bundle.PATH_XSA))
        for name, value in gains.items():
            want = settings[name].value
            if abs(value - want) > 1e-6 * max(1.0, abs(want)):
                raise UraniaError(f"Self-check: {name} is {value} in the zip, expected {want}.")
        check = night_sky.verify(os.path.join(tmp, bundle.PATH_DAT))
        if check.errors or not check.haze:
            raise UraniaError("Self-check: the star file in the zip is not correct.")
        return gains
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_build(req, log=_quiet, step=_quiet):
    """Run the full build. Return a BuildResult. Raise UraniaError with a message for the user."""
    total = len(STEPS)
    step(1, total, STEPS[0])
    settings = shaders.resolve_settings(req.overrides)
    warnings = resolve_inputs(req)
    for w in warnings:
        log(f"NOTE: {w}")
    log(f"Original shader:     {req.xsa}")
    log(f"Original star file:  {req.dat}")

    out_zip = os.path.abspath(req.out_zip)
    work = tempfile.mkdtemp(prefix="urania_build_")
    try:
        stars = inputs.extract_stars(req.stars, os.path.join(work, "catalog"))

        step(2, total, STEPS[1])
        dat = night_sky.build_dat(req.dat, stars, req.milkyway, os.path.join(work, "dat"), log=log)
        dat_file = dat.outputs[night_sky.DAT_AIRGLOW if req.airglow else night_sky.DAT_PLAIN]

        step(3, total, STEPS[2])
        xsa = shaders.build_xsa(req.xsa, os.path.join(work, "xsa"), settings, req.tools_dir, log=log)

        step(4, total, STEPS[3])
        result = bundle.make_bundle(xsa.xsa, dat_file, req.xsa, req.dat, settings, out_zip)
        log(f"Zip file: {out_zip}")

        step(5, total, STEPS[4])
        gains = self_check(out_zip, settings)
        log("Self-check OK: the plugin can read the shader gains; the star file decodes without errors.")

        report = os.path.splitext(out_zip)[0] + "_build_report.txt"
        with open(report, "w", encoding="utf-8", newline="\n") as f:
            for path in (dat.report, xsa.report):
                with open(path, encoding="utf-8") as r:
                    f.write(r.read() + "\n")
            f.write(f"Zip  {result.sha256}  {os.path.basename(out_zip)}\n")
        return BuildResult(out_zip, result.sha256, report, gains, warnings)
    finally:
        if req.keep_work:
            log(f"Work folder kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
