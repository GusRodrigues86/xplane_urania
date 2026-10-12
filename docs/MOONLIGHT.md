> **History document.** Written during the NightSky work (before Urania), 2026-10-10 and 2026-10-11. It records how the moonlit sky and the plugin were found and tested. Paths such as `test-probe-moon/`, `release/` and `nightsky-plugin/` are the old working folders; they are not in this repository. The result lives in Urania: `src/urania/engine/shader_src/moon_*.glsl`, the `MOON_*` settings in `src/urania/engine/shaders.py`, and the plugin (`plugin/src/urania.cpp`).

# Moonlit sky: all routes

Status 2026-10-10. Goal: a full moon makes the sky a Bortle 7.5 sky (M33 just not visible). The glow is brightest near the moon and follows the moon phase and height.

## 1. What X-Plane gives each shader

These facts come from the decompiled shaders (`dome.xsa`, `atmosphere.xsa`, `exposure_fusion.xsa`, `astronomical.xsa`).

| Shader | Job | Light data it gets | Moon data |
|---|---|---|---|
| `atmosphere.xsa` | Builds the Bruneton sky tables (scattering, transmittance) | Sun irradiance, air and aerosol settings | None |
| `dome.xsa` stages 1, 2, 4, 5 | Draws the sky (full screen) from the sky texture | `u_sun_dir_eye`, `u_sun_dir_wrl` (true sun), **`u_sun_position`, `u_E_sun`**, `u_time` | Unknown: see probe 1 |
| `dome.xsa` stages 3, 6 | Sun glare | Same | None |
| `astronomical.xsa` stages 0, 1 | Draws the moon | Moon mesh position (= moon direction), `u_light_position` (sun direction, for the phase), `u_light_diffuse` | **Yes** |
| `astronomical.xsa` stages 6 to 8 | Stars and our haze (the star mod) | Same as dome, plus `u_environment_data` (`u_sun_position`, `u_E_sun`) | Unknown: see probe 1 |
| `exposure_fusion.xsa` | Exposure and tone map | `u_master_exposure`, `u_shadow_gain`, color grading (ASC CDL slope, offset, power) | None |

A plugin cannot send any value to a shader. A patched shader can use only the data that X-Plane already gives it.

## 2. Routes

| # | Route | How it works | Result quality | Status |
|---|---|---|---|---|
| A | **Plugin dome** (MoonSky step 3) | Glowing dome object around the camera | Works. Calibrated: x158 at 25 % cover. The dome also hides 25 % of the star light | Code ready, not built |
| B | **Sky shader with the X-Plane "main light"** | Patch `dome.xsa`: add the Krisciunas-Schaefer glow per pixel, with `u_sun_position` as the moon direction | Best: real sky light, stars stay on top, glow behind terrain and clouds, no plugin | Possible only if X-Plane puts the moon in `u_sun_position` at night. **Probe 1 answers this** |
| C | **Moon shader, widened** | Patch `astronomical.xsa` stages 0 and 1: the moon mesh becomes a sky-size disk with the glow | Good: real added light, exact moon. Glow ends at the disk edge (30 to 90 deg) | Possible only if X-Plane draws the moon when it is off screen, and stars stay visible. **Probe 2 answers this** |
| D | **Star shader haze** | Our airglow haze sprites (2.5 deg grid, already in the generator) carry the glow | Good, if the star shader gets the moon direction | Same condition as B (probe 1) |
| E | **Plugin, own 3D drawing** | Plugin draws a full-sky glow with its own OpenGL shader (`xplm_Phase_Modern3D`, through the Vulkan bridge) | Real added light, no star cover. Risk: draw order, depth and exposure scale | Not tried. Fallback if B, C and D fail and the 25 % cover is not good enough |
| F | **Moon position computed in the shader** | Compute the moon position from date and time | — | Not possible: no shader gets the date or the observer position. `u_time` is probably sim seconds (inferred) |
| G | **Exposure or color grading** (datarefs or private art controls) | Raise exposure, or add a grey offset, at full moon | Bad: exposure does not change contrast, so M33 stays visible. An offset covers the cockpit and terrain too | Rejected for the glow |
| H | **Private art controls for the sky** | Change Rayleigh or Mie scattering, sun irradiance or similar | These change the sun sky. At night the sun is below the horizon, so the glow goes to the wrong place | Need the list to be sure. See section 4 |

## 3. Probe (one sim session)

[test-probe-moon/](test-probe-moon/): `moon-probe.zip` and `PROBE_README.txt`. It holds 2 test shaders with the same interface as the original files (checked).

- Probe 1, `dome.xsa`: rings around each light direction that the sky shader gets (red and green = `u_sun_position`, blue and yellow = true sun), and a bar for `u_E_sun` (log scale, 0.001 to 100000).
- Probe 2, `astronomical.xsa`: the moon becomes a 30 deg disk with 8 rings (dim inside, bright outside). The disk shows if X-Plane draws the moon off screen, and if stars stay visible.

Decision after the probe:

1. If red or green is on the moon at night: route B (sky shader). It replaces the plugin dome.
2. If not, but the disk stays when the moon is off screen and stars stay visible: route C.
3. If neither: route A (plugin), or route E if the 25 % star cover is a problem.

## 4. Private datarefs (art controls)

The private datarefs (`sim/private/...`) are not in `DataRefs.txt`. The list is in `X-Plane.exe`. This PowerShell command writes the list to a text file on the desktop:

```powershell
$exe = "C:\X-Plane 12\X-Plane.exe"
$text = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($exe))
[regex]::Matches($text, 'sim/private/[A-Za-z0-9_/.\-]+') | ForEach-Object { $_.Value } | Sort-Object -Unique | Set-Content "$env:USERPROFILE\Desktop\xp12_private.txt"
(Get-Content "$env:USERPROFILE\Desktop\xp12_private.txt").Count
```

The command only reads `X-Plane.exe`. The last line shows the number of names. Upload `xp12_private.txt`. Claude then looks for moon, sky, night, exposure and tone map controls.

## 5. Probe results (2026-10-10)

- Probe 1, sky shader: `u_sun_position` is the true sun in eye space (red ring on the sun). `u_E_sun` is below 0.001 at night. Routes B and D are closed.
- Probe 1, moon shader: the widened moon draws, and stars stay visible on top of it. All 8 brightness rings show when zoomed in.
- X-Plane draws the moon with vertex stage 0 or vertex stage 2 (stage 2 = stage 0 plus point size). Probe 1 changed only stage 0, so at normal zoom the moon stayed normal size. The probe 1 ring math also used the widened direction, so the rings were squeezed.
- Probe 2: [test-probe-moon2/](test-probe-moon2/) (`moon-probe2.zip`, `PROBE2_README.txt`). It changes stages 0, 1 and 2. The moon mesh covers the whole sky, with circles every 30 deg from the moon and a horizon line. Open: off-screen cull, mapping, draw order over terrain and clouds.
- Probe 2 result (Gus 17:36): nothing drawn. Cause: X-Plane does not fill `modelview_inverse` in the stage 2 draw.
- Probe 2.1: [test-probe-moon21/](test-probe-moon21/). Result (Gus): route C works.
  - X-Plane draws the visible moon with stage 2, at normal zoom and zoomed in.
  - `modelview_inverse` is empty for that draw. The shader uses `inverse(modelview_matrix)`.
  - No cull: the moon draw runs when the moon is off screen.
  - The horizon line and the 30 deg circle are correct, so the direction mapping is correct.
  - Terrain, the aircraft, the cockpit and clouds are in front of the moon pass.
  - The glow stopped at 90 deg from the moon. Inferred: the moon mesh is a hemisphere that faces the camera.
- Private moon datarefs (DataRefTool, 16 moon names): `debug/show_moon` 0, `lighting/E_moon_lx` 0.6, `moon/angular_diameter` 0.52, `moon/nits` 785, `perf/kill_moon` 0.
  - `moon/nits` scales `u_light_diffuse`: nits x10 = tint x10. This is the live glow knob.
  - `E_moon_lx` changes the clouds only (x10 = clouds brighter, near white). No change in the moon shader.
  - With the probe tint at nits 7850, terrain and cockpit looked green. Inferred: the moon pass also feeds scene light (sky light).
- Moon files: `Resources\bitmaps\world\moon.dds` 699192 bytes = 1024 x 1024 BC1 with 11 mips + 128-byte header (exact size match; inferred). Square, so a disk photo with a planar UV map is likely. Also `moon_NML.png`, `moon_NML.ktx2` (normal map).
- Dome shader: the sky output is sky texture x `u_exposure_scale.y`. The stock moon fragment writes the sky texture without that scale. If the scale is not 1, a moon pass over the whole sky changes the sky. Probe 2.2 day check answers this.
- Probe 2.2: [test-probe-moon22/](test-probe-moon22/) (`moon-probe22.zip`, `PROBE22_README.txt`, sources in `src/`).
  - Sky angle = 2 x normal angle (cap 180 deg): the hemisphere covers the whole sky. CPU model: no holes, no winding flips.
  - Glow: Krisciunas & Schaefer 1991 (k = 0.2), x luminance of `u_light_diffuse`, gain 6e-5 at rho 45 / elevation 45 / moon 45 / full. Mild blue. Off when the sun is up.
  - Moon disk: UV from the mesh UV map, extrapolated with a 2x2 Jacobian of UV vs disk coordinate. Stock lighting and stock normal-map math. WebGL test vs the stock draw: 2 % mean difference. UV is sent as UV - 0.5 for precise derivatives.
  - Day check: sun up = pixels more than 90 deg from the moon are discarded. A visible arc = exposure scale is not 1.
  - Calibration: Moab 2026-12-24 04:00 UTC (full moon 45 deg east, M33 72 deg). Gus changes `moon/nits` until M33 is just not visible.
- Probe 2.2 result (Gus 18:51): moon disk correct (planar UV confirmed). Glow brighter near the moon and the horizon, no seam. Scene gets whitish light from the glow (the moon pass feeds scene light). Sky looks best at nits 3850; terrain light looks right at nits 7850. M33 test not possible (sky washed out). E_moon_lx 1.2 = good clouds. Day: no sharp step in the screenshots (high-pass check), so the sky exposure scale is 1 (inferred). The dark day-sky area Gus saw is the stock sky (darkest about 90 deg from the sun). 8-bit rings around the moon in a dark sky.
- Probe 2.3: [test-probe-moon23/](test-probe-moon23/). Glow gain x 3850/785 (nits back to 785). Light pass (inferred = cube face, square 90 deg projection) x 7850/3850. Triangle dither 5 %. Glow fades in from sun 0 to -6 deg; sun up = moon disk only. `moon-probe23-passcolor.zip` colors the glow by pass flags (cube face, layered, multi transform) if the terrain is still too dark.
- Probe 2.3 result (Gus 19:32): terrain = 7850 look (light-pass gain works); rings gone; sunset fade smooth; PHSF 18:25 sunset + sky light "perfect". Sky still too washed out. Passcolor: sky white (main pass), terrain/cockpit blue-white = cube-face pass CONFIRMED as scene light source. Water reflections pitch black (open: also black with the stock moon?). Thin lines/black strip near the horizon in the debug shots (water area).
- Probe 2.4: [test-probe-moon24/](test-probe-moon24/). Sky glow 50 / 35 / 25 % of the 3850 look; light-pass gain raised so terrain stays at the 7850 look (env x4.08 / x5.83 / x8.16). Waits Gus pick + water check.
- Probe 2.4 result (Gus 19:51): sky25 PICKED. E_moon_lx 2.4. Night far haze / water too dark until the twilight "change"; correct after it (engine haze = sun only, inferred).

## 6. Final build (2026-10-10 20:05)

- Generator: `make_shaders.py` now builds the moon stages 0, 1, 2 too (`shader_src/moon_vertex.glsl`, `moon_fragment.glsl`). Settings `MOON`, `MOON_SKY` 0.25, `MOON_LIGHT` 1.0, `MOON_RGB`, `MOON_K_EXT`, `MOON_DIAMETER`, `MOON_DITHER`. `--set MOON=0` = stars only (byte-identical to v75).
- Check: stages 3-8 byte-identical to v75; stages 0, 2 decompile identical to probe sky25; stage 1 same math (names differ).
- Release: `release/NightSky_XP12.zip` = stars v75 + moon sky25 + no-airglow dat. Old: `release/NightSky_XP12_v75_starsonly.zip`.
- `make_bundle.py --plugin <dist/NightSky>` adds the plugin to the zip (README text follows).
- Plugin: `nightsky-plugin/` (NightSky.xpl, replaces MoonSky dome). Sets `lighting/E_moon_lx` 2.4 at start + after aircraft/airport/scenery load; restores X-Plane value on disable; menu values 0.6/1.2/2.4/3.6/4.8; NightSky.prf. Compile check with stub headers only (SDK download blocked here). Gus builds with the MoonSky CMake steps.

## 7. Night haze search (open)

- Gus lists (20:00): `fog`, `atmo`, `scattering`, `skyc`. No moon term for haze.
- `stats/skyc/mon_amb_rgb`, `mon_dir_rgb` = engine moon light (read only; r 0, g 0.00057, b 0.0014 at test). `sun_amb`, `sun_dir` = sun light.
- `volumetric/fog/*` = near fog only (max_distance_km 1).
- Hypothesis: black far band = extinction with no in-scatter at night. Lever = less extinction at night (plugin).
- Tests asked: `scattering/override_visibility_m` 0 -> 100000; `scattering/override_turbidity_t` 2.141 -> 1.2; `scattering/fog_mix` 1 -> 0; watch sun_amb / mon_amb at the change.

## 8. Stars gone with the moon release (Gus 20:22)

- Gus: release zip (stars v75 + moon sky25) shows only the moon + glow. No stars.
- Cause (inferred): moon pass now covers the whole sky and writes alpha 1 = replaces the stars drawn before it (stock moon replaced only its disk).
- `release/NightSky_XP12.zip` set back to v75 stars-only. Moon build kept as `release/NightSky_XP12_moon_nostars.zip`.
- Probe 2.5 (`test-probe-moon25/`): output vec4(mix(glow, col, mask), mask). Premultiplied blend -> glow adds over stars. No blend -> black sky + glow. Alpha blend -> stars, no glow.
- Probe 2.5 result (Gus 20:33): stars + glow + normal sky. CONFIRMED: moon draw blend = premultiplied (ONE, ONE_MINUS_SRC_ALPHA).
- Fix in generator `moon_fragment.glsl` (alpha = disk mask). `release/NightSky_XP12.zip` rebuilt: shader byte-identical to probe 2.5. `_moon_nostars` zip removed.

## 9. Plugin GUI and haze lock (2026-10-10 21:20)

- NightSky plugin 1.1: Dear ImGui settings window (native SDK 4.4 renderer, OpenGL fallback). Source: `nightsky-plugin/`, zip `nightsky-plugin.zip`.
- Sky darkness slider: level 1..9 = Bortle 9..1, `gain_photometric` = 20 x 10^(0.2 (L - 5)). Live.
- Gus test: `gain_photometric` also changes the Milky Way. Inference (not checked): `u_light_emissive` = gain_photometric.
- Shader gen2 (staging `generator-v76/`, not yet in `generator/`): gains = SPIR-V spec constants STAR 200, MW 201, NEBULA 202, GALAXY 203, HAZE_EMISSIVE 204. Stages 6, 8 stored. Haze uses HAZE_EMISSIVE (20) in place of u_light_emissive.
- Test: `test-v76-hazelock/` (waits on Gus: same look at gain 20, Milky Way fixed at 5 and 80, dusk).
- 21:57 Gus: native ImGui GUI renders (SDK 4.4 real headers). Private datarefs "not found" at XPluginEnable (log), DataRefTool shows them later -> plugin now retries every 2 s (inferred late registration). Horizon dashes gone after MoonSky dome removal; black far band remains (stock night haze, sun only). Haze sliders to test.
- 22:26 Gus: retry did not help (private datarefs still not found). 1.1.1: fallback lookup via XPLMCountDataRefs/XPLMGetDataRefsByIndex/XPLMGetDataRefInfo (as DataRefTool). Log line 'dataref list: N datarefs, M under sim/private/'.
- 23:54 Gus log 1.1.1: at enable 6032 datarefs, only 24 under sim/private -> late registration CONFIRMED. Restore lines at disable prove E_moon_lx + gain_photometric were found and written.
- 23:55 Gus: v76 Milky Way too faint (at darkness 8 the stars got x4, MW not). DECISION: haze follows gain_photometric. v77 = HAZE_EMISSIVE 0 (test-v77-mwfollow/). Plugin 1.1.1 read/write OK (Gus).
- 2026-10-11 02:05: Gus v1 scope = astronomical.xsa + earth_astro.dat + plugin with cloud moonlight (steps 0.6/1.2/2.4/4.8) + star light (Bortle) only. Plugin 1.2.0: NIGHTSKY_DEV option (default OFF) hides gains/haze/moon info. Moon crescent 'weird' -> v78 MOON_LS=1 Lommel-Seeliger disk (test-v78-moonphase/).
- 2026-10-11 02:25: Gus liked v78 moon phase. RELEASED release/NightSky_XP12_v1.zip (v78 xsa + release dat + Gus MSVC plugin 1.2.0 + README). generator-v76 merged into generator/ (old in generator-pre-v1/); rebuilds v1 xsa bit-for-bit.
