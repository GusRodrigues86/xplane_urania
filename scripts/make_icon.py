#!/usr/bin/env python3
"""
make_icon.py - Draw the Urania icon: the Pleiades (M45) with their faint blue reflection nebula.

The 9 bright stars are at their real J2000 positions (relative to Alcyone), sized by magnitude.
The glow is a sum of soft Gaussians, strongest around Merope and Maia (as in photos of M45).
Each icon size is drawn separately, so the small sizes stay sharp.

Output:
    packaging/urania.ico              Windows app icon (16 ... 256 px)
    src/urania/assets/urania.png      window icon (256 px; Tk iconphoto, Linux)

Needs Pillow and numpy. Run:  python scripts/make_icon.py
"""
import math
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# name, RA (h, m, s), Dec (deg, arcmin, arcsec), V magnitude
STARS = [
    ("Alcyone",  (3, 47, 29.1), (24, 6, 18), 2.87),
    ("Atlas",    (3, 49, 9.7),  (24, 3, 12), 3.62),
    ("Electra",  (3, 44, 52.5), (24, 6, 48), 3.70),
    ("Maia",     (3, 45, 49.6), (24, 22, 4), 3.87),
    ("Merope",   (3, 46, 19.6), (23, 56, 54), 4.18),
    ("Taygeta",  (3, 45, 12.5), (24, 28, 2), 4.30),
    ("Pleione",  (3, 49, 11.2), (24, 8, 12), 5.05),
    ("Celaeno",  (3, 44, 48.2), (24, 17, 22), 5.45),
    ("Asterope", (3, 45, 54.5), (24, 33, 16), 5.76),
]
# Extra nebula light (reflection nebula: brightest near Merope, then Maia, Electra, Alcyone).
NEBULA = {"Merope": 1.0, "Maia": 0.7, "Electra": 0.45, "Alcyone": 0.55, "Taygeta": 0.3}

BG_TOP, BG_BOTTOM = (16, 22, 40), (9, 12, 24)          # deep-space navy (theme "bg")
GLOW = np.array([90, 150, 255]) / 255.0                  # reflection-nebula blue
STAR_CORE = np.array([235, 244, 255]) / 255.0            # hot B stars: blue-white
STAR_HALO = np.array([150, 195, 255]) / 255.0


def positions():
    """Return {name: (x, y)} in degrees: x to the left = east (as in the sky), y up = north."""
    ra0 = (3 + 47 / 60 + 29.1 / 3600) * 15
    dec0 = 24 + 6 / 60 + 18 / 3600
    out = {}
    for name, (h, m, s), (d, am, asec), _ in STARS:
        ra = (h + m / 60 + s / 3600) * 15
        dec = d + am / 60 + asec / 3600
        out[name] = (-(ra - ra0) * math.cos(math.radians(dec0)), dec - dec0)
    return out


def wisps(size, angle_deg=-30, seed=45):
    """Random wisps: noise smeared along one direction (thin across, long along). Mean 0, std 1."""
    rnd = np.random.default_rng(seed)                   # fixed seed: same icon each run
    noise = rnd.normal(size=(size, size))
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    a = math.radians(angle_deg)
    fu = fx * math.cos(a) + fy * math.sin(a)             # across the wisps
    fv = -fx * math.sin(a) + fy * math.cos(a)            # along the wisps
    su, sv = 0.012 * size, 0.10 * size                   # Gaussian sigma in px
    kernel = np.exp(-2 * math.pi ** 2 * ((fu * su) ** 2 + (fv * sv) ** 2))
    field = np.real(np.fft.ifft2(np.fft.fft2(noise) * kernel))
    return (field - field.mean()) / (field.std() + 1e-12)


def render(size):
    pos = positions()
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = size * 0.70 / span                            # the cluster fills 70 % of the icon

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64) + 0.5
    t = yy / size
    img = (np.array(BG_TOP) * (1 - t[..., None]) + np.array(BG_BOTTOM) * t[..., None]) / 255.0

    def to_px(name):
        x, y = pos[name]
        return size / 2 + (x - cx) * scale, size / 2 - (y - cy) * scale

    # 1. Nebula: soft Gaussians around the stars (faint blue glow), with fine streaks.
    #    The Pleiades dust shows parallel wisps (about 30 deg from east-west in photos).
    neb = np.zeros((size, size))
    for name, w in NEBULA.items():
        px, py = to_px(name)
        for sig, a in ((0.05, 0.8), (0.12, 0.35)):
            s = sig * size
            neb += w * a * np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / (2 * s * s))
    neb *= np.clip(1 + 0.6 * wisps(size), 0.2, 2.0)
    neb = 1 - np.exp(-neb * 0.9)                          # soft saturation
    img = img + neb[..., None] * GLOW * 0.5

    # 2. Stars: halo + core. Brighter = larger. Small icons get relatively larger stars.
    min_core = 0.9 if size <= 32 else 0.6
    for name, _, _, mag in STARS:
        px, py = to_px(name)
        flux = 10 ** (-0.4 * (mag - 2.87))                 # 1.0 for Alcyone
        r_core = max(min_core, size * 0.022 * flux ** 0.35)
        r_halo = r_core * 3.2
        d2 = (xx - px) ** 2 + (yy - py) ** 2
        halo = 0.55 * flux ** 0.5 * np.exp(-d2 / (2 * r_halo ** 2))
        core = np.exp(-d2 / (2 * r_core ** 2))
        img = img + halo[..., None] * STAR_HALO + core[..., None] * STAR_CORE
        if size >= 48 and mag < 4.0:                       # thin diffraction spikes on the bright ones
            spike = 0.35 * flux ** 0.5 * (np.exp(-np.abs(xx - px) / (0.006 * size)) *
                                          np.exp(-np.abs(yy - py) / (0.10 * size)) +
                                          np.exp(-np.abs(yy - py) / (0.006 * size)) *
                                          np.exp(-np.abs(xx - px) / (0.10 * size)))
            img = img + spike[..., None] * STAR_HALO

    rgb = np.clip(img, 0, 1) ** (1 / 1.1)

    # 3. Rounded square shape (alpha), smooth edge.
    r = size * 0.22
    dx = np.maximum(np.abs(xx - size / 2) - (size / 2 - r), 0)
    dy = np.maximum(np.abs(yy - size / 2) - (size / 2 - r), 0)
    dist = np.sqrt(dx ** 2 + dy ** 2) - r
    alpha = np.clip(0.5 - dist, 0, 1)
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA")


def main():
    sizes = [256, 128, 64, 48, 32, 24, 16]
    images = [render(s) for s in sizes]
    ico = os.path.join(ROOT, "packaging", "urania.ico")
    images[0].save(ico, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    png_dir = os.path.join(ROOT, "src", "urania", "assets")
    os.makedirs(png_dir, exist_ok=True)
    images[0].save(os.path.join(png_dir, "urania.png"))
    images[0].resize((512, 512), Image.LANCZOS)            # (nothing: keep 256 for the window icon)
    print(f"wrote {ico} and {os.path.join(png_dir, 'urania.png')}")


if __name__ == "__main__":
    main()
