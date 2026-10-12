"""The moon sky mod (astronomical stages 0, 1, 2): moonlit sky glow and moon phase.

History and calibration: docs/MOONLIGHT.md. The port must give the same shader as
night-sky-generator v1 (checked against the real file in tests/test_real.py).
"""
import math
import re
import zipfile

import pytest

from urania.engine import shaders, spirv
from urania.errors import UraniaError

from conftest import MOON_FRAGMENT


def test_moon_settings_defaults_are_sky25():
    s = shaders.DEFAULT_SETTINGS
    assert s["MOON"].value == 1.0 and s["MOON_SKY"].value == 0.25 and s["MOON_LS"].value == 1.0
    assert all(s[k].stage == "m" for k in s if k.startswith("MOON"))


def test_moon_settings_not_in_star_blocks():
    assert "MOON" not in shaders.settings_block("v") and "MOON" not in shaders.settings_block("f")
    assert shaders.settings_block("m") == "// --- Settings (written by Urania) ---"


def test_moon_settings_block_values():
    text = shaders.moon_settings_block()
    values = dict(re.findall(r"const float (\w+) = ([^;]+);", text))
    assert float(values["MOON_SIN_R"]) == pytest.approx(math.sin(math.radians(0.26)))
    # MOON_ENV = (7850 x MOON_LIGHT) / (3850 x MOON_SKY) = 8.155... (the "sky25" light-pass gain)
    assert float(values["MOON_ENV"]) == pytest.approx(7850 / (3850 * 0.25))
    # glow gain: 6e-5 x 3850/785 x 0.25 at the reference point
    assert float(values["MOON_GLOW_K"]) * shaders.moon_ks_ref() == pytest.approx(6e-5 * 3850 / 785 * 0.25)
    rgb = [float(x) for x in re.search(r"MOON_RGB_N = vec3\(([^)]*)\)", text).group(1).split(",")]
    assert 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] == pytest.approx(1.0)


def test_moon_sky_must_be_positive():
    with pytest.raises(UraniaError, match="MOON_SKY"):
        shaders.moon_settings_block(shaders.resolve_settings({"MOON_SKY": 0}))


def test_moon_airmass():
    assert shaders.moon_airmass(90) == pytest.approx(1.0)
    assert shaders.moon_airmass(10) > shaders.moon_airmass(45) > 1.0


def test_assemble_moon_fragment_keeps_sky_lookup():
    decompiled = MOON_FRAGMENT.replace("vec3 view", "vec3 _42").replace("* view", "* _42")
    text = shaders.assemble_moon_fragment(decompiled)
    assert "vec3 _42 = dir;" in text                     # the stock view vector becomes the pixel direction
    assert "vec4 stock_sky = sky;" in text
    assert "#define MASTRO astro" in text and "#define MDOME dome" in text
    assert "// @STOCK_SKY@" not in text and "// @SETTINGS@" not in text


def test_assemble_moon_fragment_without_lookup():
    with pytest.raises(UraniaError, match="sky lookup"):
        shaders.assemble_moon_fragment(MOON_FRAGMENT.replace("v_ratio *", "v_texcoord0 *"))


def test_open_stock_rejects_moon_patched(tmp_path):
    p = tmp_path / "m.xsa"
    with zipfile.ZipFile(p, "w") as z:
        for i in range(9):
            z.writestr(f"astronomical_{i}.spv", b"pcg_hash" if i == 1 else b"stock")
    with pytest.raises(UraniaError, match="already patched"):
        shaders.open_stock(str(p))
    assert spirv.is_patched(str(p)) and spirv.has_moon(str(p))


@pytest.mark.tools
def test_build_with_moon(tmp_path, fake_xsa):
    r = shaders.build_xsa(fake_xsa, str(tmp_path / "out"))
    assert spirv.has_moon(r.xsa)
    with zipfile.ZipFile(r.xsa) as z, zipfile.ZipFile(fake_xsa) as zin:
        for i in (0, 1, 2):
            assert z.read(f"astronomical_{i}.spv") != zin.read(f"astronomical_{i}.spv")


@pytest.mark.tools
def test_build_without_moon_keeps_stock_moon(tmp_path, fake_xsa):
    r = shaders.build_xsa(fake_xsa, str(tmp_path / "out"), shaders.resolve_settings({"MOON": 0}))
    assert not spirv.has_moon(r.xsa)
    with zipfile.ZipFile(r.xsa) as z, zipfile.ZipFile(fake_xsa) as zin:
        for i in (0, 1, 2):
            assert z.read(f"astronomical_{i}.spv") == zin.read(f"astronomical_{i}.spv")
