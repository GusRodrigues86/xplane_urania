"""GuiModel: the rules of the window, without Tk."""
import os

import pytest

from urania import gui, syscheck

from test_spirv import ALL, make_spv, write_xsa
from test_xplane_inputs import make_root


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setattr(gui.xplane, "find_installs", lambda: [])
    m = gui.GuiModel(out_zip=str(tmp_path / "Urania_XP12.zip"))
    m.checks = [syscheck.Item("System", syscheck.OK, "ok")]
    return m


def test_new_model_is_not_ready(model):
    assert not model.can_build()
    assert len(model.problems()) >= 4


def test_xplane_folder_fills_originals(model, tmp_path):
    root = make_root(tmp_path)
    model.set_path("xplane", root)
    assert model.slots["xplane"].status == "ok"
    assert model.slots["xsa"].status == "ok" and model.slots["xsa"].auto
    assert model.slots["dat"].status == "ok" and model.slots["dat"].auto


def test_patched_xplane_marks_originals_missing(model, tmp_path):
    root = make_root(tmp_path, xsa_patched=True)
    model.set_path("xplane", root)
    assert model.slots["xsa"].status == "fail"
    assert "Update X-Plane" in model.slots["xsa"].message


def test_ready_when_all_inputs_ok(model, tmp_path, fake_catalog, fake_exr):
    model.set_path("xplane", make_root(tmp_path))
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    assert model.problems() == []
    assert model.can_build()
    req = model.request()
    assert req.stars == fake_catalog and req.overrides["VIEWPORT_H"] == model.screen_height
    assert req.overrides["STAR_GAIN"] == 1.0


def test_originals_by_hand_without_xplane(model, tmp_path, fake_dat, fake_catalog, fake_exr):
    model.set_path("xsa", write_xsa(tmp_path / "a.xsa", make_spv(ALL), stage7=b"stock"))
    model.set_path("dat", fake_dat)
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    assert model.can_build()
    assert model.request().xplane_root is None


def test_blocking_system_check(model, tmp_path, fake_catalog, fake_exr):
    model.set_path("xplane", make_root(tmp_path))
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    model.checks = [syscheck.Item("spirv-val", syscheck.FAIL, "not found", "install it")]
    assert not model.can_build()
    assert "spirv-val" in model.problems()[0]


def test_bad_options(model, tmp_path, fake_catalog, fake_exr):
    model.set_path("xplane", make_root(tmp_path))
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    model.screen_height = 100
    assert any("Screen height" in p for p in model.problems())
    model.screen_height = 1440
    model.out_zip = "x.rar"
    assert any(".zip" in p for p in model.problems())


def test_building_blocks_second_build(model, tmp_path, fake_catalog, fake_exr):
    model.set_path("xplane", make_root(tmp_path))
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    model.building = True
    assert not model.can_build()


def test_drop_routes_files(model, tmp_path, fake_catalog, fake_exr, fake_dat):
    changed = model.drop([fake_catalog, fake_exr, fake_dat, str(tmp_path / "notes.txt")])
    assert changed == ["stars", "milkyway", "dat"]
    assert model.slots["stars"].status == "ok"


@pytest.mark.parametrize("name,key", [
    ("stars.8.json", "stars"), ("d3-celestial-0.7.35.tgz", "stars"), ("milkyway_2020_4k.exr", "milkyway"),
    ("astronomical.xsa", "xsa"), ("earth_astro.dat", "dat"), ("earth_astro.dat.original", "dat"),
    ("readme.txt", None),
])
def test_guess_slot(name, key):
    assert gui.guess_slot(os.path.join("nowhere", name)) == key


def test_folder_dropped_on_file_slot(model, tmp_path):
    assert model.set_path("stars", str(tmp_path)).status == "fail"


def test_reset_gains(model):
    model.gains["STAR_GAIN"] = 9.0
    model.set_gain_text("MW_GAIN", "x")
    model.reset_gains()
    assert model.gains["STAR_GAIN"] == 1.0
    assert model.bad_gains == {}


@pytest.mark.parametrize("text,value", [("2", 2.0), (" 0.5 ", 0.5), ("1e1", 10.0)])
def test_gain_text_valid(model, text, value):
    assert model.set_gain_text("MW_GAIN", text) == ""
    assert model.gains["MW_GAIN"] == value


@pytest.mark.parametrize("text,msg", [
    ("0,5", "not a comma"), ("1,000", "not a comma"),
    ("", "more than 0"), ("abc", "more than 0"), ("0", "more than 0"), ("-1", "more than 0"),
    ("inf", "more than 0"), ("nan", "more than 0"),
])
def test_gain_text_invalid_blocks_build(model, tmp_path, fake_catalog, fake_exr, text, msg):
    model.set_path("xplane", make_root(tmp_path))
    model.set_path("stars", fake_catalog)
    model.set_path("milkyway", fake_exr)
    assert msg in model.set_gain_text("NEBULA_GAIN", text)
    assert model.gains["NEBULA_GAIN"] == 40.0                          # the last valid value stays
    assert model.problems() == [f"Nebulae: {model.bad_gains['NEBULA_GAIN']}"]
    assert not model.can_build()
    model.set_gain_text("NEBULA_GAIN", "10")
    assert model.can_build() and model.request().overrides["NEBULA_GAIN"] == 10.0


def test_find_installs_picks_first(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    monkeypatch.setattr(gui.xplane, "find_installs", lambda: [root])
    m = gui.GuiModel(out_zip=str(tmp_path / "u.zip"))
    assert m.find_installs() == [root]
    assert m.slots["xplane"].path == root
