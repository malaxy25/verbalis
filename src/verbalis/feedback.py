"""«Problem melden»: send a short report to the developer – text, version, system, optionally the log.

The report goes to a Google Apps Script web app (`doPost`) that writes a row into a Google Sheet,
stores the log ZIP in Google Drive and sends a notification mail (`tools/feedback/apps-script.js`).
Its address and a shared token are not in the public repo: the release build writes them from GitHub
secrets into `feedback.json` next to the app; in a checkout the environment variables
VERBALIS_FEEDBACK_URL and VERBALIS_FEEDBACK_TOKEN are used. Without them only the e-mail way is offered.

Nothing is sent without the user's click, and never recordings or transcripts: the log export
leaves out names and paths (see logs.py), device names are removed from the diagnosis too.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import __version__, logs

CONTACT = "andrea@frehner.tech"
CONFIG_NAME = "feedback.json"
MAX_MESSAGE = 5000
MAX_LOG_BYTES = 5 * 1024 * 1024


def config() -> dict | None:
    """{"url", "token"} or None when this installation can't send reports."""
    url = os.environ.get("VERBALIS_FEEDBACK_URL", "").strip()
    token = os.environ.get("VERBALIS_FEEDBACK_TOKEN", "").strip()
    if url:
        return {"url": url, "token": token}
    for folder in _bundle_folders():
        path = folder / CONFIG_NAME
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if str(data.get("url", "")).startswith("https://"):
                return {"url": data["url"], "token": str(data.get("token", ""))}
    return None


def _bundle_folders() -> list[Path]:
    folders = []
    if getattr(sys, "_MEIPASS", None):
        folders.append(Path(sys._MEIPASS))
    folders.append(Path(__file__).resolve().parent)
    return folders


def build(message: str, contact: str = "", diagnosis: str = "", log_zip: bytes | None = None,
          redact: list[str] | None = None) -> dict:
    """The report as sent. diagnosis: «Diagnose kopieren» text; redact: names to remove from it."""
    message = (message or "").strip()
    if not message:
        raise ValueError("Bitte kurz beschreiben, was passiert ist.")
    for secret in sorted({s for s in (redact or []) if s and len(s) >= 3}, key=len, reverse=True):
        diagnosis = diagnosis.replace(secret, "<entfernt>")
    report = {
        "kind": "report",
        "version": __version__,
        "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "message": message[:MAX_MESSAGE],
        "contact": (contact or "").strip()[:200],
        "diagnosis": diagnosis[:40000],
    }
    if log_zip:
        if len(log_zip) > MAX_LOG_BYTES:
            log_zip = None
            report["log_note"] = "Log zu gross – nicht mitgesendet"
        else:
            report["log_zip"] = base64.b64encode(log_zip).decode("ascii")
    return report


def log_zip(settings: dict, redact: list[str]) -> bytes:
    """The same ZIP as «Log exportieren», as bytes."""
    with tempfile.TemporaryDirectory() as folder:
        path = logs.export(Path(folder) / logs.default_export_name(), settings, redact=redact)
        return path.read_bytes()


def send(report: dict, target: dict, opener: Callable = urllib.request.urlopen, timeout: float = 30) -> None:
    """POST the report; raise RuntimeError with a German message if it doesn't arrive."""
    body = json.dumps({**report, "token": target.get("token", "")}).encode("utf-8")
    request = urllib.request.Request(target["url"], data=body, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": f"Verbalis/{__version__}"})
    try:
        with opener(request, timeout=timeout) as response:
            answer = response.read(200).decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as e:
        # The server answered, so the internet works – the address refuses (e.g. the web app is not open
        # to «Anyone»). Asking about the internet misled the first test (0.7.29).
        raise RuntimeError(f"Die Meldung wurde vom Empfänger abgelehnt (HTTP {e.code}).") from e
    except OSError as e:
        raise RuntimeError(f"Die Meldung konnte nicht gesendet werden ({e}). Ist das Internet verfügbar?") from e
    if answer != "ok":
        raise RuntimeError(f"Die Meldung wurde nicht angenommen ({answer[:80] or 'keine Antwort'}).")


def mail_link(message: str) -> str:
    """mailto: link as the fallback – without the log (that is attached by hand)."""
    subject = f"Verbalis {__version__}: Problem"
    body = (f"{(message or '').strip()}\n\n---\nVersion {__version__}, {platform.system()} {platform.release()}\n"
            "Log: Einstellungen → Log → «Log exportieren …» und die Datei anhängen.\n")
    return f"mailto:{CONTACT}?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                         quote_via=urllib.parse.quote)
