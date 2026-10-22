"""Transcription with faster-whisper (CTranslate2).

Important settings:
- vad_filter: Whisper likes to "hallucinate" sentences such as «Untertitel im
  Auftrag des ZDF» in silence. Each of our tracks is silent half the time
  (while the other side talks). The VAD cuts silence out beforehand.
- condition_on_previous_text=False: prevents an error from propagating through
  the rest of the recording (repetition loops).
- hotwords: names/terms the model should prefer.
- word_timestamps: needed to split paragraphs at sentence boundaries (reading flow).
- prompt: the last sentences of the previous piece when a track is transcribed in
  pieces, so names and spelling stay consistent across the cuts.
- device "auto": an Nvidia GPU when cuda.prepare() says it is ready (experimental), otherwise
  the CPU. Any GPU error (e.g. too little graphics memory) falls back to the CPU.
"""

from __future__ import annotations

import logging
from math import gcd
from pathlib import Path
from typing import Callable

import numpy as np

from .base import Segment
from .models import ModelError, resolve

log = logging.getLogger(__name__)

WHISPER_SAMPLERATE = 16_000


def load_audio(path: Path, until_s: float | None = None) -> np.ndarray:
    """Load WAV/FLAC as mono at 16 kHz.

    Deliberately not via faster_whisper.decode_audio: that uses PyAV, and newer
    PyAV versions are incompatible with it. soundfile reads our files directly.
    """
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if until_s:  # None or 0 = whole recording
        mono = mono[: int(until_s * sr)]
    return _to_whisper_rate(mono, sr)


def load_piece(path: Path, start_s: float, end_s: float) -> np.ndarray:
    """Only the part start_s…end_s of a file, mono at 16 kHz – long calls are transcribed in pieces."""
    import soundfile as sf

    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        f.seek(min(int(start_s * sr), f.frames))
        data = f.read(max(int((end_s - start_s) * sr), 0), dtype="float32", always_2d=True)
    return _to_whisper_rate(data.mean(axis=1), sr)


def _to_whisper_rate(mono: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import resample_poly

    if sr != WHISPER_SAMPLERATE and len(mono):
        divisor = gcd(sr, WHISPER_SAMPLERATE)
        mono = resample_poly(mono, WHISPER_SAMPLERATE // divisor, sr // divisor)
    return mono.astype(np.float32, copy=False)


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str | None = None,
        beam_size: int = 5,
        keywords: str | None = None,
    ):
        from . import cuda

        self.name = model
        self.beam_size = beam_size
        self.keywords = keywords or None
        self.prompt: str | None = None
        self._auto = device == "auto"
        self.device, chosen_type = cuda.choose(device)
        try:
            self._model = self._load(self.device, compute_type or chosen_type)
        except ModelError:
            if not (self._auto and self.device == "cuda"):
                raise
            log.warning("Loading %s on the Nvidia GPU failed – using the CPU", model, exc_info=True)
            self._to_cpu()
        log.info("Model %s runs on %s", model, "the Nvidia GPU" if self.device == "cuda" else "the CPU")

    def _load(self, device: str, compute_type: str):
        from faster_whisper import WhisperModel

        try:
            return WhisperModel(resolve(self.name), device=device, compute_type=compute_type)
        except (RuntimeError, ValueError, OSError) as e:
            hint = ""
            if "/" in self.name and "model.bin" in str(e):
                hint = (
                    f"\nDas Repo ist vermutlich kein CTranslate2-Modell. Einmalig konvertieren mit:\n"
                    f"  verbalis convert-model {self.name}"
                )
            raise ModelError(f"Modell '{self.name}' konnte nicht geladen werden: {e}{hint}") from e

    def _to_cpu(self) -> None:
        self._model = None            # free the graphics memory first
        self._model = self._load("cpu", "int8")
        self.device = "cpu"

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
        try:
            return self._transcribe(audio, language, progress, duration)
        except RuntimeError:     # CUDA errors (out of memory, a missing library part) show up here
            if not (self._auto and self.device == "cuda"):
                raise
            log.warning("Transcribing on the Nvidia GPU failed – again on the CPU", exc_info=True)
            self._to_cpu()
            return self._transcribe(audio, language, progress, duration)

    def _transcribe(self, audio, language, progress, duration) -> list[Segment]:
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=self.beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            hotwords=self.keywords,
            initial_prompt=self.prompt or None,
            word_timestamps=True,
        )
        result = []
        for s in segments:  # generator: the actual work happens here
            text = s.text.strip()
            if text:
                words = [(w.start, w.end, w.word) for w in (s.words or [])]
                result.append(Segment(start=s.start, end=s.end, text=text, words=words or None))
            if progress:
                progress(s.end, duration)
        return result
