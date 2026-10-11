import struct
import zipfile

import pytest

from urania.engine import spirv
from urania.errors import UraniaError


def make_spv(spec):
    """A minimal SPIR-V word stream: header + OpDecorate SpecId + OpSpecConstant for each {id: value}."""
    words = [spirv.SPIRV_MAGIC, 0x00010600, 0, 1000, 0]
    for n, (spec_id, value) in enumerate(spec.items()):
        rid = 10 + n
        words += [(4 << 16) | spirv.OP_DECORATE, rid, spirv.DECORATION_SPEC_ID, spec_id]
        words += [(4 << 16) | spirv.OP_SPEC_CONSTANT, 1, rid, struct.unpack("<I", struct.pack("<f", value))[0]]
    return struct.pack(f"<{len(words)}I", *words)


ALL = {200: 0.35, 201: 3.0, 202: 40.0, 203: 25.0, 204: 0.0}


def test_spec_constants_parsed():
    values = spirv.spec_constants(make_spv(ALL))
    assert values == pytest.approx(ALL)


@pytest.mark.parametrize("data", [b"", b"\x00" * 20, b"abcd" * 3])
def test_not_spirv(data):
    with pytest.raises(UraniaError):
        spirv.spec_constants(data)


def test_damaged_spirv():
    spv = make_spv(ALL)[:-4]
    with pytest.raises(UraniaError, match="damaged"):
        spirv.spec_constants(spv)


def write_xsa(path, stage_bytes, method=zipfile.ZIP_STORED, stage7=b"v_kind"):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(9):
            info = zipfile.ZipInfo(f"astronomical_{i}.spv")
            info.compress_type = method if i in (6, 8) else zipfile.ZIP_DEFLATED
            z.writestr(info, stage7 if i == 7 else stage_bytes)
    return str(path)


def test_read_gains(tmp_path):
    gains = spirv.read_gains(write_xsa(tmp_path / "a.xsa", make_spv(ALL)))
    assert gains == pytest.approx({"STAR_GAIN": 0.35, "MW_GAIN": 3.0, "NEBULA_GAIN": 40.0,
                                   "GALAXY_GAIN": 25.0, "HAZE_EMISSIVE": 0.0})


def test_read_gains_compressed_stage(tmp_path):
    with pytest.raises(UraniaError, match="compressed"):
        spirv.read_gains(write_xsa(tmp_path / "a.xsa", make_spv(ALL), method=zipfile.ZIP_DEFLATED))


def test_read_gains_missing_spec_id(tmp_path):
    with pytest.raises(UraniaError, match="no plugin gains"):
        spirv.read_gains(write_xsa(tmp_path / "a.xsa", make_spv({200: 1.0})))


def test_haze_emissive_optional(tmp_path):
    gains = spirv.read_gains(write_xsa(tmp_path / "a.xsa", make_spv({k: v for k, v in ALL.items() if k != 204})))
    assert gains["HAZE_EMISSIVE"] == 0.0


def test_is_patched(tmp_path):
    assert spirv.is_patched(write_xsa(tmp_path / "a.xsa", make_spv(ALL)))
    assert not spirv.is_patched(write_xsa(tmp_path / "b.xsa", make_spv(ALL), stage7=b"stock"))
