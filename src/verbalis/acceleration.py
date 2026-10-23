"""Faster transcription on graphics chips (experimental): status, loading the add-on, measuring speed.

- Windows/Linux with an Nvidia card: CUDA (transcription/cuda.py) – once ready, the app uses it.
- Mac with M chip: MLX (transcription/mlx.py) – measured only, the app keeps transcribing on the
  CPU until the measurements show MLX is as good (no beam search there).

The speed test transcribes a piece of the newest recording that still has audio, on the CPU and
on the graphics chip, and compares time and words. Only numbers leave this module – never text.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

from . import pipeline

TEST_SECONDS = 120          # the piece of a recording the speed test transcribes
SIZES = {"nvidia": "1.3 GB", "mlx": "90 MB"}
NAMES = {"cpu": "CPU", "cuda": "Nvidia-Grafikkarte", "mlx": "Apple-Grafikchip (MLX)"}


def kind() -> str | None:
    """Which graphics chip this system could use: "nvidia", "mlx" or None."""
    if sys.platform == "darwin":
        return "mlx"
    if sys.platform == "win32" or sys.platform.startswith("linux"):
        return "nvidia"
    return None


def info() -> dict:
    """{"kind", "ready", "problem", "can_install", "size"} – for the diagnosis and its buttons."""
    which = kind()
    if which == "nvidia":
        from .transcription import cuda

        status = cuda.status()
        return {"kind": which, "ready": status["problem"] is None, "problem": status["problem"],
                "can_install": status["gpus"] > 0 and bool(status["missing"]), "size": SIZES[which],
                "gpus": status["gpus"]}
    if which == "mlx":
        from .transcription import mlx

        status = mlx.status()
        return {"kind": which, "ready": status["ready"], "problem": status["problem"],
                "can_install": status["supported"] and not status["ready"], "size": SIZES[which]}
    return {"kind": None, "ready": False, "problem": "Auf diesem System gibt es keine Beschleunigung.",
            "can_install": False, "size": ""}


def install(progress: Callable[[str, float], None] | None = None) -> None:
    which = kind()
    if which == "nvidia":
        from .transcription import cuda

        cuda.install(progress)
    elif which == "mlx":
        from .transcription import mlx

        mlx.install(progress)


def newest_audio(recordings: Path) -> Path | None:
    """The system-audio track of the newest recording with audio (else its microphone track)."""
    if not recordings.is_dir():
        return None
    for folder in sorted((f for f in recordings.iterdir() if f.is_dir()), reverse=True):
        for track in ("others", "me"):
            path = pipeline.audio_file(folder, track)
            if path is not None:
                return path
    return None


def default_transcriber(model: str, device: str):
    if device == "mlx":
        from .transcription.mlx import MlxTranscriber

        return MlxTranscriber(model)
    from .transcription.faster import FasterWhisperTranscriber

    return FasterWhisperTranscriber(model, device=device)


def speed_test(model: str, audio_path: Path, accelerated: str | None,
               make: Callable[[str, str], object] = default_transcriber,
               phase: Callable[[str], None] = lambda text: None,
               clock: Callable[[], float] = time.monotonic, seconds: float = TEST_SECONDS) -> dict:
    """Transcribe the same piece on the CPU and on `accelerated` ("cuda", "mlx" or None)."""
    from .evaluation import error_rate
    from .transcription.faster import WHISPER_SAMPLERATE, load_piece

    audio = load_piece(audio_path, 0.0, seconds)
    duration = len(audio) / WHISPER_SAMPLERATE
    results, texts = [], {}
    for device in ["cpu"] + ([accelerated] if accelerated else []):
        phase(f"{NAMES[device]}: Modell laden …")
        tr = make(model, device)
        used = getattr(tr, "device", device)
        phase(f"{NAMES[device]}: {round(duration)} s Audio transkribieren …")
        started = clock()
        segments = tr.transcribe(audio)
        took = clock() - started
        texts[device] = " ".join(s.text for s in segments)
        results.append({"device": device, "used": used, "seconds": round(took, 1),
                        "factor": round(took / max(duration, 1e-9), 2), "words": len(texts[device].split())})
        del tr
    agreement = None
    if accelerated and texts.get("cpu", "").strip():
        agreement = round(max(0.0, 1.0 - error_rate(texts["cpu"], texts[accelerated]).wer), 3)
    return {"audio_s": round(duration), "results": results, "agreement": agreement}


def result_lines(result: dict) -> list[str]:
    """The speed test as German lines (screen and diagnosis)."""
    lines = []
    cpu = next((r for r in result["results"] if r["device"] == "cpu"), None)
    for r in result["results"]:
        text = f"{NAMES[r['device']]}: {r['seconds']} s für {result['audio_s']} s Audio ({r['factor']}× Echtzeit)"
        if r["used"] != r["device"]:
            text += f" – lief auf {NAMES.get(r['used'], r['used'])} (Grafikkarte nicht nutzbar, siehe Log)"
        elif cpu and r is not cpu and r["seconds"]:
            text += f" – {cpu['seconds'] / r['seconds']:.1f}× so schnell wie die CPU"
        lines.append(text)
    if result.get("agreement") is not None:
        lines.append(f"Übereinstimmung der Texte: {result['agreement']:.0%}")
    return lines
