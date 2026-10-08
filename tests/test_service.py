"""App flow without a window: recording → queue → transcript."""

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
        self.folder.mkdir(parents=True)
        self.t0 = time.monotonic() - 5  # pretend it has been running for 5 s
        for name in ("me", "others"):
            sf.write(self.folder / f"{name}.wav", np.zeros(48000, dtype=np.float32), 48000)

    def stop(self):
        self.stop_event.set()

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
    s = Settings(name="Andrea", model="test-model")
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
    time.sleep(0.2)
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
