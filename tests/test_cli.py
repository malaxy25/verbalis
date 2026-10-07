"""Befehle transkribieren/vergleichen mit einem simulierten Modell durchspielen."""

import numpy as np
import soundfile as sf

from mitschrift import __main__ as cli
from mitschrift.transcription import faster
from mitschrift.transcription.base import Segment


class FakeTranscriber:
    def __init__(self, modell, geraet="cpu", stichworte=None, beam_size=5):
        self.name = modell

    def transkribiere(self, audio, sprache="de", fortschritt=None):
        # Lauter Bereich = Sprache; liefert ein Segment pro Spur
        aktiv = np.flatnonzero(np.abs(audio) > 0.05)
        if not len(aktiv):
            return []
        start, ende = aktiv[0] / 16000, aktiv[-1] / 16000
        if fortschritt:
            fortschritt(ende, len(audio) / 16000)
        return [Segment(start, ende, f"Text von {self.name}")]


def _aufnahme(tmp_path):
    sr = 48000
    ich = np.zeros(sr * 6, dtype=np.float32)
    ich[: sr * 2] = 0.3
    gegenueber = np.zeros(sr * 6, dtype=np.float32)
    gegenueber[sr * 3: sr * 5] = 0.3
    sf.write(tmp_path / "ich.wav", ich, sr)
    sf.write(tmp_path / "gegenueber.wav", gegenueber, sr)
    return tmp_path


def test_transkribieren(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    ordner = _aufnahme(tmp_path)
    assert cli.main(["transkribieren", str(ordner), "--name", "Andrea"]) == 0
    md = (ordner / "transkript.md").read_text(encoding="utf-8")
    assert md.index("Andrea:") < md.index("Gegenüber:")
    assert "[00:03] Gegenüber:" in md


def test_vergleichen(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    ordner = _aufnahme(tmp_path)
    assert cli.main(["vergleichen", str(ordner), "--modelle", "large-v3-turbo", "a/b"]) == 0
    bericht = (ordner / "vergleich.md").read_text(encoding="utf-8")
    assert "erste 180 s" in bericht
    assert (ordner / "vergleich_a__b.md").exists()
    assert "large-v3-turbo" in bericht


def test_lade_audio_resampling(tmp_path):
    sr = 48000
    t = np.arange(sr * 2) / sr
    sf.write(tmp_path / "x.wav", 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32), sr)
    audio = faster.lade_audio(tmp_path / "x.wav")
    assert audio.dtype == np.float32 and len(audio) == 32000
    assert faster.lade_audio(tmp_path / "x.wav", bis_s=1).shape == (16000,)
    # Ton bleibt erhalten (Amplitude ~0.5)
    assert 0.45 < np.abs(audio[1000:-1000]).max() < 0.55


def test_vergleichen_mit_referenz(tmp_path, monkeypatch):
    monkeypatch.setattr(faster, "FasterWhisperTranscriber", FakeTranscriber)
    ordner = _aufnahme(tmp_path)
    ref = tmp_path / "ref.txt"
    ref.write_text("Text von large-v3-turbo Text von large-v3-turbo", encoding="utf-8")
    assert cli.main(["vergleichen", str(ordner), "--modelle", "large-v3-turbo", "--referenz", str(ref)]) == 0
    bericht = (ordner / "vergleich.md").read_text(encoding="utf-8")
    assert "| 0.0% |" in bericht
