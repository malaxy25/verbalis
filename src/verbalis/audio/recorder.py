"""Two-track recording: microphone ("me") and loopback ("others").

Each track runs in its own thread and writes straight into a WAV file (mono,
16 bit). Long calls therefore don't fill RAM, and after a crash everything
recorded so far is on disk.

Sync: both tracks refer to the same start time t0. If a device delivers no
data for a while (e.g. a driver glitch), we pad the gap with silence. This
keeps the timestamps of both tracks comparable – important for merging the
transcripts later.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

SAMPLERATE = 48_000
BLOCK_SECONDS = 0.1
GAP_TOLERANCE_SECONDS = 0.25
TRACKS = ("me", "others")


def missing_frames(
    elapsed_s: float,
    samplerate: int,
    written: int,
    chunk_length: int,
    tolerance_s: float = GAP_TOLERANCE_SECONDS,
) -> int:
    """How many frames of silence are missing before the current chunk.

    The chunk ends "now". Whatever is missing between what was written so far
    and the start of the chunk is a gap. Small deviations (jitter) are ignored
    so we don't constantly insert tiny bits of silence.
    """
    expected = int(elapsed_s * samplerate)
    gap = expected - written - chunk_length
    return gap if gap > tolerance_s * samplerate else 0


def _init_com() -> None:
    """On Windows every audio thread needs COM initialisation."""
    if sys.platform == "win32":
        import ctypes

        # COINIT_MULTITHREADED = 0; "already initialised" is fine.
        ctypes.windll.ole32.CoInitializeEx(None, 0)


@dataclass
class TrackStatus:
    name: str
    path: Path
    written_frames: int = 0
    padded_frames: int = 0
    level_rms: float = 0.0
    error: BaseException | None = None


class Track(threading.Thread):
    def __init__(
        self,
        name: str,
        device: Any,
        path: Path,
        stop: threading.Event,
        t0: float,
        samplerate: int = SAMPLERATE,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__(name=f"track-{name}", daemon=True)
        self.device = device
        self.stop_event = stop
        self.t0 = t0
        self.samplerate = samplerate
        self.clock = clock
        self.status = TrackStatus(name=name, path=path)

    def run(self) -> None:
        try:
            _init_com()
            self._record()
        except BaseException as e:  # report errors to the main thread
            self.status.error = e
            self.stop_event.set()

    def _record(self) -> None:
        block = int(self.samplerate * BLOCK_SECONDS)
        s = self.status
        with sf.SoundFile(
            s.path, "w", samplerate=self.samplerate, channels=1, subtype="PCM_16"
        ) as file, self.device.recorder(samplerate=self.samplerate, blocksize=block) as rec:
            while not self.stop_event.is_set():
                data = rec.record(numframes=block)
                mono = data.mean(axis=1) if data.ndim == 2 else data
                mono = mono.astype(np.float32, copy=False)

                gap = missing_frames(self.clock() - self.t0, self.samplerate, s.written_frames, len(mono))
                if gap:
                    file.write(np.zeros(gap, dtype=np.float32))
                    s.written_frames += gap
                    s.padded_frames += gap

                file.write(mono)
                s.written_frames += len(mono)
                s.level_rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0


@dataclass
class TwoTrackRecorder:
    """Starts and stops the microphone and loopback tracks together."""

    microphone: Any
    loopback: Any
    folder: Path
    samplerate: int = SAMPLERATE
    stop_event: threading.Event = field(default_factory=threading.Event)
    tracks: list[Track] = field(default_factory=list)
    t0: float = 0.0

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic()
        self.tracks = [
            Track("me", self.microphone, self.folder / "me.wav", self.stop_event, self.t0, self.samplerate),
            Track("others", self.loopback, self.folder / "others.wav", self.stop_event, self.t0, self.samplerate),
        ]
        for track in self.tracks:
            track.start()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        for track in self.tracks:
            track.join(timeout)

    @property
    def running(self) -> bool:
        return not self.stop_event.is_set()

    @property
    def errors(self) -> list[BaseException]:
        return [t.status.error for t in self.tracks if t.status.error]

    def status(self) -> list[TrackStatus]:
        return [t.status for t in self.tracks]
