"""Contract between the Urania app (Python) and the Urania plugin (C++).

The plugin must read and change the gains in the astronomical.xsa that the app writes.
These tests run the C++ test program (plugin/build/.../urania_tests) on files made by the
Python engine. They skip if the plugin tests are not built (python scripts/build_plugin.py).
"""
import glob
import os
import shutil
import subprocess
import zipfile

import pytest

from urania.engine import shaders, spirv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURES = os.path.join(ROOT, "plugin", "tests", "fixtures")


def find_test_binary():
    exe = "urania_tests.exe" if os.name == "nt" else "urania_tests"
    hits = sorted(glob.glob(os.path.join(ROOT, "plugin", "build", "**", exe), recursive=True), key=os.path.getmtime)
    return hits[-1] if hits else None


@pytest.fixture(scope="module")
def cpp():
    exe = find_test_binary()
    if not exe:
        pytest.skip("plugin tests not built (python scripts/build_plugin.py)")
    return exe


def cpp_read(cpp, xsa):
    r = subprocess.run([cpp, "--read-gains", xsa], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return {int(a): float(b) for a, b in (line.split() for line in r.stdout.splitlines())}


def test_fixtures_are_up_to_date():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_fixtures", os.path.join(FIXTURES, "make_fixtures.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, data in mod.fixtures().items():
        with open(os.path.join(FIXTURES, name), "rb") as f:
            assert f.read() == data, f"{name} is old: run python plugin/tests/fixtures/make_fixtures.py"


def test_cpp_reads_python_fixture(cpp):
    assert cpp_read(cpp, os.path.join(FIXTURES, "gains_stored.xsa")) == pytest.approx(
        {200: 0.35, 201: 3.0, 202: 40.0, 203: 25.0, 204: 0.0})


@pytest.mark.tools
def test_cpp_reads_and_writes_built_xsa(cpp, tmp_path, fake_xsa):
    r = shaders.build_xsa(fake_xsa, str(tmp_path / "out"),
                          shaders.resolve_settings({"NEBULA_GAIN": 12.5, "HAZE_EMISSIVE": 7}))
    assert cpp_read(cpp, r.xsa) == pytest.approx({200: 0.35, 201: 3.0, 202: 12.5, 203: 40.0, 204: 7.0})

    # The plugin writes new gains in place: Python must read them back, and the ZIP CRCs must be right.
    xsa = str(tmp_path / "astronomical.xsa")
    shutil.copy(r.xsa, xsa)
    w = subprocess.run([cpp, "--write-gains", xsa, "0.5", "2", "15", "60"], capture_output=True, text=True)
    assert w.returncode == 0, w.stderr
    assert spirv.read_gains(xsa) == pytest.approx(
        {"STAR_GAIN": 0.5, "MW_GAIN": 2.0, "NEBULA_GAIN": 15.0, "GALAXY_GAIN": 60.0, "HAZE_EMISSIVE": 7.0})
    with zipfile.ZipFile(xsa) as z:
        assert z.testzip() is None
    assert os.path.getsize(xsa) == os.path.getsize(r.xsa)
    assert os.path.isfile(xsa + ".before_urania")
