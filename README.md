# Urania

Urania is a night sky for **X-Plane 12.4.4 and newer** on Windows and Linux (Vulkan). There is no macOS version yet; see [macOS: help wanted](#macos-help-wanted).

- Stars have their real colors and sizes.
- The Milky Way, nebulae and galaxies show as soft light.
- The Urania plugin sets the moonlight on clouds and the sky darkness. It also checks the sky files and can restore the X-Plane sky.

Urania is one app. The user drops in the input files, Urania checks the computer, and Urania builds **one zip file**. Extract that zip in the X-Plane 12 folder to install everything.

## Why "Urania"? (Give it some space)

In Greek myth, **Urania** is one of the nine Muses. She is the Muse of **astronomy**, a daughter of **Zeus** and of **Mnemosyne**, the goddess of memory. Artists show her with a celestial globe and a compass, and she looks up while the other Muses look at each other. Her name comes from the Greek *ouranios*, "heavenly".

Her family tree is also on brand: Zeus's grandfather was **Ouranos**, the god of the sky itself. So the sky is Urania's great-grandfather. The Romans called him **Uranus**, and the planet has that name.

So this project has the name of the Muse who makes star maps. It also contains an undeniable opportunity to talk about Uranus. We are sorry in advance (see [Uranus: the facts](#uranus-the-facts-we-are-sorry)).

> **Why is the build on the user's computer?** The shader and the star file are built from the user's own X-Plane files, which contain Laminar Research code and data. They are for personal use only. Urania never distributes them: each user builds their own.

## For users

1. Download `Urania-<version>-windows-x64.zip` or `Urania-<version>-linux-x64.tar.gz` and extract it.
2. Start `Urania` (Windows: `Urania.exe`).
3. The window shows each input file and where to get it:

   | File | Where |
   |---|---|
   | X-Plane 12 folder | Found automatically (from the X-Plane install list) |
   | `astronomical.xsa`, `earth_astro.dat` | Taken from the X-Plane folder (originals, or Urania's backup) |
   | `d3-celestial-0.7.35.tgz` (or `stars.8.json`) | "Get it" button: npm registry |
   | `milkyway_2020_4k.exr` | "Get it" button: NASA SVS 4851 |

4. Click **Build Urania zip**. Extract the zip into the X-Plane 12 folder. In X-Plane, open the menu **Plugins > Urania**.

Command line: `urania-cli build --stars <file> --milkyway <file> [--xplane <folder>] [--screen-height 1440] [--airglow]`. Run `urania-cli --help` for all options.

## For developers

### Layout

| Folder | Content |
|---|---|
| `src/urania/` | The app: the engine (star data, shader, zip), checks, CLI, GUI |
| `src/urania/engine/shader_src/` | The GLSL mod code (sky stages 6, 7, 8) |
| `plugin/` | The X-Plane plugin (C++, CMake): `urania.cpp`, `sky_files.cpp`, `xsa_gains.cpp` |
| `tests/` | pytest suite (engine, app, GUI model, theme, plugin contract, real data) |
| `plugin/tests/` | C++ unit tests (CTest), no X-Plane needed |
| `scripts/` | `build_tools.py`, `build_plugin.py`, `build_app.py`, `release.py` |
| `docs/` | `NIGHT_SKY_ENCODING.md`, `SHADER_BUILD.md` |

### Third-party code: put it in place yourself (it is not in git)

| What | Where | How |
|---|---|---|
| X-Plane SDK 4.4 | `plugin/SDK/` | See `plugin/SDK/PUT_THE_SDK_HERE.txt` |
| Dear ImGui 1.92.9b+ | `plugin/third_party/imgui/` | See `plugin/third_party/imgui/PUT_IMGUI_HERE.txt` |
| glslang, SPIRV-Tools, SPIRV-Cross | `vendor/tools/<platform>/` | `python scripts/build_tools.py` builds them from source (tag `vulkan-sdk-1.4.363.0`) |
| Test inputs (optional) | `inputs/` | `earth_astro_original.dat`, `astronomical_original.xsa`, `stars.8.json`, `milkyway_2020_4k.exr` |

### Build on Windows (PowerShell)

You need:
- Python 3.9 to 3.14, 64-bit
- git
- CMake 3.21 or newer
- Visual Studio 2022 Build Tools, with the "Desktop development with C++" workload

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python scripts\build_tools.py      # 1. the Vulkan tools (about 10 minutes, one time)
.venv\Scripts\python scripts\build_plugin.py     # 2. Urania.xpl (win_x64) + CTest
.venv\Scripts\python -m pytest                   # 3. tests (add -m real to use the files in inputs\)
.venv\Scripts\python scripts\release.py          # 4. dist\Urania-<version>-windows-x64.zip
```

### Build on Linux (bash)

Build on **Ubuntu 22.04** (or another distribution with glibc 2.35). The programs then run on Ubuntu 22.04 and newer, and on other distributions with glibc 2.35 or newer. A program built on a newer system does not run on an older one.

```bash
sudo apt update
sudo apt install build-essential cmake git python3 python3-venv python3-dev python3-tk
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/build_tools.py          # 1. the Vulkan tools (about 10 minutes, one time)
.venv/bin/python scripts/build_plugin.py         # 2. Urania.xpl (lin_x64) + CTest
.venv/bin/python -m pytest                       # 3. tests
.venv/bin/python scripts/release.py              # 4. dist/Urania-<version>-linux-x64.tar.gz
```

The Linux archive is a `.tar.gz`, because it keeps the "executable" flag of the programs. A `.zip` loses it.

### Build the Linux files on a Windows computer (WSL)

1. Install WSL with Ubuntu 22.04 (PowerShell as administrator, then restart the computer):
   ```powershell
   wsl --install -d Ubuntu-22.04
   ```
2. In Ubuntu, copy the repository into the Linux home folder. Builds on `/mnt/c` or `/mnt/d` are slow and lose the file permissions:
   ```bash
   cp -r /mnt/d/OrionSim/sagan/urania ~/urania
   cd ~/urania && rm -rf .venv build vendor plugin/build dist
   ```
   The copy includes `plugin/SDK/` and `plugin/third_party/imgui/` if you put them in place on Windows.
3. Run the Linux steps above in `~/urania`.
4. Copy the Linux plugin back to Windows:
   ```bash
   mkdir -p /mnt/d/OrionSim/sagan/urania/vendor/plugin/Urania/lin_x64
   cp vendor/plugin/Urania/lin_x64/Urania.xpl /mnt/d/OrionSim/sagan/urania/vendor/plugin/Urania/lin_x64/
   ```

### Both plugins in each release

Each app puts the plugin files from `vendor/plugin/Urania/` into the zips it makes. The Windows app and the Linux app must both have **both** plugin files. Then a zip works on both systems, also for a user who has X-Plane on both.

Release order:
1. Build the plugin on Windows and on Linux.
2. Copy each `Urania.xpl` to the other system, into `vendor/plugin/Urania/<win_x64|lin_x64>/`.
3. Run `release.py` on each system.

`build_app.py` shows a warning if a plugin file is missing.

### Icon

`scripts/make_icon.py` draws the app icon: the Pleiades (M45) at their real positions, with the faint blue reflection nebula. It writes `packaging/urania.ico` (Windows) and `src/urania/assets/urania.png` (window icon).

### Guarantees that the tests check

- With the same inputs, `earth_astro.dat` is byte-identical to the night-sky-generator v1 reference (`tests/test_real.py`).
- The plugin (C++) reads and writes the gains in the shader that the app (Python) builds: specialization constants 200-204, and stages 6 and 8 stored (`tests/test_plugin_contract.py`).
- The same input gives the same zip (fixed dates, sorted entries).
- Each text color of the GUI meets WCAG AA contrast (`tests/test_theme.py`).

## macOS: help wanted

**Urania has no macOS version yet, and we need help to make one.**

The reason: on macOS, X-Plane 12 uses **Metal**, not Vulkan. Its sky shader is the Metal (`msl`) variant of the shader file, not the Vulkan SPIR-V file (`spv`) that Urania builds. A Mac version needs these steps:

1. Learn the format of the Metal shader file of X-Plane 12.4.4+ and how X-Plane loads it.
2. Make the Metal version of the 3 star stages:
   - Translate them from the SPIR-V that Urania already builds (SPIRV-Cross can write Metal Shading Language).
   - Compile them for macOS.
   - Keep the stock declarations, as Urania does for Vulkan.
3. Give the plugin gains a Metal equivalent (Metal function constants).
4. Build and sign the plugin as a universal binary (arm64 + x86_64). The CMake file already has the macOS link step.
5. Test on Apple Silicon and on Intel Macs.

The star file (`earth_astro.dat`) is the same on all systems. It does not need changes.

**How to help:** if you have a Mac with X-Plane 12 and you know Metal (or want to learn it), open an issue or a pull request. A first useful step is a short report on the files in X-Plane's Metal shader folder. Report only the structure; do not publish Laminar code.

Until a Mac version exists: Urania refuses to run on macOS, and its zip file is not for X-Plane on macOS.

## Uranus: the facts (we are sorry)

The author is too childish to let any Uranus joke pass. All facts below are true. The jokes are not his fault: astronomers named the planet.

- **Uranus is full of gas.** The planet is mostly hydrogen and helium, with about 2 % methane in its upper atmosphere.
- **Uranus is blue because of methane.** Methane absorbs red light. The rest of the sunlight comes back pale cyan and blue-green: the color of the Urania app.
- **Uranus smells of rotten eggs.** In 2018, astronomers found hydrogen sulfide in the cloud tops of Uranus. That gas smells like rotten eggs. Science confirmed what every 10-year-old knew.
- **Uranus is tilted 98 degrees.** The planet rolls around the Sun on its side. It spins backward, too. The Urania app draws its ring almost upright for this reason.
- **Uranus has had one visitor.** Only one spacecraft has been near Uranus: Voyager 2, on 24 January 1986. It took a quick look and left.
- **Uranus is the coldest in the Solar System.** Its atmosphere gets down to 49 K (-224 °C). That is colder than Neptune, which is farther from the Sun.
- **Uranus has rings.** It has 13 of them, dark and thin. In 1977, astronomers watched a star blink on and off as it passed behind them. That is how they found them: a star-light discovery, like this project.
- **Uranus has strong winds.** Winds on Uranus reach about 900 km/h.
- **Uranus may rain diamonds.** Under the high pressure inside, methane can possibly turn into diamonds that fall to the center. Laboratory tests support this idea. It is still not confirmed.
- **Each pole of Uranus gets 42 years of sunlight, then 42 years of darkness.** One Uranus year is 84 Earth years. On the night side, astronomy season lasts for decades.
- **Uranus almost had another name.** William Herschel found the planet in 1781, the first planet found with a telescope. He wanted to call it *Georgium Sidus* ("George's Star"), after King George III. Johann Bode suggested "Uranus" instead. Every school child since has thanked him.
- **The moons of Uranus have literary names.** Its 28 known moons have the names of characters from Shakespeare and Alexander Pope: Titania, Oberon, Miranda, Ariel and others. It is the classiest neighborhood of Uranus.
- **You can see Uranus with your own eyes.** At about magnitude 5.7, Uranus is just visible without a telescope from a truly dark site. For that sky, set the sky darkness in the Urania plugin to the darkest level.
- **There is a polite way to say it.** Many astronomers say "YOOR-uh-nus" to avoid the joke. It does not help.

## Quality and support

Automated tests check the Urania code (pytest and CTest, see "Guarantees that the tests check"). The code has also been audited by humans.

Any support is welcome: bug reports, tests on other systems, pull requests, and help with the macOS version.

If you enjoy Urania and want to say thank you: [ko-fi.com/gusrodrigues](https://ko-fi.com/gusrodrigues)

## License

The Urania code is MIT ([LICENSE](LICENSE)) and the docs are CC BY 4.0. Third-party parts keep their own licenses. See [LICENSES.md](LICENSES.md).
