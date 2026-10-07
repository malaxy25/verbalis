"""Gemeinsame Abläufe für Kommandozeile und App: Metadaten und Transkription."""

from __future__ import annotations

import json
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import __version__
from .transkript import speichern, zusammenfuehren

if TYPE_CHECKING:
    from .korrekturen import Korrekturliste

SPUREN = ("ich", "gegenueber")
AUDIO_ENDUNGEN = (".flac", ".wav")
SAMPLERATE_ARCHIV = 16_000  # damit rechnen die Modelle ohnehin
Fortschritt = Callable[[str, float], None]  # (anzeigename, anteil 0..1)


def audio_datei(ordner: Path, spur: str) -> Path | None:
    """Die Audiodatei einer Spur – komprimiert (.flac) oder frisch aufgenommen (.wav)."""
    for endung in AUDIO_ENDUNGEN:
        pfad = ordner / f"{spur}{endung}"
        if pfad.exists():
            return pfad
    return None


def hat_audio(ordner: Path) -> bool:
    return all(audio_datei(ordner, s) for s in SPUREN)


def audio_bytes(ordner: Path) -> int:
    return sum(p.stat().st_size for s in SPUREN for e in AUDIO_ENDUNGEN if (p := ordner / f"{s}{e}").exists())


def ist_aufnahmeordner(ordner: Path) -> bool:
    """Aufnahme mit Audio – oder eine, deren Audio schon gelöscht wurde."""
    return hat_audio(ordner) or (ordner / "meta.json").exists()


def audio_komprimieren(ordner: Path) -> int:
    """WAV (48 kHz) → FLAC (16 kHz, verlustfrei). Spart rund 85 % Platz.

    Läuft stückweise, damit auch stundenlange Aufnahmen wenig Speicher brauchen.
    Gibt die Anzahl umgewandelter Spuren zurück.
    """
    import numpy as np
    import soundfile as sf
    import soxr

    umgewandelt = 0
    for spur in SPUREN:
        wav, flac = ordner / f"{spur}.wav", ordner / f"{spur}.flac"
        if not wav.exists():
            continue
        tmp = ordner / f"{spur}.flac.tmp"
        with sf.SoundFile(wav) as ein, sf.SoundFile(tmp, "w", samplerate=SAMPLERATE_ARCHIV, channels=1,
                                                   subtype="PCM_16", format="FLAC") as aus:
            rs = soxr.ResampleStream(ein.samplerate, SAMPLERATE_ARCHIV, 1, dtype="float32") \
                if ein.samplerate != SAMPLERATE_ARCHIV else None
            for block in ein.blocks(blocksize=ein.samplerate * 10, dtype="float32", always_2d=True):
                mono = block.mean(axis=1)
                aus.write(rs.resample_chunk(mono) if rs else mono)
            if rs:
                aus.write(rs.resample_chunk(np.zeros(0, dtype=np.float32), last=True))
        tmp.replace(flac)
        wav.unlink()
        umgewandelt += 1
    if umgewandelt:
        meta_aktualisieren(ordner, audio={"format": "flac", "samplerate": SAMPLERATE_ARCHIV})
    return umgewandelt


def audio_loeschen(ordner: Path, grund: str) -> int:
    """Audiodateien löschen, Transkript bleibt. Gibt die freigegebenen Bytes zurück."""
    frei = audio_bytes(ordner)
    for spur in SPUREN:
        for endung in (*AUDIO_ENDUNGEN, ".flac.tmp"):
            (ordner / f"{spur}{endung}").unlink(missing_ok=True)
    meta_aktualisieren(ordner, audio_geloescht={
        "zeitpunkt": datetime.now().astimezone().isoformat(timespec="seconds"), "grund": grund})
    return frei


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


def meta_aktualisieren(ordner: Path, **felder) -> None:
    meta = {**meta_lesen(ordner), **felder}
    (ordner / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def aufnahme_start(ordner: Path) -> datetime | None:
    """Startzeit aus meta.json, sonst aus dem Ordnernamen (JJJJ-MM-TT_HHMMSS)."""
    start = meta_lesen(ordner).get("start")
    try:
        return datetime.fromisoformat(start) if start else \
            datetime.strptime(ordner.name, "%Y-%m-%d_%H%M%S").astimezone()
    except ValueError:
        return None


def transkribieren(ordner: Path, transcriber, namen: dict[str, str], bis_s: float | None = None,
                   fortschritt: Fortschritt | None = None, pausenzeit: Callable[[], float] | None = None):
    """Beide Spuren transkribieren. Gibt (absätze, rechenzeit_s, aufnahmedauer_s) zurück.

    pausenzeit: liefert die bisher pausierte Zeit in Sekunden; sie wird nicht
    zur Rechenzeit gezählt.
    """
    pausenzeit = pausenzeit or (lambda: 0.0)
    from .transcription.faster import SAMPLERATE_WHISPER, lade_audio

    spuren = {}
    rechenzeit = aufnahmedauer = 0.0
    for datei, anzeigename in namen.items():
        pfad = audio_datei(ordner, datei)
        if pfad is None:
            raise FileNotFoundError(f"Die Audiodatei der Spur «{anzeigename}» fehlt – wurde sie gelöscht?")
        audio = lade_audio(pfad, bis_s)
        aufnahmedauer = max(aufnahmedauer, len(audio) / SAMPLERATE_WHISPER)

        def melden(position, gesamt, n=anzeigename):
            if fortschritt:
                fortschritt(n, min(position / gesamt, 1.0) if gesamt else 1.0)

        t, p = time.monotonic(), pausenzeit()
        spuren[anzeigename] = transcriber.transkribiere(audio, fortschritt=melden)
        rechenzeit += (time.monotonic() - t) - (pausenzeit() - p)
        melden(1, 1)
    return zusammenfuehren(spuren), rechenzeit, aufnahmedauer


def kopf(ordner: Path, modell: str, rechenzeit: float, dauer: float) -> dict[str, str]:
    k = {"Modell": modell, "Aufnahmedauer": f"{dauer / 60:.1f} min",
         "Rechenzeit": f"{rechenzeit / 60:.1f} min ({rechenzeit / max(dauer, 1e-9):.2f}× Echtzeit)"}
    start = meta_lesen(ordner).get("start")
    return {"Aufnahme": start, **k} if start else k


def korrigieren(absaetze: list, liste: "Korrekturliste | None") -> int:
    """Korrekturliste auf alle Absätze anwenden (an Ort und Stelle). Gibt die Anzahl zurück."""
    if liste is None:
        return 0
    gesamt = 0
    for a in absaetze:
        a.text, n = liste.anwenden(a.text)
        gesamt += n
    return gesamt


def transkript_erstellen(ordner: Path, transcriber, modell: str, namen: dict[str, str],
                         fortschritt: Fortschritt | None = None,
                         pausenzeit: Callable[[], float] | None = None,
                         korrekturen: "Korrekturliste | None" = None) -> tuple[Path, float, float]:
    """Gibt (pfad, rechenzeit_s, aufnahmedauer_s) zurück."""
    absaetze, rechenzeit, dauer = transkribieren(ordner, transcriber, namen, fortschritt=fortschritt,
                                                 pausenzeit=pausenzeit)
    k = kopf(ordner, modell, rechenzeit, dauer)
    n = korrigieren(absaetze, korrekturen)
    if n:
        k["Korrekturen"] = f"{n} automatisch ersetzt"
    pfad = speichern(ordner, "transkript", absaetze, f"Transkript {ordner.name}", k, spuren=namen)
    (ordner / "transkript_original.json").unlink(missing_ok=True)  # alte Bearbeitungen sind überholt
    return pfad, rechenzeit, dauer
