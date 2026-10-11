# Licenses

| Part | License |
|---|---|
| Urania code: `src/`, `plugin/src/`, `scripts/`, `tests/`, shader mod code `src/urania/engine/shader_src/` | MIT, see [LICENSE](LICENSE) |
| Urania documentation: `docs/`, `README.md` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

You can use, copy, change and share Urania freely, also commercially. Keep the copyright notices.

## Third-party parts (they keep their own licenses)

No third-party code is in the Urania repository. The builder puts each part in its folder
(see `plugin/SDK/PUT_THE_SDK_HERE.txt` and `plugin/third_party/imgui/PUT_IMGUI_HERE.txt`).
Only the license texts that must go with the distributed files are in `src/urania/licenses/`.

| Part | Where | License |
|---|---|---|
| Dear ImGui 1.92.9b | `plugin/third_party/imgui` (builder supplies it), inside `Urania.xpl` | MIT |
| d3-celestial star catalog `stars.8.json` (B-V colors) | input file, supplied by the user | BSD-3-Clause |
| NASA SVS 4851 "Deep Star Maps 2020" | input file, supplied by the user | NASA media: no copyright, credit requested |
| glslang, SPIRV-Tools, SPIRV-Headers, SPIRV-Cross | bundled tools (`vendor/tools`) | Apache-2.0 (SPIRV-Headers: MIT-style) |
| X-Plane SDK headers and `XPLM_64.lib` | build time only, not distributed | X-Plane SDK license (MIT-style) |
| Python, numpy, OpenEXR, Tk, tkinterdnd2 | bundled in the frozen app | PSF, BSD-3, BSD-3, Tcl/Tk, MIT |

## Not covered by these licenses

The **files Urania builds** (`astronomical.xsa` and `earth_astro.dat`) are made from the user's own
X-Plane 12 files and contain code and data by Laminar Research. They are for the user's personal use.
That is why Urania builds them on the user's computer and never distributes them.
