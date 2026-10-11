import json
import os
import tarfile

import pytest

from urania import inputs, xplane

from conftest import write_dat
from test_spirv import ALL, make_spv, write_xsa


def make_root(tmp_path, log_line="Log.txt for X-Plane 12.4.4-r1-abcdef (build 124411 Intel 64-bit, Vulkan x)",
              xsa_patched=False, dat_haze=False):
    root = tmp_path / "X-Plane 12"
    (root / "Resources" / "shaders" / "bin" / "spv").mkdir(parents=True)
    (root / "Resources" / "default data").mkdir(parents=True)
    (root / "X-Plane.exe").write_bytes(b"")
    if log_line is not None:
        (root / "Log.txt").write_text(log_line + "\nmore\n")
    write_xsa(root / xplane.XSA_REL, make_spv(ALL), stage7=b"v_kind" if xsa_patched else b"stock")
    stars = [(6.7708, -16.752, -1.46, "A"), (1.0, 2.0, 2.0391, "MW")] if dat_haze else None
    write_dat(root / xplane.DAT_REL, *([stars] if stars else []))
    return str(root)


@pytest.mark.parametrize("line,version", [
    ("Log.txt for X-Plane 12.4.4-b4-fbbdaacd (build 124414 Intel 64-bit, Vulkan 55)", (12, 4, 4)),
    ("Log.txt for X-Plane 12.4.3-r2-15ff1e4d (build 124311 Intel 64-bit, Vulkan d5)", (12, 4, 3)),
    ("Log.txt for X-Plane 12.10.0 (build 121000 Intel 64-bit)", (12, 10, 0)),
])
def test_parse_version(line, version):
    v = xplane.parse_version(line)
    assert v.tuple == version


def test_parse_version_tag_and_build():
    v = xplane.parse_version("Log.txt for X-Plane 12.4.4-b4-fbbdaacd (build 124414 Intel 64-bit)")
    assert v.tag == "b4-fbbdaacd" and v.build == 124414 and str(v) == "12.4.4-b4-fbbdaacd"


def test_parse_version_unknown():
    assert xplane.parse_version("hello") is None
    assert xplane.parse_version("") is None


def test_version_ok():
    assert xplane.version_ok(xplane.parse_version("X-Plane 12.4.4-r1 (build 1"))
    assert xplane.version_ok(xplane.parse_version("X-Plane 13.0.0 (build 1"))
    assert not xplane.version_ok(xplane.parse_version("X-Plane 12.4.3-r2 (build 1"))
    assert not xplane.version_ok(None)


def test_install_list(tmp_path):
    root = make_root(tmp_path)
    lst = tmp_path / "x-plane_install_12.txt"
    lst.write_text(f"{root}/\n\nD:/does/not/exist/\n")
    assert xplane.parse_install_list(lst.read_text())[0] == os.path.normpath(root)
    assert xplane.find_installs(str(lst)) == [os.path.normpath(root)]
    assert xplane.find_installs(str(tmp_path / "missing.txt")) == []


def test_validate_xplane(tmp_path):
    assert inputs.validate_xplane(make_root(tmp_path)).ok
    old = inputs.validate_xplane(make_root(tmp_path / "o", log_line="Log.txt for X-Plane 12.4.3-r2 (build 124311 x)"))
    assert not old.ok and "too old" in old.message
    unknown = inputs.validate_xplane(make_root(tmp_path / "u", log_line=None))
    assert unknown.ok and "12.4.4" in unknown.warning
    assert not inputs.validate_xplane(str(tmp_path)).ok


def test_custom_data_warning(tmp_path):
    root = make_root(tmp_path)
    assert xplane.custom_data_warning(root) == ""
    os.makedirs(os.path.join(root, "Custom Data"))
    open(os.path.join(root, xplane.CUSTOM_DAT_REL), "w").close()
    assert "Custom Data" in inputs.validate_xplane(root).warning


def test_autodetect_originals(tmp_path):
    root = make_root(tmp_path)
    found = inputs.autodetect(root)
    assert found["xsa"][0] == os.path.join(root, xplane.XSA_REL)
    assert found["dat"][0] == os.path.join(root, xplane.DAT_REL)


def test_autodetect_uses_backups_when_installed_files_are_patched(tmp_path):
    root = make_root(tmp_path, xsa_patched=True, dat_haze=True)
    assert inputs.autodetect(root)["xsa"][0] is None
    assert "Update X-Plane" in inputs.autodetect(root)["xsa"][1]
    backup = os.path.join(root, xplane.PLUGIN_REL, "backup")
    os.makedirs(backup)
    write_xsa(os.path.join(backup, "astronomical.xsa"), make_spv(ALL), stage7=b"stock")
    write_dat(os.path.join(root, xplane.DAT_REL + ".original"))
    found = inputs.autodetect(root)
    assert found["xsa"] == (os.path.join(backup, "astronomical.xsa"), "Urania backup")
    assert found["dat"][0].endswith(".original")


def test_validate_dat(tmp_path, fake_dat):
    assert inputs.validate_dat(fake_dat).ok
    changed = write_dat(tmp_path / "c.dat", [(1.0, 2.0, 2.0391, "MW")])
    assert "already changed" in inputs.validate_dat(changed).message
    junk = tmp_path / "junk.dat"
    junk.write_text("hello\n")
    assert not inputs.validate_dat(str(junk)).ok


def test_validate_xsa(tmp_path):
    assert inputs.validate_xsa(write_xsa(tmp_path / "a.xsa", make_spv(ALL), stage7=b"stock")).ok
    assert "already patched" in inputs.validate_xsa(write_xsa(tmp_path / "b.xsa", make_spv(ALL))).message
    assert not inputs.validate_xsa(str(tmp_path / "none.xsa")).ok


def test_validate_stars_json_and_tgz(tmp_path, fake_catalog):
    assert inputs.validate_stars(fake_catalog).ok
    tgz = tmp_path / "d3-celestial-0.7.35.tgz"
    with tarfile.open(tgz, "w:gz") as t:
        t.add(fake_catalog, arcname=inputs.D3_MEMBER)
    assert inputs.validate_stars(str(tgz)).ok
    out = inputs.extract_stars(str(tgz), str(tmp_path / "x"))
    assert json.load(open(out))["features"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"features": [{"properties": {"mag": 1}}]}))
    assert not inputs.validate_stars(str(bad)).ok


def test_validate_milkyway(tmp_path, fake_exr):
    assert inputs.validate_milkyway(fake_exr).ok
    bad = tmp_path / "x.exr"
    bad.write_bytes(b"nope")
    assert not inputs.validate_milkyway(str(bad)).ok


def test_every_spec_has_guidance():
    for spec in inputs.SPECS:
        assert spec.where and spec.title
        assert spec.key in inputs.VALIDATORS
    assert inputs.SPEC_BY_KEY["stars"].url.startswith("https://registry.npmjs.org/d3-celestial")
    assert inputs.SPEC_BY_KEY["milkyway"].url == "https://svs.gsfc.nasa.gov/4851"
