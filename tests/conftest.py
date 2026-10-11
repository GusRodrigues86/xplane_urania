"""Shared test fixtures. None of them contain X-Plane (Laminar) code or data.

fake_dat      a small star file in the X-Plane earth_astro.dat format (invented stars)
fake_catalog  a small d3-celestial style catalog that matches some of the invented stars
fake_exr      a small 2:1 EXR map
fake_xsa      a 9-stage astronomical.xsa built from stand-in shaders with the same interface
              names as X-Plane (needs the Vulkan tools; the tests that use it skip without them)
"""
import json
import os
import subprocess
import zipfile

import numpy as np
import pytest

from urania import tools
from urania.errors import ToolMissing

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# Invented stars: RA (h), Dec (deg), magnitude, name. Sorted by magnitude like the X-Plane file.
STARS = [
    (6.7708, -16.752, -1.46, "Alpha"),
    (14.2800, 19.053, -0.05, "Beta"),
    (18.6298, 38.808, 0.03, "Gamma"),
    (5.2623, -8.175, 0.13, "Delta"),
    (10.1395, 11.967, 1.35, "Epsilon"),
    (3.4054, 49.861, 1.79, ""),
    (21.7200, -24.987, 6.50, "Zeta"),
]


def write_dat(path, stars=STARS):
    lines = ["I", "", "740 Version - invented test data", ""]
    # 2 decimals like the X-Plane file; 4 decimals for a row that carries a Urania code.
    for ra, dec, mag, name in stars:
        m = f"{mag:5.2f}" if round(mag, 2) == mag else f"{mag:.4f}"
        lines.append(f"{ra:7.4f} {dec:8.3f} {m} {name}".rstrip())
    lines += ["", "99"]
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return str(path)


@pytest.fixture
def fake_dat(tmp_path):
    return write_dat(tmp_path / "earth_astro.dat")


@pytest.fixture
def fake_catalog(tmp_path):
    # Catalog positions are J2000; the X-Plane rows are J2025. Precession over 25 years moves stars
    # by up to ~0.35 deg, more than the 0.15 deg match radius. So put the catalog stars at the
    # J2000 positions that precess onto the X-Plane rows (inverse precession, T = -0.25).
    from urania.engine.night_sky import precess
    feats = []
    for (ra, dec, mag, name), bv in zip(STARS, [0.0, 1.23, 0.0, -0.03, -0.11, 0.48, None]):
        ra0, dec0 = precess(ra * 15, dec, T=-0.25)
        lon = ra0 if ra0 <= 180 else ra0 - 360
        props = {"mag": mag}
        if bv is not None:
            props["bv"] = str(bv)
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [lon, dec0]}})
    p = tmp_path / "stars.8.json"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    return str(p)


@pytest.fixture
def fake_exr(tmp_path):
    import OpenEXR
    h, w = 64, 128
    y = np.linspace(-1, 1, h)[:, None]
    band = 0.05 + 0.4 * np.exp(-(y / 0.15) ** 2) * np.ones((1, w))        # a bright band at the "equator"
    rgb = np.repeat(band[:, :, None], 3, axis=2).astype(np.float32)
    header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
    p = str(tmp_path / "map.exr")
    with OpenEXR.File(header, {"RGB": rgb}) as f:
        f.write(p)
    return p


# --- Stand-in X-Plane shaders ---------------------------------------------------------

STOCK_VERTEX = """#version 460
#extension GL_ARB_shader_viewport_layer_array : require
layout(set = 0, binding = 0, std140) uniform u_transform_block_fat {
    mat4 mvp_matrix[2];
    mat4 projection_matrix[2];
    vec3 u_mv_offset;
    int u_viewport_count;
    int u_layer_count;
    int u_layer_offset;
    int u_transform_count;
} xform;
layout(set = 0, binding = 1, std140) uniform u_astronomical_data { vec4 u_light_emissive_pad; float u_light_emissive; } astro;
layout(set = 0, binding = 2, std140) uniform u_environment_data { vec4 u_exposure_scale; } env;
layout(set = 1, binding = 0) uniform sampler2D u_tex_skydome;
layout(location = 0) in vec4 a_vertex;
layout(location = 0) out float v_L;
layout(location = 6) flat out int v_eye;
void main()
{
    int inst = gl_InstanceIndex;
    gl_ViewportIndex = inst % xform.u_viewport_count;
    gl_Layer = (inst % xform.u_layer_count) + xform.u_layer_offset;
    int view = inst % xform.u_transform_count;
    gl_Position = xform.mvp_matrix[view] * vec4(a_vertex.xyz - xform.u_mv_offset, 1.0)
                + xform.projection_matrix[view][0];
    v_L = astro.u_light_emissive * env.u_exposure_scale.y * texture(u_tex_skydome, vec2(0.5)).w * a_vertex.w;
    v_eye = view;
    gl_PointSize = 2.0;
}
"""

STOCK_FRAGMENT = """#version 460
layout(location = 0) in float v_L;
layout(location = 6) flat in int v_eye;
layout(location = 0) out vec4 data_out0;
void main() { data_out0 = vec4(v_L, v_L, v_L, float(v_eye)); }
"""

OTHER_VERTEX = """#version 460
layout(location = 0) in vec4 a_vertex;
void main() {{ gl_Position = a_vertex * {k}.0; }}
"""


def tools_or_skip():
    try:
        return {n: tools.find_tool(n) for n in tools.TOOL_NAMES}
    except ToolMissing as e:
        pytest.skip(f"Vulkan tools not available: {e}")


def compile_glsl(glslang, text, stage, workdir, name):
    src = os.path.join(workdir, f"{name}.{stage}")
    out = os.path.join(workdir, f"{name}.spv")
    with open(src, "w", newline="\n") as f:
        f.write(text)
    subprocess.run([glslang, "-V", "--target-env", "vulkan1.3", "-S", stage, src, "-o", out],
                   check=True, capture_output=True)
    with open(out, "rb") as f:
        return f.read()


def build_fake_xsa(path, workdir, glslang):
    """Write a 9-stage xsa like X-Plane's: deflated entries, 1980 dates."""
    os.makedirs(workdir, exist_ok=True)
    stages = {}
    for i in range(9):
        if i in (6, 8):
            stages[i] = compile_glsl(glslang, STOCK_VERTEX, "vert", workdir, f"s{i}")
        elif i == 7:
            stages[i] = compile_glsl(glslang, STOCK_FRAGMENT, "frag", workdir, f"s{i}")
        else:
            stages[i] = compile_glsl(glslang, OTHER_VERTEX.format(k=i + 1), "vert", workdir, f"s{i}")
    with zipfile.ZipFile(path, "w") as z:
        for i in range(9):
            info = zipfile.ZipInfo(f"astronomical_{i}.spv", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, stages[i])
    return str(path)


@pytest.fixture(scope="session")
def vulkan_tools():
    return tools_or_skip()


@pytest.fixture
def fake_xsa(tmp_path, vulkan_tools):
    return build_fake_xsa(tmp_path / "astronomical.xsa", str(tmp_path / "stock_src"),
                          vulkan_tools["glslangValidator"])


# --- Real input files (pytest -m real) -------------------------------------------------

def real_inputs_dir():
    return os.environ.get("URANIA_INPUTS") or os.path.join(os.path.dirname(__file__), "..", "inputs")


@pytest.fixture(scope="session")
def real_inputs():
    d = real_inputs_dir()
    files = {"astro": "earth_astro_original.dat", "stars": "stars.8.json",
             "milkyway": "milkyway_2020_4k.exr", "xsa": "astronomical_original.xsa"}
    found = {k: os.path.join(d, v) for k, v in files.items()}
    missing = [v for k, v in files.items() if not os.path.isfile(found[k])]
    if missing:
        pytest.skip(f"real input files missing in {d}: {missing}")
    return found
