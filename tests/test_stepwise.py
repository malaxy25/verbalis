"""Step-by-step transcription: pieces cut in speech pauses, both tracks alternately, resume after a crash."""

import json

import numpy as np
import pytest
import soundfile as sf

from verbalis import pipeline
from verbalis.transcription.base import Segment

SR = 16_000


def _speech_with_pauses(seconds: float, pauses: list[float]) -> np.ndarray:
    """Loud «speech» everywhere except 1-second pauses starting at the given times."""
    audio = np.full(int(seconds * SR), 0.3, dtype=np.float32)
    for p in pauses:
        audio[int(p * SR):int((p + 1) * SR)] = 0.0
    return audio


def test_cuts_land_in_speech_pauses():
    audio = _speech_with_pauses(380, [113, 245])
    energies = ((audio.reshape(-1, int(SR * pipeline.FRAME_S))) ** 2).mean(axis=1).tolist()
    cuts = pipeline.cut_points(energies, 380)
    assert len(cuts) == 2
    assert 113 <= cuts[0] <= 114 and 245 <= cuts[1] <= 246      # in the pause, not in the middle of a word
    assert pipeline.cut_points(energies[:2000], 100) == []        # short recordings stay one piece


class PieceTranscriber:
    """Says which track and which part of it it got; can crash on a given call."""
    beam_size, keywords = 5, None

    def __init__(self, crash_on: int | None = None):
        self.calls, self.prompts, self.crash_on = [], [], crash_on

    def transcribe(self, audio, language="de", progress=None):
        self.calls.append(len(audio) / SR)
        self.prompts.append(getattr(self, "prompt", None))
        if self.crash_on is not None and len(self.calls) == self.crash_on:
            raise RuntimeError("Absturz")
        n = len(self.calls)
        return [Segment(1.0, 3.0, f"Stück {n} Satz eins.", words=[(1.0, 2.0, " Stück"), (2.0, 2.5, f" {n}"),
                                                                    (2.5, 3.0, " Satz eins.")])]


def _recording(tmp_path, seconds=380):
    folder = tmp_path / "rec"
    folder.mkdir()
    sf.write(folder / "me.flac", _speech_with_pauses(seconds, [113, 245]), SR)
    sf.write(folder / "others.flac", _speech_with_pauses(seconds, [120, 250]), SR)
    return folder


NAMES = {"me": "Andrea", "others": "Gegenüber"}


def test_both_tracks_alternate_and_progress_is_saved(tmp_path):
    folder = _recording(tmp_path)
    tr = PieceTranscriber()
    seen = []
    paragraphs, _, recording = pipeline.transcribe(folder, tr, NAMES, partial=folder / pipeline.PARTIAL,
                                                   model="m", progress=lambda n, f: seen.append((n, f)))
    assert len(tr.calls) == 6 and abs(recording - 380) < 0.1          # 3 pieces per track
    order = [n for n, _ in seen]
    first = [order[i] for i in range(len(order)) if i == 0 or order[i] != order[i - 1]]
    assert first[:4] == ["Andrea", "Gegenüber", "Andrea", "Gegenüber"]   # alternately, like a conversation
    assert seen[-1][1] == 1.0 and all(a[1] <= b[1] for a, b in zip(seen, seen[1:]))
    assert tr.prompts[0] is None and "Stück 1" in tr.prompts[2]          # previous sentences as context
    texts = [p.text for p in paragraphs]
    assert "Stück 1 Satz eins." in texts and len(paragraphs) == 6
    starts = sorted(p.start for p in paragraphs if p.track == "me")
    assert starts[1] > 113                                               # second piece offset to its real time
    saved = json.loads((folder / pipeline.PARTIAL).read_text(encoding="utf-8"))
    assert all(t["done"] == 3 for t in saved["tracks"].values())


def test_cut_off_transcription_continues_where_it_stopped(tmp_path):
    """0.7.18: a crash or closing the app used to lose the whole transcription – now only the current piece."""
    folder = _recording(tmp_path)
    crashing = PieceTranscriber(crash_on=4)
    with pytest.raises(RuntimeError):
        pipeline.transcribe(folder, crashing, NAMES, partial=folder / pipeline.PARTIAL, model="m")
    partial = pipeline.partial_transcript(folder)
    assert partial["until"] > 100 and all(s["start"] < partial["until"] for s in partial["segments"])
    assert {s["speaker"] for s in partial["segments"]} == {"Andrea", "Gegenüber"}   # both tracks shown

    again = PieceTranscriber()
    paragraphs, _, _ = pipeline.transcribe(folder, again, NAMES, partial=folder / pipeline.PARTIAL, model="m")
    assert len(again.calls) == 3                                   # only the 3 pieces that were missing
    assert len(paragraphs) == 6

    other_model = PieceTranscriber()
    pipeline.transcribe(folder, other_model, NAMES, partial=folder / pipeline.PARTIAL, model="anderes")
    assert len(other_model.calls) == 6                             # other model: starts over


def test_finished_transcript_removes_the_partial_file(tmp_path):
    folder = _recording(tmp_path, seconds=60)
    pipeline.create_transcript(folder, PieceTranscriber(), "m", NAMES)
    assert (folder / "transcript.json").exists() and not (folder / pipeline.PARTIAL).exists()
    data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    assert all(s["words"] for s in data["segments"])               # word timestamps are kept (0.7.32: splitting)


def test_service_resumes_cut_off_transcriptions_at_start(home):
    from test_service import make_service, wait_until

    folder = home / "recordings" / "2026-10-12_100000"
    folder.mkdir(parents=True)
    sf.write(folder / "me.flac", np.zeros(SR * 2, dtype=np.float32), SR)
    (folder / "meta.json").write_text(json.dumps({"start": "2026-10-12T10:00:00+02:00", "state": "complete"}))
    (folder / pipeline.PARTIAL).write_text("{}")                   # the app was closed while transcribing
    make_service()
    assert wait_until(lambda: (folder / "transcript.json").exists())
    assert not (folder / pipeline.PARTIAL).exists()
