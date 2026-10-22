"""UI: a native window (pywebview) with an HTML interface.

JavaScript calls the methods of `Api` directly (window.pywebview.api.…).
Every method returns {"ok": true, "data": …} or {"ok": false, "error": "…"},
so the UI can show errors in a readable way.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
import subprocess
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
_MUTEX = None  # holds the lock against opening the app twice (Windows mutex, Linux lock file)


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

    def state(self, focused=False):
        return self._call(self._s.state, bool(focused))

    def dismiss_call(self):
        return self._call(self._s.dismiss_call)

    def settings(self):
        return self._call(self._s.settings)

    def save_settings(self, data):
        return self._call(self._s.save_settings, data)

    def devices(self):
        return self._call(self._s.devices)

    def models(self):
        return self._call(self._s.models)

    def start_recording(self, microphone, speakers, consent, planned_id=""):
        return self._call(self._s.start_recording, microphone, speakers, bool(consent), planned_id or "")

    def plan_recording(self, data=None):
        return self._call(self._s.plan_recording, data)

    def update_details(self, recording_id, data):
        return self._call(self._s.update_details, recording_id, data)

    def projects(self):
        return self._call(self._s.projects)

    def preview_levels(self, microphone, speakers):
        return self._call(self._s.preview_levels, microphone or "", speakers or "")

    def stop_preview(self):
        return self._call(self._s.stop_preview)

    def stop_recording(self):
        return self._call(self._s.stop_recording)

    def extend_recording(self):
        return self._call(self._s.extend_recording)

    def keep_recording(self):
        return self._call(self._s.keep_recording)

    def pause_recording(self):
        return self._call(self._s.pause_recording)

    def resume_recording(self):
        return self._call(self._s.resume_recording)

    def recordings(self):
        return self._call(self._s.recordings)

    def transcript(self, recording_id):
        return self._call(self._s.transcript, recording_id)

    def transcribe(self, recording_id, people=None):
        return self._call(self._s.transcribe, recording_id, people)

    def audio_clip(self, recording_id, start, end):
        return self._call(self._s.audio_clip, recording_id, start, end)

    def pause(self):
        return self._call(self._s.pause)

    def resume(self):
        return self._call(self._s.resume)

    def edit_transcript(self, recording_id, index, text):
        return self._call(self._s.edit_transcript, recording_id, int(index), text)

    def split_paragraph(self, recording_id, index, before, after):
        return self._call(self._s.split_paragraph, recording_id, int(index), before, after)

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

    def check_models_now(self):
        return self._call(self._s.check_models_now)

    def model_updates(self):
        return self._call(self._s.model_updates)

    def open_model_page(self, model):
        return self._call(self._s.open_model_page, model)

    def speakers(self, recording_id):
        return self._call(self._s.speakers, recording_id)

    def rename_speakers(self, recording_id, names):
        return self._call(self._s.rename_speakers, recording_id, names)

    def merge_speakers(self, recording_id, source, target):
        return self._call(self._s.merge_speakers, recording_id, source, target)

    def reassign_speakers(self, recording_id, track, count):
        return self._call(self._s.reassign_speakers, recording_id, track, count)

    def partial_transcript(self, recording_id):
        return self._call(self._s.partial_transcript, recording_id)

    def set_paragraph_speaker(self, recording_id, index, speaker_id):
        return self._call(self._s.set_paragraph_speaker, recording_id, index, speaker_id)

    def speaker_sample(self, recording_id, speaker_id):
        return self._call(self._s.speaker_sample, recording_id, speaker_id)

    def prepare_model(self):
        return self._call(self._s.prepare_model)

    def update_model(self, model):
        return self._call(self._s.update_model, model)

    def rollback_model(self, model):
        return self._call(self._s.rollback_model, model)

    def dismiss_model_updates(self):
        return self._call(self._s.dismiss_model_updates)

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

    def install_check(self):
        return self._call(self._s.install_check)

    def install_to_applications(self):
        result = self._call(self._s.install_to_applications)
        if result["ok"] and self._window is not None:
            threading.Timer(1.5, self._window.destroy).start()   # the moved app starts when this one is gone
        return result

    def whats_new(self):
        return self._call(self._s.whats_new)

    def whats_new_seen(self):
        return self._call(self._s.whats_new_seen)

    def copy_text(self, text):
        from .service import copy_to_clipboard

        return self._call(copy_to_clipboard, str(text or ""))

    def diagnose_info(self):
        return self._call(self._s.diagnose_info)

    def check_network(self):
        return self._call(self._s.check_network)

    def start_diagnosis(self, microphone="", speakers=""):
        return self._call(self._s.start_diagnosis, microphone or "", speakers or "")

    def diagnosis(self):
        return self._call(self._s.diagnosis)

    def diagnose_report(self):
        return self._call(self._s.diagnose_report)

    def report_info(self):
        return self._call(self._s.report_info)

    def report_problem(self, message, contact="", with_log=True, with_diagnosis=True):
        return self._call(self._s.report_problem, message or "", contact or "", bool(with_log), bool(with_diagnosis))

    def report_by_mail(self, message):
        return self._call(self._s.report_by_mail, message or "")

    def open_data_folder(self):
        from .transcription.models import verbalis_home
        from .service import open_in_file_manager

        return self._call(open_in_file_manager, verbalis_home())

    def open_update_download(self):
        return self._call(self._s.open_update_download)

    def open_project_page(self):
        import webbrowser

        return self._call(webbrowser.open, PROJECT_URL)

    def audio_usage(self):
        return self._call(self._s.audio_usage)

    def delete_audio(self, recording_id):
        return self._call(self._s.delete_audio, recording_id)

    def keep_audio(self, recording_id, keep=True):
        return self._call(self._s.keep_audio, recording_id, bool(keep))

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
        return {"path": str(logs.export(target, self._s.settings(), redact=self._s.device_names_for_redaction()))}


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

    set_taskbar_identity()   # before any window exists
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

    def bring_to_front() -> None:   # click on the «call recognised» notification
        try:
            window.restore()
            window.show()
        except Exception:
            log.exception("Could not bring the window to the front")

    from .notify import notifier as make_notifier
    notifier = make_notifier(ICON, bring_to_front)
    service.call_notifier = notifier if notifier.available else None

    api._window = window
    window.events.resized += remember_size
    window.events.closing += on_closing
    window.events.closing += notifier.close
    webview.start(icon=str(ICON))


def set_taskbar_identity(platform: str = sys.platform, frozen: bool | None = None, shell32=None) -> bool:
    """Own taskbar identity when running from Python (development version).

    Windows groups taskbar buttons by an «application user model ID». A Python
    program without one counts as pythonw.exe and gets the Python logo, whatever
    icon the window has. The installed Verbalis.exe has its own identity already.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if platform != "win32" or frozen:
        return False
    try:
        if shell32 is None:
            import ctypes
            shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID("Frehner.Verbalis")
        return True
    except Exception as e:  # cosmetic – never stop the app for it
        log.warning("Could not set the taskbar identity: %s", e)
        return False


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


def _already_running(platform: str = sys.platform, lock_file: Path | None = None) -> bool:
    """On Windows and Linux, prevent the app from running twice (two recordings at once)."""
    global _MUTEX
    if platform.startswith("linux"):
        return _locked_elsewhere(lock_file)
    if platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\Verbalis-App")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def _locked_elsewhere(lock_file: Path | None = None) -> bool:
    """Linux: a lock on ~/.verbalis/app.lock, held as long as the app runs (freed by the system on exit)."""
    global _MUTEX
    import fcntl

    from .transcription.models import verbalis_home

    path = lock_file or verbalis_home() / "app.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return True
    _MUTEX = handle
    return False


def _notify(text: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Verbalis", 0x40)
    elif sys.platform.startswith("linux") and shutil.which("notify-send"):
        subprocess.run(["notify-send", "--app-name=Verbalis", "Verbalis", text], check=False, timeout=5)
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
        _notify(f"Verbalis konnte nicht gestartet werden.\n\nDetails stehen im Log:\n{logs.log_path()}")
    log.info("Verbalis closed")
    if audio_still_open():
        logging.shutdown()
        os._exit(0)


def audio_still_open(platform: str = sys.platform, threads=None) -> bool:
    """True on macOS while an audio device may still be open when the app ends.

    soundcard hands every audio block to Python from a CoreAudio thread. If a
    device still delivers while Python shuts down, the app crashes on quitting
    (0.7.33, after waking the Mac). Everything is saved and logged by then, so
    the app may end without Python's clean-up.
    """
    if platform != "darwin":
        return False
    threads = threading.enumerate() if threads is None else threads
    return any(t.name.startswith("track-") and t.is_alive() for t in threads)
