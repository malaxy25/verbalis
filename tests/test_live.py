"""Transcribing while recording (live.py): pieces of the growing WAV files, handed over to the normal transcription."""

import json

import numpy as np
import soundfile as sf

from verbalis import live, pipeline
from verbalis.transcription.base import Segment
from test_service import make_service, wait_until

RATE = 16000


def speech(seconds: float, pause_every: float = 30.0) -> np.ndarray:
    """Loud noise with a short pause every `pause_every` seconds (where pieces get cut)."""
    rng = np.random.default_rng(3)
    audio = rng.normal(0, 0.2, int(seconds * RATE)).astype(np.float32)
    for t in np.arange(pause_every, seconds, pause_every):
        audio[int(t * RATE):int((t + 0.8) * RATE)] = 0
    return audio


class CountingTranscriber:
    """Says which piece it got: «Stück <n> (<seconds> s)», one segment at the start of the piece."""

    def __init__(self):
        self.pieces, self.prompt, self.beam_size, self.keywords = [], None, 5, None

    def transcribe(self, audio, language="de", progress=None):
        self.pieces.append(round(len(audio) / RATE))
        if progress:
            progress(1.0, len(audio) / RATE)
        return [Segment(0.0, 1.0, f"Stück {len(self.pieces)} ({self.pieces[-1]} s)")]


def test_reads_a_wav_that_is_still_being_written(tmp_path):
    """The header sizes of a WAV are only written when it is closed – the live transcription must not rely on them."""
    path = tmp_path / "me.wav"
    with sf.SoundFile(path, "x", samplerate=RATE, channels=1, subtype="PCM_16") as f:
        f.write(np.full(RATE * 3, 0.5, dtype=np.float32))
        f.flush()
        layout = live.wav_layout(path)
        assert layout is not None and layout[1:] == (RATE, 1)
        assert abs(live.wav_seconds(path, layout) - 3.0) < 0.01
        piece = live.read_wav(path, layout, 1.0, 2.0)
        assert len(piece) == RATE and abs(float(piece.mean()) - 0.5) < 0.001
    assert live.wav_layout(tmp_path / "missing.wav") is None


def test_live_pieces_are_continued_by_the_normal_transcription(tmp_path):
    folder = tmp_path / "2026-10-28_100000"
    folder.mkdir()
    for track in ("me", "others"):
        sf.write(folder / f"{track}.wav", speech(400), RATE, subtype="PCM_16")
    names = {"me": "Andrea", "others": "Gegenüber"}
    tr = CountingTranscriber()
    rec = live.LiveTranscription(folder, names, "test-model", lambda: tr)
    while rec._piece(tr):          # what the thread does while recording
        pass
    assert sorted(rec.state["tracks"]) == ["me", "others"]
    assert all(ts["done"] == 3 for ts in rec.state["tracks"].values())   # 3 pieces each, ~40 s are left
    done = rec.done_s
    assert 340 <= done <= 380 and all(c % 30 < 1.5 for c in rec.state["tracks"]["me"]["cuts"])  # cut in pauses
    assert (folder / live.LIVE).exists() and not (folder / pipeline.PARTIAL).exists()

    rec._thread = type("Ended", (), {"join": lambda self, timeout=None: None})()
    rec.finish()                   # recording over: the rest is planned
    assert live.take_over(folder) and not (folder / live.LIVE).exists()
    after = CountingTranscriber()
    paragraphs, _, _ = pipeline.transcribe(folder, after, names, partial=folder / pipeline.PARTIAL, model="test-model")
    assert len(after.pieces) == 2 and all(p < 400 - done + 5 for p in after.pieces)   # only the rest of each track
    texts = [p.text for p in paragraphs]
    assert sum("Stück" in t for t in texts) == 8          # 6 live pieces + 2 afterwards, nothing twice


def test_live_progress_of_a_crash_is_planned_when_taken_over(tmp_path):
    """Verbalis closed during the recording: the live file was never finished, its pieces still count."""
    folder = tmp_path / "2026-10-28_100000"
    folder.mkdir()
    sf.write(folder / "me.wav", speech(300), RATE, subtype="PCM_16")
    state = {"version": 1, "model": "m", "names": {"me": "Andrea"}, "until_s": None, "compute_s": 1.0,
             "tracks": {"me": {"duration": 120.0, "cuts": [120.0], "done": 1,
                               "segments": [{"start": 0.0, "end": 1.0, "text": "Erstes Stück", "words": None}]}}}
    (folder / live.LIVE).write_text(json.dumps(state), encoding="utf-8")
    assert live.take_over(folder)
    ts = json.loads((folder / pipeline.PARTIAL).read_text(encoding="utf-8"))["tracks"]["me"]
    assert ts["cuts"][0] == 120.0 and ts["duration"] == 300.0 and ts["done"] == 1 and len(ts["segments"]) == 1


def test_service_transcribes_during_the_recording_when_switched_on():
    s = make_service(auto_transcribe="off")
    s.save_settings({"live_transcribe": "on"})
    rid = s.start_recording(consent=True)
    assert wait_until(lambda: s.state()["recording"]["live"] is not None)
    assert s.state()["recording"]["live"]["done_s"] == 0      # the fake recording has 1 s of audio: nothing to do
    s.stop_recording()
    assert wait_until(lambda: not s._live_done or not any(t.is_alive() for t in s._live_done.values()))
    assert not (s._path(rid) / live.LIVE).exists()             # nothing finished, nothing kept
    s.transcribe(rid)
    assert wait_until(lambda: s.recordings()[0]["status"] == "done")


def test_no_live_transcription_when_switched_off():
    s = make_service()
    s.start_recording(consent=True)
    assert s.state()["recording"]["live"] is None and not s._live
    s.stop_recording()
