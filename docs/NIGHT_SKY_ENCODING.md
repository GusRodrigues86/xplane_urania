# Night sky data for X-Plane 12: math and encoding

This document explains how `make_night_sky.py` builds `earth_astro.dat`.
It gives the math for each step. It also gives the reason for each encoding decision.

The script and this document go with the patched shader `astronomical.xsa`.
The shader decodes the data that this script writes.

## 1. Run the script

1. Install Python and the packages. The steps for Windows (PowerShell), Linux and macOS are in [SETUP.md](SETUP.md).
2. Get the 3 input files (see section 2 and SETUP.md, section 6).
3. Run the script (Windows paths; Linux and macOS: SETUP.md, section 7):

   ```
   python make_night_sky.py --astro earth_astro_original.dat --stars stars.8.json --milkyway milkyway_2020_4k.exr --out out
   ```

4. Read `out/generation_report.txt`. Compare the SHA-256 values with section 11.

The script writes 2 files:

| File | Content |
|---|---|
| `earth_astro.dat` | Stars with color codes, Milky Way, deep-sky objects |
| `earth_astro_airglow.dat` | Same content, plus a faint glow over the full sky |

To install a file in X-Plane, copy the file to `X-Plane 12\Resources\default data\` and rename it to `earth_astro.dat`.

> **WARNING:** The new file replaces the X-Plane original. Keep a copy of the original file before you replace it.

Other modes:

| Command | Result |
|---|---|
| `--verify FILE` | Decodes each row with float32 math, as the shader does. Prints counts and errors. |
| `--compare FILE_A FILE_B` | Compares 2 files row by row. Prints the different rows. |
| `--preview` | Also writes a PNG image of the haze, drawn with the shader math. Needs Pillow. |

## 2. Input files

| Input | Source | License or credit |
|---|---|---|
| `earth_astro.dat` | Your X-Plane 12 installation, `Resources\default data\`. Use the original file, not a patched file. | Laminar Research. The file says it comes from Hipparcos data through SIMBAD. |
| `stars.8.json` | npm package `d3-celestial` version 0.7.35, folder `data/`. Download: `https://registry.npmjs.org/d3-celestial/-/d3-celestial-0.7.35.tgz` | BSD-3-Clause, Olaf Frohn |
| `milkyway_2020_4k.exr` | NASA Scientific Visualization Studio, item 4851 "Deep Star Maps 2020": `https://svs.gsfc.nasa.gov/4851` | NASA/Goddard SVS. Gaia DR2: ESA/Gaia/DPAC. |

The NASA map is the Milky Way background only. NASA removed the bright stars from this map.
This is important: the X-Plane file already draws the bright stars. If the map also had them, each bright star would show 2 times.

## 3. Why we encode data in the magnitude

X-Plane reads 4 fields from each row: RA (hours), Dec (degrees), magnitude and name.
X-Plane then sends a 4-number vector to the GPU for each row:

```
a_vertex = (x, y, z, magnitude)      x, y, z = direction on the sky
```

The name does not go to the GPU. X-Plane does not read a 5th field.
We cannot change the X-Plane loader. Thus, the magnitude is the only channel from the file to the shader.

The stock file gives the magnitude with 2 decimals (for example `0.42`).
A float32 number holds about 7 significant digits. Thus, the 3rd and 4th decimals are free.
The script puts a code in these decimals. The patched shader reads the code and removes it from the brightness.

### 3.1 Effect of the code on brightness

The brightness of a row is proportional to `10^(-0.4 m)` (Pogson law).

* A star code adds at most 0.0089 to the magnitude. This is a brightness change of 0.8 %. The eye cannot see this change. The shader does not correct it.
* A haze code also uses the 2nd decimal. The shader removes the code exactly (see 3.3). The magnitude of a haze blob has a step of 0.1 (9.6 % in brightness). Haze is soft and large, so this step is not visible.

### 3.2 Star rows: color code k

```
field = round(m, 2) + k × 0.0001          k = 0 … 89
```

| k | Meaning |
|---|---|
| 0 | No color data. The shader draws the star white. |
| 1 … 89 | B-V color index from −0.40 (blue) to +2.00 (red), linear |
| 90 … 99 | Not a star. Reserved for haze blobs (see 3.3). |

The conversion from B-V to k:

```
t = (clamp(BV, −0.40, 2.00) + 0.40) / 2.40
k = 1 + round(88 t)
```

One step of k is 0.0273 in B-V. This step is much smaller than the color difference that the eye can see.

Example, Betelgeuse:

| Value | Number |
|---|---|
| Stock magnitude | 0.42 |
| Catalog B-V | 1.500 |
| t | (1.500 + 0.40) / 2.40 = 0.7917 |
| k | 1 + round(69.67) = 71 |
| Field in file | 0.42 + 0.0071 = **0.4271** |

Negative magnitudes also work. Sirius: −1.46, B-V 0.009, k = 16. The field is −1.46 + 0.0016 = **−1.4584**.

### 3.3 Haze rows: color and size code

A haze blob needs 2 values: a color class (4 classes) and a diameter (25 size classes).
That is 4 × 25 = 100 combinations. The 3rd and 4th decimals alone give only 10 free values (90 … 99).
Thus, the haze code also uses the 2nd decimal:

```
field = M.D c kk
        M.D = magnitude, 0.1 step
        c   = 2nd decimal, 0 … 9
        kk  = 3rd and 4th decimals, 90 … 99

code = (kk − 90) × 10 + c = color × 25 + size        code = 0 … 99
```

| Color class | Use | Shader color (linear RGB) |
|---|---|---|
| 0 | Milky Way, airglow | warm white (1.10, 0.99, 0.84) |
| 1 | H-alpha emission nebula (M42 halo, Carina, Lagoon) | red-pink (2.38, 0.59, 0.97) |
| 2 | Nebula core, reflection nebula, planetary nebula | teal (0.60, 1.15, 1.30) |
| 3 | Galaxy, globular cluster | warm yellow (1.20, 0.99, 0.66) |

```
diameter = 0.1° × 1.25^size        size = 0 … 24  →  0.1° … 21.2°
size     = round( ln(diameter / 0.1°) / ln 1.25 )
```

Each size class is 25 % larger than the one before. A 25 % step is small enough for a smooth look.

Example, the Andromeda core blob:

| Value | Number |
|---|---|
| Magnitude | 4.9 |
| Color class | 3 (galaxy) |
| Diameter | 0.4 × 60′ = 24′ = 0.40° → size = round(6.21) = 6 |
| code | 3 × 25 + 6 = 81 → kk = 98, c = 1 |
| Field in file | 4.9 + 0.01 + 0.0098 = **4.9198** |

Why kk = 90 … 99 for haze: a star code is never larger than 89.
Thus, the shader needs only 1 test (`k >= 90`) to tell a haze blob from a star.

### 3.4 Shader decode

The patched shader (stage 8, the vertex stage for point sprites) decodes each row:

```
t = w × 100
n = floor(t + 0.005)
k = round((t − n) × 100)          if k >= 90: haze blob, else: star with color k
c = n mod 10
code = (k − 90) × 10 + c
m    = (n − c) / 100              true haze magnitude
```

The `+ 0.005` protects against float32 error. For example, a white star with magnitude 0.53 gives t = 52.999996 in float32.
Without the protection, `floor` gives 52 and k becomes 100, which is wrong. With the protection, `floor` gives 53 and k = 0.

The `--verify` mode of the script runs this exact decode with float32 numbers on each row.

## 4. Star colors

Step A of the script matches each X-Plane star with a star in the d3-celestial catalog.

1. The script moves each catalog position from J2000 to J2025 (see section 9).
2. A catalog star matches if the distance is less than 0.15° **and** the magnitude difference is less than 0.6.
3. If more than 1 catalog star matches, the nearest catalog star wins.
4. If no catalog star matches, the star gets k = 0 (white).

Result with the stock X-Plane file: 8317 of 8347 stars match (99.6 %).

The shader converts k back to B-V. Then it uses a table of 90 RGB colors (`STAR_RGB` in the shader).
The table comes from the black-body spectrum of each star:

```
T = 4600 K × ( 1 / (0.92 BV + 1.7) + 1 / (0.92 BV + 0.62) )          (Ballesteros 2012)
```

The Planck spectrum at T goes through the CIE 1931 color matching functions (Wyman 2013 fit) to give XYZ, then linear sRGB.
Each color has luminance 1, so the color does not change the brightness. The shader setting `SAT = 1.3` makes the colors a little stronger than physical.

## 5. Milky Way from the NASA map

### 5.1 Calibration

The map gives a relative value v for each pixel. The script converts v to surface brightness:

```
SB = ZP − 2.5 log10(v)          [mag/arcsec²]
ZP = 20.0 + 2.5 log10(0.3103) = 18.729
```

The anchor: the mean map value in the Sagittarius star cloud box is 0.3103.
We give this box SB = 20.0 mag/arcsec², which is a typical value for the brightest Milky Way.
All other SB values follow from this one anchor, so the contrast of the map stays the same.

### 5.2 Lattice

The script needs points spread evenly over the full sky. It uses a Fibonacci sphere:

```
n    = int(41253 / step²)                   41253 = full sky in square degrees
z_i  = 1 − 2 (i + 0.5) / n
Dec_i = asin(z_i)
RA_i  = ( i × (3 − √5) / 2 × 24 h ) mod 24 h        (golden angle)
```

Each point covers the same area: `step²` square degrees.
A normal RA/Dec grid puts too many points near the poles. The Fibonacci sphere has no such problem.

### 5.3 Flux of one blob

Each blob carries the total light of its lattice cell:

```
SB_cell = Gaussian-weighted mean of the map around the point (sigma = step / 2)
mag     = SB_cell − 2.5 log10( (step × 3600)² × weight )
```

The `(step × 3600)²` term is the cell area in arcsec². Thus, the blob has the same total light as the sky area that it replaces.
The shader spreads this light again over the blob (see section 8). The result is the correct SB on the screen.

The Gaussian weight of each pixel is `exp(−0.5 (angle / sigma)²) × cos(Dec)`.
The `cos(Dec)` term corrects the pixel area: in an equirectangular map, pixels near the poles cover less sky.

### 5.4 Two layers

| Layer | Lattice step | Blob size class | Blob diameter | Used where |
|---|---|---|---|---|
| Fine | 0.5° | 13 | 1.82° | SB brighter than 21.6 (dust lanes, star clouds) |
| Coarse | 1.4° | 18 | 5.55° | SB fainter than 22.6 (outer glow) |

Between SB 21.6 and 22.6, both layers are present. A smoothstep gives the weight of each layer:

```
w_fine   = 1 − smoothstep(21.6, 22.6, SB)
w_coarse = 1 − w_fine
```

Thus, the change from fine to coarse has no visible edge.
Small blobs everywhere give the best detail, but the row count is then too high. The coarse layer covers the large faint areas with few rows.

### 5.5 Fade and limits

* Sky fainter than SB 22.8 fades out. Sky fainter than SB 24.0 is removed: `weight × (1 − smoothstep(22.8, 24.0, SB))`.
* A blob with weight less than 0.02 is removed.
* A blob fainter than magnitude 9.4 is removed.

These limits keep the row count near 58 000. X-Plane loads 58 000 rows without problems (tested). The file with airglow has 65 000 rows. The maximum row count of X-Plane is not known.

## 6. Airglow

A real dark sky is never black. Light comes from the upper air (airglow), from sunlight on dust in space (zodiacal light) and from very faint stars.
The airglow layer adds this light as a constant SB over the full sky:

```
SB = 22.3 mag/arcsec²       lattice step 2.5°       size class 21 (9.3°)
mag = 22.3 − 2.5 log10( (2.5 × 3600)² ) = 2.53  →  stored as 2.5
```

This gives 6600 rows. The blobs overlap a lot, so the result is a smooth glow.
The airglow uses color class 0. Thus, the shader setting `MW_GAIN` also changes the airglow.
The airglow does not change with the Moon or the time. In daylight, the X-Plane exposure makes it invisible (inferred, not tested).

## 7. Deep-sky objects

Each object has: RA, Dec, major axis a, minor axis b (arcmin), position angle PA, total magnitude m, color class.

### 7.1 Round objects (b / a > 0.7)

One blob. Diameter = b. Magnitude = m.

### 7.2 Elongated objects (b / a ≤ 0.7)

The shader draws each blob as a Gaussian with `sigma = diameter / 6`.
The visible width (FWHM) is `2.355 × sigma = 0.39 × diameter`.
If 2 blobs are farther apart than about 1 FWHM, the eye sees 2 separate dots.

The first version used 3 blobs, 1° apart, each 1° in diameter, for Andromeda. The FWHM was only 0.39°. Thus, Andromeda showed as 3 dots.
The current version makes a chain of overlapping blobs:

```
d    = 1.4 × b                                  blob diameter
h    = (a − 0.6 b) / 2                          chain centers go from −h to +h
n    = min(15, max(2, ceil(2h / (0.35 d)) + 1)) number of blobs
o_j  = −h + j × 2h / (n − 1)                    offset of blob j along the major axis
w_j  = exp(−0.5 (o_j / (0.3 a))²)               flux weight: bright center, faint ends
```

The step between blob centers is at most `0.35 d`. This is less than 1 FWHM, so the blobs merge into one smooth bar.

The total flux `F = 10^(−0.4 m)` goes to the blobs:

```
galaxy (class 3):  core blob, diameter 0.4 b:   mag = −2.5 log10(0.25 F)
                   chain blob j:                mag = −2.5 log10(0.75 F × w_j / Σw)
other classes:     chain blob j:                mag = −2.5 log10(F × w_j / Σw)
```

The core blob copies the bright nucleus of a real galaxy.

Each blob moves along the position angle:

```
ΔDec = o × cos(PA)
ΔRA  = o × sin(PA) / cos(Dec)
```

The script adds M32 and M110 (the companions of Andromeda).
The LMC and the SMC are not in the object list, because the NASA map already contains them.

## 8. How the shader draws a haze blob

This section explains the shader side. The shader settings are in `astronomical.xsa`, not in this script. `make_shaders.py` builds `astronomical.xsa` (see [SHADER_BUILD.md](SHADER_BUILD.md)).

1. X-Plane computes a brightness from the field w: `L = 2.128e−6 × 10^(−0.4 w) × emissive × exposure`.
2. The shader removes the effect of the code digits: `L × 10^(−0.4 (m − w))`. Now L uses the true magnitude m.
3. The shader multiplies L by the gain: `MW_GAIN` (class 0) or `DSO_GAIN` (classes 1 to 3).
4. The shader computes the sprite size S in pixels: `S = diameter (radians) × 0.5 × H × P[1][1]`. H is the screen height in pixels. P is the projection matrix. `0.5 × H × P[1][1]` is the number of pixels per radian at the screen center.
5. The fragment stage draws the profile `exp(−4.5 r²)`, with r = 0 at the center and r = 1 at the sprite edge.
6. The shader divides L by the area of the profile: `∫ exp(−4.5 r²) dA = 0.1728 × S²`.

Step 6 makes each blob "flux-conserving": the sum of all pixels of a blob is the light of magnitude m.
Thus, a blob with the same magnitude gives the same total light at all zoom levels.

At wide field of view, the screen edges stretch the sky by `1 + tan²` of the view angle. The shader makes the sprite larger by the same factor. The shader keeps the brightness of the unstretched sprite (S0), so the SB stays the same at the edges.

Current shader settings (version "stars35"): `STAR_GAIN = 0.35`, `MW_GAIN = 3`, `DSO_GAIN = 40`, star size 7 px at magnitude 0, minus 1.2 px for each magnitude, 1.5 px minimum, 12 px maximum.
The shader does not multiply stars or haze by the X-Plane sky texture transparency, because that texture has a dark band at the screen center.

## 9. Precession

The catalog and the NASA map use epoch J2000. The X-Plane file uses epoch J2025.
In 25 years, the sky coordinates move by up to 0.35°. This shift is larger than a fine Milky Way blob step, so the script corrects it.
The script uses the IAU 1976 precession, with T = 0.25 Julian centuries:

```
ζ = (2306.2181 T + 0.30188 T²)″
z = (2306.2181 T + 1.09468 T²)″
θ = (2004.3109 T − 0.42665 T²)″

A = cos δ sin(α + ζ)
B = cos θ cos δ cos(α + ζ) − sin θ sin δ
C = sin θ cos δ cos(α + ζ) + cos θ sin δ

α' = atan2(A, B) + z         δ' = asin(C)
```

## 10. File layout and order

The script keeps the header of the X-Plane file, then writes all rows, then an empty line, then the end marker `99`.

New rows have this format: `RA(7.4f) Dec(8.3f) field(.4f) name`.
The names are `MW` (Milky Way), `SKY` (airglow), or the object name with a letter for each chain blob (for example `M31a`, `M31core`).

The script sorts all rows by the field value, bright first. The stock X-Plane file has the same order.
The sort is stable: rows with the same value keep their input order. Thus, the output is the same on each run.

The file without airglow is the same as the file with airglow, minus the `SKY` rows.

## 11. Reproducibility

The script uses no random numbers. The same input files and the same settings give the same output files.

Reference run (2026-10-10, Python 3.13.16, numpy 2.5.3):

| File | SHA-256 |
|---|---|
| Input `earth_astro.dat` (X-Plane 12 stock, 8347 stars) | `348c03fe20973c68187b1e0f5c25b66af0f774255c884d5f9145b9cf4b10bc91` |
| Input `stars.8.json` | `e3ec6cde89bae0dde064d91c1edb9ec53c3c40d5c12fdf5d30f9a4de5dbc2143` |
| Input `milkyway_2020_4k.exr` | `2eb802d6e68d170b410f766c7fec07f7518619f6b6708fdc81e9302d93e74fdb` |
| Output `earth_astro.dat` (58 293 rows) | `b38e55b1f6c91081f5646d58ea0199ae7259dba848619c789a8e39d656177cd5` |
| Output `earth_astro_airglow.dat` (64 893 rows) | `91ae480738aa3e2f058f101d98dd9726a263023726c1ef835fdf2e15c32cfb17` |

These outputs are byte-identical to the test files of version v7.4.

If your input hash is different, your result is different. A different X-Plane version can have a different star file.
If only the numpy version is different, a few Milky Way rows can change by 0.1 magnitude. The cause is a different order of floating-point sums near a rounding limit.
Use `--compare` to see which rows are different.

## 12. Settings that you can change

All settings are at the top of `make_night_sky.py`, in section 1. The report file records each value.

| Setting | Effect |
|---|---|
| `SB_ANCHOR` | Brightness of the full Milky Way. 1 magnitude less = 2.5 × brighter. Same effect as `MW_GAIN` in the shader. |
| `FADE_SB` | How far the faint Milky Way goes before it fades out |
| `FINE_S`, `COARSE_S` | Blob spacing. A smaller step gives more detail and more rows. |
| `MAG_MAX` | Removes faint blobs. A larger value gives more rows. |
| `AIRGLOW_SB` | Airglow brightness. A smaller value gives a brighter sky. |
| `DSO` | The deep-sky object list. Add a row to add an object. |
| `ELONG_*`, `CORE_*` | Shape of elongated objects |

To make a change in brightness only, change the gain in the shader. To make a change in shape, position or object list, change this script.
