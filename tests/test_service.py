"""App flow without a window: recording → queue → transcript."""

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from verbalis.audio.recorder import TrackStatus
from verbalis.corrections import CorrectionList
from verbalis.service import Service
from verbalis.settings import Settings
from verbalis.transcription.base import Segment


class FakeRecorder:
    samplerate = 48000

    def __init__(self, microphone, loopback, folder: Path):
        self.folder = folder
        self.stop_event = threading.Event()
        self.errors = []
        self.t0 = 0.0

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)   # the service creates it first
        self.t0 = time.monotonic() - 5  # pretend it has been running for 5 s
        for name in ("me", "others"):
            sf.write(self.folder / f"{name}.wav", np.zeros(48000, dtype=np.float32), 48000)

    def stop(self, timeout=5.0):
        self.stop_event.set()
        return not getattr(self, "hangs", False)

    @property
    def running(self):
        return not self.stop_event.is_set()

    paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def active_seconds(self):
        return time.monotonic() - self.t0

    def status(self):
        return [TrackStatus(n, self.folder / f"{n}.wav", 48000 * 5, 0, 0.1) for n in ("me", "others")]


class FakeTranscriber:
    def __init__(self, model, fail=False):
        self.model, self.fail = model, fail
        self.beam_size, self.keywords = 5, None

    def transcribe(self, audio, language="de", progress=None):
        if self.fail:
            raise RuntimeError("Modell kaputt")
        if progress:
            progress(0.5, 1.0)
        return [Segment(0.0, 1.0, f"Hallo von {self.model}")]


class SlowTranscriber(FakeTranscriber):
    """Reports 10 segments – enough time to pause."""
    delay = 0.05

    def transcribe(self, audio, language="de", progress=None):
        for i in range(1, 11):
            time.sleep(self.delay)
            if progress:
                progress(i / 10, 1.0)
        return [Segment(0.0, 1.0, "fertig")]


class VerySlowTranscriber(SlowTranscriber):
    delay = 0.2  # 2 × 2 s – still running when the second recording starts


class ToccoTranscriber(FakeTranscriber):
    seen_keywords = []

    def transcribe(self, audio, language="de", progress=None):
        ToccoTranscriber.seen_keywords.append(self.keywords)
        return [Segment(0.0, 1.0, "Das Release von Toko kommt. Toko ist bereit.")]


def devices(microphone, speakers):
    return SimpleNamespace(microphone=SimpleNamespace(name="Mic"), loopback=SimpleNamespace(name="Lautsprecher"))


def make_service(**kwargs):
    s = Settings(name="Andrea", model="test-model", auto_transcribe=kwargs.pop("auto_transcribe", "on"))
    kwargs.setdefault("transcriber_factory", FakeTranscriber)
    return Service(settings=s, recorder_factory=FakeRecorder, select_devices=devices,
                   list_devices=lambda: {}, **kwargs)


def wait_until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


def finished_recording(s):
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    return rid


def test_no_recording_without_consent():
    with pytest.raises(RuntimeError, match="zugestimmt"):
        make_service().start_recording(consent=False)


def test_recording_to_transcript():
    s = make_service()
    rid = s.start_recording("Mic", "", consent=True)
    state = s.state()
    assert state["recording"]["id"] == rid and state["recording"]["duration_s"] >= 5
    assert s.recordings()[0]["status"] == "recording"
    with pytest.raises(RuntimeError, match="bereits"):
        s.start_recording(consent=True)

    assert s.stop_recording() == rid
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    t = s.transcript(rid)
    assert t["tracks"] == {"me": "Andrea", "others": "Gegenüber"}
    assert [p["speaker"] for p in t["segments"]] == ["Andrea", "Gegenüber"]
    assert "Hallo von test-model" in t["markdown"]
    assert s.recordings()[0]["duration_s"] >= 5
    assert Settings.load().microphone == "Mic"  # chosen devices are remembered


def test_error_is_shown_and_retryable():
    broken = {"yes": True}
    s = make_service(transcriber_factory=lambda m: FakeTranscriber(m, fail=broken["yes"]))
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: s.recordings()[0]["status"] == "error")
    assert "Modell kaputt" in s.recordings()[0]["error"]
    broken["yes"] = False
    s._transcriber = None  # force a new model
    s.transcribe(rid)
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")


def test_model_is_reused():
    created = []
    s = make_service(transcriber_factory=lambda m: created.append(m) or FakeTranscriber(m))
    for _ in range(2):
        s.start_recording(consent=True)
        s.stop_recording()
        time.sleep(1.1)  # new folder ID (seconds in the name)
    assert wait_until(lambda: all(r["status"] == "done" for r in s.recordings()))
    assert created == ["test-model"]


def test_invalid_id_is_rejected():
    s = make_service()
    for bad in ("../etc", "a/b", "", "..\\x"):
        with pytest.raises(ValueError):
            s.transcript(bad)


def test_save_and_load_settings():
    s = make_service()
    new = s.save_settings({"name": "  Andrea F. ", "quality": "fast", "unknown": "x"})
    assert new["name"] == "Andrea F." and new["quality"] == "fast"
    loaded = Settings.load()
    assert loaded.name == "Andrea F." and loaded.beam_size == 1
    assert Settings.from_dict({"quality": "turbo", "name": ""}).quality == "accurate"


def test_pause_and_resume():
    s = make_service(transcriber_factory=SlowTranscriber)
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: (s.state()["job"] or {}).get("progress", 0) > 0)
    s.pause()
    time.sleep(0.2)
    level = s.state()["job"]["progress"]
    time.sleep(0.4)
    state = s.state()
    assert state["pause"] == "manual"
    assert state["job"]["progress"] == level            # stands still
    assert s.recordings()[0]["status"] == "paused"
    s.resume()
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    # paused time doesn't count as compute time (10 × 0.05 s per track ≈ 1 s, not 1.6 s)
    assert s.transcript(rid)["header"]["Rechenzeit"].startswith("0.0 min")


def test_automatic_pause_while_recording():
    s = make_service(transcriber_factory=VerySlowTranscriber)
    first = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: s.state()["job"] is not None)
    time.sleep(1.1)
    s.start_recording(consent=True)          # new recording → transcription pauses
    assert wait_until(lambda: s.state()["pause"] == "recording")
    # the worker stops at its next progress step – up to one step (0.2 s) later; macOS CI needed more than 0.2 s
    time.sleep(VerySlowTranscriber.delay * 3)
    level = s.state()["job"]["progress"]
    time.sleep(0.3)
    assert s.state()["job"]["progress"] == level
    s.stop_recording()
    assert wait_until(lambda: all(r["status"] == "done" for r in s.recordings()), timeout=20)
    assert s.transcript(first) is not None


def test_remaining_time_from_stats_and_progress():
    s = make_service()
    job = {"start": time.monotonic() - 20, "paused_s": 0.0, "paused_since": None,
           "progress": 0.5, "duration_s": 60, "factor": None}
    assert s._remaining(job) == pytest.approx(20, abs=0.5)      # 20 s for 50 % → 20 s left
    job.update(progress=0.02, start=time.monotonic() - 5, factor=1.5)
    assert s._remaining(job) == pytest.approx(85, abs=0.5)      # 1.5 × 60 s − 5 s
    job.update(factor=None)
    assert s._remaining(job) is None                            # no basis yet
    s._remember_factor("m|beam5", 1.0)
    s._remember_factor("m|beam5", 2.0)
    assert s._factor("m|beam5") == 1.5


def test_edit_suggest_remember_apply(home):
    s = make_service(transcriber_factory=ToccoTranscriber)
    rid = finished_recording(s)

    r = s.edit_transcript(rid, 0, "Das Release von tocco kommt. Toko ist bereit.")
    assert r["suggestions"] == [{"variant": "Toko", "target": "tocco", "kind": "new", "previous": None}]
    folder = home / "recordings" / rid
    assert (folder / "transcript_original.json").exists()
    t = s.transcript(rid)
    assert t["edited"] and "Release von tocco" in t["markdown"]

    # remembering applies the rule to the rest of the transcript right away
    assert s.remember_corrections(rid, r["suggestions"]) == {"remembered": 1, "replaced": 3}  # 1 + 2 in paragraph 2
    assert s.transcript(rid)["segments"][0]["text"] == "Das Release von tocco kommt. tocco ist bereit."
    assert s.corrections() == [{"target": "tocco", "variants": ["Toko"]}]

    # next transcription: rule is applied, target is a keyword
    time.sleep(1.1)
    new = finished_recording(s)
    t = s.transcript(new)
    assert "Toko" not in t["markdown"] and t["header"]["Korrekturen"] == "4 automatisch ersetzt"
    assert "tocco" in ToccoTranscriber.seen_keywords[-1]
    assert not (home / "recordings" / new / "transcript_original.json").exists()

    # a second variant is added to the same target
    s.edit_transcript(new, 0, t["segments"][0]["text"].replace("tocco kommt", "Tokko kommt"))
    r = s.edit_transcript(new, 0, t["segments"][0]["text"])
    assert r["suggestions"][0]["kind"] == "added" and r["suggestions"][0]["variant"] == "Tokko"
    s.remember_corrections("", r["suggestions"])
    assert s.corrections() == [{"target": "tocco", "variants": ["Tokko", "Toko"]}]
    assert s.remove_correction("tocco", "Toko") == [{"target": "tocco", "variants": ["Tokko"]}]


def test_edit_validates_input():
    s = make_service(transcriber_factory=ToccoTranscriber)
    rid = finished_recording(s)
    with pytest.raises(ValueError, match="leer"):
        s.edit_transcript(rid, 0, "   ")
    with pytest.raises(ValueError, match="Absatz"):
        s.edit_transcript(rid, 99, "x")
    assert s.edit_transcript(rid, 0, s.transcript(rid)["segments"][0]["text"]) == {"suggestions": []}


def test_keywords_without_duplicates():
    c = CorrectionList()
    c.add("Toko", "tocco")
    c.add("Limetnah", "Limmat")
    assert Service._keywords("Tocco, Höngg, ", c) == "Tocco, Höngg, Limmat"


def test_delete_recording_completely(home):
    s = make_service()
    rid = finished_recording(s)
    s.delete_recording(rid)
    assert not (home / "recordings" / rid).exists()
    assert s.recordings() == []


def test_cannot_delete_running_recording():
    s = make_service()
    rid = s.start_recording(consent=True)
    with pytest.raises(RuntimeError, match="gerade"):
        s.delete_recording(rid)
    s.stop_recording()


def test_silent_others_track_is_reported():
    s = make_service()
    s.start_recording(consent=True)
    rec = s._rec
    rec.status()  # FakeRecorder: level 0.1 rms ≈ −20 dB on both tracks
    state = s.state()["recording"]
    assert state["others_silent_s"] == 0 and state["others_device"] == "Lautsprecher"

    s._others_last_sound -= 90          # pretend the last sound was 90 s ago …
    rec.status = lambda: [TrackStatus(n, rec.folder / f"{n}.wav", 0, 0, 0.0) for n in ("me", "others")]
    assert s.state()["recording"]["others_silent_s"] >= 90   # … and it is silent now
    s.stop_recording()


def test_pause_and_resume_recording():
    s = make_service()
    with pytest.raises(RuntimeError, match="keine Aufnahme"):
        s.pause_recording()
    s.start_recording(consent=True)
    s.pause_recording()
    assert s.state()["recording"]["paused"] is True
    s._others_last_sound -= 120                       # silence during a pause …
    assert s.state()["recording"]["others_silent_s"] == 0   # … doesn't trigger the warning
    s.resume_recording()
    assert s.state()["recording"]["paused"] is False
    s.stop_recording()


def test_add_correction_by_hand():
    s = make_service()
    r = s.add_correction(" Toko ", "tocco")
    assert r["info"]["kind"] == "new" and r["list"] == [{"target": "tocco", "variants": ["Toko"]}]
    r = s.add_correction("Tokko", "tocco")                      # second variant for the same word
    assert r["info"]["kind"] == "added" and r["list"][0]["variants"] == ["Tokko", "Toko"]
    with pytest.raises(ValueError, match="beide Felder"):
        s.add_correction("", "tocco")
    with pytest.raises(ValueError, match="gleich"):
        s.add_correction("tocco", "Tocco")


def test_spelling_knows_keywords_and_correction_targets(tmp_path):
    from verbalis.spelling import Speller

    folder = tmp_path / "dict"
    folder.mkdir()
    (folder / "de_CH_frami.aff").write_text("SET UTF-8\n", encoding="utf-8")
    (folder / "de_CH_frami.dic").write_text("1\nRelease\n", encoding="utf-8")
    speller = Speller(folder=folder, download=False)
    speller.load_now()
    s = make_service(speller=speller)
    s.save_settings({"keywords": "Höngg, Limmat"})
    s.add_correction("Toko", "tocco")
    assert s.spelling_check(["Release", "Höngg", "tocco", "Toko"])["misspelled"] == ["Toko"]


def _patch_models(monkeypatch, revisions, remote, downloads):
    """Fake a downloaded model whose local revision follows `revisions`."""
    from verbalis.transcription import models as m
    monkeypatch.setattr(m, "repo_for", lambda model: "org/repo")
    monkeypatch.setattr(m, "is_local", lambda model: True)
    monkeypatch.setattr(m, "local_revision", lambda model: {"revision": revisions[0], "loaded": "2026-10-08T10:00"})
    monkeypatch.setattr(m, "check_update", remote)
    monkeypatch.setattr(m, "check_revision", lambda model: {"update": remote(model),
                                                           "current_changed": "2026-09-30T10:00+02:00"})

    def fake_download(model, progress=None):
        downloads.append(model)
        if progress:
            progress(500_000_000)
        revisions[0] = "b" * 40

    monkeypatch.setattr(m, "download", fake_download)


def test_model_update_is_downloaded_and_announced(monkeypatch):
    revisions, downloads = ["a" * 40], []
    _patch_models(monkeypatch, revisions, lambda model: {"revision": "b" * 40, "changed": "2026-11-02T08:00"},
                  downloads)
    s = make_service()
    s.save_settings({"model_auto_update": "on"})
    s._transcriber = object()                 # a loaded model of the old revision
    s._job = {"phase": "", "progress": 0.0}
    s._ensure_model("large-v3")
    assert "Modell-Update" in s._job["phase"]  # the user sees that it is an update
    s._job = None
    assert downloads == ["large-v3"] and s._transcriber is None
    assert "aktualisiert" in s.state()["notice"] and "bbbbbbb" in s.state()["notice"]
    s.dismiss_notice()
    assert s.state()["notice"] is None


def test_no_download_when_current_or_offline(monkeypatch):
    revisions, downloads = ["a" * 40], []
    _patch_models(monkeypatch, revisions, lambda model: None, downloads)   # no newer model files
    s = make_service()
    s._ensure_model("large-v3")
    assert downloads == []

    def offline(model):
        raise OSError("no network")
    _patch_models(monkeypatch, revisions, offline, downloads)
    s._ensure_model("large-v3")
    assert downloads == [] and s.state()["notice"] is None


def test_model_updates_are_listed_and_cached(monkeypatch):
    calls = []

    def remote(model):
        calls.append(model)
        return {"revision": "c" * 40, "changed": "2026-11-02T08:00"}
    _patch_models(monkeypatch, ["a" * 40], remote, [])
    s = make_service()
    first = s.model_updates()
    assert first["large-v3"]["revision"] == "ccccccc"
    from verbalis.transcription.models import RECOMMENDED
    assert s.model_updates() == first and len(calls) == len(RECOMMENDED)   # cached: no second round



def test_models_have_readable_names():
    names = {m["id"]: m["name"] for m in make_service().models()}
    assert names["Flix-AI/flix-swissgerman-full"] == "Flix Schweizerdeutsch"
    assert names["large-v3-turbo"] == "Whisper large-v3 turbo"



def test_model_updates_wait_for_approval_by_default(monkeypatch):
    revisions, downloads = ["a" * 40], []
    _patch_models(monkeypatch, revisions, lambda model: {"revision": "b" * 40, "changed": None}, downloads)
    s = make_service()
    assert s._s.model_auto_update == "off"
    s._ensure_model("large-v3")
    assert downloads == []                    # not without approval


def test_model_update_on_request_and_state(monkeypatch):
    revisions, downloads = ["a" * 40], []
    _patch_models(monkeypatch, revisions, lambda model: {"revision": "b" * 40, "changed": "2026-11-02T08:00"},
                  downloads)
    s = make_service()
    assert s.model_updates()["large-v3"]["revision"] == "bbbbbbb"
    assert "large-v3" in s.state()["model_updates"]           # notice at start
    s.dismiss_model_updates()
    assert s.state()["model_updates"] == []
    s.update_model("large-v3")
    assert wait_until(lambda: s.state()["model_download"] is None)
    assert downloads == ["large-v3"] and "aktualisiert" in s.state()["notice"]



def test_introduction_downloads_a_missing_model_ahead(monkeypatch):
    """Introduction: the model download starts at the welcome step, not only after the test recording."""
    import threading

    from verbalis.transcription import models as m
    release, downloads = threading.Event(), []
    monkeypatch.setattr(m, "repo_for", lambda model: "org/repo")
    monkeypatch.setattr(m, "is_local", lambda model: False)

    def slow_download(model, progress=None):
        downloads.append(model)
        progress(400_000_000)
        release.wait(5)
    monkeypatch.setattr(m, "download", slow_download)
    monkeypatch.setattr(m, "SIZE_GB", {"test-model": 1.6})
    s = make_service()
    assert s.prepare_model()["downloading"] is True
    assert wait_until(lambda: (s.state()["model_download"] or {}).get("progress", 0) > 0.2)
    assert s.state()["model_download"]["kind"] == "download"
    s.prepare_model()                                    # a second click starts no second download
    s._job = {"phase": "", "progress": 0.0}
    waiter = threading.Thread(target=s._wait_for_prefetch, args=("test-model",))
    waiter.start()
    assert wait_until(lambda: "heruntergeladen: 25 %" in s._job["phase"])   # the transcription shows it
    release.set()
    waiter.join(5)
    s._job = None
    assert not waiter.is_alive() and downloads == ["test-model"] and s.state()["model_download"] is None


def test_introduction_skips_the_download_when_the_model_is_here(monkeypatch):
    from verbalis.transcription import models as m
    monkeypatch.setattr(m, "repo_for", lambda model: "org/repo")
    monkeypatch.setattr(m, "is_local", lambda model: True)
    s = make_service()
    assert s.prepare_model() == {"downloading": False} and s.state()["model_download"] is None

def test_model_rollback_from_settings(monkeypatch):
    from verbalis.transcription import models as m
    monkeypatch.setattr(m, "rollback", lambda model: "a" * 40)
    s = make_service()
    assert s.rollback_model("large-v3") == "a" * 40
    assert "vorherigen Stand" in s.state()["notice"]


def test_recordings_in_a_synced_folder_are_flagged(tmp_path):
    from verbalis.settings import sync_warning
    assert "synchronisierten" in sync_warning(tmp_path / "OneDrive - tocco AG" / "Verbalis")
    assert sync_warning(tmp_path / "Dropbox" / "x")
    assert sync_warning(tmp_path / "Library" / "Mobile Documents" / "x")
    assert sync_warning(tmp_path / "Documents" / "Verbalis") is None
    s = make_service()
    s.save_settings({"recordings_dir": str(tmp_path / "OneDrive" / "Aufnahmen")})
    assert s.settings()["storage_warning"]


class FakeMonitor:
    opened = []

    def __init__(self, microphone, loopback):
        self.devices = (microphone.name, loopback.name)
        self.closed = False
        FakeMonitor.opened.append(self)

    def start(self):
        pass

    def stop(self, timeout=2.0):
        self.closed = True

    def levels(self):
        return {"me": 0.1, "others": 0.0}


def test_levels_before_recording_open_and_close_the_devices(monkeypatch):
    """0.7.17: level meters while choosing devices – without recording, closed again when not needed."""
    import verbalis.service as service_module
    monkeypatch.setattr(service_module, "PREVIEW_IDLE_S", 0.3)
    FakeMonitor.opened = []
    s = make_service(monitor_factory=FakeMonitor)
    levels = s.preview_levels("Mic", "")
    assert levels == {"me": -20.0, "others": -90.0}
    s.preview_levels("Mic", "")
    assert len(FakeMonitor.opened) == 1                       # kept open while the UI asks
    assert not list((s._s.recordings).glob("*"))              # nothing is recorded

    s.preview_levels("Other mic", "")                         # other device chosen → reopened
    assert FakeMonitor.opened[0].closed and len(FakeMonitor.opened) == 2
    assert wait_until(lambda: FakeMonitor.opened[1].closed, 3)  # UI stopped asking → closed

    s.preview_levels("Mic", "")
    s.start_recording(consent=True)                           # the recording gets the devices
    assert FakeMonitor.opened[2].closed
    assert s.preview_levels("Mic", "") is None
    s.stop_recording()


def test_shutdown_closes_the_level_meters_right_away():
    """Regression 0.7.33: quitting with the level meters open left the devices to the watchdog thread;
    on the Mac a device that still delivered audio while Python ended crashed the app."""
    FakeMonitor.opened = []
    s = make_service(monitor_factory=FakeMonitor)
    s.preview_levels("Mic", "")
    s.shutdown()
    assert FakeMonitor.opened[0].closed and s._monitor is None


def test_level_preview_with_broken_device_does_not_flood_the_log(caplog):
    calls = []

    def broken(microphone, speakers):
        calls.append(microphone)
        raise RuntimeError("kein Mikrofon")

    s = make_service(monitor_factory=FakeMonitor)
    s._select_devices = broken
    for _ in range(5):
        assert s.preview_levels("Mic", "") == {"me": -90.0, "others": -90.0}
    assert len(calls) == 1
    s.stop_preview()


def test_transcription_waits_for_the_user_by_default():
    """0.7.18: after a meeting the number of people is entered first – transcribing starts by hand."""
    assert Settings().auto_transcribe == "off"
    s = make_service(auto_transcribe="off")
    rid = s.start_recording(consent=True)
    s.stop_recording()
    time.sleep(0.3)
    assert s.recordings()[0]["status"] == "none"

    s.transcribe(rid, {"me": "2", "others": ""})
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    assert s.recordings()[0]["people"] == {"me": 2, "others": None}
    with pytest.raises(ValueError, match="Anzahl"):
        s.transcribe(rid, {"me": "31"})


def test_audio_clip_mixes_both_tracks():
    s = make_service()
    rid = finished_recording(s)
    clip = s.audio_clip(rid, 0.2, 0.4)
    assert clip["url"].startswith("data:audio/wav;base64,") and clip["start"] == 0.0
    import base64
    import io
    data, rate = sf.read(io.BytesIO(base64.b64decode(clip["url"].split(",", 1)[1])))
    assert rate == 16000 and abs(len(data) / rate - 0.9) < 0.05    # from 0.3 s before to 0.5 s after


def test_delete_waits_for_a_file_that_is_open_for_a_moment():
    """0.7.21 CI failure on Windows: deleting failed with «being used by another process» when the
    background clean-up read meta.json at the same moment (WinError 32)."""
    s = make_service()
    rid = finished_recording(s)
    handle = (s._path(rid) / "meta.json").open("rb")        # like the clean-up reading it
    threading.Timer(0.3, handle.close).start()
    s.delete_recording(rid)
    assert not s._path(rid).exists()


class SilentTrackRecorder(FakeRecorder):
    """Like the first Mac test: the recording runs, but one device never delivers any audio."""

    def status(self):
        return [TrackStatus("me", self.folder / "me.wav", 0, 0, 0.0),
                TrackStatus("others", self.folder / "others.wav", 48000 * 5, 0, 0.1)]


def test_track_without_any_audio_is_reported_while_recording():
    """0.7.21 on macOS: the recording ran without sound and nothing said which device delivered nothing."""
    s = Service(settings=Settings(name="Andrea", model="test-model", auto_transcribe="on"),
                recorder_factory=SilentTrackRecorder, select_devices=devices, list_devices=lambda: {})
    s.start_recording(consent=True)
    message = s.state()["recording_error"]
    assert "Mikrofon «Mic»" in message and "keine Audiodaten" in message
    assert "Systemton" not in message                 # that track delivers
    s.stop_recording()


def test_diagnosis_runs_the_steps_of_a_recording_start(monkeypatch):
    """Diagnose tab: each device alone, both together, closing and reopening at once – with a report to copy."""
    from verbalis.audio import recorder
    seen = []

    def fake_measure(devices, seconds):
        seen.append([name for name, _ in devices])
        return [{"device": d.name, "first_data_s": 0.2, "received_s": seconds, "peak_db": -30.0, "hangs": False,
                 "close_s": 0.1, "error": None} for _, d in devices]

    monkeypatch.setattr(recorder, "measure", fake_measure)
    s = make_service()
    s.start_diagnosis("Mic", "")
    assert wait_until(lambda: not s.diagnosis()["running"])
    assert seen == [["Mikrofon"], ["Systemton"], ["Mikrofon", "Systemton"],
                    ["Mikrofon", "Systemton"], ["Mikrofon", "Systemton"]]
    report = s.diagnose_report()
    assert "Verbalis:" in report and "Nur Mikrofon" in report and "Mic: OK – erste Daten nach 0.2 s" in report
    assert s.preview_levels("Mic", "") is not None             # level meters work again afterwards
    s.stop_preview()


def test_copy_on_macos_goes_through_pbcopy(monkeypatch):
    """0.7.23.dev1 on macOS: «Diagnose kopieren» did nothing – WebKit refuses the clipboard after an await."""
    import sys

    from verbalis import service as service_module
    calls = []

    def fake_run(command, input, env, timeout, check):
        calls.append((command, input.decode("utf-8"), env["LANG"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sys, "platform", "darwin")
    assert service_module.copy_to_clipboard("Grüezi – Diagnose", run=fake_run) is True
    assert calls == [(["/usr/bin/pbcopy"], "Grüezi – Diagnose", "en_US.UTF-8")]
    monkeypatch.setattr(sys, "platform", "win32")
    assert service_module.copy_to_clipboard("x", run=fake_run) is False   # Windows: the window copies


class MicOnlyRecorder(FakeRecorder):
    """Like TwoTrackRecorder with loopback=None: only the microphone track."""

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic() - 5
        sf.write(self.folder / "me.wav", np.full(48000, 0.1, dtype=np.float32), 48000)

    def status(self):
        return [TrackStatus("me", self.folder / "me.wav", 48000 * 5, 0, 0.1)]


def test_microphone_only_recording_for_a_meeting_in_a_room():
    """0.7.26: «Keiner – nur Mikrofon» – no second track, no warning about it, nothing reported missing."""
    seen = []

    def mic_only(microphone, speakers):
        seen.append(speakers)
        return SimpleNamespace(microphone=SimpleNamespace(name="MacBook Air-Mikrofon"), loopback=None)

    s = Service(settings=Settings(name="Andrea", model="test-model", auto_transcribe="on"),
                recorder_factory=lambda mic, loop, folder: MicOnlyRecorder(mic, loop, folder),
                select_devices=mic_only, list_devices=lambda: {}, transcriber_factory=FakeTranscriber)
    rid = s.start_recording("", "__none__", consent=True)
    state = s.state()["recording"]
    assert state["only_microphone"] and state["levels"]["others"] == -90.0 and state["others_silent_s"] == 0
    assert s.state()["recording_error"] is None                       # no «keine Audiodaten» for the others
    s.stop_recording()
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")
    entry = s.recordings()[0]
    assert entry["missing_tracks"] == [] and seen == ["__none__"]
    md = (s._path(rid) / "transcript.md").read_text(encoding="utf-8")
    assert "Unvollständig" not in md and "Hallo von test-model" in md


def test_maximum_recording_time_warns_extends_and_ends_cleanly():
    """0.7.26: a forgotten recording ends after the maximum time (2 h by default) – as a complete recording."""
    from verbalis import pipeline
    notes = []
    s = make_service()
    s.call_notifier = SimpleNamespace(show=lambda title, text: notes.append(title), hide=lambda: None)
    assert s._s.max_recording_s == 7200
    rid = s.start_recording(consent=True)
    s._rec_info["limit_s"] = s._rec.active_seconds() + 200       # 3 min 20 s left
    state = s.state()["recording"]
    assert 190 <= state["ends_in_s"] <= 200 and notes == ["Die Aufnahme endet in 3 Min."]
    s.state()
    assert len(notes) == 1                                       # one notice
    s.extend_recording()                                         # «+30 Min.»
    assert "ends_in_s" not in s.state()["recording"]
    s._rec_info["limit_s"] = 4                                   # the time is up
    assert s.state()["recording"] is None
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "complete" and "automatisch beendet" in meta["ended_by"]
    assert "automatisch beendet" in s.state()["notice"]
    assert Settings.from_dict({"max_recording_min": ""}).max_recording_s is None
    assert Settings.from_dict({"max_recording_min": "abc"}).max_recording_min == "120"


def test_model_tiles_say_whether_the_model_is_up_to_date(monkeypatch):
    """0.7.26: «Stand 540fb2e, 8.10.2026» didn't say whether it is the newest – now the tile says so."""
    _patch_models(monkeypatch, ["a" * 40], lambda model: None, [])
    s = make_service()
    assert all(m["check"] is None for m in s.models())                 # not checked yet
    tiles = {m["id"]: m for m in s.check_models_now()}
    check = tiles["large-v3"]["check"]
    assert check["state"] == "current" and check["changed"].startswith("2026-09-30") and check["checked"]

    from verbalis.transcription import models as m

    def offline(model):
        raise OSError("keine Verbindung")
    monkeypatch.setattr(m, "check_revision", offline)
    assert {t["id"]: t for t in s.check_models_now()}["large-v3"]["check"]["state"] == "failed"


def test_split_paragraph_where_another_person_takes_over(home):
    """0.7.32: a paragraph that started with one person and went on with another (seen in a Teams call)
    can be split with Enter; the second part gets the time of its first word."""
    s = make_service(transcriber_factory=ToccoTranscriber)
    rid = finished_recording(s)
    folder = home / "recordings" / rid
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    words = [[20.0 + i, 21.0 + i, f" {w}"] for i, w in enumerate("Wir starten am Montag. Ich bin dabei.".split())]
    data["segments"][0].update(start=20.0, end=27.0, text="Wir starten am Montag. Ich bin dabei.", words=words)
    s._write_transcript(folder, data)

    r = s.split_paragraph(rid, 0, "Wir starten am Montag.", "Ich bin\ndabei.")
    assert r["index"] == 1
    stored = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))["segments"]
    assert (stored[0]["text"], stored[0]["end"]) == ("Wir starten am Montag.", 24.0)
    assert (stored[1]["text"], stored[1]["start"], stored[1]["end"]) == ("Ich bin\ndabei.", 24.0, 27.0)
    assert len(stored[0]["words"]) == 4 and len(stored[1]["words"]) == 3
    assert stored[1]["speaker"] == stored[0]["speaker"]                    # chosen afterwards in the window
    t = s.transcript(rid)
    assert t["edited"] and all("words" not in seg for seg in t["segments"])   # the window gets no words
    assert "Ich bin  \ndabei." in t["markdown"]
    assert (folder / "transcript_original.json").exists()
    with pytest.raises(ValueError, match="Cursor"):
        s.split_paragraph(rid, 0, "", "Wir starten am Montag.")


def test_remaining_time_during_speaker_diarization():
    """0.7.32: after transcribing, the progress was near 100 % while diarization of a long call still ran
    for minutes – the app said «noch weniger als eine Minute». Now the time left comes from diarization."""
    from verbalis.pipeline import diarization_rest

    s = make_service()
    job = {"start": time.monotonic() - 600, "paused_s": 0.0, "paused_since": None,
           "progress": 0.99, "duration_s": 3000, "factor": None, "diarizing": True, "diarize_rest": None}
    assert s._remaining(job) is None                              # «Restdauer wird geschätzt», not «< 1 min»
    job["diarize_rest"] = 240.0
    assert s._remaining(job) == 240.0
    assert diarization_rest(60, 0.25, 1500) == pytest.approx(180)              # 60 s for 25 % → 180 s left
    assert diarization_rest(60, 0.25, 1500, later_s=1500) == pytest.approx(420)   # + the next track: 240 s
    assert diarization_rest(2, 0.5, 1500) is None and diarization_rest(60, 0.01, 1500) is None
