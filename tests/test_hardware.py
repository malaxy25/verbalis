"""Processor, memory and graphics card in the diagnosis – with fake system commands."""

import sys
from types import SimpleNamespace

import pytest

import verbalis.hardware as hardware_module

REAL_DESCRIBE = hardware_module.describe     # taken at collection, before conftest replaces it


@pytest.fixture
def hardware(monkeypatch):
    monkeypatch.setattr(hardware_module, "describe", REAL_DESCRIBE)
    return hardware_module


def test_mac_shows_chip_memory_and_graphics_in_the_chip(hardware):
    answers = {"machdep.cpu.brand_string": "Apple M2 Pro\n", "hw.memsize": str(32 * 1024 ** 3)}

    def run(command, **kwargs):
        return SimpleNamespace(stdout=answers[command[-1]])
    info = hardware.describe("darwin", run=run)
    assert info["Prozessor"].startswith("Apple M2 Pro")
    assert info["Arbeitsspeicher"] == "32 GB" and info["Grafikkarte"] == "im Chip (Apple M2 Pro)"


def test_failing_commands_give_unknown_instead_of_an_error(hardware):
    def broken(command, **kwargs):
        raise OSError("no sysctl")
    info = hardware.describe("darwin", run=broken)
    assert info["Arbeitsspeicher"] == "unbekannt" and info["Grafikkarte"] == "unbekannt"


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows registry and memory status")
def test_windows_reads_processor_memory_and_graphics(hardware):
    def run(command, **kwargs):
        assert command[0] == "powershell"
        return SimpleNamespace(stdout="AMD Radeon(TM) Graphics\r\nVirtual Display\r\n")
    info = hardware.describe("win32", run=run)
    assert info["Prozessor"] != "unbekannt" and info["Arbeitsspeicher"].endswith(" GB")
    assert info["Grafikkarte"] == "AMD Radeon(TM) Graphics, Virtual Display"


def test_linux_graphics_card_from_lspci():
    """Ubuntu showed «Grafikkarte: unbekannt» on a ThinkPad with an Nvidia T500."""
    from types import SimpleNamespace

    from verbalis.hardware import _linux_gpu

    out = ("00:02.0 VGA compatible controller: Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics] (rev 01)\n"
           "00:1f.3 Audio device: Intel Corporation Tiger Lake-LP Smart Sound Technology Audio Controller (rev 20)\n"
           "01:00.0 3D controller: NVIDIA Corporation TU117GLM [T500 Mobile] (rev a1)\n")
    assert _linux_gpu(lambda *a, **k: SimpleNamespace(stdout=out)) == \
        "Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics], NVIDIA Corporation TU117GLM [T500 Mobile]"
