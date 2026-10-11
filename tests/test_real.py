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


@pytest.mark.tools
def test_xsa_from_real_stock(tmp_path, real_inputs, vulkan_tools):
    r = shaders.build_xsa(real_inputs["xsa"], str(tmp_path))
    assert spirv.is_patched(r.xsa)
    assert r.gains["STAR_GAIN"] == pytest.approx(0.35)
