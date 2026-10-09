"""Read and export the log file.

The log lives in ~/.verbalis/verbalis.log and rotates at 1 MB with one backup
(verbalis.log.1). It never contains conversation content – only technical
events, model names, folder names and error messages.

The export is meant for bug reports: a ZIP with the logs, version and system
information and the non-personal settings. The home folder path is replaced
by "~" so the Windows user name doesn't travel along.
"""

from __future__ import annotations

import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .transcription.models import verbalis_home

LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} (DEBUG|INFO|WARNING|ERROR|CRITICAL) ([\w.]+): (.*)$")
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
# Settings that are safe to share: no names, keywords or paths
SHARED_SETTINGS = ("model", "quality", "audio_days", "audio_max_mb", "microphone", "speakers")


def log_path() -> Path:
    return verbalis_home() / "verbalis.log"


def _files() -> list[Path]:
    """Backup first, then the current file – i.e. oldest to newest."""
    current = log_path()
    return [p for p in (current.with_name(current.name + ".1"), current) if p.exists()]


def read_entries(errors_only: bool = False, limit: int = 500) -> list[dict]:
    """Log entries, newest first. Continuation lines (tracebacks) go into "details"."""
    entries: list[dict] = []
    for path in _files():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LINE.match(line)
            if m:
                entries.append({"time": m.group(1), "level": m.group(2), "source": m.group(3),
                                "message": m.group(4), "details": ""})
            elif entries and line.strip():
                entries[-1]["details"] += line + "\n"
    if errors_only:
        entries = [e for e in entries if LEVELS[e["level"]] >= LEVELS["WARNING"]]
    return entries[::-1][:limit]


def _anonymise(text: str) -> str:
    home = str(Path.home())
    for variant in {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}:
        text = text.replace(variant, "~")
    return text


def _redact(text: str, secrets: list[str]) -> str:
    for secret in sorted({s for s in secrets if s and len(s) >= 3}, key=len, reverse=True):
        text = text.replace(secret, "<entfernt>")
    return text


def export(target: Path, settings: dict, redact: list[str] | None = None) -> Path:
    """Write the log export as a ZIP to `target`.

    `redact`: further texts to remove – device names (often contain a person's name,
    e.g. «AirPods von Andrea»), the user's name and the label for the others.
    """
    secrets = list(redact or []) + [settings.get("name", ""), settings.get("others", "")]
    info = {
        "app_version": __version__,
        "exported": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "system": f"{platform.system()} {platform.release()} ({platform.version()})",
        "settings": {k: settings.get(k, "") for k in SHARED_SETTINGS},
        "custom_recordings_dir": bool(settings.get("recordings_dir")),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", _redact(_anonymise(json.dumps(info, indent=2, ensure_ascii=False)), secrets))
        for path in _files():
            text = path.read_text(encoding="utf-8", errors="replace")
            z.writestr(path.name, _redact(_anonymise(text), secrets))
    return target


def default_export_name() -> str:
    return f"verbalis-protokoll-{datetime.now():%Y-%m-%d_%H%M}.zip"
