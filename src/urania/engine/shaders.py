"""
shaders.py - Build the night-sky shader file for X-Plane 12 (astronomical.xsa).

Library version of make_shaders.py (night-sky-generator v1), with these changes for the Urania
plugin (plugin/src/xsa_gains.h):
  - The gains are SPIR-V specialization constants: STAR_GAIN 200, MW_GAIN 201, NEBULA_GAIN 202,
    GALAXY_GAIN 203, HAZE_EMISSIVE 204. X-Plane does not set constants with these IDs, so the GPU
    uses the value in the file. The plugin can change the values in place.
  - DSO_GAIN is now 2 gains: NEBULA_GAIN (color classes 1 and 2) and GALAXY_GAIN (class 3).
  - HAZE_EMISSIVE > 0: the haze uses this fixed star light, not u_light_emissive (0 = old behavior).
  - Stages 6 and 8 are stored without compression (the plugin changes the values in place).

HOW THE BUILD WORKS
    1. Open the original astronomical.xsa (a ZIP file with 9 SPIR-V programs).
    2. Decompile stages 6 and 8 with spirv-cross. Keep only the stock declarations
       (uniform blocks, texture, a_vertex). Urania does not contain X-Plane code.
    3. Add the settings block and the star color table (computed here).
    4. Add the mod code from shader_src/sky_vertex.glsl and shader_src/sky_fragment.glsl.
    5. Compile each stage with glslangValidator. Check each result with spirv-val.
    6. Write a new ZIP: stages 0..5 unchanged, stages 6, 7 and 8 new.
    7. Write build_report.txt with the settings, the tool versions and the SHA-256 values.

GLOSSARY
    stage     One GPU program in the .xsa file (astronomical_0.spv ... astronomical_8.spv).
    SPIR-V    The binary GPU program format that Vulkan uses (.spv).
    GLSL      The text language that we write. glslangValidator compiles GLSL to SPIR-V.
    setting   A constant at the top of the shader (for example STAR_GAIN). See SETTINGS below.
"""
import copy
import dataclasses
import hashlib
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from importlib import resources

from urania import tools
from urania.engine import spirv
from urania.errors import UraniaError

# =====================================================================================
# 1. SETTINGS
#    name: Setting(value, stage, comment, spec_id). stage "v" = vertex stages 6 and 8,
#    "f" = fragment stage 7. spec_id = SPIR-V specialization constant ID (None = plain constant).
#    The 4 gains are multipliers over the physical brightness: with gain 1, the pixels of a star or a haze
#    blob add up to the light of its magnitude. MW_GAIN, NEBULA_GAIN and GALAXY_GAIN are the tested version
#    "stars35" (2026-10-10). STAR_GAIN 1.0 is physical and not tested yet (the stars keep their total light
#    since 2026-10-13; the old 0.35 is no longer comparable).
# =====================================================================================

@dataclass(frozen=True)
class Setting:
    value: object           # float, or a tuple of 3 floats (vec3)
    stage: str
    comment: str
    spec_id: int = None


DEFAULT_SETTINGS = {
    # --- Stars ---
    "STAR_GAIN":    Setting(1.0,    "v", "star brightness (1.0 = physical)", spirv.GAIN_SPEC_IDS["STAR_GAIN"]),
    "SAT":          Setting(1.3,    "v", "star color strength (1.0 = physical, 0 = grey)"),
    "SIZE_BASE":    Setting(7.0,    "v", "star sprite size in px at magnitude 0"),
    "SIZE_PER_MAG": Setting(1.2,    "v", "px less for each magnitude"),
    "SIZE_MIN":     Setting(1.5,    "v", "smallest star sprite in px"),
    "SIZE_MAX":     Setting(12.0,   "v", "largest star sprite in px"),
    # --- Haze (Milky Way, airglow, deep-sky objects) ---
    "MW_GAIN":      Setting(3.0,    "v", "Milky Way and airglow brightness, color class 0 (1.0 = physical)",
                            spirv.GAIN_SPEC_IDS["MW_GAIN"]),
    "NEBULA_GAIN":  Setting(40.0,   "v", "nebula brightness, color classes 1 and 2 (1.0 = physical)",
                            spirv.GAIN_SPEC_IDS["NEBULA_GAIN"]),
    "GALAXY_GAIN":  Setting(40.0,   "v", "galaxy and cluster brightness, color class 3 (1.0 = physical)",
                            spirv.GAIN_SPEC_IDS["GALAXY_GAIN"]),
    "HAZE_EMISSIVE": Setting(0.0,   "v", "fixed star light for the haze (0 = follow gain_photometric)",
                             spirv.HAZE_EMISSIVE_SPEC_ID),
    "HAZE_SAT":     Setting(1.2,    "v", "haze color strength (1.0 = table colors)"),
    "HAZE_RGB_0":   Setting((1.1039, 0.9856, 0.8378), "v", "class 0 color: Milky Way, warm white"),
    "HAZE_RGB_1":   Setting((2.3758, 0.5940, 0.9719), "v", "class 1 color: H-alpha emission, red-pink"),
    "HAZE_RGB_2":   Setting((0.6000, 1.1500, 1.3000), "v", "class 2 color: nebula core / reflection / planetary, teal"),
    "HAZE_RGB_3":   Setting((1.2003, 0.9917, 0.6560), "v", "class 3 color: galaxy / globular cluster, warm yellow"),
    # --- Screen and sprite geometry ---
    "VIEWPORT_H":   Setting(1080.0, "v", "screen height in px. Set this to your screen height."),
    "MAX_SPRITE":   Setting(1024.0, "v", "largest haze sprite in px"),
    "EDGE_STRETCH": Setting(1.0,    "v", "1 = grow haze sprites toward the screen edges (wide view), 0 = off"),
    "CLAMP_NDC":    Setting(0.98,   "v", "keep haze sprite centers inside the view (0..1 of the half view)"),
    # --- Fragment stage ---
    "DITHER":       Setting(0.14,   "f", "haze noise strength against banding (0 = off)"),
    # --- Moon sky (stages 0, 1, 2). Defaults: tested version "moon probe 2.4, sky25" (2026-10-10). ---
    "MOON":         Setting(1.0,    "m", "1 = moon sky mod, 0 = stock moon stages"),
    "MOON_SKY":     Setting(0.25,   "m", "moonlit sky glow (1.0 = probe 2.2 look at moon/nits 3850)"),
    "MOON_LIGHT":   Setting(1.0,    "m", "scene light from the moonlit sky (1.0 = probe 2.2 look at moon/nits 7850)"),
    "MOON_RGB":     Setting((0.85, 0.92, 1.0), "m", "moonlit sky color (scaled to luminance 1)"),
    "MOON_K_EXT":   Setting(0.2,    "m", "atmospheric extinction, magnitudes per airmass"),
    "MOON_DIAMETER": Setting(0.52,  "m", "moon diameter in degrees (sim/private/controls/moon/angular_diameter)"),
    "MOON_DITHER":  Setting(0.05,   "m", "glow noise strength against banding (0 = off)"),
    "MOON_LS":      Setting(1.0,    "m", "moon disk light law: 1 = Lommel-Seeliger (bright crescent), 0 = stock Lambert"),
}

# Moon glow calibration (probe 2.2, 2026-10-10; see docs/MOONLIGHT.md). Glow gain 6e-5 x luminance of
# u_light_diffuse at the reference point (45 deg from the moon, pixel and moon at 45 deg elevation,
# full moon) at moon/nits 785. The sky looked best at moon/nits 3850, the terrain light at 7850.
# The shader bakes these in, so moon/nits stays at the X-Plane default 785.
MOON_REF_GAIN = 6e-5
MOON_NITS_DEFAULT, MOON_NITS_SKY, MOON_NITS_LIGHT = 785.0, 3850.0, 7850.0
MOON_REF_DEG = 45.0

# Old setting name -> new names (night-sky-generator v1 had one DSO_GAIN).
LEGACY_ALIASES = {"DSO_GAIN": ("NEBULA_GAIN", "GALAXY_GAIN")}

# Star color table: B-V range of the color code k (must agree with night_sky.py).
STAR_K_MIN, STAR_K_MAX, BV_MIN, BV_MAX = 1, 89, -0.40, 2.00

# The stock uniform blocks that the mod code uses, and the short names that the mod code uses for them.
BLOCK_ALIASES = {"u_transform_block_fat": "XFORM", "u_astronomical_data": "ASTRO", "u_environment_data": "ENV"}

MOD_STAGES = {0: "vert", 1: "frag", 2: "vert", 6: "vert", 7: "frag", 8: "vert"}
MOON_STAGES = (0, 1, 2)
STAGE_COUNT = 9

XSA_NAME = "astronomical.xsa"
REPORT_NAME = "build_report.txt"


def _quiet(_text):
    pass


# =====================================================================================
# 2. STAR COLOR TABLE (black body -> linear sRGB)
# =====================================================================================

def _g(x, mu, s1, s2):
    s = s1 if x < mu else s2
    return math.exp(-0.5 * ((x - mu) / s) ** 2)


def cie_cmf(l):
    """CIE 1931 color matching functions x, y, z at wavelength l (nm). Multi-lobe fit (Wyman 2013)."""
    x = 1.056 * _g(l, 599.8, 37.9, 31.0) + 0.362 * _g(l, 442.0, 16.0, 26.7) - 0.065 * _g(l, 501.1, 20.4, 26.2)
    y = 0.821 * _g(l, 568.8, 46.9, 40.5) + 0.286 * _g(l, 530.9, 16.3, 31.1)
    z = 1.217 * _g(l, 437.0, 11.8, 36.0) + 0.681 * _g(l, 459.0, 26.0, 13.8)
    return x, y, z


def planck(l, T):
    """Black-body spectral radiance at wavelength l (nm), temperature T (K). Constant factors removed."""
    l *= 1e-9
    return 1 / (l ** 5 * (math.exp(1.4388e-2 / (l * T)) - 1))


def rgb_for_temperature(T):
    """Return the linear sRGB color of a black body at T (K), scaled to luminance 1."""
    X = Y = Z = 0
    for l in range(380, 781, 5):
        p = planck(l, T)
        x, y, z = cie_cmf(l)
        X += p * x; Y += p * y; Z += p * z
    X, Z = X / Y, Z / Y
    Y = 1
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z          # XYZ -> linear sRGB (D65)
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    r, g, b = (max(c, 0) for c in (r, g, b))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return r / lum, g / lum, b / lum


def bv_to_temperature(bv):
    """Convert B-V to black-body temperature (K). Ballesteros (2012)."""
    return 4600 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62))


def star_rgb_values():
    """Return the 90 star colors (k = 0 is white) as (r, g, b) tuples."""
    rows = [(1.0, 1.0, 1.0)]
    for k in range(STAR_K_MIN, STAR_K_MAX + 1):
        bv = BV_MIN + (k - STAR_K_MIN) * (BV_MAX - BV_MIN) / (STAR_K_MAX - STAR_K_MIN)
        rows.append(rgb_for_temperature(bv_to_temperature(bv)))
    return rows


def star_rgb_table():
    """Return the GLSL text of the STAR_RGB table (90 entries, k = 0 is white)."""
    rows = ["vec3(1.0, 1.0, 1.0)"] + [f"vec3({r:.4f}, {g:.4f}, {b:.4f})" for r, g, b in star_rgb_values()[1:]]
    return "const vec3 STAR_RGB[90] = vec3[90](\n    " + ",\n    ".join(rows) + ");"


# =====================================================================================
# 3. SETTINGS AND GLSL ASSEMBLY
# =====================================================================================

def glsl_value(v):
    if isinstance(v, tuple):
        return "vec3(" + ", ".join(f"{c:.4f}" for c in v) + ")"
    return repr(float(v))


def resolve_settings(overrides=None):
    """Return a settings dict: the defaults with the overrides {name: value or text}.

    A text value is parsed like the old --set option: '0.5', or '2.0,0.6,1.0' for a vec3.
    DSO_GAIN (old name) sets both NEBULA_GAIN and GALAXY_GAIN.
    """
    settings = dict(DEFAULT_SETTINGS)
    for name, raw in (overrides or {}).items():
        for target in LEGACY_ALIASES.get(name, (name,)):
            if target not in settings:
                raise UraniaError(f"unknown setting {name}. Settings: {', '.join(DEFAULT_SETTINGS)}")
            old = settings[target]
            settings[target] = dataclasses.replace(old, value=_parse_value(target, old.value, raw))
    return settings


def _parse_value(name, default, raw):
    try:
        if isinstance(default, tuple):
            new = tuple(float(x) for x in raw.split(",")) if isinstance(raw, str) else tuple(float(x) for x in raw)
            if len(new) != 3:
                raise ValueError
            return new
        value = float(raw)
    except (TypeError, ValueError):
        raise UraniaError(f"{name} needs {'3 numbers with commas' if isinstance(default, tuple) else 'a number'}, "
                          f"not {raw!r}") from None
    if not math.isfinite(value):
        raise UraniaError(f"{name} must be a finite number")
    return value


def parse_set_pairs(pairs):
    """Convert ['NAME=VALUE', ...] (CLI --set) to an overrides dict."""
    out = {}
    for pair in pairs or []:
        name, sep, text = pair.partition("=")
        if not sep:
            raise UraniaError(f"--set needs NAME=VALUE, not {pair!r}")
        out[name.strip()] = text.strip()
    return out


def settings_block(stage, settings=None):
    """Return the GLSL text of the settings for one stage type ("v" or "f")."""
    settings = settings or DEFAULT_SETTINGS
    lines = ["// --- Settings (written by Urania) ---"]
    for name, s in settings.items():
        if s.stage != stage or stage == "m":
            continue
        if isinstance(s.value, tuple):
            lines.append(f"#define {name} {glsl_value(s.value)}   // {s.comment}")
        elif s.spec_id is not None:
            lines.append(f"layout(constant_id = {s.spec_id}) const float {name} = {glsl_value(s.value)};"
                         f"   // {s.comment}")
        else:
            lines.append(f"const float {name} = {glsl_value(s.value)};   // {s.comment}")
    return "\n".join(lines)


def stock_declarations(stock_glsl):
    """Keep the stock declarations from a decompiled vertex stage. Return (text, #define lines).

    Keeps: uniform blocks, samplers and the a_vertex input.
    Removes: #version, #extension, all outputs, and the stock main function.
    """
    head = stock_glsl.split("void main()")[0]
    head = re.sub(r"^#(version|extension).*$", "", head, flags=re.M)
    head = re.sub(r"out\s+gl_PerVertex\s*\{.*?\}\s*;", "", head, flags=re.S)
    head = "\n".join(l for l in head.splitlines() if not re.search(r"\bout\b", l))
    defines = []
    for block, inst in re.findall(r"uniform\s+(\w+)\s*\{.*?\}\s*(\w+)\s*;", head, flags=re.S):
        if block in BLOCK_ALIASES:
            defines.append(f"#define {BLOCK_ALIASES[block]} {inst}")
    if len(defines) != len(BLOCK_ALIASES):
        raise UraniaError(f"The stock shader does not have all of these uniform blocks: {list(BLOCK_ALIASES)}. "
                          "An X-Plane update changed the stock shader; Urania needs an update.")
    if "a_vertex" not in head:
        raise UraniaError("The stock shader has no a_vertex input. This is not the expected X-Plane file.")
    return head.strip(), "\n".join(defines)


def moon_enabled(settings=None):
    return (settings or DEFAULT_SETTINGS)["MOON"].value >= 0.5


def moon_airmass(elev_deg):
    s = math.sin(math.radians(90.0 - elev_deg))
    return 1.0 / math.sqrt(1.0 - 0.96 * s * s)


def moon_ks_ref(settings=None):
    """Krisciunas & Schaefer (1991) moon glow, in shader units, at the reference point."""
    settings = settings or DEFAULT_SETTINGS
    r = math.radians(MOON_REF_DEG)
    k = settings["MOON_K_EXT"].value
    f = 10 ** 5.36 * (1.06 + math.cos(r) ** 2) + 10 ** (6.15 - MOON_REF_DEG / 40.0)
    x = moon_airmass(MOON_REF_DEG)
    return f * 10 ** (-0.4 * k * x) * (1.0 - 10 ** (-0.4 * k * x))


def moon_settings_block(settings=None):
    """Return the GLSL text of the moon constants (computed from the MOON_* settings)."""
    settings = settings or DEFAULT_SETTINGS
    sky, light = settings["MOON_SKY"].value, settings["MOON_LIGHT"].value
    if sky <= 0.0:
        raise UraniaError("MOON_SKY must be more than 0. Turn the moonlit sky off instead (MOON=0).")
    rgb = settings["MOON_RGB"].value
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    glow_k = MOON_REF_GAIN * MOON_NITS_SKY / MOON_NITS_DEFAULT * sky / moon_ks_ref(settings)
    env = (MOON_NITS_LIGHT * light) / (MOON_NITS_SKY * sky)
    sin_r = math.sin(math.radians(settings["MOON_DIAMETER"].value / 2.0))
    return "\n".join([
        "// --- Moon settings (written by Urania) ---",
        f"const float MOON_SIN_R = {sin_r!r};   // sin(moon radius)",
        f"const float MOON_GLOW_K = {glow_k!r};   // glow gain (MOON_SKY = {sky!r})",
        f"const float MOON_ENV = {env!r};   // extra glow in the scene light pass (MOON_LIGHT = {light!r})",
        f"const float MOON_K_EXT = {float(settings['MOON_K_EXT'].value)!r};   // extinction, mag per airmass",
        f"const float MOON_DITHER = {float(settings['MOON_DITHER'].value)!r};   // glow noise strength",
        f"const float MOON_LS = {float(settings['MOON_LS'].value)!r};   // 1 = Lommel-Seeliger disk light, 0 = stock Lambert",
        "const vec3 MOON_RGB_N = vec3(" + ", ".join(repr(c / lum) for c in rgb) + ");   // glow color, luminance 1",
    ])


def block_instance(text, block):
    m = re.search(r"uniform\s+" + block + r"\s*\{[^}]*\}\s*(\w+)\s*;", text)
    if not m:
        raise UraniaError(f"The stock moon stage has no uniform block {block}. This is not the expected X-Plane file.")
    return m.group(1)


def split_main(stock_glsl):
    """Split decompiled GLSL into (declarations, main function)."""
    i = stock_glsl.index("void main()")
    return stock_glsl[:i], stock_glsl[i:]


def assemble_moon_vertex(stock_glsl, point_size, settings=None):
    """Stage 0 or 2: keep the stock declarations (same interface as stage 1), new main function."""
    head, main = split_main(stock_glsl)
    if ("gl_PointSize" in main) != point_size:
        raise UraniaError("Unexpected stock moon vertex stage (gl_PointSize). This is not the expected X-Plane file.")
    for name in ("a_vertex", "a_normal", "a_texcoord0", "v_dir_wrl", "v_normal_eye", "v_position_eye", "v_ratio",
                 "v_eye"):
        if not re.search(r"\b" + name + r"\b", head):
            raise UraniaError(f"The stock moon vertex stage has no {name}. This is not the expected X-Plane file.")
    if "GL_ARB_shader_viewport_layer_array" not in head:
        head = head.replace("#version 460\n", "#version 460\n#extension GL_ARB_shader_viewport_layer_array : require\n", 1)
    defines = [f"#define MXFORM {block_instance(head, 'u_transform_block_fat')}"]
    ps = ""
    if point_size:
        defines.append(f"#define MIMM {block_instance(head, 'u_immediate_data')}")
        ps = "gl_PointSize = MIMM.u_imm_a_point_size.x;"
    body = _source("moon_vertex.glsl")
    body = body.replace("// @SETTINGS@", moon_settings_block(settings)).replace("// @POINT_SIZE@", ps)
    return (head.rstrip() + "\n\n// ---- End of the stock X-Plane declarations ----\n"
            + "\n".join(defines) + "\n\n" + body)


def assemble_moon_fragment(stock_glsl, settings=None):
    """Stage 1: keep the stock declarations and the stock sky texture lookup, new main function."""
    head, main = split_main(stock_glsl)
    for name in ("u_tex0", "u_tex0_nrm", "v_texcoord0", "v_dir_wrl", "v_ratio", "v_position_eye", "v_normal_eye"):
        if not re.search(r"\b" + name + r"\b", head):
            raise UraniaError(f"The stock moon fragment stage has no {name}. This is not the expected X-Plane file.")
    # The stock sky lookup starts with the view vector (from v_ratio) and ends with a do-while(false) block.
    # (spirv-cross writes "while(false)" for the stock code, "while (false)" for a literal loop.)
    m = re.search(r"(    vec3 (\w+) = normalize\(vec3\(\(v_ratio[^\n]*\n.*?\n    \} while ?\(false\);\n)", main, re.S)
    if not m:
        raise UraniaError("The stock sky lookup is not in stage 1. An X-Plane update changed the moon shader; "
                          "build without the moonlit sky (MOON=0), and report it.")
    view_var = m.group(2)
    sky_block = re.sub(r"    vec3 " + view_var + r" = normalize\(vec3\(\(v_ratio[^\n]*\n",
                       f"    vec3 {view_var} = dir;   // pixel direction in place of the stock view vector\n",
                       m.group(1), count=1)
    sky_var = re.search(r"vec4 (\w+);", sky_block)
    if not sky_var:
        raise UraniaError("The stock sky lookup in stage 1 has no sky color result.")
    sky_block = ("// ---- Stock X-Plane sky lookup (read from your astronomical.xsa) ----\n" + sky_block
                 + f"    vec4 stock_sky = {sky_var.group(1)};\n    // ---- End of the stock sky lookup ----")
    defines = [f"#define MASTRO {block_instance(head, 'u_astronomical_data')}",
               f"#define MDOME {block_instance(head, 'u_dome_data')}"]
    body = _source("moon_fragment.glsl")
    body = body.replace("// @SETTINGS@", moon_settings_block(settings)).replace("    // @STOCK_SKY@", sky_block)
    return (head.rstrip() + "\n\n// ---- End of the stock X-Plane declarations ----\n"
            + "\n".join(defines) + "\n\n" + body)


def _source(name):
    return resources.files("urania.engine").joinpath("shader_src", name).read_text(encoding="utf-8")


def assemble_vertex(stock_glsl, settings=None):
    decl, defines = stock_declarations(stock_glsl)
    body = _source("sky_vertex.glsl")
    body = body.replace("// @SETTINGS@", settings_block("v", settings)).replace("// @STAR_RGB@", star_rgb_table())
    return ("#version 460\n#extension GL_ARB_shader_viewport_layer_array : require\n\n"
            "// ---- Stock X-Plane declarations (read from your astronomical.xsa) ----\n"
            f"{decl}\n\n{defines}\n\n{body}")


def assemble_fragment(settings=None):
    body = _source("sky_fragment.glsl")
    return "#version 460\n\n" + body.replace("// @SETTINGS@", settings_block("f", settings))


# =====================================================================================
# 4. BUILD
# =====================================================================================

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def open_stock(xsa_path):
    """Open an original astronomical.xsa. Return (ZipFile, {stage: entry name}).

    Raise UraniaError if it is not a 9-stage file or if it is already patched.
    """
    try:
        zin = zipfile.ZipFile(xsa_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise UraniaError(f"{xsa_path} is not an astronomical.xsa file ({e}).") from e
    stock = {}
    for n in zin.namelist():
        m = re.search(r"_(\d+)\.spv$", n)
        if m:
            stock[int(m.group(1))] = n
    if sorted(stock) != list(range(STAGE_COUNT)):
        zin.close()
        raise UraniaError(f"{xsa_path}: expected astronomical_0.spv ... astronomical_8.spv, found {zin.namelist()}")
    if spirv.PATCH_MARK in zin.read(stock[7]) or spirv.MOON_MARK in zin.read(stock[1]):
        zin.close()
        raise UraniaError(f"{xsa_path} is already patched. Use the ORIGINAL X-Plane file.")
    return zin, stock


@dataclass
class XsaResult:
    xsa: str                       # path of the new astronomical.xsa
    report: str                    # path of build_report.txt
    gains: dict                    # gains as the plugin reads them


def decompile_xsa(xsa_path, out_dir, tools_dir=None, log=_quiet):
    """Write the stock GLSL of all 9 stages (to study them; do not publish this X-Plane code)."""
    zin, stock = open_stock(xsa_path)
    cross = tools.find_tool("spirv-cross", tools_dir)
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="urania_")
    try:
        for i in range(STAGE_COUNT):
            p = os.path.join(tmp, f"stock_{i}.spv")
            with open(p, "wb") as f:
                f.write(zin.read(stock[i]))
            text = tools.run([cross, p, "--vulkan-semantics"])
            with open(os.path.join(out_dir, f"stock_astronomical_{i}.glsl"), "w", newline="\n") as f:
                f.write(text)
    finally:
        zin.close()
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"Wrote the stock GLSL of 9 stages to {out_dir}. Do not publish this X-Plane code.")


def build_xsa(xsa_path, out_dir, settings=None, tools_dir=None, log=_quiet):
    """Build the patched astronomical.xsa in out_dir. Return an XsaResult."""
    settings = settings or DEFAULT_SETTINGS
    zin, stock = open_stock(xsa_path)
    tmp = tempfile.mkdtemp(prefix="urania_")
    try:
        cross = tools.find_tool("spirv-cross", tools_dir)
        glslang = tools.find_tool("glslangValidator", tools_dir)
        val = tools.find_tool("spirv-val", tools_dir)
        glsl_dir = os.path.join(out_dir, "glsl")
        os.makedirs(glsl_dir, exist_ok=True)

        moon = moon_enabled(settings)
        stock_glsl = {}
        for i in ((0, 1, 2, 6, 8) if moon else (6, 8)):
            p = os.path.join(tmp, f"stock_{i}.spv")
            with open(p, "wb") as f:
                f.write(zin.read(stock[i]))
            stock_glsl[i] = tools.run([cross, p, "--vulkan-semantics"])

        sources = {6: assemble_vertex(stock_glsl[6], settings), 7: assemble_fragment(settings),
                   8: assemble_vertex(stock_glsl[8], settings)}
        if moon:                                             # moonlit sky + moon phase (docs/MOONLIGHT.md)
            sources[0] = assemble_moon_vertex(stock_glsl[0], point_size=False, settings=settings)
            sources[1] = assemble_moon_fragment(stock_glsl[1], settings)
            sources[2] = assemble_moon_vertex(stock_glsl[2], point_size=True, settings=settings)
        new_spv = {}
        for i, text in sorted(sources.items()):
            ext = MOD_STAGES[i]
            src = os.path.join(glsl_dir, f"astronomical_{i}.{ext}")
            spv = os.path.join(tmp, f"astronomical_{i}.spv")
            with open(src, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            log(f"Compile stage {i} ({ext})")
            tools.run([glslang, "-V", "--target-env", "vulkan1.3", "-S", ext, src, "-o", spv])
            tools.run([val, "--target-env", "vulkan1.3", spv])
            with open(spv, "rb") as f:
                new_spv[i] = f.read()

        out_xsa = os.path.join(out_dir, XSA_NAME)
        with zipfile.ZipFile(out_xsa, "w", zipfile.ZIP_DEFLATED) as zout:
            for i in range(STAGE_COUNT):
                info = copy.copy(zin.getinfo(stock[i]))     # keep the stock entry name and date
                if i in (6, 8):
                    info.compress_type = zipfile.ZIP_STORED  # the plugin changes the gains in place
                zout.writestr(info, new_spv[i] if i in new_spv else zin.read(stock[i]))
        with open(xsa_path, "rb") as f:
            in_hash = sha256_bytes(f.read())
    finally:
        zin.close()
        shutil.rmtree(tmp, ignore_errors=True)

    gains = spirv.read_gains(out_xsa)                       # self-check: the plugin can read the gains
    with open(out_xsa, "rb") as f:
        out_hash = sha256_bytes(f.read())
    report = ["Urania shader build report", "",
              f"Input  astronomical.xsa  {in_hash}",
              f"Output astronomical.xsa  {out_hash}", ""]
    report += [f"Stage {i}: {sha256_bytes(new_spv[i])}" for i in sorted(new_spv)]
    report += ["", "Tools:",
               f"  {tools.tool_version(glslang, 'glslangValidator')}",
               f"  spirv-val: {tools.tool_version(val, 'spirv-val')}",
               f"  spirv-cross: {tools.tool_version(cross, 'spirv-cross')}",
               f"  Python {sys.version.split()[0]}", "", "Settings:"]
    report += [f"  {n} = {glsl_value(s.value)}" for n, s in settings.items()]
    report_path = os.path.join(out_dir, REPORT_NAME)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")
    log(f"Shader done: {out_xsa}")
    return XsaResult(out_xsa, report_path, gains)
