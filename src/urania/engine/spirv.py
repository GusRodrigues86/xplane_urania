"""
spirv.py - Read the sky gains (SPIR-V specialization constants) from an astronomical.xsa.

Python version of plugin/src/xsa_gains.cpp (read part). Urania uses it to check its own
output: the plugin must be able to read the gains from the file that Urania writes.
The two versions must agree:
  - the stages astronomical_6.spv and astronomical_8.spv are stored (ZIP method 0);
  - OpDecorate <id> SpecId <n> gives the ID; OpSpecConstant <type> <id> <value> the 32-bit value.
"""
import struct
import zipfile

from urania.errors import UraniaError

SPIRV_MAGIC = 0x07230203
OP_DECORATE, OP_SPEC_CONSTANT = 71, 50
DECORATION_SPEC_ID = 1

# Must agree with plugin/src/xsa_gains.h.
GAIN_SPEC_IDS = {"STAR_GAIN": 200, "MW_GAIN": 201, "NEBULA_GAIN": 202, "GALAXY_GAIN": 203}
HAZE_EMISSIVE_SPEC_ID = 204
GAIN_STAGES = ("astronomical_6.spv", "astronomical_8.spv")
PATCH_MARK = b"v_kind"        # an output name of the mod; only a patched stage 7 has it
MOON_MARK = b"pcg_hash"       # a function name of the moon mod; only a patched stage 1 has it


def spec_constants(spv):
    """Return {SpecId: float value} for the 32-bit OpSpecConstant values of a SPIR-V program."""
    if len(spv) < 20 or len(spv) % 4 or struct.unpack_from("<I", spv, 0)[0] != SPIRV_MAGIC:
        raise UraniaError("not a SPIR-V program")
    spec_of_id, value_of_id = {}, {}
    p = 20
    while p < len(spv):
        w = struct.unpack_from("<I", spv, p)[0]
        words, op = w >> 16, w & 0xFFFF
        if words == 0 or p + 4 * words > len(spv):
            raise UraniaError("damaged SPIR-V program")
        if op == OP_DECORATE and words >= 4 and struct.unpack_from("<I", spv, p + 8)[0] == DECORATION_SPEC_ID:
            target, spec = struct.unpack_from("<I", spv, p + 4)[0], struct.unpack_from("<I", spv, p + 12)[0]
            spec_of_id[target] = spec
        elif op == OP_SPEC_CONSTANT and words == 4:
            value_of_id[struct.unpack_from("<I", spv, p + 8)[0]] = struct.unpack_from("<f", spv, p + 12)[0]
        p += 4 * words
    return {spec: value_of_id[rid] for rid, spec in spec_of_id.items() if rid in value_of_id}


def read_gains(xsa_path):
    """Read the gains as the plugin does. Return {name: value} incl. HAZE_EMISSIVE.

    Raise UraniaError if the plugin could not read them (compressed stage, missing SpecId).
    """
    try:
        z = zipfile.ZipFile(xsa_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise UraniaError(f"{xsa_path} is not a ZIP file ({e})") from e
    with z:
        result = None
        for stage in GAIN_STAGES:
            try:
                info = z.getinfo(stage)
            except KeyError:
                raise UraniaError(f"no {stage} in {xsa_path}") from None
            if info.compress_type != zipfile.ZIP_STORED:
                raise UraniaError(f"{stage} is compressed: the Urania plugin cannot read the gains")
            values = spec_constants(z.read(stage))
            missing = [n for n, i in GAIN_SPEC_IDS.items() if i not in values]
            if missing:
                raise UraniaError(f"{stage} has no plugin gains ({', '.join(missing)})")
            gains = {n: values[i] for n, i in GAIN_SPEC_IDS.items()}
            gains["HAZE_EMISSIVE"] = values.get(HAZE_EMISSIVE_SPEC_ID, 0.0)
            if result is not None and gains != result:
                raise UraniaError("stages 6 and 8 have different gains")
            result = gains
        return result


def is_patched(xsa_path):
    """Return True if the .xsa has the star mod (stage 7) or the moon mod (stage 1): not the X-Plane original."""
    with zipfile.ZipFile(xsa_path) as z:
        return PATCH_MARK in z.read("astronomical_7.spv") or MOON_MARK in z.read("astronomical_1.spv")


def has_moon(xsa_path):
    """Return True if the .xsa has the moon sky mod (stage 1)."""
    with zipfile.ZipFile(xsa_path) as z:
        return MOON_MARK in z.read("astronomical_1.spv")
