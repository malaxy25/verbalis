"""Transcription with faster-whisper (CTranslate2).

Important settings:
- vad_filter: Whisper likes to "hallucinate" sentences such as «Untertitel im
  Auftrag des ZDF» in silence. Each of our tracks is silent half the time
  (while the other side talks). The VAD cuts silence out beforehand.
- condition_on_previous_text=False: prevents an error from propagating through
  the rest of the recording (repetition loops).
- hotwords: names/terms the model should prefer.
"""

from __future__ import annotations

from math import gcd
from pathlib import Path
from typing import Callable

import numpy as np

from .base import Segment
from .models import ModelError, resolve

WHISPER_SAMPLERATE = 16_000


def load_audio(path: Path, until_s: float | None = None) -> np.ndarray:
    """Load WAV/FLAC as mono at 16 kHz.

    Deliberately not via faster_whisper.decode_audio: that uses PyAV, and newer
    PyAV versions are incompatible with it. soundfile reads our files directly.
    """
    import soundfile as sf
    from scipy.signal import resample_poly

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if until_s:  # None or 0 = whole recording
        mono = mono[: int(until_s * sr)]
    if sr != WHISPER_SAMPLERATE:
        divisor = gcd(sr, WHISPER_SAMPLERATE)
        mono = resample_poly(mono, WHISPER_SAMPLERATE // divisor, sr // divisor)
    return mono.astype(np.float32, copy=False)


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str | None = None,
        beam_size: int = 5,
        keywords: str | None = None,
    ):
        from faster_whisper import WhisperModel

        self.name = model
        self.beam_size = beam_size
        self.keywords = keywords or None
        compute_type = compute_type or ("int8" if device == "cpu" else "float16")
        try:
            self._model = WhisperModel(resolve(model), device=device, compute_type=compute_type)
        except (RuntimeError, ValueError, OSError) as e:
            hint = ""
            if "/" in model and "model.bin" in str(e):
                hint = (
                    f"\nDas Repo ist vermutlich kein CTranslate2-Modell. Einmalig konvertieren mit:\n"
                    f"  verbalis convert-model {model}"
                )
            raise ModelError(f"Modell '{model}' konnte nicht geladen werden: {e}{hint}") from e

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "de",
        progress: Callable[[float, float], None] | None = None,
    ) -> list[Segment]:
        """audio: mono float32 at 16 kHz (see load_audio)."""
        duration = len(audio) / WHISPER_SAMPLERATE
        if duration == 0:
            return []
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=self.beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            hotwords=self.keywords,
        )
        result = []
        for s in segments:  # generator: the actual work happens here
            text = s.text.strip()
            if text:
                result.append(Segment(start=s.start, end=s.end, text=text))
            if progress:
                progress(s.end, duration)
        return result
