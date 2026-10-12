"""Tests with the real input files (pytest -m real). Only on a machine that has them in inputs/.

The star data must stay byte-identical to the reference build of night-sky-generator v1.
"""
import os
import re

import pytest

from urania.engine import night_sky, shaders, spirv

pytestmark = pytest.mark.real

REFERENCE = os.path.join(os.path.dirname(__file__), "fixtures", "reference_generation_report.txt")


def reference_hashes():
    text = open(REFERENCE, encoding="utf-8").read()
    return dict((name, sha) for sha, name in re.findall(r"^\s+([0-9a-f]{64})\s+(\S+\.dat)\s", text, flags=re.M))


def test_reference_report_parsed():
    assert set(reference_hashes()) == {"earth_astro.dat", "earth_astro_airglow.dat"}


def test_dat_byte_identical_to_reference(tmp_path, real_inputs):
    r = night_sky.build_dat(real_inputs["astro"], real_inputs["stars"], real_inputs["milkyway"], str(tmp_path))
    for name, sha in reference_hashes().items():
        assert night_sky.sha256(r.outputs[name]) == sha, name
    assert r.rows == {"earth_astro.dat": 58293, "earth_astro_airglow.dat": 64893}


REFERENCE_XSA = os.path.join(os.path.dirname(__file__), "fixtures", "reference_build_report.txt")
# night-sky-generator v1 (make_shaders.py) run with the tools of scripts/build_tools.py
# (vulkan-sdk-1.4.363.0) on the stock X-Plane 12.4.4 astronomical.xsa (246e6ab9...). Stage 1 also
# depends on the spirv-cross version (it keeps the decompiled stock sky lookup), so the full-file hash
# is checked only with the pinned tools.
PINNED_TOOLS_TAG = "vulkan-sdk-1.4.363.0"
V1_XSA_WITH_PINNED_TOOLS = "41c3baba8b1b398879d9eb471786e45cf68a568bf25097448b4973199b135da0"


def reference_stage_hashes():
    text = open(REFERENCE_XSA, encoding="utf-8").read()
    return {int(n): sha for n, sha in re.findall(r"^Stage (\d): ([0-9a-f]{64})$", text, flags=re.M)}


@pytest.mark.tools
def test_xsa_from_real_stock(tmp_path, real_inputs, vulkan_tools):
    import hashlib
    import zipfile
    r = shaders.build_xsa(real_inputs["xsa"], str(tmp_path))
    assert spirv.is_patched(r.xsa) and spirv.has_moon(r.xsa)
    assert r.gains["STAR_GAIN"] == pytest.approx(0.35)
    ref = reference_stage_hashes()
    with zipfile.ZipFile(r.xsa) as z:
        got = {i: hashlib.sha256(z.read(f"astronomical_{i}.spv")).hexdigest() for i in ref}
    for i in (0, 2, 6, 7, 8):                     # same as the v1 release, with any recent glslang
        assert got[i] == ref[i], f"stage {i}"
    from urania import tools
    if PINNED_TOOLS_TAG in tools.tool_version(vulkan_tools["spirv-cross"], "spirv-cross"):
        assert night_sky.sha256(r.xsa) == V1_XSA_WITH_PINNED_TOOLS
