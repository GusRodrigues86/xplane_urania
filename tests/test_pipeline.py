import os
import zipfile

import pytest

from urania import cli, pipeline
from urania.engine import bundle
from urania.errors import UraniaError

from test_xplane_inputs import make_root


@pytest.fixture
def fake_plugins(tmp_path, monkeypatch):
    plugins = {}
    for plat in ("win_x64", "lin_x64"):
        p = tmp_path / "plugin" / plat / "Urania.xpl"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"fake")
        plugins[plat] = str(p)
    monkeypatch.setattr(bundle.paths, "plugin_binaries", lambda base=None: plugins)
    return plugins


def test_resolve_inputs_needs_originals(tmp_path, fake_catalog, fake_exr):
    req = pipeline.BuildRequest(stars=fake_catalog, milkyway=fake_exr, out_zip=str(tmp_path / "u.zip"))
    with pytest.raises(UraniaError, match="X-Plane folder"):
        pipeline.resolve_inputs(req)


def test_resolve_inputs_rejects_old_xplane(tmp_path, fake_catalog, fake_exr):
    root = make_root(tmp_path, log_line="Log.txt for X-Plane 12.3.0-r1 (build 123001 x)")
    req = pipeline.BuildRequest(stars=fake_catalog, milkyway=fake_exr, out_zip="u.zip", xplane_root=root)
    with pytest.raises(UraniaError, match="too old"):
        pipeline.resolve_inputs(req)
    req.allow_any_version = True
    assert any("too old" in w for w in pipeline.resolve_inputs(req))


def test_resolve_inputs_bad_catalog(tmp_path, fake_exr):
    root = make_root(tmp_path)
    bad = tmp_path / "s.json"
    bad.write_text("{}")
    req = pipeline.BuildRequest(stars=str(bad), milkyway=fake_exr, out_zip="u.zip", xplane_root=root)
    with pytest.raises(UraniaError, match="Star catalog"):
        pipeline.resolve_inputs(req)


@pytest.mark.tools
def test_full_build(tmp_path, fake_catalog, fake_exr, fake_xsa, fake_dat, fake_plugins):
    steps, log = [], []
    req = pipeline.BuildRequest(stars=fake_catalog, milkyway=fake_exr, out_zip=str(tmp_path / "out" / "U.zip"),
                                xsa=fake_xsa, dat=fake_dat, overrides={"VIEWPORT_H": 1440}, airglow=True)
    r = pipeline.run_build(req, log=log.append, step=lambda n, t, title: steps.append(n))
    assert steps == [1, 2, 3, 4, 5]
    assert os.path.isfile(r.zip_path) and os.path.isfile(r.report_path)
    with zipfile.ZipFile(r.zip_path) as z:
        dat = z.read(bundle.PATH_DAT).decode("latin-1")
        assert " SKY" in dat                                   # airglow variant
        readme = z.read(bundle.PATH_README).decode("utf-8")
        assert "Screen height: 1440 px" in readme
    assert any("Self-check OK" in l for l in log)


@pytest.mark.tools
def test_cli_build(tmp_path, fake_catalog, fake_exr, fake_xsa, fake_dat, fake_plugins, capsys):
    out = str(tmp_path / "cli.zip")
    rc = cli.main(["build", "--stars", fake_catalog, "--milkyway", fake_exr, "--xsa", fake_xsa, "--dat", fake_dat,
                   "--out", out, "--set", "STAR_GAIN=0.5"])
    assert rc == 0 and os.path.isfile(out)
    capsys.readouterr()


def test_cli_info_missing_file(tmp_path, capsys):
    assert cli.main(["info", str(tmp_path / "nope.xsa")]) == 1
    assert "ERROR:" in capsys.readouterr().err


def test_cli_errors_are_messages(tmp_path, capsys):
    rc = cli.main(["build", "--stars", "nope.json", "--milkyway", "nope.exr", "--xsa", "a", "--dat", "b",
                   "--out", str(tmp_path / "x.zip")])
    assert rc == 1
    assert "ERROR:" in capsys.readouterr().err


def test_cli_verify(fake_dat, capsys):
    assert cli.main(["verify", fake_dat]) == 0
    assert "star" in capsys.readouterr().out
