"""Kommandozeile.

    mitschrift app                      Oberfläche starten
    mitschrift geraete
    mitschrift aufnehmen [--mikrofon X] [--lautsprecher Y] [--dauer SEK]
    mitschrift transkribieren ORDNER [--modell M] [--name Andrea]
    mitschrift vergleichen ORDNER [--modelle A B C] [--bis 180] [--referenz DATEI]
    mitschrift modelle
    mitschrift modell-konvertieren HF_ID
"""

from __future__ import annotations

import argparse
import math
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


def cmd_app(_args) -> int:
    from .app import hauptprogramm

    hauptprogramm()
    return 0


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
    from .einstellungen import Einstellungen

    basis = Path(args.ausgabe) if args.ausgabe else Einstellungen.laden().ordner
    ordner = basis / start.strftime("%Y-%m-%d_%H%M%S")

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

    from .ablauf import meta_schreiben

    meta = meta_schreiben(
        ordner, start, time.monotonic() - rec.t0, rec.samplerate, einwilligung_zeit,
        {"ich": geraete.mikrofon.name, "gegenueber": geraete.loopback.name}, rec.status(),
    )

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
    from .ablauf import transkribieren

    def fortschritt(name, anteil):
        sys.stdout.write(f"\r  {name:12s} {anteil:5.0%}")
        sys.stdout.flush()
        if anteil >= 1:
            print()

    return transkribieren(ordner, transcriber, namen, bis_s, fortschritt)


def _kopf(ordner: Path, modell: str, rechenzeit: float, dauer: float) -> dict[str, str]:
    from .ablauf import kopf

    return kopf(ordner, modell, rechenzeit, dauer)


def cmd_transkribieren(args) -> int:
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.modelle import ModellFehler
    from .transkript import speichern

    ordner = Path(args.ordner)
    _ordner_pruefen(ordner)
    print(f"Lade Modell {args.modell} …")
    try:
        tr = FasterWhisperTranscriber(args.modell, geraet=args.geraet, stichworte=args.stichworte,
                                      beam_size=args.beam)
    except ModellFehler as e:
        print(e)
        return 1

    from .ablauf import korrigieren
    from .korrekturen import Korrekturliste

    namen = {"ich": args.name, "gegenueber": args.gegenueber}
    absaetze, rechenzeit, dauer = _transkribiere_ordner(ordner, tr, namen, args.bis)
    kopf = _kopf(ordner, args.modell, rechenzeit, dauer)
    if n := korrigieren(absaetze, Korrekturliste.laden()):
        kopf["Korrekturen"] = f"{n} automatisch ersetzt"
    md = speichern(ordner, "transkript", absaetze, f"Transkript {ordner.name}", kopf, spuren=namen)
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
            tr = FasterWhisperTranscriber(modell, geraet=args.geraet, stichworte=args.stichworte,
                                          beam_size=args.beam)
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

    sub.add_parser("app", help="Oberfläche starten").set_defaults(func=cmd_app)
    sub.add_parser("geraete", help="Mikrofone und Lautsprecher auflisten").set_defaults(func=cmd_geraete)

    p = sub.add_parser("aufnehmen", help="Mikrofon und Systemaudio als zwei Spuren aufnehmen")
    p.add_argument("--mikrofon", help="Index oder Namensteil (Standard: System-Standard)")
    p.add_argument("--lautsprecher", help="Index oder Namensteil des Ausgabegeräts von Teams")
    p.add_argument("--ausgabe", help="Zielordner (Standard: Aufnahmeordner aus den Einstellungen)")
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
        q.add_argument("--beam", type=int, default=5, help="Suchbreite: 5 = genau (Standard), 1 = schneller")

    p = sub.add_parser("transkribieren", help="Aufnahme transkribieren")
    transkriptions_optionen(p)
    from .einstellungen import Einstellungen

    p.add_argument("--modell", default=Einstellungen.laden().modell,
                   help="Modellname, HF-ID oder Ordner (Standard: Modell aus den Einstellungen)")
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
