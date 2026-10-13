"""Shared steps for CLI and app: metadata, audio files, transcription."""

from __future__ import annotations

import json
import logging
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import __version__
from .transcript import merge, save, segment_dict, sentences

if TYPE_CHECKING:
    from .corrections import CorrectionList

log = logging.getLogger(__name__)

TRACKS = ("me", "others")
AUDIO_EXTENSIONS = (".flac", ".wav")
ARCHIVE_SAMPLERATE = 16_000  # what the models use anyway
Progress = Callable[[str, float], None]  # (display name of the current track, fraction of all 0..1)


# ---------------------------------------------------------------- audio files

def audio_file(folder: Path, track: str) -> Path | None:
    """The audio file of a track – compressed (.flac) or freshly recorded (.wav)."""
    for ext in AUDIO_EXTENSIONS:
        path = folder / f"{track}{ext}"
        if path.exists():
            return path
    return None


def has_audio(folder: Path) -> bool:
    """At least one track – a single rescued track can still be transcribed."""
    return any(audio_file(folder, t) for t in TRACKS)


def missing_tracks(folder: Path) -> list[str]:
    return [t for t in TRACKS if audio_file(folder, t) is None]


# ---------------------------------------------------------------- crash-safe files

def write_json_atomic(path: Path, data) -> None:
    """Write JSON so that a crash leaves either the old or the new file, never half of one."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def repair_wav(path: Path) -> bool:
    """Make a WAV readable that wasn't closed (crash, power loss).

    The sizes in the header are only written when the file is closed; after a
    crash they are 0 or too small, so players and libsndfile see little or no
    audio although it is on disk. Sets them from the real file size. Returns True
    if something was fixed.
    """
    import struct

    size = path.stat().st_size
    with path.open("r+b") as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return False
        offset, fixed = 12, False
        while offset + 8 <= size:
            f.seek(offset)
            chunk_id, chunk_size = struct.unpack("<4sI", f.read(8))
            if chunk_id == b"data":
                real = size - offset - 8
                real -= real % 2                      # whole 16-bit samples only
                if chunk_size != real:
                    f.seek(offset + 4)
                    f.write(struct.pack("<I", real))
                    fixed = True
                break
            offset += 8 + chunk_size + (chunk_size % 2)
        if struct.unpack("<I", head[4:8])[0] != size - 8:
            f.seek(4)
            f.write(struct.pack("<I", size - 8))
            fixed = True
    return fixed


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

# Recording states in meta.json
RECORDING = "recording"          # running – if found after a restart, Verbalis had crashed
COMPLETE = "complete"
INCOMPLETE = "incomplete"        # a device failed; what was recorded until then is kept
STOP_TIMEOUT = "stop_timeout"    # a track didn't end in time; files may be incomplete
INTERRUPTED = "interrupted"      # found running after a restart (crash, power loss)

# Shown next to the consent checkbox; stored with every recording so it is clear what was confirmed
CONSENT_TEXT = "Alle Teilnehmenden haben der Aufnahme zugestimmt"
CONSENT_TEXT_VERSION = "2026-10"


def consent_record(timestamp: str) -> dict:
    return {"confirmed": True, "timestamp": timestamp, "text": CONSENT_TEXT, "text_version": CONSENT_TEXT_VERSION}


def start_meta(folder: Path, start: datetime, samplerate: int, consent_time: str, devices: dict[str, str]) -> dict:
    """Written when a recording starts, so consent and start survive a crash."""
    meta = {
        "app_version": __version__,
        "start": start.isoformat(timespec="seconds"),
        "state": RECORDING,
        "samplerate": samplerate,
        "system": f"{platform.system()} {platform.release()}",
        "consent": consent_record(consent_time),
        "devices": devices,
    }
    write_json_atomic(folder / "meta.json", meta)
    return meta


def write_meta(folder: Path, start: datetime, duration_s: float, samplerate: int,
               consent_time: str, devices: dict[str, str], tracks: list,
               state: str = COMPLETE, problem: str | None = None) -> dict:
    meta = {
        "app_version": __version__,
        "start": start.isoformat(timespec="seconds"),
        "state": state,
        "duration_s": round(duration_s, 1),
        "samplerate": samplerate,
        "system": f"{platform.system()} {platform.release()}",
        "consent": consent_record(consent_time),
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
    if problem:
        meta["problem"] = problem
    write_json_atomic(folder / "meta.json", meta)
    return meta


def read_meta(folder: Path) -> dict:
    """meta.json – {} if there is none, {"damaged": True} if it can't be read (never silently empty)."""
    try:
        data = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"damaged": True}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {"damaged": True}


def update_meta(folder: Path, **fields) -> None:
    meta = {**read_meta(folder), **fields}
    write_json_atomic(folder / "meta.json", meta)


def recording_start(folder: Path) -> datetime | None:
    """Start time from meta.json, else from the folder name (YYYY-MM-DD_HHMMSS)."""
    start = read_meta(folder).get("start")
    try:
        return datetime.fromisoformat(start) if start else \
            datetime.strptime(folder.name, "%Y-%m-%d_%H%M%S").astimezone()
    except ValueError:
        return None


# ---------------------------------------------------------------- transcription

PARTIAL = "transcript.partial.json"   # finished pieces while a transcription runs (resume after a crash)
PIECE_S = 120.0          # transcribe in pieces of about this length …
CUT_WINDOW_S = 20.0      # … cut at the quietest moment within ± this of the target
FRAME_S = 0.05           # loudness is measured per 50 ms
PAUSE_FRAMES = 10        # a pause is the quietest 0.5 s
PROMPT_CHARS = 200       # end of the previous piece, given to the model as context


def audio_levels(path: Path, until_s: float | None = None) -> tuple[list[float], float]:
    """Loudness (mean square) per FRAME_S, read in blocks so long calls need little memory; and the duration."""
    import soundfile as sf

    energies: list[float] = []
    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        frame = max(int(sr * FRAME_S), 1)
        limit = min(int(until_s * sr), f.frames) if until_s else f.frames
        read = 0
        for block in f.blocks(blocksize=frame * 200, dtype="float32", always_2d=True):
            block = block[:max(limit - read, 0)]
            read += len(block)
            mono = block.mean(axis=1)
            n = len(mono) // frame
            if n:
                energies.extend((mono[:n * frame].reshape(n, frame) ** 2).mean(axis=1).tolist())
            if read >= limit:
                break
    return energies, limit / sr


def cut_points(energies: list[float], duration: float, piece_s: float = PIECE_S,
               window_s: float = CUT_WINDOW_S) -> list[float]:
    """Where to cut a track into pieces: about every piece_s, in a speech pause (the quietest half second)."""
    import numpy as np

    if duration <= piece_s + window_s:
        return []
    e = np.asarray(energies, dtype=np.float64)
    smooth = np.convolve(e, np.ones(PAUSE_FRAMES) / PAUSE_FRAMES, mode="same") if len(e) else e
    cuts: list[float] = []
    position = 0.0
    while duration - position > piece_s + window_s:
        lo = int((position + piece_s - window_s) / FRAME_S)
        hi = int((position + piece_s + window_s) / FRAME_S)
        window = smooth[lo:hi]
        cut = (lo + int(np.argmin(window))) * FRAME_S + FRAME_S / 2 if len(window) else position + piece_s
        cuts.append(round(cut, 2))
        position = cut
    return cuts


def _edges(track_state: dict) -> list[float]:
    return [0.0, *track_state["cuts"], track_state["duration"]]


def _done_until(track_state: dict) -> float:
    return _edges(track_state)[track_state["done"]]


def _finished(track_state: dict) -> bool:
    return track_state["done"] >= len(track_state["cuts"]) + 1


def _load_partial(path: Path | None, model: str, names: dict[str, str], until_s: float | None) -> dict | None:
    """The saved progress – only if it belongs to the same model, names and length; otherwise start over."""
    if path is None or not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        log.warning("Partial transcript %s unreadable – starting over", path)
        return None
    if (state.get("version") != 1 or state.get("model") != model or state.get("names") != names
            or state.get("until_s") != until_s):
        log.info("Partial transcript %s was made with other settings – starting over", path)
        return None
    return state


def _prompt(segments: list[dict]) -> str | None:
    text = " ".join(s["text"] for s in segments[-5:])
    return text[-PROMPT_CHARS:].lstrip() or None


def transcribe(folder: Path, transcriber, names: dict[str, str], until_s: float | None = None,
               progress: Progress | None = None, paused_time: Callable[[], float] | None = None,
               diarize: dict[str, bool] | None = None, phase: Callable[[str], None] | None = None,
               problems: list[str] | None = None, partial: Path | None = None, model: str = ""):
    """Transcribe both tracks step by step. Returns (paragraphs, compute_s, recording_s).

    Each track is cut into pieces of about two minutes in speech pauses; the pieces
    of both tracks are done alternately (always the track that is further behind),
    so what is finished reads like a conversation. With `partial`, the finished
    pieces are saved after each one and a transcription that was cut off (crash,
    app closed) continues from there. Diarization and merging run at the end over
    everything.

    names: track → display name. paused_time returns the seconds spent paused
    so far; they don't count as compute time. progress(display name, fraction of
    the whole transcription).
    """
    from .transcription.base import Segment
    from .transcription.faster import load_audio, load_piece

    paused_time = paused_time or (lambda: 0.0)
    if not has_audio(folder):
        raise FileNotFoundError("Die Audiodateien dieser Aufnahme fehlen – wurden sie gelöscht?")
    # a rescued single track: transcribe what is there, the header says what is missing
    paths = {t: path for t in names if (path := audio_file(folder, t)) is not None}

    state = _load_partial(partial, model, names, until_s)
    if state is None:
        state = {"version": 1, "model": model, "names": names, "until_s": until_s, "compute_s": 0.0, "tracks": {}}
        for track, path in paths.items():
            energies, duration = audio_levels(path, until_s)
            state["tracks"][track] = {"duration": duration, "cuts": cut_points(energies, duration),
                                      "done": 0, "segments": []}
    else:
        log.info("Continuing the transcription of %s where it stopped", folder.name)
    tracks = state["tracks"]
    total = sum(ts["duration"] for ts in tracks.values()) or 1.0

    while open_tracks := [t for t, ts in tracks.items() if not _finished(ts)]:
        track = min(open_tracks, key=lambda t: _done_until(tracks[t]))   # the track that is further behind
        ts = tracks[track]
        start, end = _edges(ts)[ts["done"]], _edges(ts)[ts["done"] + 1]
        done_before = sum(_done_until(x) for x in tracks.values())

        def report(position, _length, n=names[track], base=done_before, piece=end - start):
            if progress:
                progress(n, min((base + min(position, piece)) / total, 1.0))

        t, p = time.monotonic(), paused_time()
        transcriber.prompt = _prompt(ts["segments"])
        for s in transcriber.transcribe(load_piece(paths[track], start, end), progress=report):
            ts["segments"].append({
                "start": round(s.start + start, 3), "end": round(s.end + start, 3), "text": s.text,
                "words": [[round(w[0] + start, 3), round(w[1] + start, 3), w[2]] for w in s.words] if s.words else None})
        ts["done"] += 1
        state["compute_s"] += (time.monotonic() - t) - (paused_time() - p)
        if partial is not None:
            write_json_atomic(partial, state)
        report(end - start, end - start)

    result = {}
    for track, ts in tracks.items():
        units = sentences([Segment(d["start"], d["end"], d["text"], track=track, words=d.get("words"))
                           for d in ts["segments"]])
        if (diarize or {}).get(track) and units:
            t, p = time.monotonic(), paused_time()
            units = _diarize(units, load_audio(paths[track], until_s), track, names[track], phase, problems)
            state["compute_s"] += (time.monotonic() - t) - (paused_time() - p)
        result[names[track]] = units
    recording = max((ts["duration"] for ts in tracks.values()), default=0.0)
    return merge(result), state["compute_s"], recording


def partial_transcript(folder: Path) -> dict | None:
    """What is finished of a running transcription: the time range done on *both* tracks, as paragraphs."""
    from .transcription.base import Segment

    try:
        state = json.loads((folder / PARTIAL).read_text(encoding="utf-8"))
        tracks, names = state["tracks"], state["names"]
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, KeyError):
        return None
    open_until = [_done_until(ts) for ts in tracks.values() if not _finished(ts)]
    until = min(open_until) if open_until else max((ts["duration"] for ts in tracks.values()), default=0.0)
    paragraphs = merge({names.get(track, track): [
        Segment(d["start"], d["end"], d["text"], track=track, words=d.get("words"))
        for d in ts["segments"] if d["start"] < until] for track, ts in tracks.items()})
    return {"until": until, "tracks": names, "segments": [segment_dict(p) for p in paragraphs]}


def _diarize(segments, audio, track, display_name, phase, problems):
    """Tell the speakers of one track apart. Never loses the transcript: on errors it stays as it is."""
    from . import diarization

    try:
        if not diarization.models_ready():
            if phase:
                phase("Modelle für die Sprechererkennung werden geladen (ca. 46 MB)")
            diarization.ensure_models()
        if phase:
            phase(f"Sprecher in «{display_name}» werden erkannt")
        return diarization.assign(segments, diarization.find_turns(audio), track, display_name)
    except Exception as e:
        log.exception("Diarization of %s failed", track)
        if problems is not None:
            problems.append(f"Sprechererkennung für «{display_name}» nicht möglich: {e}")
        return segments


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
                      corrections: "CorrectionList | None" = None, diarize: dict[str, bool] | None = None,
                      phase: Callable[[str], None] | None = None) -> tuple[Path, float, float]:
    """Returns (path, compute_s, recording_s). diarize: track → tell speakers apart."""
    problems: list[str] = []
    paragraphs, compute, recording = transcribe(folder, transcriber, names, progress=progress,
                                                paused_time=paused_time, diarize=diarize, phase=phase,
                                                problems=problems, partial=folder / PARTIAL, model=model)
    h = header(folder, model, compute, recording)
    if missing := missing_tracks(folder):
        h["Hinweis"] = "Unvollständig – keine Aufnahme von: " + ", ".join(names.get(t, t) for t in missing)
    meta = read_meta(folder)
    if meta.get("state") in (INCOMPLETE, STOP_TIMEOUT, INTERRUPTED):
        h["Aufnahme"] = (h.get("Aufnahme") or "") + " (nicht vollständig aufgenommen)"
    if n := apply_corrections(paragraphs, corrections):
        h["Korrekturen"] = f"{n} automatisch ersetzt"
    if problems:
        h["Sprecher"] = " ".join(problems)
    path = save(folder, "transcript", paragraphs, f"Transkript {folder.name}", h, tracks=names)
    (folder / "transcript_original.json").unlink(missing_ok=True)  # older edits are obsolete
    (folder / PARTIAL).unlink(missing_ok=True)                     # done: no need to resume
    return path, compute, recording
