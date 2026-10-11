import os
import zipfile

import pytest

from urania.engine import bundle, night_sky, shaders
from urania.errors import UraniaError

from test_spirv import ALL, make_spv, write_xsa


@pytest.fixture
def built(tmp_path, fake_dat, fake_catalog, fake_exr):
    """Built star file + a patched and an original xsa (synthetic) + fake plugin binaries."""
    dat = night_sky.build_dat(fake_dat, fake_catalog, fake_exr, str(tmp_path / "dat")).outputs[night_sky.DAT_PLAIN]
    xsa = write_xsa(tmp_path / "patched.xsa", make_spv(ALL))
    orig = write_xsa(tmp_path / "orig.xsa", make_spv(ALL), stage7=b"stock stage")
    plugins = {}
    for plat in ("win_x64", "lin_x64"):
        p = tmp_path / "plugin" / plat / "Urania.xpl"
        p.parent.mkdir(parents=True)
        p.write_bytes(f"fake {plat} plugin".encode())
        plugins[plat] = str(p)
    return {"xsa": xsa, "dat": dat, "orig_xsa": orig, "orig_dat": fake_dat, "plugins": plugins}


def make(built, out, **kw):
    args = dict(xsa=built["xsa"], dat=built["dat"], original_xsa=built["orig_xsa"],
                original_dat=built["orig_dat"], settings=shaders.DEFAULT_SETTINGS, out_zip=out,
                plugins=built["plugins"])
    args.update(kw)
    return bundle.make_bundle(**args)


def test_layout(tmp_path, built):
    r = make(built, str(tmp_path / "Urania_XP12.zip"))
    with zipfile.ZipFile(r.zip_path) as z:
        names = z.namelist()
        assert names == sorted(names)
        assert set(names) == {
            "Resources/shaders/bin/spv/astronomical.xsa",
            "Resources/default data/earth_astro.dat",
            "Resources/plugins/Urania/win_x64/Urania.xpl",
            "Resources/plugins/Urania/lin_x64/Urania.xpl",
            "Resources/plugins/Urania/backup/astronomical.xsa",
            "Resources/plugins/Urania/backup/earth_astro.dat",
            "Resources/plugins/Urania/install.txt",
            "Resources/plugins/Urania/Urania_README.txt",
            "Resources/plugins/Urania/licenses/d3-celestial-LICENSE.txt",
            "Resources/plugins/Urania/licenses/imgui-LICENSE.txt",
            "Resources/plugins/Urania/licenses/NASA-SVS-credit.txt",
        }
        assert z.read("Resources/plugins/Urania/backup/earth_astro.dat") == open(built["orig_dat"], "rb").read()
        assert z.read("Resources/default data/earth_astro.dat") == open(built["dat"], "rb").read()
        readme = z.read("Resources/plugins/Urania/Urania_README.txt").decode("utf-8")
        assert "\r\n" in readme and "Screen height: 1080 px" in readme and "{" not in readme
        manifest = z.read("Resources/plugins/Urania/install.txt").decode()
        assert f"dat_size {os.path.getsize(built['dat'])}" in manifest
        xpl = z.getinfo("Resources/plugins/Urania/lin_x64/Urania.xpl")
        assert (xpl.external_attr >> 16) == 0o755


def test_reproducible(tmp_path, built):
    a = make(built, str(tmp_path / "a" / "Urania_XP12.zip"))     # same name: the README contains it
    b = make(built, str(tmp_path / "b" / "Urania_XP12.zip"))
    assert a.sha256 == b.sha256


def test_refuses_unpatched_shader(tmp_path, built):
    with pytest.raises(UraniaError, match="X-Plane original"):
        make(built, str(tmp_path / "a.zip"), xsa=built["orig_xsa"])


def test_refuses_patched_backup(tmp_path, built):
    with pytest.raises(UraniaError, match="not the X-Plane original"):
        make(built, str(tmp_path / "a.zip"), original_xsa=built["xsa"])


def test_refuses_original_dat(tmp_path, built):
    with pytest.raises(UraniaError, match="no haze rows"):
        make(built, str(tmp_path / "a.zip"), dat=built["orig_dat"])


def test_refuses_missing_plugins(tmp_path, built):
    with pytest.raises(UraniaError, match="plugin binaries"):
        make(built, str(tmp_path / "a.zip"), plugins={})
