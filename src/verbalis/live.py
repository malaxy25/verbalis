"""Transcribe while recording (0.7.42, on by default; setting «Schon während der Aufnahme transkribieren»).

While a recording runs, a background thread transcribes its WAV files piece by piece as they grow – the same
~2-minute pieces cut in speech pauses as `pipeline.transcribe`, in the same format. Its progress is kept in
`transcript.live.json`. When the recording ends, the rest of each track is planned (cut points up to the real
end) and the file waits for the normal transcription: that renames it to `transcript.partial.json` and simply
continues – so only the last minutes and the speaker diarization (which needs the whole recording) are left.
A separate name, because a cut-off normal transcription is resumed automatically at start, but a recording
the user has not asked to transcribe yet (number of people first) must not be.

The recording has priority: on Windows the process runs «below normal» while this works (Teams and other
programs come first) and the recorder threads raise themselves back to normal (priority.py). If the
transcription can't keep up, it simply falls behind; nothing is lost and the normal transcription does the rest.
"""

from __future__ import annotations

import json
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import pipeline
from .priority import lower_process

log = logging.getLogger(__name__)

LIVE = "transcript.live.json"
POLL_S = 5.0                                        # look for new audio this often
# a piece is cut once this much new audio is there (a little more than cut_points needs to look for a pause)
AHEAD_S = pipeline.PIECE_S + pipeline.CUT_WINDOW_S + 1.0


class Stopped(Exception):
    """The recording ended while a piece was being transcribed – the piece is dropped, the next job redoes it."""


# ---------------------------------------------------------------- reading a growing WAV

def wav_layout(path: Path) -> tuple[int, int, int] | None:
    """(start of the samples, sample rate, channels) of a 16-bit WAV, or None. The sizes in the header of a file
    still being written are not up to date (written at the end), so they are not used."""
    try:
        with path.open("rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return None
    offset, rate, channels = 12, None, None
    while offset + 8 <= len(head):
        chunk_id, size = struct.unpack("<4sI", head[offset:offset + 8])
        if chunk_id == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", head[offset + 8:offset + 24])
            if bits != 16:
                return None
        elif chunk_id == b"data":
            return (offset + 8, rate, channels) if rate and channels else None
        offset += 8 + size + (size % 2)
    return None


def wav_seconds(path: Path, layout: tuple[int, int, int]) -> float:
    start, rate, channels = layout
    try:
        return max(path.stat().st_size - start, 0) // (2 * channels) / rate
    except OSError:
        return 0.0


def read_wav(path: Path, layout: tuple[int, int, int], start_s: float, end_s: float) -> np.ndarray:
    """Mono float32 at the file's rate, start_s…end_s."""
    start, rate, channels = layout
    first, count = int(start_s * rate), max(int((end_s - start_s) * rate), 0)
    with path.open("rb") as f:
        f.seek(start + first * 2 * channels)
        raw = f.read(count * 2 * channels)
    data = np.frombuffer(raw[:len(raw) - len(raw) % (2 * channels)], dtype="<i2").astype(np.float32) / 32768
    return data.reshape(-1, channels).mean(axis=1)


def quiet_cut(audio: np.ndarray, rate: int, start_s: float) -> float:
    """Where to end the piece that starts at start_s: the quietest half second around PIECE_S (see cut_points).
    audio: the track from start_s on."""
    frame = max(int(rate * pipeline.FRAME_S), 1)
    n = len(audio) // frame
    energies = (audio[:n * frame].reshape(n, frame) ** 2).mean(axis=1)
    cuts = pipeline.cut_points(energies.tolist(), n * pipeline.FRAME_S)
    return round(start_s + (cuts[0] if cuts else pipeline.PIECE_S), 2)


# ---------------------------------------------------------------- the live transcription

class LiveTranscription:
    """One recording's transcription while it is recorded. start() → stop() when the recording ends →
    finish() once its files are closed (plans the rest; may wait for the current piece)."""

    def __init__(self, folder: Path, names: dict[str, str], model: str, prepare: Callable[[], object]):
        self.folder, self.names, self.model = folder, names, model
        self._prepare = prepare            # loads and returns the transcriber (in the thread)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="live-transcription", daemon=True)
        self.state = {"version": 1, "model": model, "names": names, "until_s": None, "compute_s": 0.0,
                      "tracks": {}}
        self.problem: str | None = None    # why it stopped working (shown in the app)
        self.stopped = False               # «Anhalten» in the app
        self.available_s = 0.0             # audio recorded so far (the shorter track)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def done_s(self) -> float:
        """Seconds transcribed on every track."""
        tracks = self.state["tracks"].values()
        return min((pipeline._done_until(ts) for ts in tracks), default=0.0)

    def _run(self) -> None:
        lower_process(True)
        try:
            transcriber = self._prepare()
            while not self._stop.is_set():
                if not self._piece(transcriber):
                    self._stop.wait(POLL_S)
        except Stopped:
            pass
        except Exception as e:
            log.exception("Live transcription of %s failed", self.folder.name)
            self.problem = str(e) or type(e).__name__
        finally:
            lower_process(False)

    def _piece(self, transcriber) -> bool:
        """Transcribe the next piece of the track that is further behind, if there is enough new audio."""
        ready = {}
        for track in self.names:
            path = self.folder / f"{track}.wav"
            layout = wav_layout(path) if path.exists() else None
            if layout is None:
                continue
            ts = self.state["tracks"].setdefault(track, {"duration": 0.0, "cuts": [], "done": 0, "segments": []})
            ready[track] = (path, layout, wav_seconds(path, layout), ts)
        self.available_s = min((r[2] for r in ready.values()), default=0.0)
        waiting = {t: r for t, r in ready.items() if r[2] - pipeline._done_until(r[3]) > AHEAD_S}
        if not waiting:
            return False
        track = min(waiting, key=lambda t: pipeline._done_until(waiting[t][3]))
        path, layout, _, ts = waiting[track]
        start = pipeline._done_until(ts)
        audio = read_wav(path, layout, start, start + AHEAD_S)
        end = quiet_cut(audio, layout[1], start)

        def check(_position, _length):
            if self._stop.is_set():
                raise Stopped()

        from .transcription.faster import _to_whisper_rate

        t = time.monotonic()
        transcriber.prompt = pipeline._prompt(ts["segments"])
        segments = transcriber.transcribe(_to_whisper_rate(audio[:int((end - start) * layout[1])], layout[1]),
                                          progress=check)
        for s in segments:
            ts["segments"].append({
                "start": round(s.start + start, 3), "end": round(s.end + start, 3), "text": s.text,
                "words": [[round(w[0] + start, 3), round(w[1] + start, 3), w[2]] for w in s.words]
                if s.words else None})
        # until the end is known: the cut points are the ends of the pieces done, "duration" the last of them
        ts["cuts"].append(end)
        ts["done"] = len(ts["cuts"])
        ts["duration"] = end
        self.state["compute_s"] += time.monotonic() - t
        pipeline.write_json_atomic(self.folder / LIVE, self.state)
        log.info("Live transcription of %s/%s: %.0f s done (%.1f s computing)", self.folder.name, track, end,
                 time.monotonic() - t)
        return True

    def finish(self, timeout: float | None = None) -> None:
        """After the recording: wait for the thread, then plan the rest of every track (plan_rest)."""
        self.stop()
        self._thread.join(timeout)
        if not any(ts["done"] for ts in self.state["tracks"].values()):
            (self.folder / LIVE).unlink(missing_ok=True)    # nothing finished: nothing to keep
            return
        plan_rest(self.folder, self.state)
        pipeline.write_json_atomic(self.folder / LIVE, self.state)
        log.info("Live transcription of %s finished: %.0f s done, rest planned", self.folder.name, self.done_s)


def plan_rest(folder: Path, state: dict) -> None:
    """Cut the rest of every track up to its real end, so the normal transcription continues from the last piece.
    While recording the end was unknown: the cut points were only the ends of the pieces done."""
    for track, ts in state["tracks"].items():
        path = pipeline.audio_file(folder, track)
        if path is None:
            continue
        energies, duration = pipeline.audio_levels(path)
        done_cuts = ts["cuts"][:ts["done"]]
        start = done_cuts[-1] if done_cuts else 0.0
        if duration > start + 1:
            rest = pipeline.cut_points(energies[int(start / pipeline.FRAME_S):], duration - start)
            ts["cuts"] = done_cuts + [round(start + c, 2) for c in rest]
            ts["duration"] = round(duration, 2)
            ts["done"] = len(done_cuts)
        else:     # (almost) nothing after the last piece: it was the end of the track
            ts["cuts"], ts["duration"] = done_cuts[:-1], start
            ts["done"] = len(ts["cuts"]) + 1
    state["planned"] = True


def take_over(folder: Path) -> bool:
    """Before the normal transcription: the live progress becomes its partial transcript (only if there is no
    newer one). Returns whether there was one."""
    live, partial = folder / LIVE, folder / pipeline.PARTIAL
    if not live.exists():
        return False
    try:
        state = json.loads(live.read_text(encoding="utf-8"))
        if not partial.exists():
            if not state.get("planned"):     # Verbalis was closed or crashed before the recording ended
                plan_rest(folder, state)
            pipeline.write_json_atomic(partial, state)
            live.unlink()
            return True
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("Live transcription of %s unreadable – transcribing from the start", folder.name)
    live.unlink(missing_ok=True)
    return False
