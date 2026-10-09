"""macOS system audio: the recorder side of the Swift helper, with a fake helper speaking its protocol."""

import sys
import textwrap

import numpy as np
import pytest

from verbalis.audio import devices, mac_tap


def fake_helper(tmp_path, body):
    script = tmp_path / "fake_tap.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


STREAM = """
    import sys, struct, time
    sys.stderr.write('{"samplerate": 44100, "channels": 2}\\n'); sys.stderr.flush()
    chunk = struct.pack("<441f", *([0.5] * 441))
    for _ in range(400):
        sys.stdout.buffer.write(chunk); sys.stdout.buffer.flush()
"""


def test_tap_device_delivers_blocks_at_the_target_rate(tmp_path):
    device = mac_tap.TapDevice(fake_helper(tmp_path, STREAM))
    with device.recorder(samplerate=48_000, blocksize=4_800) as rec:
        blocks = [rec.record(numframes=4_800) for _ in range(5)]
    assert all(b.shape == (4_800, 1) and b.dtype == np.float32 for b in blocks)
    assert abs(float(blocks[-1].mean()) - 0.5) < 0.01          # 44.1 kHz resampled to 48 kHz


def test_tap_device_reports_helper_errors_in_german(tmp_path):
    failing = fake_helper(tmp_path, """
        import sys
        sys.stderr.write('{"error": "Systemton-Tap konnte nicht erstellt werden (OSStatus -1)"}\\n')
        sys.exit(1)
    """)
    with pytest.raises(RuntimeError, match="Systemton kann nicht aufgenommen werden.*Tap"):
        with mac_tap.TapDevice(failing).recorder(samplerate=48_000):
            pass


def test_tap_device_notices_when_helper_stops(tmp_path):
    short = fake_helper(tmp_path, """
        import sys, struct
        sys.stderr.write('{"samplerate": 48000, "channels": 2}\\n'); sys.stderr.flush()
        sys.stdout.buffer.write(struct.pack("<100f", *([0.1] * 100)))
    """)
    with mac_tap.TapDevice(short).recorder(samplerate=48_000) as rec:
        with pytest.raises(RuntimeError, match="Systemton-Aufnahme wurde beendet"):
            rec.record(numframes=4_800)


def test_mac_prefers_system_audio_when_available(monkeypatch):
    from test_devices import use
    use(monkeypatch, "darwin", ["MacBook-Mikrofon", "BlackHole 2ch"])
    monkeypatch.setattr(mac_tap, "available", lambda: True)
    monkeypatch.setattr(mac_tap.TapDevice, "__init__", lambda self, command=None: None)
    names = devices.device_names()
    assert names["speakers"][0] == mac_tap.SYSTEM_AUDIO and names["default_speakers"] == mac_tap.SYSTEM_AUDIO
    assert names["system_audio"] is True
    sel = devices.select(None, None)
    assert isinstance(sel.loopback, mac_tap.TapDevice) and sel.microphone.name == "MacBook-Mikrofon"
    assert devices.select(None, "BlackHole 2ch").loopback.name == "BlackHole 2ch"   # still selectable


def test_old_mac_falls_back_to_virtual_device(monkeypatch):
    from test_devices import use
    use(monkeypatch, "darwin", ["MacBook-Mikrofon"])
    monkeypatch.setattr(mac_tap, "available", lambda: False)
    with pytest.raises(ValueError, match="macOS 14.2"):
        devices.select(None, mac_tap.SYSTEM_AUDIO)


def test_macos_version_check(monkeypatch):
    monkeypatch.setattr(mac_tap.platform, "mac_ver", lambda: ("14.1.2", ("", "", ""), ""))
    assert mac_tap.macos_version() == (14, 1, 2) and mac_tap.macos_version() < mac_tap.MIN_MACOS
    monkeypatch.setattr(mac_tap.platform, "mac_ver", lambda: ("27.0", ("", "", ""), ""))
    assert mac_tap.macos_version() >= mac_tap.MIN_MACOS
