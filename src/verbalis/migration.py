"""One-time migration from «Mitschrift» (versions up to 0.6) to Verbalis.

Up to 0.6 the app was called «Mitschrift» and used German names for files and
fields. This moves everything from ~/.mitschrift to ~/.verbalis and renames
files and JSON fields in every recording folder:

    einstellungen.json → settings.json      ich.flac       → me.flac
    korrekturen.json   → corrections.json   gegenueber.flac → others.flac
    statistik.json     → stats.json         transkript.*   → transcript.*
    modelle/           → models/            vergleich*     → comparison*
    aufnahmen/         → recordings/

Safe to run repeatedly: a marker file in the old folder prevents a second run,
and existing new files are never overwritten.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from .transcription.models import verbalis_home

log = logging.getLogger(__name__)

MARKER = "MOVED_TO_VERBALIS.txt"
SETTINGS_KEYS = {
    "name": "name", "gegenueber": "others", "modell": "model", "qualitaet": "quality",
    "stichworte": "keywords", "aufnahme_ordner": "recordings_dir", "mikrofon": "microphone",
    "lautsprecher": "speakers", "fenster": "window_size", "audio_tage": "audio_days",
    "audio_max_mb": "audio_max_mb",
}
QUALITY = {"genau": "accurate", "schnell": "fast"}
TRACKS = {"ich": "me", "gegenueber": "others"}


def old_home() -> Path:
    return Path(os.environ.get("MITSCHRIFT_HOME", Path.home() / ".mitschrift"))


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _rename(src: Path, dst: Path) -> bool:
    if src.exists() and not dst.exists():
        src.rename(dst)
        return True
    return False


# ---------------------------------------------------------------- recording folders

def _meta(old: dict) -> dict:
    new = {k: v for k, v in old.items()
           if k not in ("dauer_s", "einwilligung", "spuren", "audio_geloescht")}
    if "dauer_s" in old:
        new["duration_s"] = old["dauer_s"]
    if "einwilligung" in old:
        e = old["einwilligung"]
        new["consent"] = {"confirmed": e.get("bestaetigt", True), "timestamp": e.get("zeitpunkt")}
    if "spuren" in old:
        new["tracks"] = {
            TRACKS.get(name, name): {
                "file": TRACKS.get(name, name) + Path(t.get("datei", ".wav")).suffix,
                "device": t.get("geraet", ""),
                "length_s": t.get("laenge_s"),
                "padded_silence_s": t.get("aufgefuellte_stille_s"),
            }
            for name, t in old["spuren"].items()
        }
    if "audio_geloescht" in old:
        g = old["audio_geloescht"]
        new["audio_deleted"] = {"timestamp": g.get("zeitpunkt"), "reason": g.get("grund")}
    return new


def _transcript(old: dict) -> dict:
    if "segments" in old:  # already new
        return old
    new = {
        "title": old.get("titel", ""),
        "header": old.get("kopf", {}),
        "tracks": {TRACKS.get(k, k): v for k, v in old.get("spuren", {}).items()},
        "segments": [
            {"start": s["start"], "end": s.get("ende", s["start"]), "text": s["text"], "speaker": s.get("sprecher")}
            for s in old.get("segmente", [])
        ],
    }
    if old.get("bearbeitet"):
        new["edited"] = True
    return new


def migrate_recording(folder: Path) -> bool:
    """Rename files and fields of one recording folder. Returns True if anything changed."""
    changed = False
    for old_track, new_track in TRACKS.items():
        for ext in (".wav", ".flac", ".flac.tmp"):
            changed |= _rename(folder / f"{old_track}{ext}", folder / f"{new_track}{ext}")

    meta = _read(folder / "meta.json")
    if meta and any(k in meta for k in ("dauer_s", "einwilligung", "spuren", "audio_geloescht")):
        _write(folder / "meta.json", _meta(meta))
        changed = True

    for old_name, new_name in (("transkript", "transcript"), ("transkript_original", "transcript_original")):
        old_json, new_json = folder / f"{old_name}.json", folder / f"{new_name}.json"
        if old_json.exists() and not new_json.exists():
            data = _read(old_json)
            if data is not None:
                _write(new_json, _transcript(data))
                old_json.unlink()
                changed = True
    changed |= _rename(folder / "transkript.md", folder / "transcript.md")

    for f in list(folder.glob("vergleich*")):
        changed |= _rename(f, folder / f.name.replace("vergleich", "comparison", 1))
    return changed


# ---------------------------------------------------------------- the whole home folder

def migrate_if_needed(new: Path | None = None, old: Path | None = None) -> list[str]:
    """Migrate once from the old home folder. Returns a list of what was done."""
    old = old or old_home()
    new = new or verbalis_home()
    if not old.exists() or (old / MARKER).exists():
        return []
    done: list[str] = []
    new.mkdir(parents=True, exist_ok=True)

    settings = _read(old / "einstellungen.json")
    custom_dir = ""
    if settings is not None:
        mapped = {SETTINGS_KEYS[k]: v for k, v in settings.items() if k in SETTINGS_KEYS}
        mapped["quality"] = QUALITY.get(mapped.get("quality", ""), "accurate")
        custom_dir = mapped.get("recordings_dir", "") or ""
        if custom_dir and not Path(custom_dir).expanduser().exists():
            custom_dir = mapped["recordings_dir"] = ""  # e.g. inside a renamed repo folder → default
        if not (new / "settings.json").exists():
            _write(new / "settings.json", mapped)
            done.append("Einstellungen")

    corrections = _read(old / "korrekturen.json")
    if corrections is not None and not (new / "corrections.json").exists():
        _write(new / "corrections.json", {"rules": corrections.get("regeln", {})})
        done.append("Korrekturliste")

    stats = _read(old / "statistik.json")
    if stats is not None and not (new / "stats.json").exists():
        _write(new / "stats.json", {"realtime_factor": stats.get("echtzeitfaktor", {})})

    if (old / "modelle").exists():
        (new / "models").mkdir(exist_ok=True)
        for d in (old / "modelle").iterdir():
            target = new / "models" / d.name
            if d.is_dir() and not target.exists():
                shutil.move(str(d), str(target))
                info = _read(target / "mitschrift.json")
                if info is not None:
                    _write(target / "verbalis.json", {"source": info.get("quelle"),
                                                      "quantization": info.get("quantisierung")})
                    (target / "mitschrift.json").unlink()
                done.append(f"Modell {d.name}")

    if (old / "aufnahmen").exists():
        (new / "recordings").mkdir(exist_ok=True)
        for d in (old / "aufnahmen").iterdir():
            if d.is_dir() and not (new / "recordings" / d.name).exists():
                shutil.move(str(d), str(new / "recordings" / d.name))

    folders = [new / "recordings"]
    if custom_dir:
        folders.append(Path(custom_dir).expanduser())
    migrated = 0
    for base in folders:
        if base.exists():
            migrated += sum(migrate_recording(d) for d in base.iterdir() if d.is_dir())
    if migrated:
        done.append(f"{migrated} Aufnahmen")

    (old / MARKER).write_text(
        f"Die App heisst jetzt Verbalis. Einstellungen, Korrekturliste, Modelle und Aufnahmen\n"
        f"wurden nach {new} übernommen. Dieser Ordner kann gelöscht werden.\n",
        encoding="utf-8")
    log.info("Migrated from %s: %s", old, ", ".join(done) or "nothing")
    return done
