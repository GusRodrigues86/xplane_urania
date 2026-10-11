import os
import zipfile

import pytest

from urania.engine import shaders, spirv
from urania.errors import UraniaError

DECOMPILED = """#version 460
#extension GL_ARB_shader_viewport_layer_array : require

layout(set = 0, binding = 0, std140) uniform u_transform_block_fat
{
    mat4 mvp_matrix[2];
} _21;

layout(set = 0, binding = 1, std140) uniform u_astronomical_data
{
    float u_light_emissive;
} _33;

layout(set = 0, binding = 2, std140) uniform u_environment_data
{
    vec4 u_exposure_scale;
} _40;

layout(location = 0) in vec4 a_vertex;
layout(location = 0) out float v_L;
out gl_PerVertex
{
    vec4 gl_Position;
};

void main()
{
    gl_Position = vec4(0.0);
}
"""


def test_settings_block_spec_constants():
    text = shaders.settings_block("v")
    assert "layout(constant_id = 200) const float STAR_GAIN = 0.35;" in text
    assert "layout(constant_id = 201) const float MW_GAIN = 3.0;" in text
    assert "layout(constant_id = 202) const float NEBULA_GAIN = 40.0;" in text
    assert "layout(constant_id = 203) const float GALAXY_GAIN = 40.0;" in text
    assert "layout(constant_id = 204) const float HAZE_EMISSIVE = 0.0;" in text
    assert "const float SAT = 1.3;" in text
    assert "#define HAZE_RGB_1 vec3(2.3758, 0.5940, 0.9719)" in text
    assert "DITHER" not in text
    assert "DSO_GAIN" not in text


def test_settings_block_fragment():
    text = shaders.settings_block("f")
    assert "const float DITHER = 0.14;" in text
    assert "STAR_GAIN" not in text


def test_spec_ids_agree_with_plugin_header():
    header = os.path.join(os.path.dirname(__file__), "..", "plugin", "src", "xsa_gains.h")
    text = open(header, encoding="utf-8").read()
    assert "kGainSpecId[kGainCount] = {200, 201, 202, 203}" in text
    assert "kHazeEmissiveSpecId = 204" in text
    defaults = [shaders.DEFAULT_SETTINGS[n].value for n in ("STAR_GAIN", "MW_GAIN", "NEBULA_GAIN", "GALAXY_GAIN")]
    assert "kGainDefault[kGainCount] = {0.35f, 3.0f, 40.0f, 40.0f}" in text
    assert defaults == [0.35, 3.0, 40.0, 40.0]


def test_resolve_settings_overrides():
    s = shaders.resolve_settings({"STAR_GAIN": "0.5", "HAZE_RGB_1": "2.0,0.6,1.0", "VIEWPORT_H": 1440})
    assert s["STAR_GAIN"].value == 0.5
    assert s["STAR_GAIN"].spec_id == 200
    assert s["HAZE_RGB_1"].value == (2.0, 0.6, 1.0)
    assert s["VIEWPORT_H"].value == 1440.0
    assert shaders.DEFAULT_SETTINGS["STAR_GAIN"].value == 0.35       # defaults unchanged


def test_resolve_settings_legacy_dso_gain():
    s = shaders.resolve_settings({"DSO_GAIN": "15"})
    assert s["NEBULA_GAIN"].value == 15.0 and s["GALAXY_GAIN"].value == 15.0


@pytest.mark.parametrize("over,msg", [
    ({"NOPE": "1"}, "unknown setting"),
    ({"STAR_GAIN": "abc"}, "needs a number"),
    ({"HAZE_RGB_0": "1,2"}, "3 numbers"),
    ({"STAR_GAIN": "nan"}, "finite"),
])
def test_resolve_settings_errors(over, msg):
    with pytest.raises(UraniaError, match=msg):
        shaders.resolve_settings(over)


def test_parse_set_pairs():
    assert shaders.parse_set_pairs(["A=1", " B = 2,3,4 "]) == {"A": "1", "B": "2,3,4"}
    with pytest.raises(UraniaError):
        shaders.parse_set_pairs(["A"])


def test_stock_declarations():
    decl, defines = shaders.stock_declarations(DECOMPILED)
    assert "uniform u_transform_block_fat" in decl
    assert "a_vertex" in decl
    assert "out float v_L" not in decl and "gl_PerVertex" not in decl and "#version" not in decl
    assert defines.splitlines() == ["#define XFORM _21", "#define ASTRO _33", "#define ENV _40"]


def test_stock_declarations_missing_block():
    with pytest.raises(UraniaError, match="uniform blocks"):
        shaders.stock_declarations(DECOMPILED.replace("u_environment_data", "u_other"))


def test_star_rgb_table():
    rows = shaders.star_rgb_values()
    assert len(rows) == 90
    for r, g, b in rows[1:]:
        assert 0.2126 * r + 0.7152 * g + 0.0722 * b == pytest.approx(1.0, abs=1e-9)
    assert rows[1][2] > rows[1][0]          # k = 1 (B-V -0.4) is blue
    assert rows[89][0] > rows[89][2]        # k = 89 (B-V 2.0) is red
    assert shaders.star_rgb_table().count("vec3(") == 90


def test_assemble_vertex_has_mod_code():
    text = shaders.assemble_vertex(DECOMPILED)
    assert text.startswith("#version 460\n")
    assert "// @SETTINGS@" not in text and "// @STAR_RGB@" not in text      # the markers are replaced
    assert "GALAXY_GAIN" in text and "NEBULA_GAIN" in text and "DSO_GAIN" not in text


def test_open_stock_rejects_bad_files(tmp_path):
    p = tmp_path / "a.xsa"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("astronomical_0.spv", b"x")
    with pytest.raises(UraniaError, match="expected astronomical_0.spv"):
        shaders.open_stock(str(p))
    p2 = tmp_path / "b.xsa"
    p2.write_bytes(b"not a zip")
    with pytest.raises(UraniaError, match="not an astronomical.xsa"):
        shaders.open_stock(str(p2))


# --- Integration: real compile with the Vulkan tools (skipped without them) ---------------

@pytest.mark.tools
def test_build_xsa(tmp_path, fake_xsa):
    r = shaders.build_xsa(fake_xsa, str(tmp_path / "out"),
                          shaders.resolve_settings({"GALAXY_GAIN": 25, "VIEWPORT_H": 1440}))
    assert r.gains == pytest.approx({"STAR_GAIN": 0.35, "MW_GAIN": 3.0, "NEBULA_GAIN": 40.0,
                                     "GALAXY_GAIN": 25.0, "HAZE_EMISSIVE": 0.0})
    with zipfile.ZipFile(fake_xsa) as zin, zipfile.ZipFile(r.xsa) as zout:
        assert zout.namelist() == zin.namelist()
        for i in range(9):
            a, b = zin.getinfo(f"astronomical_{i}.spv"), zout.getinfo(f"astronomical_{i}.spv")
            assert b.date_time == a.date_time
            if i in (6, 8):
                assert b.compress_type == zipfile.ZIP_STORED
            else:
                assert b.compress_type == a.compress_type
            if i < 6:
                assert zout.read(b) == zin.read(a)            # stages 0..5 unchanged
    assert spirv.is_patched(r.xsa)
    assert "VIEWPORT_H = 1440.0" in open(r.report, encoding="utf-8").read()


@pytest.mark.tools
def test_build_xsa_refuses_patched_input(tmp_path, fake_xsa):
    r = shaders.build_xsa(fake_xsa, str(tmp_path / "out"))
    with pytest.raises(UraniaError, match="already patched"):
        shaders.build_xsa(r.xsa, str(tmp_path / "out2"))


@pytest.mark.tools
def test_build_xsa_is_reproducible(tmp_path, fake_xsa):
    a = shaders.build_xsa(fake_xsa, str(tmp_path / "a"))
    b = shaders.build_xsa(fake_xsa, str(tmp_path / "b"))
    assert open(a.xsa, "rb").read() == open(b.xsa, "rb").read()
