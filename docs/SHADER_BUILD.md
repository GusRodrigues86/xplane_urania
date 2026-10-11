# Night sky shader for X-Plane 12: build guide

`make_shaders.py` builds the night sky shader file `astronomical.xsa`.
The shader decodes the data that `make_night_sky.py` writes into `earth_astro.dat`.
Use the 2 files together. The data encoding is in [NIGHT_SKY_ENCODING.md](NIGHT_SKY_ENCODING.md).

Contents:

1. Files
2. Install the tools
3. Build the shader
4. Install the shader in X-Plane
5. Settings
6. How the script builds the shader
7. What the mod changes
8. Change the mod code
9. Check the build
10. Error messages
11. Reproducibility
12. License

---

## 1. Files

| File | Content |
|---|---|
| `make_shaders.py` | Build script. Python standard library only. |
| `make_bundle.py` | Puts the shader and the data file into one zip file for other users (section 4.1). |
| `check_setup.py` | Checks that the tools are installed (SETUP.md). |
| `SETUP.md` | Install and check steps for Windows, Linux and macOS. |
| `shader_src/sky_vertex.glsl` | Mod code for the vertex stages 6 and 8. |
| `shader_src/sky_fragment.glsl` | Mod code for the fragment stage 7. |
| `reference_build_report.txt` | Report of the reference build (default settings). |

Glossary:

- **stage**: one GPU program in the `.xsa` file. The file has 9 stages, `astronomical_0.spv` to `astronomical_8.spv`.
- **.xsa**: a ZIP file. X-Plane reads the stages from this ZIP file.
- **SPIR-V**: the binary GPU program format of Vulkan (`.spv`).
- **GLSL**: the text language of the mod code. The compiler changes GLSL into SPIR-V.
- **stock**: the original X-Plane code or file, without the mod.

---

## 2. Install the tools

You need Python and 3 tools from the Vulkan SDK. The script needs no extra Python packages.

The install and check steps for Windows (PowerShell), Linux and macOS are in [SETUP.md](SETUP.md).
To check all tools with one command, run `check_setup.py` (SETUP.md, section 5).

The script uses these 3 tools:

| Tool | Function |
|---|---|
| `glslangValidator` | Compiles GLSL to SPIR-V. |
| `spirv-val` | Checks each compiled stage. |
| `spirv-cross` | Decompiles the stock stages to GLSL. |

The script looks for the tools in this order:

1. The folder that you give with `--tools`.
2. `%VULKAN_SDK%\Bin` (Windows) or `$VULKAN_SDK/bin` (Linux, macOS).
3. The folders on `PATH`.

---

## 3. Build the shader

The script needs the ORIGINAL X-Plane file. A modded file does not work.

The commands in this section use Windows paths. For the Linux and macOS commands, see SETUP.md, section 7.

1. Find your original `astronomical.xsa`. Use the backup copy from your first mod install.
2. If you have no backup copy, run the X-Plane installer. Select "Update X-Plane". The installer finds modified files and can restore them.
3. Copy `C:\X-Plane 12\Resources\shaders\bin\spv\astronomical.xsa` to the generator folder.
4. Rename the copy to `astronomical_original.xsa`.
5. Open a command window in the generator folder.
6. Type this command:

```
python make_shaders.py --xsa astronomical_original.xsa --out out
```

The script writes these files:

| File | Content |
|---|---|
| `out\astronomical.xsa` | The new shader file. |
| `out\glsl\astronomical_6.vert` | Full GLSL of stage 6, as compiled. |
| `out\glsl\astronomical_7.frag` | Full GLSL of stage 7, as compiled. |
| `out\glsl\astronomical_8.vert` | Full GLSL of stage 8, as compiled. |
| `out\build_report.txt` | Settings, tool versions and SHA-256 values. |

The `out\glsl` files contain stock X-Plane declarations. Do not publish them (see section 12).

Other commands:

```
python make_shaders.py --xsa astronomical_original.xsa --out out_neb15 --set DSO_GAIN=15
python make_shaders.py --xsa astronomical_original.xsa --out out_1440 --set VIEWPORT_H=1440
python make_shaders.py --xsa astronomical_original.xsa --out out_red --set HAZE_RGB_1=2.0,0.6,1.0
python make_shaders.py --xsa astronomical_original.xsa --out stock --decompile
python make_shaders.py --xsa astronomical_original.xsa --out out --tools "C:\VulkanSDK\1.4.321.1\Bin"
```

- Repeat `--set` to change more than one setting.
- A color setting needs 3 numbers with commas and no spaces.
- `--decompile` writes the stock GLSL of all 9 stages. Use it to study X-Plane. It builds no shader.
- The SDK folder name in the `--tools` example is an example. Use your SDK version.

---

## 4. Install the shader in X-Plane

**WARNING: This step overwrites the X-Plane file `astronomical.xsa`. Keep a backup copy of the original file. Without the original file, you cannot build the shader again.**

1. Close X-Plane.
2. Make sure that `astronomical_original.xsa` is in a safe folder.
3. Copy `out\astronomical.xsa` to `C:\X-Plane 12\Resources\shaders\bin\spv\`.
4. Replace the file in that folder.
5. Copy the matching `earth_astro.dat` to `C:\X-Plane 12\Resources\default data\`.
6. Start X-Plane.

To remove the mod, copy the original files back to the same folders.

An X-Plane update can replace `astronomical.xsa`. After an update, do these steps:

1. Copy the new X-Plane file as the new `astronomical_original.xsa`.
2. Build the shader again.
3. Install the new `out\astronomical.xsa`.

### 4.1 Share the mod as one zip file

`make_bundle.py` puts the shader and the data file into one zip file. The zip file has the X-Plane folder layout. Other users extract it into their X-Plane 12 folder.

```
python make_bundle.py --xsa out\astronomical.xsa --dat out\earth_astro.dat --out NightSky_XP12.zip
```

The zip file contains:

| Path in the zip | Content |
|---|---|
| `Resources/shaders/bin/spv/astronomical.xsa` | The shader from `make_shaders.py`. |
| `Resources/default data/earth_astro.dat` | The data file from `make_night_sky.py`. |
| `NightSky_README.txt` | Backup, install and remove steps, settings, credits and licenses. |

- For the airglow version, use `--dat out\earth_astro_airglow.dat`. The script writes it into the zip as `earth_astro.dat`.
- The script reads `build_report.txt` next to the `.xsa` file. It writes the settings into the README.
- The script refuses an original X-Plane `.xsa` or `.dat` file.
- 2 runs with the same input files give the same zip file.

**The shader is correct only for one screen height (`VIEWPORT_H`).** The README tells the user the screen height of the build. For a user with a different screen height, build the shader with `--set VIEWPORT_H=<height>` and make a new zip file.

The zip file contains X-Plane code (section 12). Share it privately only.

---

## 5. Settings

The defaults are the tested version "stars35" (2026-10-10).

| Setting | Default | Stage | Function |
|---|---|---|---|
| `STAR_GAIN` | 0.35 | vertex | Star brightness. 1.0 = physical. |
| `SAT` | 1.3 | vertex | Star color strength. 1.0 = physical. 0 = grey. |
| `SIZE_BASE` | 7.0 | vertex | Star sprite size in pixels at magnitude 0. |
| `SIZE_PER_MAG` | 1.2 | vertex | Pixels less for each magnitude. |
| `SIZE_MIN` | 1.5 | vertex | Smallest star sprite in pixels. |
| `SIZE_MAX` | 12.0 | vertex | Largest star sprite in pixels. |
| `MW_GAIN` | 3.0 | vertex | Milky Way and airglow brightness (color class 0). |
| `DSO_GAIN` | 40.0 | vertex | Nebula, galaxy and cluster brightness (color classes 1 to 3). |
| `HAZE_SAT` | 1.2 | vertex | Haze color strength. 1.0 = table colors. |
| `HAZE_RGB_0` | 1.1039, 0.9856, 0.8378 | vertex | Class 0 color: Milky Way, warm white. |
| `HAZE_RGB_1` | 2.3758, 0.5940, 0.9719 | vertex | Class 1 color: H-alpha emission, red-pink. |
| `HAZE_RGB_2` | 0.6000, 1.1500, 1.3000 | vertex | Class 2 color: nebula core, reflection, planetary. Teal. |
| `HAZE_RGB_3` | 1.2003, 0.9917, 0.6560 | vertex | Class 3 color: galaxy, globular cluster. Warm yellow. |
| `VIEWPORT_H` | 1080 | vertex | Screen height in pixels. Set this to your screen height. |
| `MAX_SPRITE` | 1024 | vertex | Largest haze sprite in pixels. |
| `EDGE_STRETCH` | 1.0 | vertex | 1 = haze sprites grow toward the screen edges. 0 = off. |
| `CLAMP_NDC` | 0.98 | vertex | Haze sprite centers stay inside this part of the view. |
| `DITHER` | 0.14 | fragment | Haze noise against color bands. 0 = off. |

Notes:

- The haze colors have a luminance of about 1. Thus, a color change does not change the brightness.
- `VIEWPORT_H` changes the haze sprite size. A wrong value makes haze blobs too large or too small.
- The star color table `STAR_RGB` is not a setting. The script computes it (section 6).

---

## 6. How the script builds the shader

The script builds each vertex stage from 3 parts:

1. **Stock declarations.** The script decompiles stock stages 6 and 8 with `spirv-cross`. It keeps the uniform blocks, the samplers and the `a_vertex` input. It removes the outputs and the stock `main` function.
2. **Settings and star colors.** The script writes the settings as GLSL constants. It writes the `STAR_RGB` table.
3. **Mod code.** The script adds `shader_src/sky_vertex.glsl`.

The fragment stage 7 needs no stock declarations. The script adds the settings to `shader_src/sky_fragment.glsl`.

Then the script does these steps:

1. Compile each stage with `glslangValidator -V --target-env vulkan1.3`.
2. Check each stage with `spirv-val`.
3. Write a new ZIP file. Stages 0 to 5 stay the same. Stages 6, 7 and 8 are new.
4. Write `build_report.txt`.

The new ZIP keeps the stock entry names, dates and compression. Thus, 2 builds with the same input give the same file.

**Why the script reads the stock code at build time:** this repository contains only mod code. It contains no X-Plane code. Each user reads the stock part from their own X-Plane copy.

The mod code uses 3 short names for the stock uniform blocks. The script writes them as `#define` lines:

| Short name | Stock block | Fields that the mod uses |
|---|---|---|
| `XFORM` | `u_transform_block_fat` | `u_viewport_count`, `u_layer_count`, `u_layer_offset`, `u_transform_count`, `u_mv_offset`, `mvp_matrix[]`, `projection_matrix[]` |
| `ASTRO` | `u_astronomical_data` | `u_light_emissive` |
| `ENV` | `u_environment_data` | `u_exposure_scale` |

### 6.1 Star color table

The script computes 90 colors. Index k is the star color code from `earth_astro.dat`.

- k = 0: white, `vec3(1, 1, 1)`.
- k = 1 to 89: B−V = −0.40 to 2.00, in equal steps. This range must agree with `make_night_sky.py`.

For each k, the script does these steps:

1. Convert B−V to a temperature (Ballesteros 2012): `T = 4600 × (1 / (0.92 BV + 1.7) + 1 / (0.92 BV + 0.62))`.
2. Compute the black-body spectrum (Planck law) from 380 nm to 780 nm, in 5 nm steps.
3. Multiply the spectrum by the CIE 1931 color matching functions (Wyman 2013 fit). The sum is XYZ.
4. Convert XYZ to linear sRGB (D65 matrix). Set negative values to 0.
5. Divide by the luminance `0.2126 R + 0.7152 G + 0.0722 B`. Each color then has luminance 1.

Luminance 1 means that the color does not change the star brightness. Only the magnitude sets the brightness.

---

## 7. What the mod changes

Stage roles in `astronomical.xsa` (stages 3 to 5 and stage 6 use are inferred, not documented):

| Stage | Type | Role | Mod |
|---|---|---|---|
| 0, 1, 2 | vertex, fragment | Moon | No change |
| 3, 4, 5 | vertex, fragment | Sun and planet discs | No change |
| 6 | vertex | Stars, non-point path | Replaced |
| 7 | fragment | Stars | Replaced |
| 8 | vertex | Stars, point sprite path | Replaced |

The stock star stages draw each row of `earth_astro.dat` as one white dot. The dot size is fixed. The brightness comes from the magnitude. The stock code also multiplies the brightness by the sky texture transparency (`u_tex_skydome.w`).

The mod makes these changes:

1. **Decode.** The mod reads the code digits in the magnitude field (NIGHT_SKY_ENCODING.md, section 3.4). Each row becomes a star or a haze blob.
2. **Star color.** The mod reads the color from `STAR_RGB[k]`. `SAT` makes the color stronger.
3. **Star size.** The sprite size is `SIZE_BASE − SIZE_PER_MAG × magnitude`, between `SIZE_MIN` and `SIZE_MAX`.
4. **Star brightness.** The mod multiplies the stock brightness by `STAR_GAIN`.
5. **Haze blob.** The mod draws a large soft sprite with the profile `exp(−4.5 r²)`. The total light of the blob equals the light of its magnitude (NIGHT_SKY_ENCODING.md, section 8).
6. **Wide view.** A flat projection stretches the sky toward the screen edges by `1 + tan²`. The mod grows each haze sprite by the same factor (`EDGE_STRETCH`).
7. **Blob center.** The GPU drops a point sprite if its center is outside the view. The mod moves the center inside the view (`CLAMP_NDC`). The fragment stage gets the true center shift in `v_haze`.
8. **Cull.** The mod does not draw a blob that is fully outside the view or behind the camera. Without the cull, the GPU frame time was about 10 times larger in a test.
9. **No sky texture.** The mod does not multiply by `u_tex_skydome.w`. That texture has a dark band at the screen center (the "dark lane").
10. **Fragment profile.** A small star is a flat dot. A star larger than 1.5 px gets a soft glow `exp(−4 r²)`. A haze blob gets the Gaussian profile and a small noise (`DITHER`).

Vertex outputs (the fragment stage reads them):

| Location | Name | Content |
|---|---|---|
| 0 | `v_L` | Brightness |
| 1 | `v_col` | Color |
| 2 | `v_size` | Sprite size in pixels |
| 3 | `v_kind` | 0 = star, 1 = haze blob |
| 4 | `v_haze` | Haze: sprite size ratio, true center shift (x, y) |
| 6 | `v_eye` | View index (stock output) |

---

## 8. Change the mod code

1. Edit `shader_src/sky_vertex.glsl` or `shader_src/sky_fragment.glsl`.
2. Run the build again.
3. Read the error text if the compiler stops. The line numbers refer to the files in `out\glsl`.

Rules:

- Stages 6 and 8 use the same file `sky_vertex.glsl`.
- The vertex outputs must agree with the fragment inputs (same location, same type).
- Keep the markers `// @SETTINGS@` and `// @STAR_RGB@`. The script replaces them.
- To add a setting, add a line to `SETTINGS` in `make_shaders.py`. Use stage `"v"` or `"f"`.

---

## 9. Check the build

The script checks each stage with `spirv-val`. A stage with an error stops the build.

To check a build against the reference, compare `out\build_report.txt` with `reference_build_report.txt`:

- **Input SHA-256** is the same if your original file is the same X-Plane version.
- **Stage and output SHA-256** are the same only with the same `glslangValidator` version (section 11).
- **Settings** must be the same for the same visual result.

### 9.1 How we checked this script against "stars35"

"stars35" is the test shader that Gus approved on 2026-10-10. Its source contained old test code: own extinction, a sky texture search and an edge fade. The final "stars35" settings turned that code off. This script does not contain the old code. Thus, the SPIR-V bytes are different.

We did these checks:

1. Stages 0 to 5 are byte-identical to "stars35".
2. The shader interface (inputs, outputs, uniform blocks, textures) of stages 6, 7 and 8 is the same (`spirv-cross --reflect`).
3. The `STAR_RGB` table text is identical.
4. We optimized both versions with `spirv-opt -O` and decompiled them again.
   - Stage 7: identical.
   - Stages 6 and 8: the same math. There are 2 differences. One output starts its value at a different line. "stars35" also has a test (`k ≤ 89`) that is always true in that branch.
5. 2 builds with the same input give a byte-identical `astronomical.xsa`.

Do one check in X-Plane: the new build must look the same as "stars35".

---

## 10. Error messages

| Message | Cause | Remedy |
|---|---|---|
| `ERROR: spirv-cross not found. Install the Vulkan SDK, or give its Bin folder with --tools.` | The script cannot find the tool. | Install the Vulkan SDK. Open a new command window. Or use `--tools`. |
| `ERROR: this astronomical.xsa is already patched. Use the ORIGINAL X-Plane file.` | The input is a modded file. | Use the original X-Plane file (section 3). |
| `ERROR: expected astronomical_0.spv ... astronomical_8.spv, found [...]` | The input is not the astronomical shader, or it is the Metal (`msl`) file. | Use the file from the `spv` folder. |
| `ERROR: the stock stage does not have all of these uniform blocks: [...]` | An X-Plane update changed the stock shader. | The mod code needs an update for the new X-Plane version. |
| `ERROR: the stock stage has no a_vertex input. This is not the expected X-Plane file.` | Same as above. | Same as above. |
| `ERROR in: glslangValidator ...` | The GLSL has an error. | Read the error text. Correct the mod code (section 8). |
| `ERROR: unknown setting NAME. Settings: ...` | A `--set` name has a typing error. | Use a name from section 5. |
| `ERROR: NAME needs 3 numbers` | A color setting has the wrong number of values. | Give 3 numbers: `--set HAZE_RGB_1=2.0,0.6,1.0`. |

---

## 11. Reproducibility

- The same input file, the same settings and the same `glslangValidator` version give a byte-identical `astronomical.xsa`.
- A different `glslangValidator` version can give different SPIR-V bytes. The visual result stays the same.
- `build_report.txt` records the tool versions. Keep it with each build.

Reference build (`reference_build_report.txt`):

| Item | Value |
|---|---|
| Input `astronomical.xsa` (stock, Gus X-Plane 12 copy) | `246e6ab98b562cefc52659ccf192079e6ca1dd30b539f14e6610f6a785025ec0` |
| glslangValidator | 15.1.0 |
| spirv-val | SPIRV-Tools v2025.1 |
| Settings | Defaults (section 5) |

---

## 12. License

- This repository contains only mod code. The script reads the stock code from your own X-Plane copy.
- `astronomical.xsa` from a build contains X-Plane stages 0 to 5 without change. Stages 6 and 8 contain stock declarations.
- The files in `out\glsl` and the `--decompile` output contain X-Plane code. Do not publish them.
- To share the generator, share the generator folder without the `out` folder. Each user builds the shader from their own X-Plane copy.
- A zip file from `make_bundle.py` contains X-Plane code. Share it privately only. Do not upload it to public sites.
