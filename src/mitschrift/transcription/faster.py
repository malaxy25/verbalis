"""Transkription mit faster-whisper (CTranslate2).

Wichtige Einstellungen:
- vad_filter: Whisper "halluziniert" in Stille gerne Sätze wie
  «Untertitel im Auftrag des ZDF». Jede unserer Spuren ist aber zur Hälfte
  still (während die andere Seite spricht). Der VAD schneidet Stille vorher weg.
- condition_on_previous_text=False: verhindert, dass sich ein Fehler über
  den Rest der Aufnahme fortpflanzt (Wiederholungsschleifen).
- hotwords: Fachbegriffe/Namen, die das Modell bevorzugt erkennen soll.
"""

from __future__ import annotations

from math import gcd
from pathlib import Path
from typing import Callable

import numpy as np

from .base import Segment
from .modelle import ModellFehler, aufloesen

SAMPLERATE_WHISPER = 16_000


def lade_audio(wav: Path, bis_s: float | None = None) -> np.ndarray:
    """WAV laden, auf Mono und 16 kHz bringen.

    Bewusst nicht über faster_whisper.decode_audio: das nutzt PyAV, und
    neuere PyAV-Versionen sind damit inkompatibel. Unsere WAVs liest
    soundfile direkt.
    """
    import soundfile as sf
    from scipy.signal import resample_poly

    daten, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    mono = daten.mean(axis=1)
    if bis_s:  # None oder 0 = ganze Aufnahme
        mono = mono[: int(bis_s * sr)]
    if sr != SAMPLERATE_WHISPER:
        teiler = gcd(sr, SAMPLERATE_WHISPER)
        mono = resample_poly(mono, SAMPLERATE_WHISPER // teiler, sr // teiler)
    return mono.astype(np.float32, copy=False)


class FasterWhisperTranscriber:
    def __init__(
        self,
        modell: str = "large-v3-turbo",
        geraet: str = "cpu",
        compute_type: str | None = None,
        beam_size: int = 5,
        stichworte: str | None = None,
    ):
        from faster_whisper import WhisperModel

        self.name = modell
        self.beam_size = beam_size
        self.stichworte = stichworte or None
        compute_type = compute_type or ("int8" if geraet == "cpu" else "float16")
        try:
            self._modell = WhisperModel(aufloesen(modell), device=geraet, compute_type=compute_type)
        except (RuntimeError, ValueError, OSError) as e:
            hinweis = ""
            if "/" in modell and "model.bin" in str(e):
                hinweis = (
                    f"\nDas Repo ist vermutlich kein CTranslate2-Modell. Einmalig konvertieren mit:\n"
                    f"  mitschrift modell-konvertieren {modell}"
                )
            raise ModellFehler(f"Modell '{modell}' konnte nicht geladen werden: {e}{hinweis}") from e

    def transkribiere(
        self,
        audio: np.ndarray,
        sprache: str = "de",
        fortschritt: Callable[[float, float], None] | None = None,
    ) -> list[Segment]:
        """audio: Mono float32 mit 16 kHz (siehe lade_audio)."""
        dauer = len(audio) / SAMPLERATE_WHISPER
        if dauer == 0:
            return []
        segmente, _info = self._modell.transcribe(
            audio,
            language=sprache,
            task="transcribe",
            beam_size=self.beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            hotwords=self.stichworte,
        )
        ergebnis = []
        for s in segmente:  # Generator: hier passiert die eigentliche Arbeit
            text = s.text.strip()
            if text:
                ergebnis.append(Segment(start=s.start, ende=s.end, text=text))
            if fortschritt:
                fortschritt(s.end, dauer)
        return ergebnis
