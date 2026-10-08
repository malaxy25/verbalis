"""Run transcribe/compare with a simulated model."""

import numpy as np
import soundfile as sf

from verbalis import cli
from verbalis.transcription import faster
from verbalis.transcription.base import Segment


class FakeTranscriber:
    def __init__(self, model, device="cpu", keywords=None, beam_size=5):
        self.name = model

    def transcribe(self, audio, language="de", progress=None):
        # loud part = speech; returns one segment per track
        active = np.flatnonzero(np.abs(audio) > 0.05)
        if not len(active):
            return []
        start, end = active[0] / 16000, active[-1] / 16000
        if progress:
            progress(end, len(audio) / 16000)
        return [Segment(start, end, f"Text von {self.name}")]


def _recording(tmp_path):
    sr = 48000
    me = np.zeros(sr * 6, dtype=np.float32)
    me[: sr * 2] = 0.3
    others = np.zeros(sr * 6, dtype=np.float32)
    others[sr * 3: sr * 5] = 0.3
    sf.write(tmp_path / "me.wav", me, sr)
    sf.write(tmp_path / "others.wav", others, sr)
    return tmp_path


def test_transcribe(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    folder = _recording(tmp_path)
    assert cli.main(["transcribe", str(folder), "--name", "Andrea"]) == 0
    md = (folder / "transcript.md").read_text(encoding="utf-8")
    assert md.index("Andrea:") < md.index("Gegenüber:")
    assert "[00:03] Gegenüber:" in md


def test_compare(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    folder = _recording(tmp_path)
    assert cli.main(["compare", str(folder), "--models", "large-v3-turbo", "a/b"]) == 0
    report = (folder / "comparison.md").read_text(encoding="utf-8")
    assert "erste 180 s" in report
    assert (folder / "comparison_a__b.md").exists()
    assert "large-v3-turbo" in report


def test_compare_with_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    folder = _recording(tmp_path)
    ref = tmp_path / "ref.txt"
    ref.write_text("Text von large-v3-turbo Text von large-v3-turbo", encoding="utf-8")
    assert cli.main(["compare", str(folder), "--models", "large-v3-turbo", "--reference", str(ref)]) == 0
    assert "| 0.0% |" in (folder / "comparison.md").read_text(encoding="utf-8")


def test_load_audio_resampling(tmp_path):
    sr = 48000
    t = np.arange(sr * 2) / sr
    sf.write(tmp_path / "x.wav", 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32), sr)
    audio = faster.load_audio(tmp_path / "x.wav")
    assert audio.dtype == np.float32 and len(audio) == 32000
    assert faster.load_audio(tmp_path / "x.wav", until_s=1).shape == (16000,)
    assert 0.45 < np.abs(audio[1000:-1000]).max() < 0.55  # tone preserved


def test_selftest_passes(capsys):
    assert cli.main(["selftest"]) == 0
    assert "Alles in Ordnung" in capsys.readouterr().out


def test_compare_with_corrected_transcript_per_track(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    folder = _recording(tmp_path)
    reference = {"tracks": {"me": "Andrea", "others": "Gegenüber"}, "edited": True, "segments": [
        {"start": 0.0, "end": 2.0, "text": "Text von large-v3", "speaker": "Andrea"},
        {"start": 3.0, "end": 5.0, "text": "ganz anders gesagt", "speaker": "Gegenüber"}]}
    (folder / "transcript.json").write_text(json.dumps(reference), encoding="utf-8")
    assert cli.main(["compare", str(folder), "--models", "large-v3", "--reference", "transcript"]) == 0
    report = (folder / "comparison.md").read_text(encoding="utf-8")
    assert "| WER Ich | WER Gegenüber |" in report
    row = next(line for line in report.splitlines() if line.startswith("| large-v3 |"))
    cells = [c.strip() for c in row.split("|")]
    # own track perfect; others: 3 wrong + 1 extra word against 3 reference words = 133 %
    assert cells[6] == "0.0%" and cells[7] == "133.3%"
    assert "nicht korrigiert" not in capsys.readouterr().out


def test_compare_warns_about_uncorrected_reference(tmp_path, monkeypatch, capsys):
    import json
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    folder = _recording(tmp_path)
    (folder / "transcript.json").write_text(json.dumps({"tracks": {}, "segments": []}), encoding="utf-8")
    assert cli.main(["compare", str(folder), "--models", "large-v3", "--reference", "transcript"]) == 0
    assert "nicht korrigiert" in capsys.readouterr().out
