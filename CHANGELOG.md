# Changelog

## Unreleased

### Brightness gains are multipliers over the physical brightness

- Stars keep the total light of their magnitude: the shader divides the star brightness by the area of the star sprite,
  as it already did for the haze blobs. All 4 gains now mean the same thing: 1 = physical (the catalog brightness),
  2 = twice as bright.
- `STAR_GAIN` default 0.35 -> 1.0 (physical, not tested yet in X-Plane). The old 0.35 is not comparable: with the old
  rule, the light of a star also grew with its sprite area (x2.25 for faint stars, x28 for the brightest).
- GUI, Advanced: "brightness multipliers". The box explains the values and what a higher value does. A comma in a value
  is an error ("use a dot for decimals"); an invalid value blocks Build (before, the app used the last valid value).
- Plugin (developer build): star slider range 0.05 to 20, button "App defaults".

### Galaxies: no core blob

- A galaxy is now only the elongated smudge. The 6 core blobs (M31, M33, NGC253, M81, M104, M110) are removed; the
  chain blobs get their 25 % of the light. `earth_astro.dat` has 58 287 rows (was 58 293). New reference hashes in
  `tests/fixtures/`.

## 1.0.1 (2026-10-11)

### Moonlit sky (new in Urania; from the NightSky v1 work)

- The shader also replaces the moon stages 0, 1 and 2 of `astronomical.xsa`:
  - The moon draw covers the whole sky. The sky glows around the moon: Krisciunas & Schaefer (1991). The glow is brightest near the moon and the horizon, and it follows the moon phase and height.
  - The glow fades in between sunset and the end of twilight (sun 0 to -6 degrees).
  - The scene light pass gets more glow, so terrain and cockpit get moonlit sky light.
  - The moon disk uses the Lommel-Seeliger light law, so the crescent stays bright up to its edge.
  - The glow adds over the stars (premultiplied blend), so the stars stay visible.
- Defaults are the tested "sky25" calibration, with `moon/nits` at the X-Plane default 785. History and probes: `docs/MOONLIGHT.md`.
- New settings `MOON`, `MOON_SKY`, `MOON_LIGHT`, `MOON_RGB`, `MOON_K_EXT`, `MOON_DIAMETER`, `MOON_DITHER`, `MOON_LS`.
- New app options: GUI "Moonlit sky" checkbox (on by default), CLI `--no-moon`.
- With the same tools, the shader is byte-identical to the night-sky-generator v1 release. Stages 0, 2, 6, 7 and 8 also match the v1 reference hashes (`tests/test_real.py`).

### Plugin 1.0.1

- The settings window shows if the installed sky has the moonlit sky (`install.txt` now has a `moon` line).
- New warning when `moon/nits` is not 785 (the moonlit sky calibration), with a button that sets it to 785.

### Docs

- `docs/MOONLIGHT.md`: the moonlit sky and plugin history (routes, probes, decisions).
- `docs/ASTRONOMICAL_SHADER.md`: the first analysis of the X-Plane 12 astronomical shader.

## 1.0.0 (2026-10-11)

First release:

- The app builds the star data and the star shader from the user's X-Plane files, and makes one install zip.
- GUI with drag and drop, and a CLI.
- The Urania plugin sets the cloud moonlight and the sky darkness. It checks the sky files and can restore the X-Plane sky.
