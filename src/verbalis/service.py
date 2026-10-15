"""The logic behind the UI – independent of the window.

The UI polls `state()` regularly and calls actions. Transcriptions run one
after another in a background thread so recording and UI never block. The
loaded model stays in memory as long as the setting doesn't change (loading
takes ~15 s).

Pausing: the thread stops after each finished text segment while paused
manually or while a recording is running (otherwise both compete for the CPU,
which can cause dropouts in the recording).

User-facing strings (errors, phases) are German – the UI is German.
"""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import __version__, feedback, hardware, pipeline, updates
from .corrections import CorrectionList, suggestions
from .settings import Settings
from .spelling import Speller
from .transcript import is_default_name, segment_from_dict, to_markdown
from .transcription.models import verbalis_home

VALID_ID = re.compile(r"^[\w\-]+$")

# Disk space: two 48 kHz 16-bit tracks ≈ 11.5 MB per minute before compression
MB_PER_MINUTE = 2 * 48_000 * 2 * 60 / 1e6
MIN_FREE_TO_START_MB = 500     # refuse to start below this
WARN_FREE_MB = 2_000           # show how many minutes are left below this
STOP_FREE_MB = 150             # stop and save the recording below this
DISK_CHECK_EVERY_S = 5


class ShuttingDown(BaseException):
    """Raised in the worker when the app closes while it waits (e.g. during a pause).

    BaseException, so that «never lose the transcript» handlers (except Exception) don't
    swallow it and save half a result.
    """
CLEANUP = ":cleanup"          # queue task (not a valid recording ID)
CLEANUP_EVERY_S = 3600        # additionally every hour while the app stays open
SOUND_DB = -55.0              # louder than this counts as "something is coming through"
NO_DATA_AFTER_S = 5.0         # a track that has delivered no audio at all after this is reported
MAX_CLIP_S = 120.0            # longest passage played at once
MAX_PEOPLE = 30               # «Anzahl Personen» when re-assigning speakers
CALL_CHECK_S = 3.0            # how often to look for a call app using the microphone
PLANNED_DUE_S = 30 * 60       # a planned recording this close to now is offered when a call starts
CALL_OVER_AFTER_S = 30.0      # the call app hasn't used the microphone this long: ask whether to stop
END_WARNING_S = 5 * 60        # notice this long before the maximum recording time is reached
EXTEND_S = 30 * 60            # «+30 Min.»
UI_FOCUS_S = 2.0              # the window counts as «in front» if it said so this recently
PREVIEW_IDLE_S = 3.0          # level meters before a recording: close the devices when the UI stops asking
MB = 1024 * 1024              # as shown in Windows Explorer
log = logging.getLogger(__name__)


def _db(rms: float) -> float:
    return round(max(20 * math.log10(rms), -90.0), 1) if rms > 1e-9 else -90.0


def copy_to_clipboard(text: str, run: Callable = subprocess.run) -> bool:
    """Copy text with the system's own tool. True if done here; False = let the window do it.

    On macOS the window (WebKit) only allows the clipboard right after a click – Verbalis
    first asks Python for the text, and by then WebKit has refused («Kopieren» did nothing).
    """
    if sys.platform != "darwin":
        return False
    result = run(["/usr/bin/pbcopy"], input=text.encode("utf-8"), env={**os.environ, "LANG": "en_US.UTF-8"},
                 timeout=5, check=False)
    return result.returncode == 0


def open_in_file_manager(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Service:
    def __init__(
        self,
        settings: Settings | None = None,
        recorder_factory: Callable | None = None,
        transcriber_factory: Callable | None = None,
        select_devices: Callable | None = None,
        list_devices: Callable | None = None,
        cleanup_on_start: bool = True,
        speller: Speller | None = None,
        check_updates_on_start: bool = False,
        monitor_factory: Callable | None = None,
        detect_calls: Callable | None = None,
    ):
        self._lock = threading.RLock()
        self._s = settings or Settings.load()
        self._recorder_factory = recorder_factory or self._default_recorder
        self._transcriber_factory = transcriber_factory or self._default_transcriber
        self._select_devices = select_devices or self._default_select
        self._list_devices = list_devices or self._default_list
        self._monitor_factory = monitor_factory or self._default_monitor
        self._monitor = None              # level meters before a recording
        self._monitor_key: tuple | None = None
        self._monitor_asked = 0.0         # when the UI last asked for levels (monotonic)
        self._monitor_failed: tuple | None = None   # (devices, when) – don't retry 4× a second
        self._call: dict | None = None    # a call app uses the microphone: {"apps", "dismissed", "planned"}
        self._ui_focused = 0.0            # when the window last said it is in front (monotonic)
        self.call_notifier = None         # set by the app: shows a Windows notification (show/hide)
        self._diagnosis: dict | None = None   # the audio test in steps: {"running", "steps": [...]}
        self._network: list[dict] | None = None

        self._rec = None
        self._rec_info: dict = {}
        self._recording_error: str | None = None
        self._others_last_sound = 0.0   # when the others track last had sound (monotonic)

        self._queue: queue.Queue[str | tuple | None] = queue.Queue()   # recording ids, CLEANUP, («speakers», …)
        self._queued: list[str] = []
        self._job: dict | None = None
        self._errors: dict[str, str] = {}
        self._transcriber = None
        self._transcriber_model: str | None = None
        self._manual_pause = False
        self._speller = speller or Speller()   # loads the dictionary on first use
        self._stopping = threading.Event()      # set by shutdown(); waiting loops give up
        self._disk = {"checked": 0.0, "free_mb": None}
        self._update: dict | None = None        # result of the last update check
        self._notice: str | None = None         # neutral information for the UI, e.g. a model update
        self._model_updates: tuple[float, dict] | None = None   # (checked at, result) – cached
        self._model_status: dict[str, dict] = {}   # model → {"state": current|update|failed, "changed", "checked"}
        self._model_updates_dismissed = False
        self._model_download: dict | None = None  # {"model", "progress"} while an update downloads
        self._transcriber_revision: str | None = None
        self._update_progress: float | None = None

        self._worker = threading.Thread(target=self._work, name="transcription", daemon=True)
        self._worker.start()
        try:
            self._recover_interrupted()   # before anything else touches the recordings
        except OSError:
            log.exception("Checking for interrupted recordings failed")
        try:
            self._resume_transcriptions()
        except OSError:
            log.exception("Checking for cut-off transcriptions failed")
        if cleanup_on_start:
            self._queue.put(CLEANUP)  # check old audio files
        if detect_calls is None and sys.platform == "win32":
            from .audio.call_detect import detect as detect_calls
        if detect_calls is not None:
            threading.Thread(target=self._watch_calls, args=(detect_calls,), name="call-detection",
                             daemon=True).start()
        if check_updates_on_start and self._s.update_check == "on":
            threading.Thread(target=self._check_updates_safely, name="update-check", daemon=True).start()

    # ------------------------------------------------------------ default building blocks

    @staticmethod
    def _default_recorder(microphone, loopback, folder):
        from .audio.recorder import TwoTrackRecorder

        return TwoTrackRecorder(microphone, loopback, folder)

    @staticmethod
    def _default_monitor(microphone, loopback):
        from .audio.recorder import LevelMonitor

        return LevelMonitor(microphone, loopback)

    @staticmethod
    def _default_transcriber(model: str):
        from .transcription.faster import FasterWhisperTranscriber

        return FasterWhisperTranscriber(model)

    @staticmethod
    def _default_select(microphone, speakers):
        from .audio.devices import select

        return select(microphone, speakers)

    @staticmethod
    def _default_list():
        from .audio.devices import device_names

        return device_names()

    # ------------------------------------------------------------ settings & devices

    def settings(self) -> dict:
        return self._s.as_dict()

    def device_names_for_redaction(self) -> list[str]:
        """Names of all audio devices – removed from a log export (they often contain personal names)."""
        names = [self._s.microphone, self._s.speakers]
        try:
            found = self._list_devices() or {}
            names += found.get("microphones", []) + found.get("speakers", [])
        except Exception:
            pass
        return [n for n in names if n]

    def save_settings(self, data: dict) -> dict:
        with self._lock:
            old = self._s
            new = Settings.from_dict({**self._s.as_dict(), **data})
            new.save()
            self._s = new
        if (old.audio_days, old.audio_max_mb) != (new.audio_days, new.audio_max_mb):
            self._queue.put(CLEANUP)
        return self._s.as_dict()

    def devices(self) -> dict:
        return self._list_devices()

    def models(self) -> list[dict]:
        """Recommended and own models, with whether they are already on this computer."""
        from .transcription.models import (DISPLAY_NAMES, RECOMMENDED, SIZE_GB, converted_models, is_local,
                                           local_revision, page_url, previous_revision, repo_for)

        entries = list(RECOMMENDED) + [(m, "selbst konvertiert") for m in sorted(
            set(converted_models()) - {m for m, _ in RECOMMENDED})]
        result = []
        for model, description in entries:
            try:
                local = is_local(model)
            except Exception:  # cache unreadable – treat as "will be downloaded"
                local = False
            size = SIZE_GB.get(model)
            if local:
                status = "auf diesem PC"
            elif size:
                status = f"wird bei Bedarf heruntergeladen (ca. {size:.1f} GB)".replace(".", ",", 1)
            else:
                status = "wird bei Bedarf heruntergeladen"
            cached = self._model_updates[1] if self._model_updates else {}
            entry = {"id": model, "name": DISPLAY_NAMES.get(model, model), "description": description,
                     "previous": bool(local and previous_revision(model)), "update": cached.get(model),
                     "status": status, "local": local,
                     "size_gb": size, "label": f"{model} – {status}", "page": page_url(model),
                     "revision": None, "loaded": None, "source": "Hugging Face",
                     "check": self._model_status.get(model) if local else None}
            if local:
                rev = local_revision(model)
                if rev:
                    entry.update(revision=rev["revision"][:7], loaded=rev["loaded"])
                elif repo_for(model) is None:
                    entry["source"] = "auf diesem PC umgewandelt"
            result.append(entry)
        return result

    def model_updates(self, force: bool = False) -> dict:
        """Newer revisions on Hugging Face for downloaded models (network; cached for 6 hours).

        Also remembers per model whether it is up to date – shown on the model tiles.
        """
        from .transcription.models import RECOMMENDED, check_revision, is_local

        if not force and self._model_updates and time.monotonic() - self._model_updates[0] < 6 * 3600:
            return self._model_updates[1]
        result = {}
        checked = datetime.now().astimezone().isoformat(timespec="minutes")
        for model, _ in RECOMMENDED:
            try:
                info = check_revision(model) if is_local(model) else None
            except Exception as e:  # offline – just no information
                log.info("Model update check for %s failed: %s", model, e)
                self._model_status[model] = {"state": "failed", "changed": None, "checked": checked}
                continue
            if info is None:
                continue
            update = info["update"]
            if update:
                result[model] = {"revision": update["revision"][:7], "changed": update["changed"]}
            self._model_status[model] = {"state": "update" if update else "current",
                                         "changed": info["current_changed"], "checked": checked}
        self._model_updates = (time.monotonic(), result)
        return result

    def check_models_now(self) -> list[dict]:
        """«Jetzt prüfen» in the settings: ask Hugging Face again, then the tiles with the new state."""
        self._model_updates_dismissed = False
        self.model_updates(force=True)
        return self.models()

    def open_model_page(self, model: str) -> None:
        from .transcription.models import HF_PAGE, page_url

        url = page_url(model)
        if not url or not url.startswith(HF_PAGE):
            raise ValueError("Für dieses Modell gibt es keine Seite auf Hugging Face.")
        import webbrowser
        webbrowser.open(url)

    def dismiss_notice(self) -> None:
        self._notice = None

    def _ensure_model(self, model: str) -> None:
        """Before loading: download a missing model, or a newer revision of a downloaded one.

        Both with progress in the job. faster-whisper would fetch a newer revision
        on its own, but silently – this way the user sees it and gets a notice.
        """
        from .transcription.models import SIZE_GB, check_update, download, is_local, local_revision, repo_for

        try:
            if repo_for(model) is None:
                return
            local = is_local(model)
        except Exception:
            return  # can't tell – resolve() will download it when loading
        before = local_revision(model) if local else None
        if local:
            if self._s.model_auto_update != "on":
                return   # updates only on request (update notice / settings)
            try:
                update = check_update(model)
            except Exception as e:  # offline: use what is there
                log.info("Could not check %s for updates: %s", model, e)
                return
            if not update:
                return
        size = SIZE_GB.get(model)
        what = "Modell-Update wird heruntergeladen" if local else "Modell wird heruntergeladen"

        def progress(done: int) -> None:
            gb = done / 1e9
            with self._lock:
                if self._job:
                    total = f" von ca. {size:.1f} GB" if size else " GB"
                    self._job["phase"] = f"{what}: {gb:.1f}{total}".replace(".", ",")
                    self._job["progress"] = min(gb / size, 0.99) if size else 0.0

        log.info("Downloading model %s (%s)", model, "update" if local else "first download")
        download(model, progress)
        after = local_revision(model)
        if before and after and after["revision"] != before["revision"]:
            self._transcriber = None   # load the new revision, not the one in memory
            self._model_updates = None
            self._notice = (f"Das Modell {model} wurde aktualisiert (neuer Stand {after['revision'][:7]}). "
                            "Details auf der Modellseite in den Einstellungen.")
            log.info("Model %s updated %s → %s", model, before["revision"][:7], after["revision"][:7])

    # ------------------------------------------------------------ recognising calls

    def _watch_calls(self, detect: Callable[[], list[str]]) -> None:
        while not self._stopping.wait(CALL_CHECK_S):
            try:
                self._check_call(detect)
            except Exception:
                log.exception("Call detection failed")

    def _check_call(self, detect: Callable[[], list[str]]) -> None:
        """One look: did a call start (suggest recording) or end (forget it; while recording: ask to stop)?"""
        apps = detect() if self._s.call_detection == "on" else []
        call_over = None
        with self._lock:
            recording = self._rec is not None
            if recording:
                info, now = self._rec_info, time.monotonic()
                app = info.get("call_app")
                if app and app in apps:
                    info["call_seen"] = now
                elif app and not info.get("call_over") and now - info.get("call_seen", now) >= CALL_OVER_AFTER_S:
                    info["call_over"] = True
                    call_over = app
            started = bool(apps) and self._call is None
            ended = not apps and self._call is not None
            if started:   # during a recording: no suggestion – it is being recorded
                self._call = {"apps": apps, "dismissed": recording, "planned": None if recording else self._due_planned()}
            elif ended:
                self._call = None
            call = self._call
        in_front = time.monotonic() - self._ui_focused < UI_FOCUS_S
        if call_over:
            log.info("The %s call is over – asking whether to stop the recording", call_over)
            if self.call_notifier is not None and not in_front:
                self.call_notifier.show(f"Der {call_over}-Call ist zu Ende – Aufnahme beenden?",
                                        "Klicken, um Verbalis zu öffnen.")
            return
        if recording:
            return
        if started:
            log.info("Call recognised (%s) – suggesting a recording", ", ".join(apps))
            if self.call_notifier is not None and not in_front:
                planned = call["planned"]
                text = (f"Geplant: {planned['title']}. " if planned else "") + \
                       "Klicken, um Verbalis zu öffnen – aufgenommen wird erst, wenn du die Zustimmung bestätigst."
                self.call_notifier.show(f"{apps[0]}-Call erkannt – aufnehmen?", text)
        elif ended and self.call_notifier is not None:
            self.call_notifier.hide()

    def _due_planned(self) -> dict | None:
        """The planned recording closest to now, if it is within PLANNED_DUE_S."""
        now = datetime.now().astimezone()
        best = None
        base = self._s.recordings
        for folder in (base.iterdir() if base.exists() else []):
            if not folder.is_dir() or not VALID_ID.match(folder.name):
                continue
            meta = pipeline.read_meta(folder)
            start = _parse_time(meta.get("start")) if meta.get("state") == pipeline.PLANNED else None
            if start is not None and abs((start - now).total_seconds()) <= PLANNED_DUE_S:
                distance = abs((start - now).total_seconds())
                if best is None or distance < best[0]:
                    best = (distance, {"id": folder.name, "title": meta.get("title") or pipeline.default_title(start)})
        return best[1] if best else None

    def dismiss_call(self) -> None:
        """«Nicht aufnehmen»: don't ask again during this call."""
        with self._lock:
            if self._call is not None:
                self._call["dismissed"] = True
        if self.call_notifier is not None:
            self.call_notifier.hide()

    # ------------------------------------------------------------ levels before recording

    # ------------------------------------------------------------ diagnostics

    def diagnose_info(self) -> dict:
        """What helps to find a problem: versions, system, paths, devices, models."""
        import platform as platform_module

        from .audio import mac_tap
        from .transcription.models import converted_models, verbalis_home

        free = self._free_mb(force=True)
        info = {
            "Verbalis": __version__ + ("" if updates.is_installed() else " (aus dem Quellcode)"),
            "System": f"{platform_module.system()} {platform_module.release()} ({platform_module.machine()})",
            "Python": platform_module.python_version(),
            **hardware.describe(),
            "Daten": str(verbalis_home()),
            "Aufnahmen": str(self._s.recordings),
            "Freier Speicher": f"{free / 1000:.1f} GB" if free is not None else "unbekannt",
            "Modell": self._s.model,
            "Eigene Modelle": ", ".join(converted_models()) or "keine",
        }
        if sys.platform == "darwin":
            info["macOS"] = ".".join(map(str, mac_tap.macos_version())) or "unbekannt"
            info["Systemton-Hilfsprogramm"] = str(mac_tap.helper_path() or "fehlt")
            bundle = updates.app_bundle()
            info["App-Ort"] = str(bundle) if bundle else "kein App-Paket"
        try:
            found = self._list_devices() or {}
            info["Mikrofone"] = ", ".join(found.get("microphones", [])) or "keine"
            info["Ausgabe / Ton der anderen"] = ", ".join(found.get("speakers", [])) or "keine"
        except Exception as e:
            info["Geräte"] = f"Fehler: {e}"
        return info

    def check_network(self) -> list[dict]:
        """Can Verbalis reach GitHub (updates) and Hugging Face (models)? HTTPS with certificates."""
        import urllib.request

        results = []
        for name, url in (("GitHub (Updates)", updates.LATEST_API),
                          ("Hugging Face (Modelle)", "https://huggingface.co/api/models/openai/whisper-large-v3"),
                          ("Modelle für die Sprechererkennung", "https://github.com/k2-fsa/sherpa-onnx/releases")):
            started = time.monotonic()
            try:
                request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Verbalis"})
                with urllib.request.urlopen(request, timeout=8) as response:
                    ok, detail = True, f"HTTP {response.status}"
            except Exception as e:
                ok, detail = False, str(e) or type(e).__name__
            results.append({"name": name, "ok": ok, "detail": detail, "seconds": round(time.monotonic() - started, 1)})
            log.info("Network check %s: %s (%s)", name, "ok" if ok else "failed", detail)
        self._network = results
        return results

    def start_diagnosis(self, microphone: str = "", speakers: str = "") -> None:
        """The audio test in steps, in the background: each device alone, both together, and closing and
        reopening right away – as when a recording starts after the level meters."""
        with self._lock:
            if self._rec is not None:
                raise RuntimeError("Während einer Aufnahme nicht möglich.")
            if self._diagnosis and self._diagnosis["running"]:
                return
            self._close_monitor()
            self._diagnosis = {"running": True, "steps": [], "error": None}
        threading.Thread(target=self._run_diagnosis, args=(microphone or "", speakers or ""),
                         name="diagnosis", daemon=True).start()

    def _run_diagnosis(self, microphone: str, speakers: str) -> None:
        from .audio.recorder import measure

        def step(title: str, devices: list, seconds: float) -> None:
            with self._lock:
                self._diagnosis["steps"].append({"title": title, "running": True, "results": []})
            results = measure(devices, seconds)
            with self._lock:
                self._diagnosis["steps"][-1].update(running=False, results=results)
            log.info("Diagnosis «%s»: %s", title, results)

        try:
            chosen = self._select_devices(microphone or None, speakers or None)
            mic = ("Mikrofon", chosen.microphone)
            if chosen.loopback is None:                       # «nur Mikrofon»
                step("Nur Mikrofon", [mic], 3)
                step("Wie beim Aufnahmestart: öffnen …", [mic], 2)
                step("… schliessen und sofort neu öffnen", [mic], 3)
                return
            others = ("Ton der anderen", chosen.loopback)
            step("Nur Mikrofon", [mic], 3)
            step("Nur Ton der anderen", [others], 3)
            step("Beide zusammen", [mic, others], 3)
            step("Wie beim Aufnahmestart: beide öffnen …", [mic, others], 2)
            step("… schliessen und sofort neu öffnen", [mic, others], 3)
        except Exception as e:
            log.exception("Diagnosis failed")
            with self._lock:
                self._diagnosis["error"] = str(e) or type(e).__name__
        finally:
            with self._lock:
                self._diagnosis["running"] = False

    def diagnosis(self) -> dict | None:
        with self._lock:
            return json.loads(json.dumps(self._diagnosis)) if self._diagnosis else None

    def diagnose_report(self) -> str:
        """Everything as text to copy into an e-mail. Contains device names, no conversation content."""
        lines = [f"Verbalis-Diagnose {datetime.now().astimezone():%Y-%m-%d %H:%M}", ""]
        lines += [f"{k}: {v}" for k, v in self.diagnose_info().items()]
        if self._network:
            lines += ["", "Netzwerk:"] + [f"  {r['name']}: {'OK' if r['ok'] else 'FEHLER'} – {r['detail']} "
                                          f"({r['seconds']} s)" for r in self._network]
        diagnosis = self.diagnosis()
        if diagnosis:
            lines += ["", "Audiotest:"]
            for s in diagnosis["steps"]:
                lines.append(f"  {s['title']}")
                for r in s["results"]:
                    lines.append("    " + _result_text(r))
            if diagnosis.get("error"):
                lines.append(f"  Fehler: {diagnosis['error']}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------ «Problem melden»

    def report_info(self) -> dict:
        return {"can_send": feedback.config() is not None, "contact": feedback.CONTACT}

    def report_problem(self, message: str, contact: str = "", with_log: bool = True,
                       with_diagnosis: bool = True) -> dict:
        """Send a problem report (see feedback.py). Names and device names are removed."""
        target = feedback.config()
        if target is None:
            raise RuntimeError("Diese Version kann Meldungen nicht direkt senden – bitte «Per E-Mail» wählen.")
        redact = self.device_names_for_redaction() + [self._s.name, self._s.others]
        report = feedback.build(message, contact,
                                diagnosis=self.diagnose_report() if with_diagnosis else "",
                                log_zip=feedback.log_zip(self.settings(), redact) if with_log else None,
                                redact=redact)
        feedback.send(report, target)
        log.info("Problem report sent (log: %s, diagnosis: %s)", "log_zip" in report, bool(report["diagnosis"]))
        return {"sent": True}

    def report_by_mail(self, message: str) -> None:
        import webbrowser

        webbrowser.open(feedback.mail_link(message))

    # ------------------------------------------------------------ levels before recording

    def preview_levels(self, microphone: str = "", speakers: str = "") -> dict | None:
        """Levels of the chosen devices without recording, while the user chooses them.

        Opens the devices on the first call and keeps them open while the UI keeps
        asking; a watchdog closes them PREVIEW_IDLE_S after the last call (Windows
        shows the microphone icon while they are open). None while recording.
        """
        with self._lock:
            if self._rec is not None or (self._diagnosis and self._diagnosis["running"]):
                return None
            key = (microphone or "", speakers or "")
            if self._monitor is not None and self._monitor_key != key:
                self._close_monitor()
            if self._monitor is None:
                failed = self._monitor_failed
                if failed and failed[0] == key and time.monotonic() - failed[1] < 10:
                    return {"me": -90.0, "others": -90.0}
                try:
                    devices = self._select_devices(microphone or None, speakers or None)
                    monitor = self._monitor_factory(devices.microphone, devices.loopback)
                    monitor.start()
                except Exception as e:   # the recording itself will report the problem readably
                    log.warning("Level meters could not open the devices: %s", e)
                    self._monitor_failed = (key, time.monotonic())
                    return {"me": -90.0, "others": -90.0}
                self._monitor, self._monitor_key, self._monitor_failed = monitor, key, None
                threading.Thread(target=self._watch_monitor, args=(monitor,), name="level-monitor",
                                 daemon=True).start()
            self._monitor_asked = time.monotonic()
            levels = self._monitor.levels()
        return {track: _db(levels.get(track, 0.0)) for track in ("me", "others")}

    def stop_preview(self) -> None:
        with self._lock:
            self._close_monitor()

    def _close_monitor(self) -> None:
        """Call with the lock held."""
        monitor, self._monitor, self._monitor_key = self._monitor, None, None
        if monitor is not None:
            try:
                monitor.stop()
            except Exception:
                log.exception("Closing the level meters failed")

    def _watch_monitor(self, monitor) -> None:
        while not self._stopping.wait(0.5):
            with self._lock:
                if self._monitor is not monitor:
                    return
                if time.monotonic() - self._monitor_asked > PREVIEW_IDLE_S:
                    self._close_monitor()
                    return
        with self._lock:
            if self._monitor is monitor:
                self._close_monitor()

    # ------------------------------------------------------------ recording

    def start_recording(self, microphone: str = "", speakers: str = "", consent: bool = False,
                        planned_id: str = "") -> str:
        """planned_id: record into this planned recording (its details stay)."""
        with self._lock:
            if self._rec is not None:
                raise RuntimeError("Es läuft bereits eine Aufnahme.")
            if not consent:
                raise RuntimeError("Bitte zuerst bestätigen, dass alle Teilnehmenden der Aufnahme zugestimmt haben.")

            free = self._free_mb(force=True)
            if free is not None and free < MIN_FREE_TO_START_MB:
                raise RuntimeError(f"Zu wenig Speicherplatz für eine Aufnahme (noch {free:.0f} MB frei). "
                                   "Bitte Platz schaffen, z.B. alte Audiodateien löschen.")
            self._close_monitor()   # free the devices for the recording
            if self._call is not None:
                self._call["dismissed"] = True   # being recorded: no more suggestion
                if self.call_notifier is not None:
                    self.call_notifier.hide()
            devices = self._select_devices(microphone or None, speakers or None)
            start = datetime.now().astimezone()
            known = {}
            if planned_id:
                folder = self._path(planned_id)
                meta = pipeline.read_meta(folder)
                if meta.get("state") != pipeline.PLANNED or pipeline.has_audio(folder):
                    raise RuntimeError("Diese geplante Aufnahme gibt es nicht mehr oder sie wurde schon aufgenommen.")
                known = {**pipeline.details(meta), "planned_start": meta.get("start")}
            else:
                folder = self._new_folder(start)
            consent = datetime.now().astimezone().isoformat(timespec="seconds")
            only_microphone = devices.loopback is None          # «Keiner – nur Mikrofon»
            names = {"me": devices.microphone.name, "others": "" if only_microphone else devices.loopback.name}
            if only_microphone:
                known["only_microphone"] = True
            rec = self._recorder_factory(devices.microphone, devices.loopback, folder)
            # consent and start are on disk before the first sample – they survive a crash
            pipeline.start_meta(folder, start, getattr(rec, "samplerate", 48_000), consent, names, known)
            rec.start()

            self._rec = rec
            self._recording_error = None
            self._others_last_sound = time.monotonic()
            self._rec_info = {"id": folder.name, "folder": folder, "start": start, "consent": consent,
                              "devices": names, "limit_s": self._s.max_recording_s,
                              # a recognised call: ask to stop the recording when it is over
                              "call_app": self._call["apps"][0] if self._call else None,
                              "call_seen": time.monotonic()}
            # Remember the chosen devices for next time
            if (microphone, speakers) != (self._s.microphone, self._s.speakers):
                self.save_settings({"microphone": microphone, "speakers": speakers})
            return folder.name

    def pause_recording(self) -> None:
        with self._lock:
            if self._rec is None:
                raise RuntimeError("Es läuft keine Aufnahme.")
            self._rec.pause()

    def resume_recording(self) -> None:
        with self._lock:
            if self._rec is None:
                raise RuntimeError("Es läuft keine Aufnahme.")
            self._rec.resume()
            self._others_last_sound = time.monotonic()  # silence during the pause doesn't count

    def stop_recording(self, reason: str | None = None, note: str | None = None) -> str | None:
        """reason: ended early (incomplete). note: ended on purpose by Verbalis (complete), e.g. the maximum time."""
        with self._lock:
            rec, info = self._rec, self._rec_info
            if rec is None:
                return None
            self._rec, self._rec_info = None, {}
        state = self._finish(rec, info, reason)
        if note:
            pipeline.update_meta(info["folder"], ended_by=note)
            self._notice = note
            log.info("Recording %s: %s", info["id"], note)
        if self.call_notifier is not None and (info.get("call_over") or info.get("end_warned")):
            self.call_notifier.hide()
        if self._s.auto_transcribe == "on" and state in (pipeline.COMPLETE, pipeline.INCOMPLETE) \
                and rec.active_seconds() >= 1 and pipeline.has_audio(info["folder"]):
            self.transcribe(info["id"])   # otherwise the user enters the number of people first and starts it
        return info["id"]

    def extend_recording(self, seconds: float = EXTEND_S) -> None:
        """«+30 Min.»: push the maximum recording time back."""
        with self._lock:
            info = self._rec_info
            if self._rec is None or not info.get("limit_s"):
                return
            info["limit_s"] = max(info["limit_s"], self._rec.active_seconds()) + seconds
            info["end_warned"] = False
        if self.call_notifier is not None:
            self.call_notifier.hide()

    def keep_recording(self) -> None:
        """«Weiter aufnehmen» after the call was over: don't ask again during this recording."""
        with self._lock:
            self._rec_info["call_over_dismissed"] = True
        if self.call_notifier is not None:
            self.call_notifier.hide()

    def _finish(self, rec, info: dict, reason: str | None = None) -> str:
        """Stop the recorder and record honestly in meta.json how the recording ended."""
        ended = rec.stop()
        errors = [str(e) or type(e).__name__ for e in rec.errors]   # readable, not repr()
        if not ended:
            for track in getattr(rec, "tracks", []):
                if track.is_alive():
                    log.warning("Track %s (%s) did not end: %.1f s written, device %s", track.status.name,
                                info["devices"].get(track.status.name, "?"),
                                track.status.written_frames / rec.samplerate, getattr(track.device, "name", "?"))
            state = pipeline.STOP_TIMEOUT
            problem = ("Eine Spur liess sich nicht rechtzeitig beenden. Das Audio bis dahin ist gesichert, "
                       "wurde aber nicht automatisch transkribiert – bitte prüfen.")
        elif errors:
            state, problem = pipeline.INCOMPLETE, "Gerätefehler: " + "; ".join(errors)
        elif reason:
            state, problem = pipeline.INCOMPLETE, reason
        else:
            state, problem = pipeline.COMPLETE, None
        if problem:
            self._recording_error = ("Die Aufnahme wurde vorzeitig beendet. " if state != pipeline.STOP_TIMEOUT
                                     else "") + problem
            log.warning("Recording %s ended as %s: %s", info["id"], state, problem)
        try:
            pipeline.write_meta(info["folder"], info["start"], rec.active_seconds(), rec.samplerate,
                                info["consent"], info["devices"], rec.status(), state, problem)
        except OSError as e:  # e.g. disk full – the audio files are still there
            log.exception("Writing meta.json for %s failed", info["id"])
            self._recording_error = f"Die Angaben zur Aufnahme konnten nicht gespeichert werden ({e})."
        return state

    def _check_time_limit(self, recording: dict) -> dict | None:
        """The maximum recording time: a notice 5 minutes before, then the recording ends (complete)."""
        with self._lock:
            info, rec = self._rec_info, self._rec
            limit = info.get("limit_s")
            if rec is None or not limit:
                return recording
            left = limit - rec.active_seconds()
            warn = left <= END_WARNING_S and not info.get("end_warned")
            if warn:
                info["end_warned"] = True
        if left <= 0:
            hours, minutes = divmod(int(round(limit / 60)), 60)
            length = f"{hours} Std. {minutes} Min." if hours and minutes else f"{hours} Std." if hours else f"{minutes} Min."
            self.stop_recording(note=f"Die Aufnahme wurde nach {length} automatisch beendet (Höchstdauer, "
                                     "einstellbar unter Einstellungen → Allgemein).")
            return None
        if left <= END_WARNING_S:
            recording["ends_in_s"] = round(left)
        if warn and self.call_notifier is not None and time.monotonic() - self._ui_focused >= UI_FOCUS_S:
            self.call_notifier.show(f"Die Aufnahme endet in {max(round(left / 60), 1)} Min.",
                                    "Höchstdauer erreicht. Klicken, um Verbalis zu öffnen und zu verlängern.")
        return recording

    def _check_no_data(self, rec, info: dict) -> None:
        """Call with the lock held. A track that has delivered no audio at all is reported once –
        silence still arrives as data, so this means the device or the system blocks it."""
        if rec.paused or rec.active_seconds() < NO_DATA_AFTER_S or info.get("no_data_reported"):
            return
        silent = [s.name for s in rec.status() if s.written_frames == 0]
        if not silent:
            return
        info["no_data_reported"] = True
        names = {"me": "Mikrofon", "others": "Ton der anderen"}
        devices = ", ".join(f"{names.get(t, t)} «{info['devices'].get(t, '?')}»" for t in silent)
        log.warning("No audio data after %.0f s from: %s", rec.active_seconds(), devices)
        hint = (" Unter macOS: eine offene Frage nach der Berechtigung beantworten bzw. in Systemeinstellungen → "
                "Datenschutz & Sicherheit → Mikrofon und «Bildschirm- & Systemaudioaufnahme» prüfen.") \
            if sys.platform == "darwin" else " Sonst ein anderes Gerät wählen."
        self._recording_error = (f"Von {devices} kommen bisher keine Audiodaten an. Die Aufnahme läuft weiter "
                                 "und holt den Ton nach, sobald er kommt." + hint)

    def _new_folder(self, start: datetime) -> Path:
        """A new, empty recording folder – never an existing one (two starts in the same second)."""
        base = self._s.recordings / start.strftime("%Y-%m-%d_%H%M%S")
        base.parent.mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):
            folder = base if n == 1 else base.with_name(f"{base.name}_{n}")
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                continue
        raise RuntimeError("Kein freier Name für den Aufnahmeordner gefunden.")

    def _free_mb(self, force: bool = False) -> float | None:
        """Free space where recordings are stored (checked at most every few seconds)."""
        now = time.monotonic()
        if force or now - self._disk["checked"] > DISK_CHECK_EVERY_S:
            try:
                folder = self._s.recordings
                while not folder.exists() and folder != folder.parent:
                    folder = folder.parent
                self._disk["free_mb"] = shutil.disk_usage(folder).free / 1e6
            except OSError:
                self._disk["free_mb"] = None
            self._disk["checked"] = now
        return self._disk["free_mb"]

    def _recover_interrupted(self) -> None:
        """At start: recordings still marked as running were cut off by a crash or power loss.

        Repair the WAV headers so the audio up to that point is readable and mark them,
        so they show up as interrupted instead of looking finished.
        """
        base = self._s.recordings
        if not base.exists():
            return
        for folder in base.iterdir():
            if not folder.is_dir() or pipeline.read_meta(folder).get("state") != pipeline.RECORDING:
                continue
            for track in pipeline.TRACKS:
                wav = folder / f"{track}.wav"
                if wav.exists():
                    try:
                        pipeline.repair_wav(wav)
                    except OSError:
                        log.exception("Repairing %s failed", wav)
            pipeline.update_meta(folder, state=pipeline.INTERRUPTED,
                                 problem="Verbalis wurde während der Aufnahme beendet (Absturz oder Stromausfall). "
                                         "Das Audio bis dahin ist gesichert.")
            log.warning("Recording %s was interrupted – marked and repaired", folder.name)

    def _resume_transcriptions(self) -> None:
        """At start: transcriptions that were cut off (crash, app closed) continue where they stopped."""
        base = self._s.recordings
        if not base.exists():
            return
        for folder in sorted(base.iterdir()):
            if (folder.is_dir() and VALID_ID.match(folder.name) and (folder / pipeline.PARTIAL).exists()
                    and pipeline.has_audio(folder)):
                log.info("Transcription of %s was cut off – continuing", folder.name)
                self.transcribe(folder.name)

    # ------------------------------------------------------------ transcription

    def partial_transcript(self, recording_id: str) -> dict | None:
        """What is already finished of a running transcription (read-only in the app)."""
        return pipeline.partial_transcript(self._path(recording_id))

    def transcribe(self, recording_id: str, people: dict | None = None) -> None:
        """Queue a transcription. people: track → number of people on it (None/empty = find out);
        remembered in meta.json, so a later «Neu transkribieren» uses it too."""
        folder = self._path(recording_id)
        if not pipeline.has_audio(folder):
            raise RuntimeError("Das Audio dieser Aufnahme wurde gelöscht – neu transkribieren ist nicht mehr möglich.")
        if people is not None:
            clean = {}
            for track in pipeline.TRACKS:
                value = people.get(track)
                if value in (None, ""):
                    clean[track] = None
                    continue
                number = int(value)
                if not 1 <= number <= MAX_PEOPLE:
                    raise ValueError(f"Bitte bei der Anzahl Personen eine Zahl zwischen 1 und {MAX_PEOPLE} eingeben.")
                clean[track] = number
            pipeline.update_meta(folder, people=clean)
        with self._lock:
            if recording_id in self._queued or (self._job and self._job["id"] == recording_id):
                return
            self._errors.pop(recording_id, None)
            self._queued.append(recording_id)
        self._queue.put(recording_id)

    def _get_model(self, model: str):
        from .transcription.models import active_revision

        try:
            revision = active_revision(model)
        except Exception:
            revision = None
        if (self._transcriber is None or self._transcriber_model != model
                or self._transcriber_revision != revision):
            self._transcriber = None  # free the old one first
            self._transcriber = self._transcriber_factory(model)
            self._transcriber_model = model
            self._transcriber_revision = revision
        return self._transcriber

    # ------------------------------------------------------------ model updates on request

    def update_model(self, model: str) -> None:
        """Download the newer revision of a model in the background and make it the active one."""
        with self._lock:
            if self._model_download is not None:
                raise RuntimeError("Es wird bereits ein Modell aktualisiert.")
            self._model_download = {"model": model, "progress": 0.0}
        threading.Thread(target=self._update_model, args=(model,), name="model-update", daemon=True).start()

    def _update_model(self, model: str) -> None:
        from .transcription.models import SIZE_GB, download, local_revision

        size = SIZE_GB.get(model)

        def progress(done: int) -> None:
            with self._lock:
                if self._model_download is not None and size:
                    self._model_download["progress"] = min(done / 1e9 / size, 0.99)

        before = local_revision(model)
        try:
            download(model, progress)
            after = local_revision(model)
            self._model_updates = None
            if after and (not before or after["revision"] != before["revision"]):
                self._notice = (f"Das Modell {model} wurde aktualisiert (Stand {after['revision'][:7]}). "
                                "Falls es schlechter transkribiert: in den Einstellungen zurück auf den vorherigen Stand.")
                log.info("Model %s updated on request → %s", model, after["revision"][:7])
        except Exception as e:
            log.exception("Model update of %s failed", model)
            self._notice = f"Das Modell-Update ist fehlgeschlagen; der bisherige Stand bleibt aktiv. ({e})"
        finally:
            with self._lock:
                self._model_download = None

    def rollback_model(self, model: str) -> str:
        from .transcription.models import rollback

        revision = rollback(model)
        self._model_updates = None
        self._notice = f"Das Modell {model} verwendet wieder den vorherigen Stand ({revision[:7]})."
        log.info("Model %s rolled back to %s", model, revision[:7])
        return revision

    def dismiss_model_updates(self) -> None:
        self._model_updates_dismissed = True

    # ------------------------------------------------------------ pause

    def _pause_reason(self) -> str | None:
        if self._manual_pause:
            return "manual"
        if self._rec is not None:
            return "recording"
        return None

    def pause(self) -> None:
        with self._lock:
            self._manual_pause = True

    def resume(self) -> None:
        with self._lock:
            self._manual_pause = False

    def _wait_while_paused(self) -> None:
        """Call from the worker thread: blocks while paused."""
        since = None
        while True:
            if self._stopping.is_set():
                raise ShuttingDown()
            with self._lock:
                if self._pause_reason() is None:
                    if since is not None and self._job:
                        self._job["paused_s"] += time.monotonic() - since
                        self._job["paused_since"] = None
                    return
                if since is None:
                    since = time.monotonic()
                    if self._job:
                        self._job["paused_since"] = since
            time.sleep(0.1)

    # ------------------------------------------------------------ remaining time

    @staticmethod
    def _stats_path() -> Path:
        return verbalis_home() / "stats.json"

    def _factor(self, key: str) -> float | None:
        try:
            return json.loads(self._stats_path().read_text(encoding="utf-8"))["realtime_factor"].get(key)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _remember_factor(self, key: str, factor: float) -> None:
        path = self._stats_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        factors = data.setdefault("realtime_factor", {})
        old = factors.get(key)
        factors[key] = round(factor if old is None else (old + factor) / 2, 3)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _remaining(self, job: dict) -> float | None:
        if job["start"] is None:
            return None
        now = job["paused_since"] or time.monotonic()
        active = max(now - job["start"] - job["paused_s"], 0.0)
        progress = job["progress"]
        if progress >= 0.1 and active >= 10:
            return active * (1 - progress) / progress
        if job["factor"] and job["duration_s"]:
            rest = job["factor"] * job["duration_s"] - active
            return rest if rest > 0 else None
        return None

    # ------------------------------------------------------------ worker

    def _work(self) -> None:
        while True:
            try:
                recording_id = self._queue.get(timeout=CLEANUP_EVERY_S)
            except queue.Empty:
                recording_id = CLEANUP
            if recording_id is None:
                return
            if recording_id == CLEANUP:
                self._cleanup_safely()
                continue
            if isinstance(recording_id, tuple):   # ("speakers", id, track, count)
                try:
                    self._run_reassign(*recording_id[1:])
                except ShuttingDown:
                    return
                continue
            try:
                self._wait_while_paused()
            except ShuttingDown:
                return
            with self._lock:
                if recording_id in self._queued:
                    self._queued.remove(recording_id)
                s = self._s
                key = f"{s.model}|beam{s.beam_size}"
                self._job = {
                    "id": recording_id, "phase": f"Modell {s.model} wird geladen", "progress": 0.0,
                    "start": None, "paused_s": 0.0, "paused_since": None,
                    "duration_s": pipeline.read_meta(self._path(recording_id)).get("duration_s"),
                    "factor": self._factor(key),
                }
            try:
                self._compress_safely(self._path(recording_id))
                self._ensure_model(s.model)
                with self._lock:
                    self._job["phase"] = f"Modell {s.model} wird geladen"
                    self._job["progress"] = 0.0
                tr = self._get_model(s.model)
                tr.beam_size = s.beam_size
                corrections = CorrectionList.load()
                tr.keywords = self._keywords(s.keywords, corrections) or None
                names = {"me": s.name, "others": s.others}
                with self._lock:
                    self._job["start"] = time.monotonic()
                    self._job["phase"] = "Transkription beginnt"

                def progress(name: str, fraction: float):
                    with self._lock:
                        if self._job:
                            self._job["phase"] = f"Spur «{name}» wird transkribiert"
                            self._job["progress"] = fraction
                    self._wait_while_paused()

                def paused_time() -> float:
                    with self._lock:
                        return self._job["paused_s"] if self._job else 0.0

                def phase(text: str) -> None:
                    with self._lock:
                        if self._job:
                            self._job["phase"] = text
                    self._wait_while_paused()

                diarize = {"others": s.diarize_others == "on", "me": s.diarize_me == "on"}
                people = pipeline.read_meta(self._path(recording_id)).get("people") or {}
                for track, number in people.items():   # a given number decides: 1 = nobody to tell apart
                    if number:
                        diarize[track] = number > 1
                _, compute, duration = pipeline.create_transcript(
                    self._path(recording_id), tr, s.model, names, progress, paused_time, corrections,
                    diarize=diarize, phase=phase, people={t: n for t, n in people.items() if n and n > 1})
                if duration > 0 and compute > 0:
                    self._remember_factor(key, compute / duration)
            except ShuttingDown:
                log.info("Transcription of %s stopped because Verbalis is closing", recording_id)
                with self._lock:
                    self._job = None
                return
            except Exception as ex:  # show the error per recording, the worker keeps running
                log.exception("Transcription of %s failed", recording_id)
                with self._lock:
                    self._errors[recording_id] = str(ex) or repr(ex)
            finally:
                with self._lock:
                    self._job = None
            self._cleanup_safely()

    # ------------------------------------------------------------ audio retention

    def _compress_safely(self, folder: Path) -> None:
        if not any((folder / f"{t}.wav").exists() for t in pipeline.TRACKS):
            return
        with self._lock:
            if self._job:
                self._job["phase"] = "Audio wird komprimiert"
        try:
            pipeline.compress_audio(folder)
        except Exception:  # not critical – the WAV gets transcribed instead
            log.exception("Compressing %s failed", folder.name)

    def _protected(self) -> set[str]:
        with self._lock:
            return {i for i in (self._rec_info.get("id"), self._job and self._job["id"], *self._queued) if i}

    def _cleanup_safely(self) -> None:
        try:
            self.cleanup()
        except Exception:
            log.exception("Cleanup failed")

    def cleanup(self) -> list[str]:
        """Compress leftover WAVs, delete audio past the retention period or over the size limit.

        Never touched: the running recording, recordings queued or in progress,
        recordings without a transcript – their audio is all there is of the
        conversation – and recordings whose audio the user chose to keep. Kept
        audio doesn't count towards the size limit either; otherwise it would
        push out the audio of all other recordings.
        """
        s, base = self._s, self._s.recordings
        if not base.exists():
            return []
        protected = self._protected()
        candidates: list[tuple[datetime, Path]] = []
        for folder in base.iterdir():
            if not folder.is_dir() or not VALID_ID.match(folder.name) or folder.name in protected:
                continue
            if self._pause_reason() is None:
                self._compress_safely(folder)  # e.g. leftovers from the CLI or after a crash
            if (folder / "transcript.json").exists() and pipeline.audio_bytes(folder)                     and not pipeline.read_meta(folder).get("keep_audio"):
                start = pipeline.recording_start(folder) or datetime.fromtimestamp(folder.stat().st_mtime).astimezone()
                candidates.append((start, folder))
        candidates.sort(key=lambda c: c[0])  # oldest first

        deleted: list[str] = []
        if s.days is not None:
            limit = datetime.now().astimezone() - timedelta(days=s.days)
            reason = "nach dem Transkribieren" if s.days == 0 else f"älter als {s.days} Tage"
            for start, folder in list(candidates):
                if start <= limit:
                    pipeline.delete_audio(folder, reason)
                    deleted.append(folder.name)
                    candidates.remove((start, folder))
        if s.max_mb is not None:
            total = self._audio_total(include_kept=False)
            for start, folder in candidates:
                if total <= s.max_mb * MB:
                    break
                total -= pipeline.delete_audio(folder, f"Speichergrenze {s.max_mb} MB")
                deleted.append(folder.name)
        if deleted:
            log.info("Audio deleted: %s", ", ".join(deleted))
        return deleted

    def _audio_total(self, include_kept: bool = True) -> int:
        base = self._s.recordings
        if not base.exists():
            return 0
        return sum(pipeline.audio_bytes(f) for f in base.iterdir()
                   if f.is_dir() and (include_kept or not pipeline.read_meta(f).get("keep_audio")))

    def audio_usage(self) -> dict:
        return {"audio_mb": round(self._audio_total() / MB, 1)}

    def delete_audio(self, recording_id: str) -> None:
        folder = self._path(recording_id)
        if recording_id in self._protected():
            raise RuntimeError("Diese Aufnahme wird gerade aufgenommen oder transkribiert.")
        pipeline.delete_audio(folder, "von Hand")

    def keep_audio(self, recording_id: str, keep: bool = True) -> None:
        """Protect the audio of one recording from automatic deletion (retention days and size limit)."""
        folder = self._path(recording_id)
        if not pipeline.is_recording_folder(folder):
            raise ValueError("Diese Aufnahme gibt es nicht (mehr).")
        pipeline.update_meta(folder, keep_audio=bool(keep))
        log.info("Audio of %s %s", recording_id, "kept" if keep else "no longer kept")
        if not keep:
            self._queue.put(CLEANUP)

    def _deletion_date(self, folder: Path) -> str | None:
        """When the audio will probably be deleted (only with a retention period in days)."""
        days = self._s.days
        if days is None or not (folder / "transcript.json").exists() or pipeline.read_meta(folder).get("keep_audio"):
            return None
        if days == 0:
            return "now"
        start = pipeline.recording_start(folder)
        return (start + timedelta(days=days)).isoformat(timespec="minutes") if start else None

    # ------------------------------------------------------------ corrections

    @staticmethod
    def _keywords(own: str, corrections: CorrectionList) -> str:
        """Own keywords plus all correction targets, without duplicates."""
        words: list[str] = []
        for w in [*own.split(","), *corrections.targets()]:
            w = w.strip()
            if w and w.lower() not in (x.lower() for x in words):
                words.append(w)
        return ", ".join(words)

    def _write_transcript(self, folder: Path, data: dict) -> None:
        data.pop("markdown", None)
        (folder / "transcript.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        paragraphs = [segment_from_dict(s) for s in data["segments"]]
        (folder / "transcript.md").write_text(
            to_markdown(paragraphs, data.get("title") or f"Transkript {folder.name}", data.get("header", {})),
            encoding="utf-8")

    def edit_transcript(self, recording_id: str, index: int, text: str) -> dict:
        """Change one paragraph. Returns suggestions for the correction list."""
        folder = self._path(recording_id)
        data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
        segments = data["segments"]
        if not 0 <= index < len(segments):
            raise ValueError("Diesen Absatz gibt es nicht (mehr).")
        text = " ".join(text.split())
        if not text:
            raise ValueError("Ein Absatz darf nicht leer sein.")
        old = segments[index]["text"]
        if text == old:
            return {"suggestions": []}

        original = folder / "transcript_original.json"
        if not original.exists():  # keep the unedited version once
            original.write_text((folder / "transcript.json").read_text(encoding="utf-8"), encoding="utf-8")
        segments[index]["text"] = text
        data["edited"] = True
        self._write_transcript(folder, data)

        corrections = CorrectionList.load()
        proposals = [corrections.classify(v, t) for v, t in suggestions(old, text)]
        return {"suggestions": [p for p in proposals if p["kind"] != "known"]}

    # ------------------------------------------------------------ speakers

    def _transcript_data(self, recording_id: str) -> tuple[Path, dict]:
        folder = self._path(recording_id)
        path = folder / "transcript.json"
        if not path.exists():
            raise ValueError("Für diese Aufnahme gibt es noch kein Transkript.")
        return folder, json.loads(path.read_text(encoding="utf-8"))

    def speakers(self, recording_id: str) -> list[dict]:
        """Speakers told apart in this transcript, with how long each talks."""
        _, data = self._transcript_data(recording_id)
        talk: dict[str, float] = {}
        for seg in data["segments"]:
            if seg.get("speaker_id"):
                talk[seg["speaker_id"]] = talk.get(seg["speaker_id"], 0.0) + seg["end"] - seg["start"]
        return [{"id": sid, "name": info["name"], "track": info.get("track"), "seconds": round(talk.get(sid, 0.0))}
                for sid, info in data.get("speakers", {}).items() if sid in talk]

    def rename_speakers(self, recording_id: str, names: dict[str, str]) -> list[dict]:
        """Give speakers names, e.g. {"others-1": "Hans Muster"}."""
        folder, data = self._transcript_data(recording_id)
        speakers = data.get("speakers", {})
        for sid, name in names.items():
            name = " ".join((name or "").split())
            if sid not in speakers:
                raise ValueError("Diesen Sprecher gibt es in diesem Transkript nicht.")
            if not name:
                raise ValueError("Ein Name darf nicht leer sein.")
            speakers[sid]["name"] = name
        for seg in data["segments"]:
            if seg.get("speaker_id") in names:
                seg["speaker"] = speakers[seg["speaker_id"]]["name"]
        self._write_transcript(folder, data)
        return self.speakers(recording_id)

    def merge_speakers(self, recording_id: str, source: str, target: str) -> list[dict]:
        """One person was recognised as two: give all of «source» to «target»."""
        folder, data = self._transcript_data(recording_id)
        speakers = data.get("speakers", {})
        if source not in speakers or target not in speakers or source == target:
            raise ValueError("Diese Sprecher lassen sich nicht zusammenlegen.")
        base = (data.get("tracks") or {}).get(speakers[target].get("track"), "")
        if is_default_name(speakers[target]["name"], base) and not is_default_name(speakers[source]["name"], base):
            speakers[target]["name"] = speakers[source]["name"]   # never lose a name the user gave
        for seg in data["segments"]:
            if seg.get("speaker_id") in (source, target):
                seg["speaker_id"], seg["speaker"] = target, speakers[target]["name"]
        del speakers[source]
        data["segments"] = _join_neighbours(data["segments"])
        self._write_transcript(folder, data)
        return self.speakers(recording_id)

    def reassign_speakers(self, recording_id: str, track: str, count: int) -> None:
        """Diarize one track again with a known number of people – without transcribing again.

        Runs in the background like a transcription (with progress, waits while recording).
        Paragraphs keep their text (also corrections); names given before go to the new
        speaker whose voice overlaps most with them.
        """
        count = int(count)
        if not 1 <= count <= MAX_PEOPLE:
            raise ValueError(f"Bitte eine Anzahl zwischen 1 und {MAX_PEOPLE} angeben.")
        folder, data = self._transcript_data(recording_id)
        if not (data.get("tracks") or {}).get(track):
            raise ValueError("Diese Spur gibt es in diesem Transkript nicht.")
        if pipeline.audio_file(folder, track) is None:
            raise RuntimeError("Das Audio dieser Spur wurde gelöscht – neu zuordnen ist nicht mehr möglich.")
        with self._lock:
            if recording_id in self._queued or (self._job and self._job["id"] == recording_id):
                raise RuntimeError("Diese Aufnahme wird gerade bearbeitet – bitte warten, bis das fertig ist.")
            self._queued.append(recording_id)
        self._queue.put(("speakers", recording_id, track, count))

    def _run_reassign(self, recording_id: str, track: str, count: int) -> None:
        """Worker thread: the background part of reassign_speakers."""
        self._wait_while_paused()
        with self._lock:
            if recording_id in self._queued:
                self._queued.remove(recording_id)
            self._job = {"id": recording_id, "kind": "speakers", "phase": "Sprecher werden neu zugeordnet",
                         "progress": 0.0, "start": time.monotonic(), "paused_s": 0.0, "paused_since": None,
                         "duration_s": None, "factor": None}

        def progress(fraction: float) -> None:
            with self._lock:
                if self._job:
                    self._job["progress"] = min(fraction, 0.99)
                    self._job["phase"] = f"Sprecher werden neu zugeordnet: {fraction:.0%}"
            self._wait_while_paused()

        try:
            self._reassign(recording_id, track, count, progress)
        except ShuttingDown:
            raise
        except Exception as e:
            log.exception("Re-assigning speakers of %s failed", recording_id)
            self._notice = f"Neu zuordnen hat nicht geklappt; die bisherige Zuordnung bleibt. ({e})"
        finally:
            with self._lock:
                self._job = None

    def _reassign(self, recording_id: str, track: str, count: int, progress=None) -> None:
        from . import diarization

        folder = self._path(recording_id)
        path = pipeline.audio_file(folder, track)
        if path is None:
            raise RuntimeError("Das Audio dieser Spur wurde gelöscht.")
        diarization.ensure_models()
        turns = diarization.turns_for_file(path, progress=progress, num_speakers=count)
        folder, data = self._transcript_data(recording_id)   # read now: the newest state of the transcript
        base = data["tracks"][track]
        old = [seg for seg in data["segments"] if seg.get("track") == track]
        new = diarization.assign([segment_from_dict(seg) for seg in old], turns, track, base)
        names = diarization.reassign_names(old, new, base)
        speakers = {sid: info for sid, info in data.get("speakers", {}).items() if info.get("track") != track}
        for seg, assigned in zip(old, new):
            seg["speaker_id"] = assigned.speaker_id
            seg["speaker"] = names.get(assigned.speaker_id, assigned.speaker)
            speakers.setdefault(assigned.speaker_id, {"name": seg["speaker"], "track": track})
        data["speakers"] = speakers
        data["segments"] = _join_neighbours(data["segments"])
        self._write_transcript(folder, data)
        log.info("Speakers of %s/%s re-assigned to %d people", recording_id, track, count)

    def set_paragraph_speaker(self, recording_id: str, index: int, speaker_id: str) -> None:
        """A paragraph was assigned to the wrong person."""
        folder, data = self._transcript_data(recording_id)
        segments, speakers = data["segments"], data.get("speakers", {})
        if not 0 <= index < len(segments):
            raise ValueError("Diesen Absatz gibt es nicht (mehr).")
        if speaker_id not in speakers or speakers[speaker_id].get("track") != segments[index].get("track"):
            raise ValueError("Dieser Sprecher gehört nicht zu dieser Spur.")
        segments[index]["speaker_id"], segments[index]["speaker"] = speaker_id, speakers[speaker_id]["name"]
        self._write_transcript(folder, data)

    def speaker_sample(self, recording_id: str, speaker_id: str, seconds: float = 8.0) -> dict:
        """A few seconds of this speaker as a WAV data URL, to hear who it is."""
        import soundfile as sf

        folder, data = self._transcript_data(recording_id)
        own = [s for s in data["segments"] if s.get("speaker_id") == speaker_id]
        if not own:
            raise ValueError("Von diesem Sprecher gibt es keinen Abschnitt.")
        longest = max(own, key=lambda s: s["end"] - s["start"])
        audio_path = pipeline.audio_file(folder, longest.get("track") or "others")
        if audio_path is None:
            raise ValueError("Das Audio dieser Aufnahme wurde schon gelöscht – eine Hörprobe ist nicht mehr möglich.")
        with sf.SoundFile(audio_path) as f:
            start = max(longest["start"] + 0.3, 0)
            f.seek(min(int(start * f.samplerate), max(f.frames - 1, 0)))
            clip = f.read(int(min(seconds, longest["end"] - start) * f.samplerate), dtype="float32")
            rate = f.samplerate
        return {"url": _wav_url(clip, rate), "start": round(start, 1)}

    def audio_clip(self, recording_id: str, start: float, end: float) -> dict:
        """A passage of the conversation – both tracks mixed – as a WAV data URL, to listen to it."""
        import numpy as np

        from .transcription.faster import WHISPER_SAMPLERATE, load_piece

        folder = self._path(recording_id)
        start = max(float(start) - 0.3, 0.0)
        end = min(float(end) + 0.5, start + MAX_CLIP_S)
        pieces = [load_piece(path, start, end) for t in pipeline.TRACKS
                  if (path := pipeline.audio_file(folder, t)) is not None]
        if not pieces:
            raise ValueError("Das Audio dieser Aufnahme wurde schon gelöscht – abspielen ist nicht mehr möglich.")
        mix = np.zeros(max(len(p) for p in pieces), dtype=np.float32)
        for p in pieces:
            mix[:len(p)] += p
        return {"url": _wav_url(np.clip(mix, -1.0, 1.0), WHISPER_SAMPLERATE), "start": round(start, 1)}

    def remember_corrections(self, recording_id: str, rules: list[dict]) -> dict:
        """Save the chosen suggestions and apply them to the whole transcript right away."""
        corrections = CorrectionList.load()
        new = CorrectionList()
        for r in rules:
            info = corrections.add(r["variant"], r["target"])
            if info["kind"] != "ignored":
                new.add(r["variant"], info["target"])
        corrections.save()

        replaced = 0
        if recording_id:
            folder = self._path(recording_id)
            data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
            for s in data["segments"]:
                s["text"], n = new.apply(s["text"])
                replaced += n
            if replaced:
                data["edited"] = True
                self._write_transcript(folder, data)
        return {"remembered": sum(len(v) for v in new.rules.values()), "replaced": replaced}

    def corrections(self) -> list[dict]:
        return CorrectionList.load().as_list()

    def add_correction(self, variant: str, target: str) -> dict:
        """Add a correction by hand (settings). Same rules as from the transcript."""
        variant, target = " ".join((variant or "").split()), " ".join((target or "").split())
        if not variant or not target:
            raise ValueError("Bitte beide Felder ausfüllen: was falsch erkannt wird und wie es richtig heisst.")
        corrections = CorrectionList.load()
        info = corrections.add(variant, target)
        if info["kind"] == "ignored":
            raise ValueError("Falsch und richtig sind gleich – da gibt es nichts zu korrigieren.")
        corrections.save()
        return {"info": info, "list": corrections.as_list()}

    # ------------------------------------------------------------ spelling

    def _known_terms(self) -> list[str]:
        """Keywords and correction targets count as correctly spelled."""
        return [w.strip() for w in self._s.keywords.split(",") if w.strip()] + CorrectionList.load().targets()

    def spelling_check(self, words: list[str]) -> dict:
        return self._speller.check(list(words)[:2000], extra=self._known_terms())

    def spelling_suggest(self, word: str) -> dict:
        return {"suggestions": self._speller.suggest(word)}

    def spelling_add(self, word: str) -> None:
        self._speller.add_word(word)

    def remove_correction(self, target: str, variant: str | None = None) -> list[dict]:
        corrections = CorrectionList.load()
        corrections.remove(target, variant)
        corrections.save()
        return corrections.as_list()

    # ------------------------------------------------------------ updates

    def _check_updates_safely(self) -> None:
        try:
            self._update = updates.check()
            log.info("Update check: latest %s, current %s", self._update["latest"], __version__)
        except Exception as e:  # offline or GitHub unreachable – not worth bothering the user
            log.warning("Update check failed: %s", e)
        try:
            found = self.model_updates()
            if found:
                log.info("Model updates available: %s", ", ".join(found))
        except Exception as e:
            log.warning("Model update check failed: %s", e)

    def check_updates(self) -> dict:
        """Manual check from the settings."""
        try:
            self._update = updates.check()
        except Exception as e:
            raise RuntimeError(f"GitHub ist nicht erreichbar – später nochmals versuchen. ({e})") from e
        return self._update

    def update_info(self) -> dict | None:
        """The update found – on a Mac where Verbalis can't replace itself, with `manual` explaining why
        (the dialog then offers the download instead of installing)."""
        if not self._update:
            return None
        info = dict(self._update)
        if info.get("available") and info.get("can_install") and sys.platform == "darwin":
            reason = self._mac_update_blocked()
            if reason:
                info["can_install"], info["manual"] = False, reason
        return info

    @staticmethod
    def _mac_update_blocked() -> str | None:
        bundle = updates.app_bundle()
        if bundle is None:
            return None
        if updates.translocated(bundle):
            return ("Verbalis wurde direkt aus «Downloads» gestartet und kann sich so nicht selbst ersetzen. "
                    "Bitte das Update herunterladen, entpacken und Verbalis.app in den Ordner «Programme» ziehen.")
        if not updates.can_write(bundle.parent):
            return (f"Verbalis darf «{bundle.parent}» nicht ändern – dafür braucht es ein Administratorkonto. "
                    "Bitte das Update herunterladen, entpacken und Verbalis.app dort ersetzen (der Finder fragt "
                    "nach dem Admin-Passwort). Tipp: Im persönlichen Ordner «Programme» (im Benutzerordner) "
                    "kann sich Verbalis künftig selbst aktualisieren.")
        return None

    # ------------------------------------------------------------ macOS: install into «Programme»

    def install_check(self) -> dict | None:
        """On a Mac: should Verbalis move itself into «Programme»? None if not (or not a Mac app)."""
        bundle = updates.app_bundle() if sys.platform == "darwin" else None
        reason = updates.install_place(bundle) if bundle else None
        if not reason:
            return None
        target = updates.install_target()
        shared = target == updates.application_folders()[0]
        return {"reason": reason, "target": str(target),
                "target_name": "Programme" if shared else "Programme (in deinem Benutzerordner)"}

    def install_to_applications(self) -> dict:
        """Move (or copy) Verbalis into «Programme» and start it from there; this one quits (see app.py)."""
        import tempfile

        bundle = updates.app_bundle()
        if bundle is None or sys.platform != "darwin":
            raise RuntimeError("Nur in der Mac-App möglich.")
        if self._rec is not None or self._job is not None:
            raise RuntimeError("Bitte zuerst die Aufnahme beenden bzw. die Transkription abwarten.")
        target, left_behind = updates.move_to_applications(bundle)
        log.info("Moved Verbalis %s → %s", bundle, target)
        script = updates.write_relaunch_script(target, os.getpid(),
                                               Path(tempfile.gettempdir()) / "verbalis-relaunch.sh")
        updates.start_swap(script)
        return {"target": str(target), "left_behind": str(left_behind) if left_behind else None}

    def open_update_download(self) -> None:
        """Open the download of the update in the browser (only a file of a Verbalis release on GitHub)."""
        import webbrowser

        url = (self._update or {}).get("installer_url") or ""
        if not url.startswith("https://github.com/malaxy25/verbalis/releases/"):
            url = "https://github.com/malaxy25/verbalis/releases/latest"
        webbrowser.open(url)

    def install_update(self) -> dict:
        """Download the installer and start it. The app closes afterwards (see app.py)."""
        info = self._update
        if not info or not info.get("available"):
            raise RuntimeError("Es ist kein Update verfügbar.")
        if not info.get("can_install"):
            raise RuntimeError("In dieser Installation (Entwicklungsversion) bitte über git aktualisieren.")
        if not updates.expected_name(info):
            raise RuntimeError(f"Unerwartete Update-Datei «{info.get('installer_name')}» – sie wird nicht ausgeführt.")
        if self._rec is not None or self._job is not None or self._queued:
            raise RuntimeError("Bitte zuerst die Aufnahme beenden bzw. die Transkription abwarten.")
        import tempfile

        blocked = self._mac_update_blocked() if sys.platform == "darwin" else None
        if blocked:
            raise RuntimeError(blocked)
        bundle = updates.app_bundle() if sys.platform == "darwin" else None
        if bundle is not None and updates.translocated(bundle):
            raise RuntimeError("Verbalis wurde direkt aus «Downloads» gestartet – dort kann es sich nicht selbst "
                               "aktualisieren (macOS führt es dann aus einer schreibgeschützten Kopie aus). "
                               "Bitte Verbalis beenden, im Finder in den Ordner «Programme» ziehen, von dort "
                               "starten und das Update nochmals wählen.")
        if bundle is not None and not updates.can_write(bundle.parent):
            raise RuntimeError(f"Verbalis darf «{bundle.parent}» nicht ändern. Das Update bitte von der "
                               "Release-Seite laden oder Verbalis in einen Ordner mit Schreibrechten verschieben.")
        name = info["installer_url"].rsplit("/", 1)[-1]
        target = Path(tempfile.gettempdir()) / name
        self._update_progress = 0.0

        def progress(fraction: float) -> None:
            self._update_progress = fraction

        try:
            updates.download_installer(info["installer_url"], target, progress,
                                       sha256=info.get("installer_sha256"), size=info.get("installer_size"))
            if bundle is not None:
                # unpack next to the running app (same disk, so the final move is instant)
                new_app = updates.unpack_mac_update(target, bundle.parent / ".verbalis-update")
                updates.check_same_signer(new_app, bundle)
                script = updates.write_swap_script(bundle, new_app, os.getpid(),
                                                   Path(tempfile.gettempdir()) / "verbalis-update.sh")
                log.info("Swapping app bundle %s → %s", new_app, bundle)
                updates.start_swap(script)
            else:
                log.info("Starting installer %s", target)
                subprocess.Popen([str(target)], close_fds=True)
        except Exception as e:
            self._update_progress = None
            raise RuntimeError(f"Das Update konnte nicht vorbereitet werden. ({e})") from e
        self._update_progress = None
        return {"started": True}

    def whats_new(self) -> list[dict]:
        """Changelog sections since the version seen last – empty on the very first start."""
        last = self._s.last_seen_version
        if not last:
            self.save_settings({"last_seen_version": __version__})
            return []
        return updates.changes_between(last, __version__)

    def whats_new_seen(self) -> None:
        self.save_settings({"last_seen_version": __version__})

    # ------------------------------------------------------------ recordings

    def _path(self, recording_id: str) -> Path:
        if not VALID_ID.match(recording_id or ""):
            raise ValueError(f"Ungültige Aufnahme: {recording_id!r}")
        return self._s.recordings / recording_id

    def _status(self, recording_id: str, folder: Path, meta: dict | None = None) -> str:
        if self._rec_info.get("id") == recording_id:
            return "recording"
        if (meta or {}).get("state") == pipeline.PLANNED:
            return "planned"
        if self._job and self._job["id"] == recording_id:
            return "paused" if self._pause_reason() and self._job["start"] is not None else "running"
        if recording_id in self._queued:
            return "queued"
        if recording_id in self._errors:
            return "error"
        return "done" if (folder / "transcript.json").exists() else "none"

    def recordings(self) -> list[dict]:
        base = self._s.recordings
        if not base.exists():
            return []
        result = []
        with self._lock:
            for folder in sorted(base.iterdir(), reverse=True):
                if not folder.is_dir() or not VALID_ID.match(folder.name):
                    continue
                recording = self._rec_info.get("id") == folder.name
                if not recording and not pipeline.is_recording_folder(folder):
                    continue
                meta = pipeline.read_meta(folder)
                audio = pipeline.audio_bytes(folder)
                result.append({
                    "id": folder.name,
                    "start": meta.get("start") or folder.name,
                    "duration_s": meta.get("duration_s"),
                    "status": self._status(folder.name, folder, meta),
                    "state": "damaged" if meta.get("damaged") else meta.get("state", pipeline.COMPLETE),
                    "problem": meta.get("problem"),
                    "missing_tracks": pipeline.missing_tracks(folder) if audio else [],
                    "error": self._errors.get(folder.name),
                    "audio": bool(audio) or recording,
                    "audio_mb": round(audio / MB, 1),
                    "audio_delete": self._deletion_date(folder) if audio else None,
                    "keep_audio": bool(meta.get("keep_audio")),
                    "people": meta.get("people") or {},
                    "title": meta.get("title") or pipeline.default_title(_parse_time(meta.get("start"))
                                                                         or pipeline.recording_start(folder)),
                    "project": meta.get("project") or "",
                    "participants": meta.get("participants") or {},
                    "notes": meta.get("notes") or "",
                })
        return result

    # ------------------------------------------------------------ details and planned recordings

    def plan_recording(self, data: dict | None = None) -> str:
        """A planned recording: its details are entered now, the audio is recorded later into it."""
        data = dict(data or {})
        start = _parse_time(data.pop("start", None)) or _next_half_hour()
        with self._lock:
            folder = self._new_folder(start)
            pipeline.write_json_atomic(folder / "meta.json", {"app_version": __version__, "state": pipeline.PLANNED,
                                                              "start": start.isoformat(timespec="seconds")})
        self.update_details(folder.name, data)
        log.info("Recording %s planned", folder.name)
        return folder.name

    def update_details(self, recording_id: str, data: dict) -> dict:
        """Name, project, participants, notes – and for a planned recording its start."""
        folder = self._path(recording_id)
        meta = pipeline.read_meta(folder)
        if not meta or meta.get("damaged"):
            raise ValueError("Die Angaben dieser Aufnahme lassen sich nicht ändern (meta.json fehlt oder ist defekt).")
        changes: dict = {}
        if "title" in data:
            changes["title"] = _clean_text(data["title"], 200)
        if "project" in data:
            changes["project"] = _clean_text(data["project"], 100)
        if "notes" in data:
            changes["notes"] = str(data["notes"] or "").strip()[:10_000]
        if "participants" in data:
            changes["participants"] = {t: _names(v) for t, v in (data["participants"] or {}).items()
                                       if t in pipeline.TRACKS}
        if "start" in data:
            if meta.get("state") != pipeline.PLANNED:
                raise ValueError("Datum und Startzeit ergeben sich aus der Aufnahme und lassen sich nicht ändern.")
            start = _parse_time(data["start"])
            if start is None:
                raise ValueError("Bitte ein gültiges Datum mit Uhrzeit angeben.")
            changes["start"] = start.isoformat(timespec="seconds")
        pipeline.update_meta(folder, **changes)
        if ("title" in changes or "project" in changes) and (folder / "transcript.json").exists():
            _, transcript = self._transcript_data(recording_id)
            meta = pipeline.read_meta(folder)
            transcript["title"] = meta.get("title") or pipeline.default_title(pipeline.recording_start(folder))
            transcript.setdefault("header", {}).pop("Projekt", None)
            if meta.get("project"):
                transcript["header"]["Projekt"] = meta["project"]
            self._write_transcript(folder, transcript)
        return pipeline.details(pipeline.read_meta(folder))

    def projects(self) -> list[str]:
        """Projects of earlier recordings – suggestions while typing."""
        base = self._s.recordings
        found: dict[str, str] = {}
        if base.exists():
            for folder in base.iterdir():
                if folder.is_dir() and VALID_ID.match(folder.name):
                    project = pipeline.read_meta(folder).get("project")
                    if project:
                        found.setdefault(project.lower(), project)
        return sorted(found.values(), key=str.lower)

    def transcript(self, recording_id: str) -> dict | None:
        folder = self._path(recording_id)
        try:
            data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        md = folder / "transcript.md"
        data["markdown"] = md.read_text(encoding="utf-8") if md.exists() else ""
        return data

    def delete_recording(self, recording_id: str) -> None:
        """Delete a recording completely: audio, transcript, metadata."""
        folder = self._path(recording_id)
        if recording_id in self._protected():
            raise RuntimeError("Diese Aufnahme wird gerade aufgenommen oder transkribiert.")
        _remove_folder(folder)
        with self._lock:
            self._errors.pop(recording_id, None)
        log.info("Recording deleted: %s", recording_id)

    def open_folder(self, recording_id: str = "") -> None:
        path = self._path(recording_id) if recording_id else self._s.recordings
        path.mkdir(parents=True, exist_ok=True)
        open_in_file_manager(path)

    # ------------------------------------------------------------ state for the UI

    def state(self, focused: bool = False) -> dict:
        """focused: the window is in front – then a recognised call is shown there, not as a notification."""
        if focused:
            self._ui_focused = time.monotonic()
        with self._lock:
            call = None
            if self._call is not None and not self._call["dismissed"] and self._rec is None:
                call = {"app": self._call["apps"][0], "planned": self._call["planned"]}
            rec, info = self._rec, self._rec_info
            recording = None
            if rec is not None and rec.running:  # stopped by itself = a track failed
                tracks = {s.name: s for s in rec.status()}
                others = tracks.get("others")                  # None: «nur Mikrofon»
                now = time.monotonic()
                if rec.paused or others is None or _db(others.level_rms) > SOUND_DB:
                    self._others_last_sound = now
                self._check_no_data(rec, info)
                recording = {
                    "id": info["id"],
                    "duration_s": round(rec.active_seconds(), 1),
                    "paused": rec.paused,
                    "levels": {"me": _db(tracks["me"].level_rms),
                               "others": _db(others.level_rms) if others else -90.0},
                    # long silence on the others track usually means the wrong output device
                    "others_silent_s": round(now - self._others_last_sound),
                    "others_device": info["devices"]["others"],
                    "only_microphone": others is None,
                    "call_over": info.get("call_app") if info.get("call_over")
                    and not info.get("call_over_dismissed") else None,
                }
            job = None
            if self._job:
                rest = self._remaining(self._job)
                job = {"id": self._job["id"], "kind": self._job.get("kind", "transcription"),
                       "phase": self._job["phase"], "progress": self._job["progress"],
                       "remaining_s": round(rest) if rest is not None else None}
            queued = list(self._queued)
            pause = self._pause_reason()
        if rec is not None and recording is None:
            self.stop_recording()
        elif recording is not None:
            free = self._free_mb()
            if free is not None and free < STOP_FREE_MB:
                self.stop_recording(reason=f"Der Speicher ist fast voll (noch {free:.0f} MB). "
                                           "Die Aufnahme wurde gestoppt und bis hierhin gesichert.")
                recording = None
            elif free is not None and free < WARN_FREE_MB:
                recording["disk_minutes_left"] = max(int((free - STOP_FREE_MB) / MB_PER_MINUTE), 0)
            if recording is not None:
                recording = self._check_time_limit(recording)
        update = self._update
        return {"recording": recording, "job": job, "queued": queued, "pause": pause,
                "recording_error": self._recording_error, "notice": self._notice,
                "update": {"latest": update["latest"]} if update and update.get("available") else None,
                "model_updates": (sorted(self._model_updates[1]) if self._model_updates and self._model_updates[1]
                                  and not self._model_updates_dismissed else []),
                "model_download": dict(self._model_download) if self._model_download else None,
                "call": call,
                "update_progress": self._update_progress}

    def shutdown(self, wait_s: float = 0.0) -> None:
        """When the window closes: save a running recording properly.

        wait_s: how long to wait for the background thread to end (tests).
        """
        self._stopping.set()
        if self._rec is not None:
            rec, info = self._rec, self._rec_info
            self._rec, self._rec_info = None, {}
            self._finish(rec, info)
        self._queue.put(None)
        if wait_s:
            self._worker.join(wait_s)


def _join_neighbours(segments: list[dict], max_pause: float = 2.0) -> list[dict]:
    """After merging speakers: paragraphs of the same speaker that now follow each other become one."""
    joined: list[dict] = []
    for seg in segments:
        last = joined[-1] if joined else None
        if (last and seg.get("speaker_id") and last.get("speaker_id") == seg["speaker_id"]
                and not seg.get("aside") and not last.get("aside")
                and seg["start"] - last["end"] <= max_pause):
            last["end"] = max(last["end"], seg["end"])
            last["text"] = f"{last['text']} {seg['text']}"
        else:
            joined.append(dict(seg))
    return joined


def _wav_url(samples, rate: int) -> str:
    """Audio as a WAV data URL the window can play."""
    import base64
    import io

    import soundfile as sf

    buffer = io.BytesIO()
    sf.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
    return "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _parse_time(value) -> datetime | None:
    """An ISO date-time (from meta.json or the date field of the UI), with the local time zone if it has none."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _next_half_hour() -> datetime:
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    return now + timedelta(minutes=30 - now.minute % 30)


def _clean_text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _names(value) -> list[str]:
    """Participants from a list or from text with one name per line or separated by commas."""
    items = value if isinstance(value, list) else re.split(r"[\n,;]", str(value or ""))
    names: list[str] = []
    for item in items:
        name = _clean_text(item, 80)
        if name and name.lower() not in (n.lower() for n in names):
            names.append(name)
    return names[:MAX_PEOPLE]


def _remove_folder(folder: Path, attempts: int = 10, wait_s: float = 0.2) -> None:
    """Delete a recording folder. On Windows a file that another thread or program has open for a
    moment (the clean-up reading meta.json, a virus scanner, the search index) can't be deleted –
    try again shortly instead of failing."""
    for attempt in range(attempts):
        if not folder.exists():
            return
        try:
            shutil.rmtree(folder)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise RuntimeError("Die Aufnahme lässt sich gerade nicht löschen, weil eine Datei darin noch "
                                   "geöffnet ist. Bitte in einem Moment nochmals versuchen.") from None
            time.sleep(wait_s)


def _result_text(r: dict) -> str:
    """One device of the audio test, in words (German)."""
    if r.get("error"):
        state = f"FEHLER: {r['error']}"
    elif r.get("first_data_s") is None:
        state = "KEINE DATEN"
    else:
        state = f"OK – erste Daten nach {r['first_data_s']} s, {r['received_s']} s erhalten, Pegel {r['peak_db']:.0f} dB"
    hang = f"; hängt beim Schliessen ({r['close_s']} s gewartet)" if r.get("hangs") else ""
    return f"{r['device']}: {state}{hang}"
