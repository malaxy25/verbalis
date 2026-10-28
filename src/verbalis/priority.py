"""Thread and process priority on Windows: while Verbalis transcribes during a recording (live.py), the process
runs «below normal», so Teams and other programs come first – and the recorder threads raise themselves within
the process, so the audio is still read at normal level. Elsewhere these do nothing."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def _kernel32():
    import ctypes

    return ctypes.windll.kernel32 if sys.platform == "win32" else None


def lower_process(low: bool) -> None:
    """The whole process «below normal» (low) or back to normal. Only on Windows; never fails."""
    try:
        if k := _kernel32():
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000 if low else 0x20)  # BELOW_NORMAL / NORMAL
    except Exception:
        log.debug("Changing the process priority failed", exc_info=True)


def boost_thread() -> None:
    """The calling thread «highest» within the process: audio threads stay at normal level when the process
    runs below normal. Only on Windows; never fails."""
    try:
        if k := _kernel32():
            k.SetThreadPriority(k.GetCurrentThread(), 2)   # THREAD_PRIORITY_HIGHEST
    except Exception:
        log.debug("Raising the thread priority failed", exc_info=True)
