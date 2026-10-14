"""
night_sky.py - Build the night-sky data file for X-Plane 12 (earth_astro.dat).

Library version of make_night_sky.py (night-sky-generator v1). The math and the settings are
unchanged: the same input files give byte-identical output files (see tests/fixtures/
reference_generation_report.txt).

This module reads 3 input files and writes 2 output files:

    earth_astro.dat           stars + star colors + Milky Way + deep-sky objects
    earth_astro_airglow.dat   the same data + a faint glow over the full sky (airglow)

It also writes a report (generation_report.txt) with counts, settings and SHA-256 values.

GLOSSARY (one word = one meaning in this file)
    row        One line in earth_astro.dat: RA (hours), Dec (degrees), magnitude, name.
    star       A row from the X-Plane star file. The shader draws a star as a small dot.
    haze blob  A row that this module adds. The shader draws a haze blob as a soft round glow.
    code       A small integer that this module hides in the decimals of the magnitude field.
    magnitude  Astronomical brightness. A larger magnitude is a dimmer object (Pogson scale).
    SB         Surface brightness, in magnitudes per square arcsecond (mag/arcsec^2).
    map        The NASA Milky Way image (EXR file), one value per pixel.
    lattice    A set of points spread evenly over the full sky (Fibonacci sphere).

INPUT FILES
    astro     X-Plane 12 star file: <X-Plane 12>/Resources/default data/earth_astro.dat (original).
    stars     d3-celestial star catalog "stars.8.json" (npm package d3-celestial 0.7.35,
              BSD-3-Clause). It gives the B-V color index of each star.
    milkyway  NASA SVS 4851 "Deep Star Maps 2020", file milkyway_2020_4k.exr
              (Milky Way background, celestial J2000 frame). Credit: NASA/Goddard SVS, ESA/Gaia/DPAC.

See docs/NIGHT_SKY_ENCODING.md for the math and for the reasons behind the encoding.
"""
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

from urania.errors import UraniaError

# =====================================================================================
# 1. SETTINGS
#    Each setting changes the output. The report file records all of these values.
# =====================================================================================

# --- Star color code (stars from the X-Plane file) ---------------------------------
# The color code k is an integer from 1 to 89. k = 0 means "no color" (white).
# Codes 90 to 99 are reserved for haze blobs. The shader uses this rule to tell them apart.
STAR_K_MIN, STAR_K_MAX = 1, 89
BV_MIN, BV_MAX = -0.40, 2.00        # B-V range. k = 1 is B-V -0.40 (blue), k = 89 is B-V 2.00 (red).
MATCH_RADIUS_DEG = 0.15             # A catalog star must be nearer than this to match an X-Plane star.
MATCH_MAG_DIFF = 0.6                # A catalog star must have a magnitude within this value to match.

# --- Precession ---------------------------------------------------------------------
# The X-Plane star file uses epoch J2025. The catalog and the NASA map use epoch J2000.
# The module moves J2000 positions to J2025 (IAU 1976 precession, T in Julian centuries).
PRECESSION_T = 0.25

# --- Milky Way from the NASA map ----------------------------------------------------
SB_ANCHOR = 20.0                    # SB that we give to the Sagittarius star cloud.
SB_ANCHOR_MAP_VALUE = 0.3103        # Mean map value in the Sagittarius star cloud box.
ZP = SB_ANCHOR + 2.5 * math.log10(SB_ANCHOR_MAP_VALUE)   # Zero point: SB = ZP - 2.5 log10(map value)
FADE_SB = (22.8, 24.0)              # Sky dimmer than 22.8 fades out. Sky dimmer than 24.0 is removed.
FINE_S, FINE_SIZE = 0.5, 13         # Fine layer: 0.5 deg lattice, size class 13 (1.82 deg blobs).
COARSE_S, COARSE_SIZE = 1.4, 18     # Coarse layer: 1.4 deg lattice, size class 18 (5.55 deg blobs).
BLEND_SB = (21.6, 22.6)             # Fine layer where SB < 21.6, coarse layer where SB > 22.6, mix between.
MAG_MAX = 9.4                       # The module drops Milky Way blobs dimmer than this magnitude.

# --- Airglow (only in earth_astro_airglow.dat) --------------------------------------
# Airglow is the natural glow of a dark night sky (upper air glow + zodiacal light).
AIRGLOW_SB, AIRGLOW_S, AIRGLOW_SIZE = 22.3, 2.5, 21   # SB, lattice step (deg), size class (9.3 deg)

# --- Deep-sky objects ---------------------------------------------------------------
# One tuple for each object:
#   name, RA (hours, J2000), Dec (deg, J2000), major axis (arcmin), minor axis (arcmin),
#   position angle (deg, north through east), total magnitude, color class.
# Color classes: 0 Milky Way, 1 H-alpha (red emission), 2 teal (nebula core, reflection, planetary),
#                3 galaxy or star cluster (warm white).
# The LMC and the SMC are not in this list. The NASA map already contains them.
DSO = [
    ("M31",     0.7123,  41.269, 190,  60,  35, 3.4, 3),
    ("M33",     1.5641,  30.660,  70,  40,  23, 5.7, 3),
    ("NGC5128", 13.4247, -43.019,  26,  20,  35, 6.8, 3),
    ("NGC253",  0.7925, -25.288,  27,   7,  52, 7.1, 3),
    ("M81",     9.9258,  69.065,  27,  14, 157, 6.9, 3),
    ("M104",   12.6667, -11.623,   9,   4,  90, 8.0, 3),
    ("M42",     5.5881,  -5.391,  50,  45,   0, 5.0, 1),
    ("M42core", 5.5881,  -5.391,  12,  12,   0, 4.6, 2),
    ("NGC3372", 10.7517, -59.867, 120, 120,   0, 1.0, 1),
    ("M8",     18.0606, -24.383,  90,  40,  90, 6.0, 1),
    ("M20",    18.0447, -23.030,  28,  28,   0, 6.3, 1),
    ("M17",    18.3469, -16.177,  46,  37,   0, 6.0, 1),
    ("M16",    18.3133, -13.817,  35,  28,   0, 6.4, 1),
    ("NGC7000", 20.9792,  44.333, 120, 100,   0, 4.0, 1),
    ("NGC2070", 5.6442, -69.101,  40,  25,   0, 7.3, 1),
    ("M45neb",  3.7900,  24.117, 110, 110,   0, 7.0, 2),
    ("wCen",   13.4469, -47.479,  36,  36,   0, 3.9, 3),
    ("47Tuc",   0.4014, -72.081,  31,  31,   0, 4.1, 3),
    ("M13",    16.6948,  36.461,  20,  20,   0, 5.8, 3),
    ("M22",    18.6067, -23.905,  32,  32,   0, 5.1, 3),
    ("NGC7293", 22.4936, -20.837,  16,  16,   0, 7.6, 2),
    ("M27",    19.9934,  22.721,   8,   6,   0, 7.4, 2),
    ("M32",     0.7117,  40.865,   9,   7, 170, 8.1, 3),   # Andromeda companion
    ("M110",    0.6730,  41.685,  22,  11, 170, 8.5, 3),   # Andromeda companion
]
# Elongated objects (minor / major < 0.7) become a chain of overlapping haze blobs:
ELONG_DIAM = 1.4    # Blob diameter = 1.4 x minor axis.
ELONG_STEP = 0.35   # Distance between blob centers <= 0.35 x blob diameter (the blobs overlap).
ELONG_SIG = 0.3     # Flux along the major axis is a Gaussian with sigma = 0.3 x major axis.

# The settings that the report lists (all the values above).
_REPORT_SETTINGS = (
    "AIRGLOW_S", "AIRGLOW_SB", "AIRGLOW_SIZE", "BLEND_SB", "BV_MAX", "BV_MIN", "COARSE_S", "COARSE_SIZE",
    "ELONG_DIAM", "ELONG_SIG", "ELONG_STEP", "FADE_SB", "FINE_S", "FINE_SIZE",
    "MAG_MAX", "MATCH_MAG_DIFF", "MATCH_RADIUS_DEG", "PRECESSION_T", "SB_ANCHOR", "SB_ANCHOR_MAP_VALUE",
    "STAR_K_MAX", "STAR_K_MIN", "ZP")

# Output file names.
DAT_PLAIN = "earth_astro.dat"
DAT_AIRGLOW = "earth_astro_airglow.dat"
REPORT_NAME = "generation_report.txt"

# The X-Plane file is plain ASCII. latin-1 reads and writes each byte unchanged.
_ENC = "latin-1"


def _quiet(_text):
    pass


# =====================================================================================
# 2. ENCODING
#    X-Plane reads only 4 fields per row. The shader receives the magnitude as one float.
#    The module hides extra data in the decimals of the magnitude. See NIGHT_SKY_ENCODING.md.
# =====================================================================================

def bv_to_k(bv):
    """Convert a B-V color index to the star color code k (1..89). Linear steps of 0.0273 in B-V."""
    t = (min(max(bv, BV_MIN), BV_MAX) - BV_MIN) / (BV_MAX - BV_MIN)
    return STAR_K_MIN + round(t * (STAR_K_MAX - STAR_K_MIN))


def encode_star(mag, k):
    """Return the magnitude field for a star: magnitude to 0.01 + k in the 3rd and 4th decimals."""
    return round(mag, 2) + k * 1e-4


def size_class(diam_deg):
    """Convert a diameter in degrees to the size class (0..24). Diameter = 0.1 deg x 1.25^size."""
    return max(0, min(24, round(math.log(max(diam_deg, 0.1) / 0.1) / math.log(1.25))))


def encode_haze(mag, color, size):
    """Return the magnitude field for a haze blob.

    Layout of the decimals:   M.D c kk
        M.D  magnitude to 0.1
        c    2nd decimal (0..9)
        kk   3rd and 4th decimals (90..99)
    code = (kk - 90) * 10 + c = color * 25 + size   (0..99: 4 colors x 25 sizes)
    """
    code = color * 25 + size
    kk, c = 90 + code // 10, code % 10
    m10 = max(0, math.floor(max(mag, 0.0) * 10 + 0.5))     # magnitude in tenths, 0 or more
    return (m10 * 10 + c) / 100 + kk * 1e-4


def decode_like_shader(field_value):
    """Decode a magnitude field with float32 math, as the patched shader does.

    Return (kind, magnitude, k, color, size). kind is "star" or "haze".
    The shader code is:  t = w*100; n = floor(t + 0.005); k = round((t - n) * 100)
    """
    w = np.float32(field_value)
    t = w * np.float32(100)
    n = float(np.floor(t + np.float32(0.005)))
    k = int(np.clip(np.round((t - np.float32(n)) * np.float32(100)), 0, 99))
    if k >= 90:
        c = int(n - 10.0 * math.floor(n / 10.0) + 0.5) % 10
        code = (k - 90) * 10 + c
        return "haze", (n - c) * 0.01, k, code // 25, code % 25
    return "star", float(w), k, None, None


# =====================================================================================
# 3. ASTRONOMY HELPERS
# =====================================================================================

def precess(ra_deg, dec_deg, T=PRECESSION_T):
    """Move a J2000 position to the epoch J2000 + T centuries (IAU 1976). Return (RA deg, Dec deg)."""
    a = math.radians
    zeta = a((2306.2181 * T + 0.30188 * T * T) / 3600)
    z = a((2306.2181 * T + 1.09468 * T * T) / 3600)
    th = a((2004.3109 * T - 0.42665 * T * T) / 3600)
    ra, dec = a(ra_deg), a(dec_deg)
    A = math.cos(dec) * math.sin(ra + zeta)
    B = math.cos(th) * math.cos(dec) * math.cos(ra + zeta) - math.sin(th) * math.sin(dec)
    C = math.sin(th) * math.cos(dec) * math.cos(ra + zeta) + math.cos(th) * math.sin(dec)
    return (math.degrees(math.atan2(A, B) + z)) % 360, math.degrees(math.asin(C))


def smoothstep(a, b, x):
    """Return 0 below a, 1 above b, and a smooth S-curve between a and b."""
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def lattice(step_deg):
    """Yield (RA hours, Dec deg) points spread evenly over the full sky (Fibonacci sphere).

    The number of points = sky area (41253 square degrees) / step^2.
    """
    n = int(41253 / step_deg ** 2)
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        yield (i * math.pi * (3 - math.sqrt(5)) / (2 * math.pi) * 24) % 24, math.degrees(math.asin(z))


def is_row(fields):
    """Return True if the fields are a star row (RA, Dec, magnitude are numbers, RA has a dot)."""
    try:
        float(fields[0]); float(fields[1]); float(fields[2])
        return '.' in fields[0]
    except (ValueError, IndexError):
        return False


# =====================================================================================
# 4. STEP A - READ THE X-PLANE STAR FILE AND ADD STAR COLOR CODES
# =====================================================================================

def load_catalog(stars_json):
    """Read the d3-celestial catalog. Return a list of (RA deg, Dec deg, magnitude, B-V) at J2025."""
    try:
        with open(stars_json, encoding="utf-8") as f:
            features = json.load(f)['features']
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise UraniaError(f"{stars_json} is not the d3-celestial star catalog stars.8.json ({e}).") from e
    cat = []
    for f in features:
        bv = f['properties'].get('bv')
        if bv in (None, ''):
            continue                                   # No color index: the star stays white.
        lon, lat = f['geometry']['coordinates']        # d3-celestial: lon = RA in degrees (-180..180)
        ra, dec = precess(lon % 360, lat)
        cat.append((ra, dec, float(f['properties']['mag']), float(bv)))
    return cat


def color_code_stars(astro_lines, cat):
    """Add a color code k to each star row. Return (new lines, number of stars, number of matches).

    The match rule: same place (within MATCH_RADIUS_DEG) and similar magnitude (within MATCH_MAG_DIFF).
    If more than one catalog star matches, the nearest catalog star wins.
    """
    grid = {}                                          # Put catalog stars in 1-degree Dec bands (fast search).
    for s in cat:
        grid.setdefault(int(math.floor(s[1])), []).append(s)

    def match(ra, dec, mag):
        best, best_d = None, MATCH_RADIUS_DEG
        for band in range(int(math.floor(dec)) - 1, int(math.floor(dec)) + 2):
            for s in grid.get(band, []):
                dra = (s[0] - ra + 180) % 360 - 180
                d = math.hypot(dra * math.cos(math.radians(dec)), s[1] - dec)
                if d < best_d and abs(s[2] - mag) < MATCH_MAG_DIFF:
                    best, best_d = s, d
        return best

    out, n_star, n_hit = [], 0, 0
    for ln in astro_lines:
        p = ln.split()
        if len(p) < 3:
            out.append(ln)
            continue
        try:
            ra_h, dec, mag = float(p[0]), float(p[1]), float(p[2])
        except ValueError:
            out.append(ln)                             # Header or comment line: keep it as it is.
            continue
        n_star += 1
        s = match(ra_h * 15, dec, mag)
        k = bv_to_k(s[3]) if s else 0                  # No match: k = 0 (white).
        n_hit += bool(s)
        name = ' '.join(p[3:])
        # Keep the original text up to the magnitude field. Replace only the magnitude and the name spacing.
        prefix = ln[:ln.index(p[2], len(p[0]) + len(p[1]))]
        out.append(f"{prefix}{encode_star(mag, k):.4f}{(' ' + name) if name else ''}")
    return out, n_star, n_hit


# =====================================================================================
# 5. STEP B - MILKY WAY HAZE BLOBS FROM THE NASA MAP
# =====================================================================================

def load_map(exr_path):
    """Read the NASA EXR map. Return {block factor: 2-D array} for block factors 1, 4 and 16.

    The map is equirectangular: RA 0h at the image center, RA grows to the left, Dec +90 at the top.
    The module uses the mean of R, G and B (grey value) for each pixel.
    """
    import OpenEXR
    try:
        lum = OpenEXR.File(exr_path).channels()["RGB"].pixels.astype(np.float64).mean(2)
    except Exception as e:                              # OpenEXR raises several error types
        raise UraniaError(f"{exr_path} is not the NASA map milkyway_2020_4k.exr ({e}).") from e
    h, w = lum.shape
    if w != 2 * h or h % 16:
        raise UraniaError(f"{exr_path}: the map must be 2:1 with a height divisible by 16, not {w} x {h}.")
    return {f: lum.reshape(h // f, f, w // f, f).mean((1, 3)) for f in (1, 4, 16)}


def gauss_mean(maps, ra_h, dec, sigma, f):
    """Return the Gaussian-weighted mean map value around (RA, Dec). sigma is in degrees.

    The weight of each pixel = exp(-0.5 (angle / sigma)^2) x cos(Dec). cos(Dec) corrects the
    pixel area of the equirectangular map. The module uses pixels within 3 sigma.
    """
    m = maps[f]
    h, w = m.shape
    dpp = 180 / h                                       # degrees per pixel
    r = 3 * sigma
    y0, y1 = max(0, int((90 - dec - r) / dpp)), min(h, int((90 - dec + r) / dpp) + 1)
    ys = np.arange(y0, y1)
    decs = 90 - (ys + 0.5) * dpp
    cosd = max(math.cos(math.radians(dec)), 0.0)
    rx = r / max(min(cosd, min(np.cos(np.radians(decs)).clip(1e-3))), 1e-3)   # wider in RA near the poles
    nx = min(w // 2, int(rx / dpp) + 1)
    u = ((0.5 - ra_h / 24) % 1) * w
    xs = (np.arange(int(u) - nx, int(u) + nx + 1)) % w
    ras = np.radians((0.5 - (xs + 0.5) / w) * 360)
    d1, r1 = math.radians(dec), math.radians(ra_h * 15)
    D, R = np.meshgrid(np.radians(decs), ras, indexing="ij")
    cosang = np.sin(d1) * np.sin(D) + np.cos(d1) * np.cos(D) * np.cos(R - r1)
    ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    wgt = np.exp(-0.5 * (ang / sigma) ** 2) * np.cos(D)
    return float((m[np.ix_(ys, xs)] * wgt).sum() / wgt.sum())


def sb_of(v):
    """Convert a map value to surface brightness (mag/arcsec^2)."""
    return ZP - 2.5 * math.log10(max(v, 1e-9))


def milky_way_layer(maps, step, size, sigma, f, fine):
    """Make one layer of Milky Way haze blobs. Return a list of (RA h, Dec, field, name).

    For each lattice point:
      1. Read the SB at the point (block-16 map) to choose the layer weight.
      2. Read the Gaussian-weighted SB around the point (smooths the map to the blob size).
      3. Give the blob the total flux of its lattice cell: mag = SB - 2.5 log10(cell area x weight).
    """
    entries = []
    cell = (step * 3600) ** 2                           # cell area in arcsec^2
    m16 = maps[16]
    for ra_h, dec in lattice(step):
        sb_c = sb_of(m16[min(int((90 - dec) / 180 * m16.shape[0]), m16.shape[0] - 1),
                         int(((0.5 - ra_h / 24) % 1) * m16.shape[1])])
        wb = 1 - smoothstep(*BLEND_SB, sb_c)            # 1 = fine layer, 0 = coarse layer
        wgt = (wb if fine else 1 - wb) * (1 - smoothstep(*FADE_SB, sb_c))
        if wgt < 0.02:
            continue                                    # Too faint or other layer: skip.
        sb = sb_of(gauss_mean(maps, ra_h, dec, sigma, f))
        mag = sb - 2.5 * math.log10(cell * wgt)
        if mag > MAG_MAX:
            continue
        ra2, dec2 = precess(ra_h * 15, dec)
        entries.append(((ra2 % 360) / 15, dec2, encode_haze(mag, 0, size), "MW"))
    return entries


# =====================================================================================
# 6. STEP C - AIRGLOW HAZE BLOBS
# =====================================================================================

def airglow_layer():
    """Make the airglow layer: one faint haze blob per lattice point, same SB everywhere."""
    entries = []
    mag = AIRGLOW_SB - 2.5 * math.log10((AIRGLOW_S * 3600) ** 2)
    for ra_h, dec in lattice(AIRGLOW_S):
        ra2, dec2 = precess(ra_h * 15, dec)
        entries.append(((ra2 % 360) / 15, dec2, encode_haze(mag, 0, AIRGLOW_SIZE), "SKY"))
    return entries


# =====================================================================================
# 7. STEP D - DEEP-SKY OBJECTS
# =====================================================================================

def dso_entries():
    """Make the haze blobs for the deep-sky objects in DSO. Return a list of (RA h, Dec, field, name)."""
    entries = []

    def add_blob(name, ra_h, dec, off, pa, mag, color, diam_deg):
        # Move the blob center by 'off' degrees along the position angle, then precess to J2025.
        d_dec = off * math.cos(math.radians(pa))
        d_ra = off * math.sin(math.radians(pa)) / math.cos(math.radians(dec))
        ra2, dec2 = precess(ra_h * 15 + d_ra, dec + d_dec)
        entries.append(((ra2 % 360) / 15, dec2, encode_haze(mag, color, size_class(diam_deg)), name))

    for name, ra_h, dec, a, b, pa, mag, color in DSO:
        if b / a > 0.7:                                 # Round object: one blob.
            add_blob(name, ra_h, dec, 0.0, pa, mag, color, b / 60)
            continue
        # Elongated object: a chain of overlapping blobs along the major axis.
        flux = 10 ** (-0.4 * mag)
        diam = ELONG_DIAM * b / 60
        half = 0.5 * (a - 0.6 * b) / 60                 # Chain centers go from -half to +half (deg).
        n = min(15, max(2, int(math.ceil(2 * half / (ELONG_STEP * diam))) + 1))
        offs = [(j - (n - 1) / 2) * (2 * half / (n - 1)) for j in range(n)]
        w = [math.exp(-0.5 * (o / (ELONG_SIG * a / 60)) ** 2) for o in offs]
        sw = sum(w)
        for j, (o, wj) in enumerate(zip(offs, w)):
            add_blob(name + chr(97 + j), ra_h, dec, o, pa,
                     -2.5 * math.log10(flux * wj / sw), color, diam)
    return entries


# =====================================================================================
# 8. STEP E - WRITE THE OUTPUT FILE
# =====================================================================================

def assemble(lines, entries):
    """Merge the star rows and the haze blob rows. Return the full file text.

    The X-Plane file has a header, the rows, an empty line and the end marker "99".
    The module sorts all rows by magnitude (bright first), as in the original X-Plane file.
    The sort is stable: rows with the same magnitude keep their input order.
    """
    ends = [i for i, l in enumerate(lines) if l.strip() == "99"]
    if not ends:
        raise UraniaError("The X-Plane star file has no end marker '99'. Use the original earth_astro.dat.")
    end = max(ends)
    idx = [i for i, l in enumerate(lines[:end]) if is_row(l.split())]
    if not idx:
        raise UraniaError("The X-Plane star file has no star rows. Use the original earth_astro.dat.")
    rows = sorted([lines[i] for i in idx] +
                  [f"{ra:7.4f} {dec:8.3f} {m:.4f} {nm}" for ra, dec, m, nm in entries],
                  key=lambda l: float(l.split()[2]))
    return "\n".join(lines[:idx[0]] + rows + [""] + lines[end:]) + "\n"


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_lines(path):
    """Read a star file as lines (no line ends)."""
    with open(path, encoding=_ENC) as f:
        return f.read().splitlines()


# =====================================================================================
# 9. CHECK TOOLS (verify, compare, preview)
# =====================================================================================

@dataclass
class VerifyResult:
    counts: dict = field(default_factory=dict)      # "star" / "haze color N" -> rows
    errors: list = field(default_factory=list)      # bad rows (text)

    @property
    def stars(self):
        return self.counts.get("star", 0)

    @property
    def haze(self):
        return sum(v for k, v in self.counts.items() if k.startswith("haze"))


def verify(path):
    """Decode each row like the shader. Return a VerifyResult with counts and bad rows."""
    result = VerifyResult()
    for ln in read_lines(path):
        p = ln.split()
        if not is_row(p):
            continue
        kind, mag, k, color, size = decode_like_shader(float(p[2]))
        key = kind if kind == "star" else f"haze color {color}"
        result.counts[key] = result.counts.get(key, 0) + 1
        if kind == "haze" and not (0 <= color <= 3 and 0 <= size <= 24):
            result.errors.append(f"bad code: {ln.rstrip()}")
        if kind == "star" and not (0 <= k <= 89):
            result.errors.append(f"bad star code: {ln.rstrip()}")
    return result


def compare(path_a, path_b):
    """Compare 2 files row by row (by RA, Dec, name). Return a list of report lines."""
    def load(path):
        d = {}
        for ln in read_lines(path):
            p = ln.split()
            if is_row(p):
                d[(p[0], p[1], ' '.join(p[3:]))] = p[2]
        return d
    a, b = load(path_a), load(path_b)
    only_a, only_b = a.keys() - b.keys(), b.keys() - a.keys()
    changed = [key for key in a.keys() & b.keys() if a[key] != b[key]]
    out = [f"rows: {len(a)} / {len(b)}   only in A: {len(only_a)}   only in B: {len(only_b)}   "
           f"changed magnitude field: {len(changed)}"]
    for key in sorted(changed)[:20]:
        out.append(f"  {key[2]:12s} RA {key[0]} Dec {key[1]}: {a[key]} -> {b[key]}")
    if sha256(path_a) == sha256(path_b):
        out.append("files are byte-identical")
    return out


def preview(path, png_path):
    """Draw the haze blobs as the shader does (equirectangular, log scale). Needs Pillow."""
    from PIL import Image
    PW, PH = 1440, 720
    img = np.zeros((PH, PW))
    for ln in read_lines(path):
        p = ln.split()
        if not is_row(p):
            continue
        kind, mag, k, color, size = decode_like_shader(float(p[2]))
        if kind != "haze":
            continue
        ra_h, dec = float(p[0]), float(p[1])
        sig = 0.1 * 1.25 ** size / 6                    # Gaussian sigma = diameter / 6 (see the MD file)
        x0, y0 = (0.5 - ra_h / 24) % 1 * PW, (90 - dec) / 180 * PH
        ry = int(3 * sig / 180 * PH) + 1
        rx = int(ry / max(math.cos(math.radians(dec)), 0.05)) + 1
        ys = np.arange(max(0, int(y0) - ry), min(PH, int(y0) + ry + 1))
        xs = np.arange(int(x0) - rx, int(x0) + rx + 1)
        Y, X = np.meshgrid(ys, xs, indexing="ij")
        dd = np.hypot((X - x0) * 360 / PW * math.cos(math.radians(dec)), (Y - y0) * 180 / PH)
        img[np.ix_(ys, xs % PW)] += 10 ** (-0.4 * mag) * np.exp(-0.5 * (dd / sig) ** 2) / (2 * math.pi * sig ** 2)
    sbm = -2.5 * np.log10(img / 3600 ** 2 + 1e-30)
    Image.fromarray((np.clip((24.0 - sbm) / 4.5, 0, 1) ** 0.8 * 255).astype(np.uint8)).save(png_path)


# =====================================================================================
# 10. BUILD
# =====================================================================================

@dataclass
class DatResult:
    outputs: dict                  # file name -> full path
    rows: dict                     # file name -> number of rows
    stars: int
    matched: int
    report: str                    # path of generation_report.txt


def build_dat(astro, stars, milkyway, out_dir, log=_quiet, want_preview=False):
    """Build earth_astro.dat and earth_astro_airglow.dat in out_dir. Return a DatResult.

    log(text) receives one progress line at a time.
    """
    os.makedirs(out_dir, exist_ok=True)
    log("Step A: read the X-Plane star file and add star color codes")
    astro_lines = read_lines(astro)
    cat = load_catalog(stars)
    lines, n_star, n_hit = color_code_stars(astro_lines, cat)
    if n_star == 0:
        raise UraniaError(f"{astro} has no star rows. Use the original X-Plane earth_astro.dat.")
    log(f"  stars={n_star} matched={n_hit} ({100 * n_hit / max(n_star, 1):.1f} %)")

    log("Step B: make Milky Way haze blobs from the NASA map (this step takes some time)")
    maps = load_map(milkyway)
    fine = milky_way_layer(maps, FINE_S, FINE_SIZE, FINE_S * 0.5, 1, True)
    coarse = milky_way_layer(maps, COARSE_S, COARSE_SIZE, COARSE_S * 0.5, 4, False)
    log(f"  fine={len(fine)} coarse={len(coarse)}")

    log("Step C: make airglow haze blobs")
    sky = airglow_layer()
    log(f"  airglow={len(sky)}")

    log("Step D: make deep-sky haze blobs")
    dso = dso_entries()
    log(f"  deep-sky={len(dso)}")

    log("Step E: write the output files")
    outputs = {DAT_PLAIN: fine + coarse + dso, DAT_AIRGLOW: fine + coarse + sky + dso}
    report = ["make_night_sky.py report", "",
              "Inputs (SHA-256):",
              f"  astro     {sha256(astro)}  {os.path.basename(astro)}",
              f"  stars     {sha256(stars)}  {os.path.basename(stars)}",
              f"  milkyway  {sha256(milkyway)}  {os.path.basename(milkyway)}",
              "", f"Python {sys.version.split()[0]}, numpy {np.__version__}", "",
              f"stars={n_star} matched={n_hit} fine={len(fine)} coarse={len(coarse)} "
              f"airglow={len(sky)} deep-sky={len(dso)}", "", "Outputs (SHA-256):"]
    paths, rows = {}, {}
    for name, entries in outputs.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding=_ENC, newline="\n") as f:
            f.write(assemble(lines, entries))
        n_rows = sum(1 for l in read_lines(path) if is_row(l.split()))
        log(f"  {name}: {n_rows} rows")
        report.append(f"  {sha256(path)}  {name}  ({n_rows} rows)")
        paths[name], rows[name] = path, n_rows
        if want_preview:
            preview(path, path + ".preview.png")

    report += ["", "Settings:"] + [f"  {k} = {globals()[k]!r}" for k in _REPORT_SETTINGS]
    report += ["  DSO ="] + [f"    {d!r}" for d in DSO]
    report_path = os.path.join(out_dir, REPORT_NAME)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report) + "\n")
    return DatResult(paths, rows, n_star, n_hit, report_path)
