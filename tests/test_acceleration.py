"""Experimental tests in the diagnosis: speed test, MLX wheels, notification and call-detection checks."""

from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from verbalis import acceleration
from verbalis.transcription import mlx

from test_service import make_service, wait_until


def test_mac_wheel_picks_the_binary_for_this_macos():
    names = ["mlx-0.32.4-cp312-cp312-macosx_14_0_arm64.whl", "mlx-0.32.4-cp312-cp312-macosx_15_0_arm64.whl",
             "mlx-0.32.4-cp312-cp312-macosx_26_0_arm64.whl", "mlx-0.32.4-cp313-cp313-macosx_15_0_arm64.whl"]
    assert mlx.mac_wheel(names, (3, 12), (15, 5)) == "mlx-0.32.4-cp312-cp312-macosx_15_0_arm64.whl"
    assert mlx.mac_wheel(names, (3, 12), (14, 2)) == "mlx-0.32.4-cp312-cp312-macosx_14_0_arm64.whl"
    assert mlx.mac_wheel(names, (3, 12), (13, 6)) is None                     # too old for MLX
    assert mlx.mac_wheel(names, (3, 11), (15, 0)) is None                     # no wheel for this Python
    assert mlx.mac_wheel(["regex-1-cp312-cp312-macosx_10_13_universal2.whl", "regex-1-cp312-cp312-win_amd64.whl"],
                         (3, 12), (15, 0)) == "regex-1-cp312-cp312-macosx_10_13_universal2.whl"
    assert mlx.mac_wheel(["requests-2-py3-none-any.whl"], (3, 12), (15, 0)) == "requests-2-py3-none-any.whl"
    assert mlx.mac_wheel(["x-1-py3-none-any.whl", "x-1-cp312-cp312-macosx_11_0_arm64.whl"], (3, 12), (15, 0)) \
        == "x-1-cp312-cp312-macosx_11_0_arm64.whl"                              # binary before pure Python


def _recording(root, name, tracks=("me", "others")):
    folder = root / name
    folder.mkdir(parents=True)
    for track in tracks:
        sf.write(str(folder / f"{track}.flac"), np.zeros(16000 * 3, dtype=np.float32), 16000)
    return folder


def test_speed_test_uses_the_newest_recording_with_audio(tmp_path):
    _recording(tmp_path, "2026-10-20_100000")
    _recording(tmp_path, "2026-10-22_172906", tracks=("me",))
    (tmp_path / "2026-10-23_080000").mkdir()                 # planned, no audio yet
    assert acceleration.newest_audio(tmp_path) == tmp_path / "2026-10-22_172906" / "me.flac"
    assert acceleration.newest_audio(tmp_path / "none") is None


class FakeTranscriber:
    def __init__(self, model, device, used=None, text="eins zwei drei vier"):
        self.device = used or device
        self.text = text

    def transcribe(self, audio, language="de", progress=None):
        return [SimpleNamespace(text=self.text)]


def test_speed_test_compares_cpu_and_graphics_chip(tmp_path):
    folder = _recording(tmp_path, "2026-10-22_172906")
    clock = iter([0.0, 60.0, 100.0, 120.0]).__next__        # CPU 60 s, GPU 20 s
    made = []

    def make(model, device):
        made.append((model, device))
        return FakeTranscriber(model, device, text="eins zwei drei vier" if device == "cpu" else "eins zwei drei fünf")

    result = acceleration.speed_test("gcoli/x", folder / "others.flac", "cuda", make=make, clock=clock)
    assert made == [("gcoli/x", "cpu"), ("gcoli/x", "cuda")]
    assert [r["seconds"] for r in result["results"]] == [60.0, 20.0]
    assert result["agreement"] == 0.75
    lines = acceleration.result_lines(result)
    assert "3.0× so schnell wie die CPU" in lines[1] and lines[2] == "Übereinstimmung der Texte: 75%"


def test_speed_test_says_when_the_gpu_fell_back_to_the_cpu(tmp_path):
    folder = _recording(tmp_path, "r")
    clock = iter([0.0, 30.0, 30.0, 61.0]).__next__
    result = acceleration.speed_test("m", folder / "me.flac", "cuda", clock=clock,
                                     make=lambda m, d: FakeTranscriber(m, d, used="cpu"))
    assert "lief auf CPU" in acceleration.result_lines(result)[1]


def test_speed_test_in_the_service_reports_numbers_only(tmp_path, monkeypatch):
    s = make_service()
    s._s.recordings_dir = str(tmp_path)
    _recording(tmp_path, "2026-10-22_172906")
    monkeypatch.setattr(acceleration, "info", lambda: {"kind": "nvidia", "ready": True, "problem": None,
                                                      "can_install": False, "size": "1.3 GB"})
    monkeypatch.setattr(type(s), "_speed_test", staticmethod(
        lambda model, audio, accelerated, phase: {"audio_s": 120, "agreement": 0.97, "results": [
            {"device": "cpu", "used": "cpu", "seconds": 80.0, "factor": 0.67, "words": 300},
            {"device": accelerated, "used": accelerated, "seconds": 20.0, "factor": 0.17, "words": 301}]}))
    s.start_speed_test()
    assert wait_until(lambda: s.acceleration_info()["task"] is None and s.acceleration_info()["speed"])
    info = s.acceleration_info()
    assert info["speed"][1].startswith("Nvidia-Grafikkarte: 20.0 s") and info["error"] is None
    report = s.diagnose_report()
    assert "Experimentell:" in report and "4.0× so schnell wie die CPU" in report


def test_speed_test_refused_while_transcribing(tmp_path):
    s = make_service()
    s._job = {"id": "x"}
    with pytest.raises(RuntimeError, match="laufende Transkription"):
        s.start_speed_test()


def test_failed_install_is_shown(monkeypatch):
    s = make_service()

    def broken(progress=None):
        progress("nvidia-cudnn-cu12", 0.5)
        raise OSError("Speicher voll")

    monkeypatch.setattr(acceleration, "install", broken)
    s.start_acceleration_install()
    assert wait_until(lambda: s.acceleration_info()["task"] is None)
    assert s.acceleration_info()["error"] == "Speicher voll"


class Notifier:
    def __init__(self):
        self.shown = []

    def show(self, title, text):
        self.shown.append(title)

    def hide(self):
        pass


def test_test_notification_and_its_click():
    s = make_service()
    assert s.test_notification()["ok"] is False                 # no notifications on this system
    s.call_notifier = Notifier()
    assert s.test_notification()["clicked"] is False
    assert s.call_notifier.shown == ["Verbalis – Test-Meldung"]
    s.notification_clicked()
    assert s.acceleration_info()["notification"]["clicked"] is True
    assert "angeklickt" in s.diagnose_report()


def test_call_check_lists_program_names_only(monkeypatch):
    from verbalis.audio import call_detect

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(call_detect, "registry_entries", lambda: [
        ("C:#Users#andrea#AppData#Local#Microsoft#Teams#current#Teams.exe", 1, 0),
        ("C:#Program Files#Voicemeeter#voicemeeterpro.exe", 1, 0), ("C:#Program Files#Zoom#Zoom.exe", 1, 5)])
    s = make_service()
    result = s.check_calls()
    assert result["calls"] == ["Teams"] and result["programs"] == ["teams", "voicemeeterpro"]
    assert "andrea" not in result["detail"]                      # no user folders in the diagnosis


def test_speed_test_prefers_a_recording_of_at_least_a_minute(tmp_path):
    """The first test on Windows took the newest recording: 31 s of silence, 0 words – nothing to compare."""
    long = tmp_path / "2026-10-23_090921"
    long.mkdir()
    sf.write(str(long / "others.flac"), np.zeros(16000 * 70, dtype=np.float32), 16000)
    _recording(tmp_path, "2026-10-23_090307")                 # newer, but only 3 s
    assert acceleration.newest_audio(tmp_path) == long / "others.flac"
