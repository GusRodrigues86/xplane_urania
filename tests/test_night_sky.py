import math
import os

import numpy as np
import pytest

from urania.engine import night_sky as ns
from urania.errors import UraniaError


# --- Encoding: the shader decode (float32) must give back what the encoder wrote ---------

@pytest.mark.parametrize("k", range(0, 90))
@pytest.mark.parametrize("mag", [-1.46, -0.05, 0.0, 0.03, 1.35, 4.99, 6.5])
def test_star_code_round_trip(mag, k):
    kind, dec_mag, dec_k, color, size = ns.decode_like_shader(ns.encode_star(mag, k))
    assert kind == "star"
    assert dec_k == k
    assert abs(dec_mag - mag) <= 0.0089 + 0.005


@pytest.mark.parametrize("color", range(4))
@pytest.mark.parametrize("size", range(25))
def test_haze_code_round_trip(color, size):
    for mag in (0.0, 2.3, 5.7, 9.4, 12.0):
        kind, dec_mag, k, dec_color, dec_size = ns.decode_like_shader(ns.encode_haze(mag, color, size))
        assert kind == "haze"
        assert (dec_color, dec_size) == (color, size)
        assert 90 <= k <= 99
        assert abs(dec_mag - round(mag, 1)) < 1e-6


def test_haze_negative_magnitude_is_clamped_to_zero():
    kind, mag, *_ = ns.decode_like_shader(ns.encode_haze(-2.0, 1, 5))
    assert kind == "haze" and mag == 0.0


def test_bv_to_k_range_and_order():
    assert ns.bv_to_k(-5) == 1
    assert ns.bv_to_k(5) == 89
    ks = [ns.bv_to_k(bv) for bv in np.linspace(-0.4, 2.0, 50)]
    assert ks == sorted(ks)


@pytest.mark.parametrize("diam,size", [(0.05, 0), (0.1, 0), (0.125, 1), (1.82, 13), (5.55, 18), (100, 24)])
def test_size_class(diam, size):
    assert ns.size_class(diam) == size


# --- Astronomy helpers -----------------------------------------------------------------

def test_precess_zero_time_is_identity():
    ra, dec = ns.precess(123.4, -45.6, T=0.0)
    assert ra == pytest.approx(123.4) and dec == pytest.approx(-45.6)


def test_precess_round_trip():
    ra, dec = ns.precess(*ns.precess(83.82, -5.39, T=0.25), T=-0.25)
    assert ra == pytest.approx(83.82, abs=1e-4) and dec == pytest.approx(-5.39, abs=1e-4)


def test_precess_vega_j2025():
    # Vega J2000 (279.2347, 38.7837). Annual precession m + n sin(RA) tan(Dec) = 2.01 s/yr in RA,
    # n cos(RA) = 3.1 arcsec/yr in Dec. 25 years: RA +0.21 deg, Dec +0.022 deg.
    ra, dec = ns.precess(279.2347, 38.7837)
    assert ra - 279.2347 == pytest.approx(0.21, abs=0.01)
    assert dec - 38.7837 == pytest.approx(0.023, abs=0.01)


def test_lattice_count_and_range():
    pts = list(ns.lattice(10.0))
    assert len(pts) == int(41253 / 100)
    assert all(0 <= ra < 24 and -90 <= dec <= 90 for ra, dec in pts)


def test_is_row():
    assert ns.is_row("6.7708  -16.752 -1.46 Sirius".split())
    assert not ns.is_row("99".split())
    assert not ns.is_row("740 Version - x".split())


# --- Steps -----------------------------------------------------------------------------

def test_color_code_stars_matches_catalog(fake_dat, fake_catalog):
    lines = ns.read_lines(fake_dat)
    out, n_star, n_hit = ns.color_code_stars(lines, ns.load_catalog(fake_catalog))
    assert n_star == 7
    assert n_hit == 6                     # "Zeta" has no B-V in the catalog
    rows = [l for l in out if ns.is_row(l.split())]
    assert rows[0].endswith("Alpha")
    k_alpha = ns.decode_like_shader(float(rows[0].split()[2]))[2]
    assert k_alpha == ns.bv_to_k(0.0)
    assert ns.decode_like_shader(float(rows[-1].split()[2]))[2] == 0   # unmatched star stays white


def test_dso_entries_count_and_classes():
    entries = ns.dso_entries()
    assert len(entries) == 63            # reference: deep-sky=63
    classes = {ns.decode_like_shader(e[2])[3] for e in entries}
    assert classes == {1, 2, 3}


def test_airglow_layer():
    entries = ns.airglow_layer()
    assert len(entries) == 6600          # reference: airglow=6600
    assert {e[3] for e in entries} == {"SKY"}


def test_assemble_keeps_header_and_end_marker(fake_dat):
    lines = ns.read_lines(fake_dat)
    text = ns.assemble(lines, [(1.0, 2.0, ns.encode_haze(3.0, 0, 13), "MW")])
    out = text.splitlines()
    assert out[:4] == lines[:4]
    assert out[-2:] == ["", "99"]
    mags = [float(l.split()[2]) for l in out if ns.is_row(l.split())]
    assert mags == sorted(mags)


def test_assemble_without_end_marker_raises():
    with pytest.raises(UraniaError, match="end marker"):
        ns.assemble(["I", " 1.0000  2.000 1.00 X"], [])


def test_load_catalog_bad_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(UraniaError, match="stars.8.json"):
        ns.load_catalog(str(p))


def test_load_map_rejects_bad_file(tmp_path):
    p = tmp_path / "x.exr"
    p.write_bytes(b"not an exr")
    with pytest.raises(UraniaError):
        ns.load_map(str(p))


def test_build_dat_small(tmp_path, fake_dat, fake_catalog, fake_exr):
    log = []
    r = ns.build_dat(fake_dat, fake_catalog, fake_exr, str(tmp_path / "out"), log=log.append)
    assert set(r.outputs) == {ns.DAT_PLAIN, ns.DAT_AIRGLOW}
    assert r.stars == 7 and r.matched == 6
    assert r.rows[ns.DAT_AIRGLOW] - r.rows[ns.DAT_PLAIN] == 6600
    assert any("Step E" in l for l in log)
    for path in r.outputs.values():
        check = ns.verify(path)
        assert check.errors == []
        assert check.stars == 7 and check.haze > 63
        with open(path, "rb") as f:
            assert b"\r\n" not in f.read()
    assert os.path.isfile(r.report)


def test_build_dat_is_reproducible(tmp_path, fake_dat, fake_catalog, fake_exr):
    a = ns.build_dat(fake_dat, fake_catalog, fake_exr, str(tmp_path / "a"))
    b = ns.build_dat(fake_dat, fake_catalog, fake_exr, str(tmp_path / "b"))
    for name in a.outputs:
        assert ns.sha256(a.outputs[name]) == ns.sha256(b.outputs[name])


def test_compare_identical(tmp_path, fake_dat):
    assert ns.compare(fake_dat, fake_dat)[-1] == "files are byte-identical"
