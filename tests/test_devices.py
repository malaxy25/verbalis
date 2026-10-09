"""Device selection, including macOS where the others' voices come from a virtual input device."""

from types import SimpleNamespace as NS

import pytest

from verbalis.audio import devices


class FakeSoundcard:
    def __init__(self, mics, speakers):
        self.mics = [NS(name=n, id=n, isloopback=False) for n in mics]
        self.speakers = [NS(name=n, id=n) for n in speakers]

    def all_microphones(self, include_loopback=False):
        loop = [NS(name=f"Loopback {s.name}", id=s.id, isloopback=True) for s in self.speakers]
        return self.mics + (loop if include_loopback else [])

    def all_speakers(self):
        return self.speakers

    def default_microphone(self):
        return self.mics[0]

    def default_speaker(self):
        return self.speakers[0]


def use(monkeypatch, platform, mics, speakers=("Lautsprecher",)):
    monkeypatch.setattr(devices.sys, "platform", platform)
    sc = FakeSoundcard(mics, speakers)
    monkeypatch.setattr(devices, "soundcard_module", lambda: sc)
    return sc


def test_windows_uses_loopback_of_speakers(monkeypatch):
    use(monkeypatch, "win32", ["Headset-Mikrofon"], ["Headset", "Realtek"])
    sel = devices.select(None, "Realtek")
    assert sel.loopback.isloopback and sel.loopback.id == "Realtek"
    assert devices.device_names()["speakers"] == ["Headset", "Realtek"]


def test_mac_uses_virtual_input_device(monkeypatch):
    use(monkeypatch, "darwin", ["MacBook-Mikrofon", "BlackHole 2ch"])
    names = devices.device_names()
    assert names["speakers"] == ["MacBook-Mikrofon", "BlackHole 2ch"]
    assert names["default_speakers"] == "BlackHole 2ch" and names["virtual_device"]
    sel = devices.select(None, None)                    # BlackHole is found by itself
    assert sel.microphone.name == "MacBook-Mikrofon" and sel.loopback.name == "BlackHole 2ch"


def test_mac_without_virtual_device_explains_what_to_do(monkeypatch):
    use(monkeypatch, "darwin", ["MacBook-Mikrofon"])
    assert devices.device_names()["virtual_device"] is False
    with pytest.raises(ValueError, match="BlackHole"):
        devices.select(None, None)
    with pytest.raises(ValueError, match="dasselbe Gerät"):
        devices.select(None, "MacBook-Mikrofon")
