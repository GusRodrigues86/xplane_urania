"""Tests with the real input files (pytest -m real). Only on a machine that has them in inputs/.

The star data must stay byte-identical to the reference build (fixtures/reference_generation_report.txt).
Since 2026-10-13 the reference has no galaxy core blobs (night-sky-generator v1 had 6 more rows).
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
    assert r.rows == {"earth_astro.dat": 58287, "earth_astro_airglow.dat": 64887}


REFERENCE_XSA = os.path.join(os.path.dirname(__file__), "fixtures", "reference_build_report.txt")
# Urania build (default settings, 2026-10-13: stars keep the total light of their magnitude) with the tools
# of scripts/build_tools.py (vulkan-sdk-1.4.363.0) on inputs/astronomical_original.xsa. Stage 1 also
# depends on the spirv-cross version (it keeps the decompiled stock sky lookup), so the full-file hash
# is checked only with the pinned tools.
PINNED_TOOLS_TAG = "vulkan-sdk-1.4.363.0"
REFERENCE_XSA_WITH_PINNED_TOOLS = "93e4b78f9160d2f488a2bdad586a0e43ff149973a269a1ab6d74453ee84e55d5"


def reference_stage_hashes():
    text = open(REFERENCE_XSA, encoding="utf-8").read()
    return {int(n): sha for n, sha in re.findall(r"^Stage (\d): ([0-9a-f]{64})$", text, flags=re.M)}


@pytest.mark.tools
def test_xsa_from_real_stock(tmp_path, real_inputs, vulkan_tools):
    import hashlib
    import zipfile
    r = shaders.build_xsa(real_inputs["xsa"], str(tmp_path))
    assert spirv.is_patched(r.xsa) and spirv.has_moon(r.xsa)
    assert r.gains["STAR_GAIN"] == pytest.approx(1.0)
    ref = reference_stage_hashes()
    with zipfile.ZipFile(r.xsa) as z:
        got = {i: hashlib.sha256(z.read(f"astronomical_{i}.spv")).hexdigest() for i in ref}
    for i in (0, 2, 6, 7, 8):                     # same as the reference, with any recent glslang
        assert got[i] == ref[i], f"stage {i}"
    from urania import tools
    if PINNED_TOOLS_TAG in tools.tool_version(vulkan_tools["spirv-cross"], "spirv-cross"):
        assert night_sky.sha256(r.xsa) == REFERENCE_XSA_WITH_PINNED_TOOLS
