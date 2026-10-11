import sys

import pytest

from urania import paths, syscheck, tools
from urania.errors import ToolMissing


def test_run_all_returns_items(tmp_path):
    items = syscheck.run_all(str(tmp_path))
    names = [i.name for i in items]
    assert names[0] == "System"
    assert "Disk space" in names and "Output folder" in names
    assert all(i.status in (syscheck.OK, syscheck.WARN, syscheck.FAIL) for i in items)


def test_missing_tool_gives_install_hint(monkeypatch):
    def missing(name, tools_dir=None):
        raise ToolMissing(f"{name} not found")
    monkeypatch.setattr(tools, "find_tool", missing)
    items = syscheck.check_tools()
    assert [i.status for i in items] == [syscheck.FAIL] * 3
    assert all("Vulkan SDK" in i.fix or "apt install" in i.fix for i in items)


def test_tool_that_does_not_run(monkeypatch, tmp_path):
    fake = tmp_path / "glslangValidator.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(tools, "find_tool", lambda name, tools_dir=None: str(fake))
    monkeypatch.setattr(tools, "tool_version", lambda path, name=None: "unknown")
    monkeypatch.setattr(syscheck.os, "access", lambda p, m: True)
    assert syscheck.check_tools()[0].status == syscheck.FAIL


def test_missing_package_offers_pip(monkeypatch):
    real_import = syscheck.importlib.import_module

    def fake_import(name):
        if name == "tkinterdnd2":
            raise ImportError("No module named tkinterdnd2")
        return real_import(name)
    monkeypatch.setattr(syscheck.importlib, "import_module", fake_import)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    items = {i.name: i for i in syscheck.check_packages()}
    bad = items["Package tkinterdnd2"]
    assert bad.status == syscheck.FAIL
    assert bad.fix_command[:4] == [sys.executable, "-m", "pip", "install"]
    assert "tkinterdnd2" in bad.fix_command


def test_frozen_app_skips_python_checks(monkeypatch):
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    assert syscheck.check_python() is None
    assert syscheck.check_packages() == []


def test_plugin_check(monkeypatch):
    monkeypatch.setattr(paths, "plugin_binaries", lambda base=None: {})
    assert syscheck.check_plugin().status == syscheck.FAIL
    monkeypatch.setattr(paths, "plugin_binaries", lambda base=None: {"win_x64": "x", "lin_x64": "y"})
    assert syscheck.check_plugin().status == syscheck.OK


def test_low_disk_space(monkeypatch, tmp_path):
    class Usage:
        free = 10 << 20
    monkeypatch.setattr(syscheck.shutil, "disk_usage", lambda p: Usage())
    items = {i.name: i for i in syscheck.check_output_dir(str(tmp_path))}
    assert items["Disk space"].status == syscheck.FAIL


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_glibc_check_on_linux():
    assert syscheck.check_glibc().status in (syscheck.OK, syscheck.WARN, syscheck.FAIL)


def test_run_fix_without_command():
    ok, text = syscheck.run_fix(syscheck.Item("x", syscheck.FAIL, "d", "do this"))
    assert not ok and "do this" in text
