"""Keep the computer awake while recording and processing (0.7.45).

A recording that runs into sleep mode stops; a transcription or speaker diarization just halts. While Verbalis
records (also paused: the meeting goes on afterwards) or processes, it therefore asks the system not to sleep;
while it records it can also keep the screen on (setting «Bildschirm während der Aufnahme anlassen», on by
default – at a meeting on site you click the names in «Wer spricht gerade?»).

- Windows: a power request (PowerCreateRequest/PowerSetRequest); it shows in `powercfg /requests` and ends with
  the process.
- macOS: `caffeinate -i` (system) plus `-d` (screen), with `-w <pid>` so it ends with Verbalis.
- Linux: `systemd-inhibit` (sleep, plus idle for the screen) around `tail --pid=<pid>`, so it ends with
  Verbalis. Whether the desktop honours the idle lock for the screen differs; without systemd nothing happens.

Closing a laptop's lid still sends it to sleep. Everything here is best effort: a failure is logged once and
never disturbs a recording.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

REASON = "Verbalis: Aufnahme oder Transkription läuft"


class _Windows:
    SYSTEM, DISPLAY = 1, 0   # POWER_REQUEST_TYPE: PowerRequestSystemRequired, PowerRequestDisplayRequired

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class ReasonContext(ctypes.Structure):   # REASON_CONTEXT with POWER_REQUEST_CONTEXT_SIMPLE_STRING
            _fields_ = [("Version", wintypes.ULONG), ("Flags", wintypes.DWORD),
                        ("SimpleReasonString", wintypes.LPWSTR),
                        ("_rest", ctypes.c_byte * 16)]   # the union's larger «Detailed» variant

        k = ctypes.WinDLL("kernel32", use_last_error=True)   # own instance: argtypes stay local
        k.PowerCreateRequest.restype = wintypes.HANDLE
        k.PowerCreateRequest.argtypes = [ctypes.POINTER(ReasonContext)]
        k.PowerSetRequest.argtypes = k.PowerClearRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
        self._reason = ctypes.create_unicode_buffer(REASON)   # must stay alive with the request
        context = ReasonContext(0, 1, ctypes.cast(self._reason, wintypes.LPWSTR))
        handle = k.PowerCreateRequest(ctypes.byref(context))
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error() or "PowerCreateRequest failed")
        self._k, self._handle = k, handle
        self._on = {self.SYSTEM: False, self.DISPLAY: False}

    def apply(self, system: bool, display: bool) -> None:
        for kind, wanted in ((self.SYSTEM, system), (self.DISPLAY, display)):
            if wanted != self._on[kind]:
                call = self._k.PowerSetRequest if wanted else self._k.PowerClearRequest
                if not call(self._handle, kind):
                    raise OSError(f"PowerSetRequest/PowerClearRequest({kind}) failed")
                self._on[kind] = wanted


class _Process:
    """macOS and Linux: a helper process holds the lock as long as it runs."""

    def __init__(self, command) -> None:
        self._command = command   # (system, display) → argument list
        self._proc: subprocess.Popen | None = None

    def apply(self, system: bool, display: bool) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if system or display:
            self._proc = subprocess.Popen(self._command(system, display), stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mac_command(system: bool, display: bool, pid: int) -> list[str]:
    return ["/usr/bin/caffeinate", "-i", *(["-d"] if display else []), "-w", str(pid)]


def linux_command(system: bool, display: bool, pid: int, inhibit: str = "systemd-inhibit") -> list[str]:
    return [inhibit, "--what=" + ("sleep:idle" if display else "sleep"), "--who=Verbalis", "--why=" + REASON,
            "--mode=block", "tail", f"--pid={pid}", "-f", "/dev/null"]


def default_backend():
    """The way to keep this system awake, or None (then nothing happens)."""
    pid = os.getpid()
    if sys.platform == "win32":
        return _Windows()
    if sys.platform == "darwin" and os.path.exists("/usr/bin/caffeinate"):
        return _Process(lambda system, display: mac_command(system, display, pid))
    if sys.platform.startswith("linux") and (inhibit := shutil.which("systemd-inhibit")):
        return _Process(lambda system, display: linux_command(system, display, pid, inhibit))
    return None


class KeepAwake:
    """set(system, display) whenever the wish may have changed; only real changes reach the system."""

    def __init__(self, backend=None) -> None:
        self._backend = backend
        self._ready = backend is not None
        self._state = (False, False)
        self._failed = False
        self._lock = threading.Lock()

    @property
    def state(self) -> tuple[bool, bool]:
        return self._state

    def set(self, system: bool, display: bool) -> None:
        system = bool(system or display)   # a screen kept on keeps the system on too
        wanted = (system, bool(display))
        with self._lock:
            if wanted == self._state or self._failed:
                return
            try:
                if not self._ready:
                    self._backend, self._ready = default_backend(), True
                if self._backend is not None:
                    self._backend.apply(*wanted)
                    log.info("Keep awake: system %s, screen %s", *("on" if w else "off" for w in wanted))
                self._state = wanted
            except Exception:
                self._failed = True   # once is enough: the next try would fail the same way
                log.exception("Keeping the computer awake failed – it may go to sleep during a recording")
