"""Kommandozeile.

    mitschrift geraete
    mitschrift aufnehmen [--mikrofon X] [--lautsprecher Y] [--dauer SEK]
    mitschrift transkribieren ORDNER [--modell M] [--name Andrea]
    mitschrift vergleichen ORDNER [--modelle A B C] [--bis 180] [--referenz DATEI]
    mitschrift modelle
    mitschrift modell-konvertieren HF_ID
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


# ---------------------------------------------------------------- Transkription

def _ordner_pruefen(ordner: Path) -> None:
    for datei in ("ich.wav", "gegenueber.wav"):
        if not (ordner / datei).exists():
            raise SystemExit(f"{ordner / datei} fehlt – ist das ein Aufnahmeordner?")


def _transkribiere_ordner(ordner: Path, transcriber, namen: dict[str, str], bis_s: float | None):
    """Beide Spuren transkribieren. Gibt (absätze, rechenzeit_s, aufnahmedauer_s) zurück."""
    from .transcription.faster import SAMPLERATE_WHISPER, lade_audio
    from .transkript import zusammenfuehren

    spuren = {}
    rechenzeit = 0.0
    aufnahmedauer = 0.0
    for datei, anzeigename in namen.items():
        audio = lade_audio(ordner / f"{datei}.wav", bis_s)
        aufnahmedauer = max(aufnahmedauer, len(audio) / SAMPLERATE_WHISPER)

        def fortschritt(position, gesamt, n=anzeigename):
            sys.stdout.write(f"\r  {n:12s} {min(position / gesamt, 1.0):5.0%}")
            sys.stdout.flush()

        t = time.monotonic()
        spuren[anzeigename] = transcriber.transkribiere(audio, fortschritt=fortschritt)
        rechenzeit += time.monotonic() - t
        print(f"\r  {anzeigename:12s} fertig ({len(spuren[anzeigename])} Segmente)")
    return zusammenfuehren(spuren), rechenzeit, aufnahmedauer


def _kopf(ordner: Path, modell: str, rechenzeit: float, dauer: float) -> dict[str, str]:
    kopf = {"Modell": modell, "Aufnahmedauer": f"{dauer / 60:.1f} min",
            "Rechenzeit": f"{rechenzeit / 60:.1f} min ({rechenzeit / max(dauer, 1e-9):.2f}× Echtzeit)"}
    meta = ordner / "meta.json"
    if meta.exists():
        kopf = {"Aufnahme": json.loads(meta.read_text(encoding="utf-8"))["start"], **kopf}
    return kopf


def cmd_transkribieren(args) -> int:
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.modelle import ModellFehler
    from .transkript import speichern

    ordner = Path(args.ordner)
    _ordner_pruefen(ordner)
    print(f"Lade Modell {args.modell} …")
    try:
        tr = FasterWhisperTranscriber(args.modell, geraet=args.geraet, stichworte=args.stichworte)
    except ModellFehler as e:
        print(e)
        return 1

    namen = {"ich": args.name, "gegenueber": args.gegenueber}
    absaetze, rechenzeit, dauer = _transkribiere_ordner(ordner, tr, namen, args.bis)
    md = speichern(ordner, "transkript", absaetze, f"Transkript {ordner.name}", _kopf(ordner, args.modell, rechenzeit, dauer))
    print(f"\nGespeichert: {md}  ({rechenzeit / max(dauer, 1e-9):.2f}× Echtzeit)")
    return 0


def cmd_vergleichen(args) -> int:
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.modelle import ModellFehler, slug
    from .transkript import speichern

    from .auswertung import fehlerquote

    ordner = Path(args.ordner)
    _ordner_pruefen(ordner)
    namen = {"ich": args.name, "gegenueber": args.gegenueber}
    referenz = Path(args.referenz).read_text(encoding="utf-8") if args.referenz else None
    zeilen = []

    for modell in args.modelle:
        print(f"\n=== {modell} ===")
        t = time.monotonic()
        try:
            tr = FasterWhisperTranscriber(modell, geraet=args.geraet, stichworte=args.stichworte)
        except ModellFehler as e:
            print(e)
            zeilen.append(f"| {modell} | – | – | – | – | Fehler beim Laden |")
            continue
        ladezeit = time.monotonic() - t
        absaetze, rechenzeit, dauer = _transkribiere_ordner(ordner, tr, namen, args.bis)
        datei = f"vergleich_{slug(modell)}"
        speichern(ordner, datei, absaetze, f"Vergleich: {modell}", _kopf(ordner, modell, rechenzeit, dauer))
        woerter = sum(len(a.text.split()) for a in absaetze)
        wer = "–"
        if referenz is not None:
            quote = fehlerquote(referenz, " ".join(a.text for a in absaetze))
            wer = f"{quote.wer:.1%}"
            print(f"  Fehlerquote: {quote}")
        zeilen.append(
            f"| {modell} | {ladezeit:.0f} s | {rechenzeit:.0f} s | {rechenzeit / max(dauer, 1e-9):.2f}× "
            f"| {wer} | [{datei}.md]({datei}.md), {woerter} Wörter |"
        )
        del tr  # Speicher freigeben, bevor das nächste Modell lädt

    bericht = ordner / "vergleich.md"
    bericht.write_text(
        "# Modellvergleich\n\n"
        f"Ausschnitt: {'erste ' + str(int(args.bis)) + ' s' if args.bis else 'ganze Aufnahme'}\n\n"
        + (f"Referenz: {args.referenz} – WER = Wortfehlerquote, tiefer ist besser. "
           "Übersetzungsvarianten zählen als Fehler, also nur relativ vergleichen.\n\n" if referenz else "")
        + "| Modell | Laden | Rechnen | Echtzeitfaktor | WER | Ergebnis |\n|---|---|---|---|---|---|\n"
        + "\n".join(zeilen) + "\n",
        encoding="utf-8",
    )
    print(f"\nÜbersicht: {bericht}")
    return 0


def cmd_modelle(_args) -> int:
    from .transcription.modelle import EMPFOHLEN, eingebaute_modelle, konvertierte_modelle, modell_ordner

    konvertiert = set(konvertierte_modelle())
    eingebaut = set(eingebaute_modelle())
    print("Empfohlene Modelle:")
    for modell, beschreibung in EMPFOHLEN:
        if modell in eingebaut:
            status = "eingebaut"
        elif modell in konvertiert:
            status = "konvertiert ✓"
        else:
            status = "→ mitschrift modell-konvertieren"
        print(f"  {modell}\n      {beschreibung}  [{status}]")
    andere = konvertiert - {m for m, _ in EMPFOHLEN}
    if andere:
        print("\nWeitere konvertierte Modelle:")
        for m in sorted(andere):
            print(f"  {m}")
    print(f"\nModellordner: {modell_ordner()}")
    print("Jedes Whisper-Modell von Hugging Face lässt sich konvertieren und dann per --modell nutzen.")
    return 0


def cmd_modell_konvertieren(args) -> int:
    from .transcription.modelle import ModellFehler, konvertieren

    print(f"Konvertiere {args.modell_id} – Download und Umwandlung können einige Minuten dauern …")
    try:
        ziel = konvertieren(args.modell_id, erzwingen=args.erzwingen)
    except ModellFehler as e:
        print(e)
        return 1
    print(f"Fertig: {ziel}\nNutzen mit: --modell {args.modell_id}")
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

    def transkriptions_optionen(q):
        q.add_argument("ordner", help="Aufnahmeordner mit ich.wav und gegenueber.wav")
        q.add_argument("--name", default="Ich", help="Name für die Mikrofonspur (Standard: Ich)")
        q.add_argument("--gegenueber", default="Gegenüber", help="Name für die Systemaudio-Spur")
        q.add_argument("--geraet", default="cpu", choices=["cpu", "cuda"], help="Rechnen auf CPU oder Nvidia-GPU")
        q.add_argument("--stichworte", help="Namen/Fachbegriffe, z.B. \"tocco, Höngg\"")
        q.add_argument("--bis", type=float, help="Nur die ersten N Sekunden transkribieren")

    p = sub.add_parser("transkribieren", help="Aufnahme transkribieren")
    transkriptions_optionen(p)
    p.add_argument("--modell", default="large-v3-turbo", help="Modellname, HF-ID oder Ordner (siehe: mitschrift modelle)")
    p.set_defaults(func=cmd_transkribieren)

    from .transcription.modelle import EMPFOHLEN

    p = sub.add_parser("vergleichen", help="Mehrere Modelle auf derselben Aufnahme vergleichen")
    transkriptions_optionen(p)
    p.add_argument("--modelle", nargs="+", default=[m for m, _ in EMPFOHLEN], help="Zu vergleichende Modelle")
    p.add_argument("--referenz", help="Referenztext für die Fehlerquote, z.B. testdaten/referenz_hochdeutsch.txt")
    p.set_defaults(func=cmd_vergleichen, bis=180)  # Standard: erste 3 Minuten, 0 = alles

    sub.add_parser("modelle", help="Empfohlene und konvertierte Modelle anzeigen").set_defaults(func=cmd_modelle)

    p = sub.add_parser("modell-konvertieren", help="Hugging-Face-Whisper-Modell für faster-whisper umwandeln")
    p.add_argument("modell_id", help="z.B. Flix-AI/flix-swissgerman-full")
    p.add_argument("--erzwingen", action="store_true", help="Neu konvertieren, auch wenn schon vorhanden")
    p.set_defaults(func=cmd_modell_konvertieren)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
