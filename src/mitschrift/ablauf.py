"""Gemeinsame Abläufe für Kommandozeile und App: Metadaten und Transkription."""

from __future__ import annotations

import json
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__
from .transkript import speichern, zusammenfuehren

SPUREN = ("ich", "gegenueber")
Fortschritt = Callable[[str, float], None]  # (anzeigename, anteil 0..1)


def ist_aufnahmeordner(ordner: Path) -> bool:
    return all((ordner / f"{s}.wav").exists() for s in SPUREN)


def meta_schreiben(ordner: Path, start: datetime, dauer_s: float, samplerate: int,
                   einwilligung_zeit: str, geraete: dict[str, str], spuren: list) -> dict:
    meta = {
        "app_version": __version__,
        "start": start.isoformat(timespec="seconds"),
        "dauer_s": round(dauer_s, 1),
        "samplerate": samplerate,
        "system": f"{platform.system()} {platform.release()}",
        "einwilligung": {"bestaetigt": True, "zeitpunkt": einwilligung_zeit},
        "spuren": {
            s.name: {
                "datei": s.pfad.name,
                "geraet": geraete.get(s.name, ""),
                "laenge_s": round(s.geschrieben_frames / samplerate, 1),
                "aufgefuellte_stille_s": round(s.aufgefuellt_frames / samplerate, 2),
            }
            for s in spuren
        },
    }
    (ordner / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def meta_lesen(ordner: Path) -> dict:
    try:
        return json.loads((ordner / "meta.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def transkribieren(ordner: Path, transcriber, namen: dict[str, str], bis_s: float | None = None,
                   fortschritt: Fortschritt | None = None):
    """Beide Spuren transkribieren. Gibt (absätze, rechenzeit_s, aufnahmedauer_s) zurück."""
    from .transcription.faster import SAMPLERATE_WHISPER, lade_audio

    spuren = {}
    rechenzeit = aufnahmedauer = 0.0
    for datei, anzeigename in namen.items():
        audio = lade_audio(ordner / f"{datei}.wav", bis_s)
        aufnahmedauer = max(aufnahmedauer, len(audio) / SAMPLERATE_WHISPER)

        def melden(position, gesamt, n=anzeigename):
            if fortschritt:
                fortschritt(n, min(position / gesamt, 1.0) if gesamt else 1.0)

        t = time.monotonic()
        spuren[anzeigename] = transcriber.transkribiere(audio, fortschritt=melden)
        rechenzeit += time.monotonic() - t
        melden(1, 1)
    return zusammenfuehren(spuren), rechenzeit, aufnahmedauer


def kopf(ordner: Path, modell: str, rechenzeit: float, dauer: float) -> dict[str, str]:
    k = {"Modell": modell, "Aufnahmedauer": f"{dauer / 60:.1f} min",
         "Rechenzeit": f"{rechenzeit / 60:.1f} min ({rechenzeit / max(dauer, 1e-9):.2f}× Echtzeit)"}
    start = meta_lesen(ordner).get("start")
    return {"Aufnahme": start, **k} if start else k


def transkript_erstellen(ordner: Path, transcriber, modell: str, namen: dict[str, str],
                         fortschritt: Fortschritt | None = None) -> Path:
    absaetze, rechenzeit, dauer = transkribieren(ordner, transcriber, namen, fortschritt=fortschritt)
    return speichern(ordner, "transkript", absaetze, f"Transkript {ordner.name}",
                     kopf(ordner, modell, rechenzeit, dauer), spuren=namen)
