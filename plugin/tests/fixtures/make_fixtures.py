#!/usr/bin/env python3
"""
make_fixtures.py - Write the small test files for the plugin tests (test_core.cpp).

The files contain no X-Plane code: each stage is a minimal SPIR-V word stream with the
specialization constants that the Urania shader has. Run from the repository root:

    python plugin/tests/fixtures/make_fixtures.py

tests/test_plugin_contract.py checks that the files in git are the same as this script writes.
"""
import os
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "src")))
from urania.engine import spirv  # noqa: E402

GAINS = {200: 0.35, 201: 3.0, 202: 40.0, 203: 25.0, 204: 0.0}
DATE = (2026, 10, 11, 0, 0, 0)


def make_spv(spec):
    words = [spirv.SPIRV_MAGIC, 0x00010600, 0, 1000, 0]
    for n, (spec_id, value) in enumerate(spec.items()):
        rid = 10 + n
        words += [(4 << 16) | spirv.OP_DECORATE, rid, spirv.DECORATION_SPEC_ID, spec_id]
        words += [(4 << 16) | spirv.OP_SPEC_CONSTANT, 1, rid, struct.unpack("<I", struct.pack("<f", value))[0]]
    return struct.pack(f"<{len(words)}I", *words)


def write_xsa(path, spv, method):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(9):
            info = zipfile.ZipInfo(f"astronomical_{i}.spv", DATE)
            info.compress_type = method if i in (6, 8) else zipfile.ZIP_DEFLATED
            data = spv if i in (6, 8) else (b"v_kind stage" if i == 7 else b"other stage %d" % i)
            z.writestr(info, data)


def fixtures():
    """Return {file name: bytes} of all fixtures."""
    out = {}
    for name, spv, method in [("gains_stored.xsa", make_spv(GAINS), zipfile.ZIP_STORED),
                              ("gains_deflated.xsa", make_spv(GAINS), zipfile.ZIP_DEFLATED),
                              ("no_gains.xsa", make_spv({200: 1.0}), zipfile.ZIP_STORED)]:
        tmp = os.path.join(HERE, name + ".tmp")
        write_xsa(tmp, spv, method)
        with open(tmp, "rb") as f:
            out[name] = f.read()
        os.remove(tmp)
    return out


if __name__ == "__main__":
    for name, data in fixtures().items():
        with open(os.path.join(HERE, name), "wb") as f:
            f.write(data)
        print(f"wrote {name} ({len(data)} bytes)")
