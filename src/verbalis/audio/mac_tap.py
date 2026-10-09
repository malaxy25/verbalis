"""System audio on macOS through the Swift helper `verbalis-audiotap`.

macOS has no loopback; since macOS 14.2 Core Audio "process taps" can record what
all programs play. The helper (tools/macos/audiotap.swift, built by the GitHub
Actions and bundled into Verbalis.app) does that and streams mono float32 samples
on stdout. `TapDevice` wraps it so the recorder can use it like any soundcard
device: `with device.recorder(samplerate=…, blocksize=…) as rec: rec.record(numframes=…)`.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

HELPER_NAME = "verbalis-audiotap"
SYSTEM_AUDIO = "Systemton (alle Programme)"
MIN_MACOS = (14, 2)


def helper_path() -> Path | None:
    """The helper inside the app bundle, or the one built locally in a checkout."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / HELPER_NAME)
    candidates += [Path(sys.executable).parent / HELPER_NAME,
                   Path(__file__).resolve().parents[3] / "tools" / "macos" / "build" / HELPER_NAME]
    helper = next((p for p in candidates if p.is_file()), None)
    if helper is not None and not os.access(helper, os.X_OK):
        try:
            helper.chmod(0o755)   # in case packaging lost the executable bit
        except OSError:
            pass
    return helper


def macos_version() -> tuple[int, ...]:
    text = platform.mac_ver()[0]
    return tuple(int(p) for p in text.split(".") if p.isdigit()) if text else ()


def available() -> bool:
    """Can this Mac record the system audio without extra software?"""
    return sys.platform == "darwin" and macos_version() >= MIN_MACOS and helper_path() is not None


class TapDevice:
    """Looks like a soundcard microphone to the recorder."""

    name = SYSTEM_AUDIO
    id = "verbalis-audiotap"
    isloopback = True

    def __init__(self, command: list[str] | None = None):
        if command is None:
            helper = helper_path()
            if helper is None:
                raise RuntimeError("Das Hilfsprogramm für den Systemton fehlt in dieser Installation.")
            command = [str(helper)]
        self.command = command

    @contextmanager
    def recorder(self, samplerate: int, blocksize: int | None = None, channels: int | None = None):
        proc = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            header = _read_header(proc)
            yield _TapReader(proc, int(header["samplerate"]), samplerate)
        finally:
            proc.terminate()   # the helper removes its tap and aggregate device on SIGTERM
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _read_header(proc: subprocess.Popen) -> dict:
    line = proc.stderr.readline().decode("utf-8", "replace").strip()
    try:
        header = json.loads(line) if line else {"error": "keine Antwort"}
    except json.JSONDecodeError:
        header = {"error": line}
    if "error" in header or "samplerate" not in header:
        raise RuntimeError(f"Der Systemton kann nicht aufgenommen werden: {header.get('error', line)}")
    return header


class _TapReader:
    def __init__(self, proc: subprocess.Popen, source_rate: int, target_rate: int):
        self.proc = proc
        self.source_rate = source_rate
        self.target_rate = target_rate
        self.buffer = np.zeros(0, dtype=np.float32)
        self.resampler = None
        if source_rate != target_rate:
            import soxr

            self.resampler = soxr.ResampleStream(source_rate, target_rate, 1, dtype="float32")

    def record(self, numframes: int) -> np.ndarray:
        """Exactly `numframes` samples at the target rate, shape (numframes, 1). Blocks like a device."""
        while len(self.buffer) < numframes:
            wanted = max(int((numframes - len(self.buffer)) * self.source_rate / self.target_rate), 64)
            raw = self.proc.stdout.read(wanted * 4)
            if not raw:
                detail = self.proc.stderr.read().decode("utf-8", "replace").strip()
                raise RuntimeError("Die Systemton-Aufnahme wurde beendet." + (f" ({detail})" if detail else ""))
            samples = np.frombuffer(raw[: len(raw) // 4 * 4], dtype=np.float32)
            if self.resampler is not None:
                samples = self.resampler.resample_chunk(samples)
            self.buffer = np.concatenate([self.buffer, samples.astype(np.float32, copy=False)])
        block, self.buffer = self.buffer[:numframes], self.buffer[numframes:]
        return block.reshape(-1, 1)
