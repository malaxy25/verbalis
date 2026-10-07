"""Kommandozeile für den Aufnahme-Spike.

    mitschrift geraete
    mitschrift aufnehmen [--mikrofon X] [--lautsprecher Y] [--dauer SEK]
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__


def _pegelbalken(rms: float, breite: int = 20) -> str:
    db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
    anteil = min(max((db + 60) / 60, 0.0), 1.0)  # -60 dB … 0 dB
    voll = round(anteil * breite)
    return f"{'█' * voll}{'·' * (breite - voll)} {db:6.1f} dB"


def _einwilligung_einholen(bereits_bestaetigt: bool) -> bool:
    if bereits_bestaetigt:
        return True
    print(
        "Hinweis: Gespräche ohne Einwilligung aller Teilnehmenden aufzunehmen,\n"
        "ist in der Schweiz strafbar (StGB Art. 179ter).\n"
        "Vorschlag zum Vorlesen: «Ich würde das Gespräch gerne für das Protokoll\n"
        "aufnehmen und transkribieren lassen – ist das für alle in Ordnung?»\n"
    )
    antwort = input("Haben alle Teilnehmenden zugestimmt? [j/N] ").strip().lower()
    return antwort in {"j", "ja", "y", "yes"}


def cmd_geraete(_args) -> int:
    from .audio.devices import liste_ausgeben

    liste_ausgeben()
    return 0


def cmd_aufnehmen(args) -> int:
    from .audio.devices import ermittle
    from .audio.recorder import ZweiSpurRecorder

    if not _einwilligung_einholen(args.einwilligung):
        print("Keine Einwilligung – Aufnahme abgebrochen.")
        return 1
    einwilligung_zeit = datetime.now().astimezone().isoformat(timespec="seconds")

    geraete = ermittle(args.mikrofon, args.lautsprecher)
    start = datetime.now().astimezone()
    ordner = Path(args.ausgabe) / start.strftime("%Y-%m-%d_%H%M%S")

    print(f"\nMikrofon:   {geraete.mikrofon.name}")
    print(f"Loopback:   {geraete.loopback.name}")
    print(f"Speichere:  {ordner}")
    print("Aufnahme läuft – beenden mit Ctrl+C.\n")

    rec = ZweiSpurRecorder(geraete.mikrofon, geraete.loopback, ordner)
    rec.start()
    try:
        while rec.laeuft:
            vergangen = time.monotonic() - rec.t0
            if args.dauer and vergangen >= args.dauer:
                break
            ich, gegenueber = rec.status()
            mm, ss = divmod(int(vergangen), 60)
            sys.stdout.write(
                f"\r● {mm:02d}:{ss:02d}   Ich {_pegelbalken(ich.pegel_rms)}"
                f"   Gegenüber {_pegelbalken(gegenueber.pegel_rms)}  "
            )
            sys.stdout.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stoppen()
    print("\n")

    if rec.fehler:
        for fehler in rec.fehler:
            print(f"Fehler in einer Spur: {fehler!r}")
        return 2

    dauer = time.monotonic() - rec.t0
    meta = {
        "app_version": __version__,
        "start": start.isoformat(timespec="seconds"),
        "dauer_s": round(dauer, 1),
        "samplerate": rec.samplerate,
        "system": f"{platform.system()} {platform.release()}",
        "einwilligung": {"bestaetigt": True, "zeitpunkt": einwilligung_zeit},
        "spuren": {
            s.name: {
                "datei": s.pfad.name,
                "geraet": (geraete.mikrofon if s.name == "ich" else geraete.loopback).name,
                "laenge_s": round(s.geschrieben_frames / rec.samplerate, 1),
                "aufgefuellte_stille_s": round(s.aufgefuellt_frames / rec.samplerate, 2),
            }
            for s in rec.status()
        },
    }
    (ordner / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    for name, info in meta["spuren"].items():
        print(f"{name:11s} {info['laenge_s']:7.1f} s   aufgefüllte Stille: {info['aufgefuellte_stille_s']} s")
    print(f"\nGespeichert in {ordner}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mitschrift", description="Gespräche aufnehmen und transkribieren.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="befehl", required=True)

    sub.add_parser("geraete", help="Mikrofone und Lautsprecher auflisten").set_defaults(func=cmd_geraete)

    p = sub.add_parser("aufnehmen", help="Mikrofon und Systemaudio als zwei Spuren aufnehmen")
    p.add_argument("--mikrofon", help="Index oder Namensteil (Standard: System-Standard)")
    p.add_argument("--lautsprecher", help="Index oder Namensteil des Ausgabegeräts von Teams")
    p.add_argument("--ausgabe", default="aufnahmen", help="Zielordner (Standard: ./aufnahmen)")
    p.add_argument("--dauer", type=float, help="Automatisch nach N Sekunden stoppen")
    p.add_argument("--einwilligung", action="store_true", help="Einwilligung bereits eingeholt (keine Rückfrage)")
    p.set_defaults(func=cmd_aufnehmen)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
