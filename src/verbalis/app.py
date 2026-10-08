"""UI: a native window (pywebview) with an HTML interface.

JavaScript calls the methods of `Api` directly (window.pywebview.api.…).
Every method returns {"ok": true, "data": …} or {"ok": false, "error": "…"},
so the UI can show errors in a readable way.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from . import __version__, logs
from .service import Service

UI = Path(__file__).parent / "ui" / "index.html"
PROJECT_URL = "https://github.com/malaxy25/verbalis/releases"
# pywebview only accepts letters, digits and spaces before the brackets (no hyphen)
ZIP_FILTER = "ZIP Archiv (*.zip)"
ICON = Path(__file__).parent / "ui" / "verbalis.ico"
log = logging.getLogger("verbalis")
_MUTEX = None  # holds the Windows lock against opening the app twice


class Api:
    def __init__(self, service: Service):
        self._s = service  # leading underscore: not exposed to JavaScript
        self._window = None  # set after the window is created (for the save dialog)

    def _call(self, fn, *args):
        try:
            return {"ok": True, "data": fn(*args)}
        except Exception as e:
            log.exception("Error in %s", getattr(fn, "__name__", fn))
            return {"ok": False, "error": str(e) or repr(e)}

    def version(self):
        return {"ok": True, "data": __version__}

    def state(self):
        return self._call(self._s.state)

    def settings(self):
        return self._call(self._s.settings)

    def save_settings(self, data):
        return self._call(self._s.save_settings, data)

    def devices(self):
        return self._call(self._s.devices)

    def models(self):
        return self._call(self._s.models)

    def start_recording(self, microphone, speakers, consent):
        return self._call(self._s.start_recording, microphone, speakers, bool(consent))

    def stop_recording(self):
        return self._call(self._s.stop_recording)

    def pause_recording(self):
        return self._call(self._s.pause_recording)

    def resume_recording(self):
        return self._call(self._s.resume_recording)

    def recordings(self):
        return self._call(self._s.recordings)

    def transcript(self, recording_id):
        return self._call(self._s.transcript, recording_id)

    def transcribe(self, recording_id):
        return self._call(self._s.transcribe, recording_id)

    def pause(self):
        return self._call(self._s.pause)

    def resume(self):
        return self._call(self._s.resume)

    def edit_transcript(self, recording_id, index, text):
        return self._call(self._s.edit_transcript, recording_id, int(index), text)

    def remember_corrections(self, recording_id, rules):
        return self._call(self._s.remember_corrections, recording_id, rules)

    def corrections(self):
        return self._call(self._s.corrections)

    def remove_correction(self, target, variant=None):
        return self._call(self._s.remove_correction, target, variant)

    def add_correction(self, variant, target):
        return self._call(self._s.add_correction, variant, target)

    def spelling_check(self, words):
        return self._call(self._s.spelling_check, words)

    def spelling_suggest(self, word):
        return self._call(self._s.spelling_suggest, word)

    def spelling_add(self, word):
        return self._call(self._s.spelling_add, word)

    def model_updates(self):
        return self._call(self._s.model_updates)

    def open_model_page(self, model):
        return self._call(self._s.open_model_page, model)

    def dismiss_notice(self):
        return self._call(self._s.dismiss_notice)

    def update_info(self):
        return self._call(self._s.update_info)

    def check_updates(self):
        return self._call(self._s.check_updates)

    def install_update(self):
        result = self._call(self._s.install_update)
        if result["ok"] and self._window is not None:
            # give the UI a moment to show the message, then close so the installer can replace files
            threading.Timer(1.5, self._window.destroy).start()
        return result

    def whats_new(self):
        return self._call(self._s.whats_new)

    def whats_new_seen(self):
        return self._call(self._s.whats_new_seen)

    def open_project_page(self):
        import webbrowser

        return self._call(webbrowser.open, PROJECT_URL)

    def audio_usage(self):
        return self._call(self._s.audio_usage)

    def delete_audio(self, recording_id):
        return self._call(self._s.delete_audio, recording_id)

    def open_folder(self, recording_id=""):
        return self._call(self._s.open_folder, recording_id)

    def delete_recording(self, recording_id):
        return self._call(self._s.delete_recording, recording_id)

    def logs(self, errors_only=False):
        return self._call(logs.read_entries, bool(errors_only))

    def export_logs(self):
        return self._call(self._export_logs)

    def _export_logs(self) -> dict | None:
        """Ask where to save (save dialog), then write the ZIP. None = cancelled."""
        name = logs.default_export_name()
        downloads = Path.home() / "Downloads"
        if self._window is None:
            target = downloads / name
        else:
            import webview

            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE, directory=str(downloads if downloads.exists() else Path.home()),
                save_filename=name, file_types=(ZIP_FILTER,))
            if not result:
                return None
            target = Path(result if isinstance(result, str) else result[0])
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        return {"path": str(logs.export(target, self._s.settings()))}


# ---------------------------------------------------------------- window size and position

DEFAULT_SIZE = (1180, 780)
MIN_SIZE = (860, 560)
TASKBAR = 48  # estimate in case Windows doesn't report the free area


def window_size(remembered: str = "", screen=None) -> tuple[int, int]:
    """Remembered or default size, but never larger than the screen.

    Room for taskbar and title bar is subtracted. All values are logical
    pixels – at 150 % scaling a Full HD screen has 1280 × 720.
    """
    width, height = DEFAULT_SIZE
    try:
        w, h = (int(x) for x in remembered.lower().split("x"))
        width, height = w, h
    except ValueError:
        pass
    if screen is not None:
        width = min(width, screen.width - 40)
        height = min(height, screen.height - 100)
    return max(width, MIN_SIZE[0]), max(height, MIN_SIZE[1])


def work_area(screen) -> tuple[int, int, int, int]:
    """Free area (x, y, width, height) without taskbar."""
    frame = getattr(screen, "frame", None)
    try:  # on Windows: WorkingArea, same units as the screen size
        return int(frame.X), int(frame.Y), int(frame.Width), int(frame.Height)
    except AttributeError:
        return screen.x, screen.y, screen.width, screen.height - TASKBAR


def window_position(width: int, height: int, screen) -> tuple[int | None, int | None]:
    """Center the window in the free area, all edges visible."""
    if screen is None:
        return None, None
    x, y, w, h = work_area(screen)
    return x + max((w - width) // 2, 0), y + max((h - height) // 2, 0)


def start() -> None:
    import webview

    service = Service(check_updates_on_start=True)
    try:
        screen = webview.screens[0]
    except Exception:
        log.warning("Screen size unknown, using default size", exc_info=True)
        screen = None
    width, height = window_size(service.settings()["window_size"], screen)
    x, y = window_position(width, height, screen)

    api = Api(service)
    window = webview.create_window(
        "Verbalis",
        html=UI.read_text(encoding="utf-8"),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        min_size=MIN_SIZE,
        text_select=True,
        background_color="#EEF1F4",
    )

    last_size: dict[str, str] = {}

    def remember_size(width: int, height: int) -> None:
        last_size["value"] = f"{width}x{height}"

    def on_closing() -> None:
        if "value" in last_size:
            service.save_settings({"window_size": last_size["value"]})
        service.shutdown()  # save a running recording properly

    api._window = window
    window.events.resized += remember_size
    window.events.closing += on_closing
    webview.start(icon=str(ICON))  # icon applies on Linux; on Windows it comes from the shortcut


# ---------------------------------------------------------------- start by double-click


class _ToLog:
    """Replaces stdout/stderr when there is no console window (verbalis-app.exe).

    Progress bars (tqdm, e.g. during model download) query isatty() and
    encoding – hence both exist.
    """

    encoding = "utf-8"

    def __init__(self, level: int):
        self.level = level

    def isatty(self) -> bool:
        return False

    def write(self, text: str) -> int:
        if text.strip():
            log.log(self.level, text.rstrip())
        return len(text)

    def flush(self) -> None:
        pass


def _setup_logging() -> None:
    path = logs.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    if sys.stdout is None or sys.stderr is None:  # no console
        sys.stdout, sys.stderr = _ToLog(logging.INFO), _ToLog(logging.ERROR)
    sys.excepthook = lambda t, v, tb: log.critical("Unhandled error", exc_info=(t, v, tb))
    threading.excepthook = lambda a: log.critical(
        "Unhandled error in thread %s", a.thread, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def _already_running() -> bool:
    """On Windows, prevent the app from running twice (two recordings at once)."""
    global _MUTEX
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\Verbalis-App")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def _notify(text: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Verbalis", 0x40)
    else:
        print(text)


def main() -> None:
    """Entry point for verbalis-app.exe and `verbalis app`."""
    from .migration import migrate_if_needed

    _setup_logging()
    log.info("Verbalis %s starting", __version__)
    if _already_running():
        _notify("Verbalis ist bereits geöffnet.")
        return
    try:
        migrate_if_needed()
    except Exception:
        log.exception("Migration from Mitschrift failed")
    try:
        start()
    except Exception:
        log.exception("Start failed")
        _notify(f"Verbalis konnte nicht gestartet werden.\n\nDetails stehen im Protokoll:\n{logs.log_path()}")
    log.info("Verbalis closed")
