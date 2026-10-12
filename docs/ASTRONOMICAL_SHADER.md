> **Research notes.** Written at the start of the NightSky work (2026-10-09), before Urania. They describe the structure of the X-Plane 12 astronomical shader (no X-Plane code). The decoded source folder `astronomical_msl/` mentioned below is not in this repository: it is X-Plane code. The encoding that Urania uses is in `NIGHT_SKY_ENCODING.md`.

# X-Plane 12 astronomical shader analysis

Source: `Resources\shaders\bin\msl\astronomical.xsa` and `...\spv\astronomical.xsa`, uploaded by Gus on 2026-10-09.
Decoded Metal source: [astronomical_msl/](astronomical_msl/).

## File format

| File | Content |
|---|---|
| `bin\*_mapping.xsv` | Binding map. Magic `XSV6`, resource names, slot numbers. No code. |
| `bin\msl\*.xsa` | Standard ZIP (deflate). Holds `name_N.msl`, readable Metal source. |
| `bin\spv\*.xsa` | Standard ZIP (deflate). Holds `name_N.spv`, SPIR-V 1.6 from glslang. Debug names are kept. |

On Windows with Vulkan, X-Plane uses the `spv` set. The `msl` set is for Mac. The two sets hold the same shaders (same names, same structure).

Because the SPIR-V keeps names, SPIRV-Cross can turn it back into GLSL. glslang can compile the edited GLSL back to SPIR-V.

## The 9 shader stages

| # | Stage | Job (inferred from code) |
|---|---|---|
| 0 | vertex | Lit sphere (moon). Position, normal, UV. |
| 1 | fragment | Moon: `u_tex0` × `u_light_diffuse`, normal map, Lambert / π, plus sky in front. |
| 2 | vertex | Same as 0, plus `gl_PointSize = u_imm_a_point_size.x`. |
| 3 | vertex | Disc or billboard. UV = radial distance `length(a_vertex.xy)`. |
| 4 | fragment | Disc: radial texture `u_tex0` × `u_light_diffuse` × atmosphere transmittance, plus sky. Probably sun or planet glow. |
| 5 | vertex | Same as 3, plus point size from a uniform. Probably planets drawn as points. |
| 6 | vertex | **Stars.** `a_vertex.xyz` = direction, `a_vertex.w` = **magnitude**. |
| 7 | fragment | **Stars.** `out = float4(L, L, L, 0)`. Grey only. |
| 8 | vertex | Same as 6, plus point size from a uniform. |

## Star math (stages 6 and 8)

```
L = 2.128e-6 * exp(-0.921034 * mag) * u_light_emissive * u_exposure_scale.y
L *= skydome.w      // sky transmittance / visibility
```

- `exp(-0.921034 * m)` = `10^(-0.4 m)` = Pogson law. `2.128e-6` is about the illuminance of a mag 0 star, in lux.
- Color: hard-coded grey `(L, L, L)`. **No color input.**
- Size: `gl_PointSize = u_imm_a_point_size.x`. **One size for all stars** in a draw.

## Planet and moon color

Stages 1 and 4 multiply by `u_light_diffuse` (float3). The engine sets this uniform per draw. So the engine can give one RGB per body. We do not know which values it sends. The values may be plain white.

## What a shader patch can do

The vertex input `a_vertex.w` carries the magnitude, read from `earth_astro.dat`. A patch can hide extra data in that number:

1. Round each magnitude to 0.01.
2. Add a color code `k × 0.0001` (k = 0…99, a B‑V bucket). Float precision is enough for mag < 10.
3. Patched stage 8 decodes `k`, keeps the true magnitude, and sends a color to the fragment stage.
4. Patched stage 8 sets `gl_PointSize` from the magnitude, so bright stars get bigger.
5. Patched stage 7 outputs `L × color`, and can use `gl_PointCoord` for a soft round glow.

Milky Way: there is no texture slot for it. One option: add thousands of "haze" entries in `earth_astro.dat` along the galactic band. Give them a reserved code `k` so the patch draws them big, faint and soft.

## Risks

- Every X-Plane update can replace `spv\astronomical.xsa`.
- Unknown: whether X-Plane checks a hash or signature of `.xsa` files, or caches compiled pipelines.
- Unknown: whether the engine drops faint stars on the CPU before the draw. The patch keeps magnitudes valid, so this is not a problem.
- The CPU side can change the vertex layout in any update.
- Laminar does not support shader edits. Do not distribute a patch as a product.
