"""Robustness of recordings: honest end states, no overwriting, crash recovery, disk space, shutdown."""

import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from verbalis import pipeline, service as service_module
from test_service import SlowTranscriber, make_service, wait_until


# ---------------------------------------------------------------- files

def test_meta_is_written_atomically_and_damage_is_detected(tmp_path):
    pipeline.write_json_atomic(tmp_path / "meta.json", {"state": "complete"})
    assert pipeline.read_meta(tmp_path) == {"state": "complete"}
    assert not (tmp_path / "meta.json.tmp").exists()
    (tmp_path / "meta.json").write_text('{"state": "comp', encoding="utf-8")   # cut off by a crash
    assert pipeline.read_meta(tmp_path) == {"damaged": True}                    # not silently empty
    assert pipeline.read_meta(tmp_path / "nothing") == {}


def test_wav_left_open_by_a_crash_is_repaired(tmp_path):
    """Regression guard: after a crash the WAV header still says 0 bytes of audio."""
    wav = tmp_path / "me.wav"
    sf.write(wav, np.full(48_000, 0.25, dtype=np.float32), 48_000, subtype="PCM_16")
    raw = bytearray(wav.read_bytes())
    data = raw.index(b"data")
    raw[4:8] = struct.pack("<I", 36)                # sizes as written when the file was opened
    raw[data + 4:data + 8] = struct.pack("<I", 0)
    wav.write_bytes(bytes(raw))
    assert sf.info(wav).frames == 0                 # looks empty although the audio is there
    assert pipeline.repair_wav(wav) is True
    assert sf.info(wav).frames == 48_000
    assert pipeline.repair_wav(wav) is False        # nothing left to fix


def test_new_recording_never_reuses_a_folder(tmp_path):
    s = make_service()
    from datetime import datetime
    start = datetime(2026, 10, 9, 9, 0, 0)
    first, second = s._new_folder(start), s._new_folder(start)
    assert first.name == "2026-10-09_090000" and second.name == "2026-10-09_090000_2"


def test_recorder_refuses_to_overwrite_a_wav(tmp_path):
    from verbalis.audio.recorder import Track
    import threading
    (tmp_path / "me.wav").write_bytes(b"existing recording")

    class Device:
        name = "x"

        def recorder(self, samplerate, blocksize):
            raise AssertionError("must not get this far")

    track = Track("me", Device(), tmp_path / "me.wav", threading.Event(), t0=0.0)
    track.run()
    assert track.status.error is not None
    assert (tmp_path / "me.wav").read_bytes() == b"existing recording"


# ---------------------------------------------------------------- end states

def test_complete_recording_is_marked_complete():
    s = make_service()
    rid = s.start_recording(consent=True)
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "recording" and meta["consent"]["text_version"]   # on disk from the start
    s.stop_recording()
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "complete" and "problem" not in meta
    assert meta["consent"]["text"] == pipeline.CONSENT_TEXT


def test_stop_timeout_is_not_treated_as_success(monkeypatch):
    s = make_service()
    rid = s.start_recording(consent=True)
    s._rec.hangs = True                              # a device blocks, the track doesn't end
    s.stop_recording()
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "stop_timeout" and "nicht rechtzeitig" in meta["problem"]
    assert rid not in s._queued                      # no automatic transcription of maybe broken files
    assert "nicht rechtzeitig" in s.state()["recording_error"]


def test_device_error_keeps_audio_and_marks_incomplete():
    s = make_service()
    rid = s.start_recording(consent=True)
    s._rec.errors = [OSError("Gerät getrennt")]
    s.stop_recording()
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "incomplete" and "Gerät getrennt" in meta["problem"]
    assert wait_until(lambda: (s._path(rid) / "transcript.json").exists())   # still transcribed
    assert s.recordings()[0]["state"] == "incomplete"


def test_single_rescued_track_is_transcribed_and_flagged():
    s = make_service()
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: (s._path(rid) / "transcript.json").exists())
    folder = s._path(rid)
    for f in folder.glob("others.*"):
        f.unlink()                                   # the others track is lost
    (folder / "transcript.json").unlink()
    s.transcribe(rid)
    assert wait_until(lambda: (folder / "transcript.json").exists())
    md = (folder / "transcript.md").read_text(encoding="utf-8")
    assert "Unvollständig" in md and "Gegenüber" in md
    assert s.recordings()[0]["missing_tracks"] == ["others"]


# ---------------------------------------------------------------- crash recovery

def test_interrupted_recording_is_recovered_at_start(tmp_path):
    # no background clean-up here: it would compress the WAV to FLAC while the test reads it
    s = make_service(cleanup_on_start=False)
    rid = s.start_recording(consent=True)
    folder = s._path(rid)
    s._rec, s._rec_info = None, {}                   # the app "crashes": nothing is finished
    raw = bytearray((folder / "me.wav").read_bytes())
    raw[raw.index(b"data") + 4:raw.index(b"data") + 8] = struct.pack("<I", 0)
    (folder / "me.wav").write_bytes(bytes(raw))
    s.shutdown(wait_s=2)

    restarted = make_service(cleanup_on_start=False)
    meta = pipeline.read_meta(folder)
    assert meta["state"] == "interrupted" and "Absturz" in meta["problem"]
    assert sf.info(folder / "me.wav").frames == 48_000       # audio readable again
    assert restarted.recordings()[0]["state"] == "interrupted"


# ---------------------------------------------------------------- disk space

def fake_free(monkeypatch, mb):
    monkeypatch.setattr(service_module.shutil, "disk_usage", lambda path: type("U", (), {"free": mb * 1e6})())


def test_no_recording_without_disk_space(monkeypatch):
    s = make_service()
    fake_free(monkeypatch, 100)
    with pytest.raises(RuntimeError, match="Zu wenig Speicherplatz"):
        s.start_recording(consent=True)


def test_low_disk_space_warns_and_finally_stops_the_recording(monkeypatch):
    s = make_service()
    rid = s.start_recording(consent=True)
    fake_free(monkeypatch, 1_000)
    s._disk["checked"] = 0
    assert s.state()["recording"]["disk_minutes_left"] > 0
    fake_free(monkeypatch, 100)
    s._disk["checked"] = 0
    assert s.state()["recording"] is None                  # stopped and saved
    meta = pipeline.read_meta(s._path(rid))
    assert meta["state"] == "incomplete" and "Speicher" in meta["problem"]


# ---------------------------------------------------------------- shutdown

def test_shutdown_during_pause_ends_the_worker():
    s = make_service(transcriber_factory=SlowTranscriber)
    s.pause()
    rid = s.start_recording(consent=True)
    s.stop_recording()
    assert wait_until(lambda: rid in s._queued or s._job)
    s.shutdown(wait_s=3)
    assert not s._worker.is_alive()                         # didn't hang in the pause loop



def test_recovery_runs_before_the_clean_up_compresses_audio():
    """Order at start matters: repair the WAV first, then the clean-up may compress it."""
    # read the file: conftest wraps Service.__init__ to shut services down after each test
    source = Path(service_module.__file__).read_text(encoding="utf-8")
    init = source[source.index("    def __init__"):source.index("\n    def ", source.index("    def __init__") + 10)]
    assert init.index("self._recover_interrupted()") < init.index("self._queue.put(CLEANUP)")
