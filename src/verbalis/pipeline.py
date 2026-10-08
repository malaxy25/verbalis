"""Shared steps for CLI and app: metadata, audio files, transcription."""

from __future__ import annotations

import json
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import __version__
from .transcript import merge, save

if TYPE_CHECKING:
    from .corrections import CorrectionList

TRACKS = ("me", "others")
AUDIO_EXTENSIONS = (".flac", ".wav")
ARCHIVE_SAMPLERATE = 16_000  # what the models use anyway
Progress = Callable[[str, float], None]  # (display name, fraction 0..1)


# ---------------------------------------------------------------- audio files

def audio_file(folder: Path, track: str) -> Path | None:
    """The audio file of a track – compressed (.flac) or freshly recorded (.wav)."""
    for ext in AUDIO_EXTENSIONS:
        path = folder / f"{track}{ext}"
        if path.exists():
            return path
    return None


def has_audio(folder: Path) -> bool:
    return all(audio_file(folder, t) for t in TRACKS)


def audio_bytes(folder: Path) -> int:
    """Size of the audio files. Tolerates a file disappearing meanwhile
    (the background thread deletes the WAV after compressing)."""
    total = 0
    for t in TRACKS:
        for ext in AUDIO_EXTENSIONS:
            try:
                total += (folder / f"{t}{ext}").stat().st_size
            except FileNotFoundError:
                pass
    return total


def is_recording_folder(folder: Path) -> bool:
    """A recording with audio – or one whose audio was already deleted."""
    return has_audio(folder) or (folder / "meta.json").exists()


def compress_audio(folder: Path) -> int:
    """WAV (48 kHz) → FLAC (16 kHz, lossless). Saves about 85 % space.

    Works in chunks, so even hour-long recordings need little memory.
    Returns the number of converted tracks.
    """
    import numpy as np
    import soundfile as sf
    import soxr

    converted = 0
    for track in TRACKS:
        wav, flac = folder / f"{track}.wav", folder / f"{track}.flac"
        if not wav.exists():
            continue
        tmp = folder / f"{track}.flac.tmp"
        with sf.SoundFile(wav) as src, sf.SoundFile(tmp, "w", samplerate=ARCHIVE_SAMPLERATE, channels=1,
                                                    subtype="PCM_16", format="FLAC") as dst:
            resampler = soxr.ResampleStream(src.samplerate, ARCHIVE_SAMPLERATE, 1, dtype="float32") \
                if src.samplerate != ARCHIVE_SAMPLERATE else None
            for block in src.blocks(blocksize=src.samplerate * 10, dtype="float32", always_2d=True):
                mono = block.mean(axis=1)
                dst.write(resampler.resample_chunk(mono) if resampler else mono)
            if resampler:
                dst.write(resampler.resample_chunk(np.zeros(0, dtype=np.float32), last=True))
        tmp.replace(flac)
        wav.unlink()
        converted += 1
    if converted:
        update_meta(folder, audio={"format": "flac", "samplerate": ARCHIVE_SAMPLERATE})
    return converted


def delete_audio(folder: Path, reason: str) -> int:
    """Delete the audio files, keep the transcript. Returns the bytes freed."""
    freed = audio_bytes(folder)
    for track in TRACKS:
        for ext in (*AUDIO_EXTENSIONS, ".flac.tmp"):
            (folder / f"{track}{ext}").unlink(missing_ok=True)
    update_meta(folder, audio_deleted={
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "reason": reason})
    return freed


# ---------------------------------------------------------------- metadata

def write_meta(folder: Path, start: datetime, duration_s: float, samplerate: int,
               consent_time: str, devices: dict[str, str], tracks: list) -> dict:
    meta = {
        "app_version": __version__,
        "start": start.isoformat(timespec="seconds"),
        "duration_s": round(duration_s, 1),
        "samplerate": samplerate,
        "system": f"{platform.system()} {platform.release()}",
        "consent": {"confirmed": True, "timestamp": consent_time},
        "tracks": {
            t.name: {
                "file": t.path.name,
                "device": devices.get(t.name, ""),
                "length_s": round(t.written_frames / samplerate, 1),
                "padded_silence_s": round(t.padded_frames / samplerate, 2),
            }
            for t in tracks
        },
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def read_meta(folder: Path) -> dict:
    try:
        return json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_meta(folder: Path, **fields) -> None:
    meta = {**read_meta(folder), **fields}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def recording_start(folder: Path) -> datetime | None:
    """Start time from meta.json, else from the folder name (YYYY-MM-DD_HHMMSS)."""
    start = read_meta(folder).get("start")
    try:
        return datetime.fromisoformat(start) if start else \
            datetime.strptime(folder.name, "%Y-%m-%d_%H%M%S").astimezone()
    except ValueError:
        return None


# ---------------------------------------------------------------- transcription

def transcribe(folder: Path, transcriber, names: dict[str, str], until_s: float | None = None,
               progress: Progress | None = None, paused_time: Callable[[], float] | None = None):
    """Transcribe both tracks. Returns (paragraphs, compute_s, recording_s).

    names: track → display name. paused_time returns the seconds spent paused
    so far; they don't count as compute time.
    """
    from .transcription.faster import WHISPER_SAMPLERATE, load_audio

    paused_time = paused_time or (lambda: 0.0)
    tracks = {}
    compute = recording = 0.0
    for track, display_name in names.items():
        path = audio_file(folder, track)
        if path is None:
            raise FileNotFoundError(f"Die Audiodatei der Spur «{display_name}» fehlt – wurde sie gelöscht?")
        audio = load_audio(path, until_s)
        recording = max(recording, len(audio) / WHISPER_SAMPLERATE)

        def report(position, total, n=display_name):
            if progress:
                progress(n, min(position / total, 1.0) if total else 1.0)

        t, p = time.monotonic(), paused_time()
        tracks[display_name] = transcriber.transcribe(audio, progress=report)
        compute += (time.monotonic() - t) - (paused_time() - p)
        report(1, 1)
    return merge(tracks), compute, recording


def header(folder: Path, model: str, compute_s: float, recording_s: float) -> dict[str, str]:
    """User-facing header of a transcript (German labels)."""
    h = {"Modell": model, "Aufnahmedauer": f"{recording_s / 60:.1f} min",
         "Rechenzeit": f"{compute_s / 60:.1f} min ({compute_s / max(recording_s, 1e-9):.2f}× Echtzeit)"}
    start = read_meta(folder).get("start")
    return {"Aufnahme": start, **h} if start else h


def apply_corrections(paragraphs: list, corrections: "CorrectionList | None") -> int:
    """Apply the correction list to all paragraphs in place. Returns the count."""
    if corrections is None:
        return 0
    total = 0
    for p in paragraphs:
        p.text, n = corrections.apply(p.text)
        total += n
    return total


def create_transcript(folder: Path, transcriber, model: str, names: dict[str, str],
                      progress: Progress | None = None,
                      paused_time: Callable[[], float] | None = None,
                      corrections: "CorrectionList | None" = None) -> tuple[Path, float, float]:
    """Returns (path, compute_s, recording_s)."""
    paragraphs, compute, recording = transcribe(folder, transcriber, names, progress=progress,
                                                paused_time=paused_time)
    h = header(folder, model, compute, recording)
    if n := apply_corrections(paragraphs, corrections):
        h["Korrekturen"] = f"{n} automatisch ersetzt"
    path = save(folder, "transcript", paragraphs, f"Transkript {folder.name}", h, tracks=names)
    (folder / "transcript_original.json").unlink(missing_ok=True)  # older edits are obsolete
    return path, compute, recording
