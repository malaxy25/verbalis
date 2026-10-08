"""Command line. Commands and options are English, output is German.

    verbalis app                        open the UI
    verbalis devices
    verbalis record [--microphone X] [--speakers Y] [--duration SEC]
    verbalis transcribe FOLDER [--model M] [--name Andrea]
    verbalis compare FOLDER [--models A B C] [--until 180] [--reference FILE]
    verbalis models
    verbalis convert-model HF_ID
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__


def _level_bar(rms: float, width: int = 20) -> str:
    db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
    fraction = min(max((db + 60) / 60, 0.0), 1.0)  # -60 dB … 0 dB
    full = round(fraction * width)
    return f"{'█' * full}{'·' * (width - full)} {db:6.1f} dB"


def _ask_consent(already_confirmed: bool) -> bool:
    if already_confirmed:
        return True
    print(
        "Hinweis: Gespräche ohne Einwilligung aller Teilnehmenden aufzunehmen,\n"
        "ist in der Schweiz strafbar (StGB Art. 179ter).\n"
        "Vorschlag zum Vorlesen: «Ich würde das Gespräch gerne für das Protokoll\n"
        "aufnehmen und transkribieren lassen – ist das für alle in Ordnung?»\n"
    )
    answer = input("Haben alle Teilnehmenden zugestimmt? [j/N] ").strip().lower()
    return answer in {"j", "ja", "y", "yes"}


def cmd_app(_args) -> int:
    from .app import main as app_main

    app_main()
    return 0


def cmd_devices(_args) -> int:
    from .audio.devices import print_devices

    print_devices()
    return 0


def cmd_record(args) -> int:
    from .audio.devices import select
    from .audio.recorder import TwoTrackRecorder
    from .pipeline import compress_audio, write_meta
    from .settings import Settings

    if not _ask_consent(args.consent):
        print("Keine Einwilligung – Aufnahme abgebrochen.")
        return 1
    consent_time = datetime.now().astimezone().isoformat(timespec="seconds")

    devices = select(args.microphone, args.speakers)
    start = datetime.now().astimezone()
    base = Path(args.output_dir) if args.output_dir else Settings.load().recordings
    folder = base / start.strftime("%Y-%m-%d_%H%M%S")

    print(f"\nMikrofon:   {devices.microphone.name}")
    print(f"Loopback:   {devices.loopback.name}")
    print(f"Speichere:  {folder}")
    print("Aufnahme läuft – beenden mit Ctrl+C.\n")

    rec = TwoTrackRecorder(devices.microphone, devices.loopback, folder)
    rec.start()
    try:
        while rec.running:
            elapsed = time.monotonic() - rec.t0
            if args.duration and elapsed >= args.duration:
                break
            me, others = rec.status()
            mm, ss = divmod(int(elapsed), 60)
            sys.stdout.write(
                f"\r● {mm:02d}:{ss:02d}   Ich {_level_bar(me.level_rms)}"
                f"   Gegenüber {_level_bar(others.level_rms)}  "
            )
            sys.stdout.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
    print("\n")

    if rec.errors:
        for error in rec.errors:
            print(f"Fehler in einer Spur: {error!r}")
        return 2

    meta = write_meta(
        folder, start, time.monotonic() - rec.t0, rec.samplerate, consent_time,
        {"me": devices.microphone.name, "others": devices.loopback.name}, rec.status(),
    )
    for name, info in meta["tracks"].items():
        print(f"{name:7s} {info['length_s']:7.1f} s   aufgefüllte Stille: {info['padded_silence_s']} s")

    print("Komprimiere Audio (16 kHz, FLAC) …")
    compress_audio(folder)
    print(f"\nGespeichert in {folder}")
    return 0


# ---------------------------------------------------------------- transcription

def _check_folder(folder: Path) -> None:
    from .pipeline import has_audio

    if not has_audio(folder):
        raise SystemExit(f"In {folder} fehlen die Audiodateien (me/others als .wav oder .flac).")


def _transcribe_folder(folder: Path, transcriber, names: dict[str, str], until_s: float | None):
    from .pipeline import transcribe

    def progress(name, fraction):
        sys.stdout.write(f"\r  {name:12s} {fraction:5.0%}")
        sys.stdout.flush()
        if fraction >= 1:
            print()

    return transcribe(folder, transcriber, names, until_s, progress)


def cmd_transcribe(args) -> int:
    from .corrections import CorrectionList
    from .pipeline import apply_corrections, header
    from .transcript import save
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.models import ModelError

    folder = Path(args.folder)
    _check_folder(folder)
    print(f"Lade Modell {args.model} …")
    try:
        tr = FasterWhisperTranscriber(args.model, device=args.device, keywords=args.keywords, beam_size=args.beam)
    except ModelError as e:
        print(e)
        return 1

    names = {"me": args.name, "others": args.others}
    paragraphs, compute, duration = _transcribe_folder(folder, tr, names, args.until)
    h = header(folder, args.model, compute, duration)
    if n := apply_corrections(paragraphs, CorrectionList.load()):
        h["Korrekturen"] = f"{n} automatisch ersetzt"
    md = save(folder, "transcript", paragraphs, f"Transkript {folder.name}", h, tracks=names)
    print(f"\nGespeichert: {md}  ({compute / max(duration, 1e-9):.2f}× Echtzeit)")
    return 0


def cmd_compare(args) -> int:
    from .evaluation import error_rate
    from .pipeline import header
    from .transcript import save
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.models import ModelError, slug

    folder = Path(args.folder)
    _check_folder(folder)
    names = {"me": args.name, "others": args.others}
    reference = Path(args.reference).read_text(encoding="utf-8") if args.reference else None
    rows = []

    for model in args.models:
        print(f"\n=== {model} ===")
        t = time.monotonic()
        try:
            tr = FasterWhisperTranscriber(model, device=args.device, keywords=args.keywords, beam_size=args.beam)
        except ModelError as e:
            print(e)
            rows.append(f"| {model} | – | – | – | – | Fehler beim Laden |")
            continue
        load_time = time.monotonic() - t
        paragraphs, compute, duration = _transcribe_folder(folder, tr, names, args.until)
        filename = f"comparison_{slug(model)}"
        save(folder, filename, paragraphs, f"Vergleich: {model}", header(folder, model, compute, duration))
        words = sum(len(p.text.split()) for p in paragraphs)
        wer = "–"
        if reference is not None:
            rate = error_rate(reference, " ".join(p.text for p in paragraphs))
            wer = f"{rate.wer:.1%}"
            print(f"  Fehlerquote: {rate}")
        rows.append(
            f"| {model} | {load_time:.0f} s | {compute:.0f} s | {compute / max(duration, 1e-9):.2f}× "
            f"| {wer} | [{filename}.md]({filename}.md), {words} Wörter |"
        )
        del tr  # free memory before loading the next model

    report = folder / "comparison.md"
    report.write_text(
        "# Modellvergleich\n\n"
        f"Ausschnitt: {'erste ' + str(int(args.until)) + ' s' if args.until else 'ganze Aufnahme'}\n\n"
        + (f"Referenz: {args.reference} – WER = Wortfehlerquote, tiefer ist besser. "
           "Übersetzungsvarianten zählen als Fehler, also nur relativ vergleichen.\n\n" if reference else "")
        + "| Modell | Laden | Rechnen | Echtzeitfaktor | WER | Ergebnis |\n|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    print(f"\nÜbersicht: {report}")
    return 0


def cmd_models(_args) -> int:
    from .transcription.models import RECOMMENDED, builtin_models, converted_models, models_dir

    converted = set(converted_models())
    builtin = set(builtin_models())
    print("Empfohlene Modelle:")
    for model, description in RECOMMENDED:
        if model in builtin:
            status = "eingebaut"
        elif model in converted:
            status = "konvertiert ✓"
        else:
            status = "→ verbalis convert-model"
        print(f"  {model}\n      {description}  [{status}]")
    others = converted - {m for m, _ in RECOMMENDED}
    if others:
        print("\nWeitere konvertierte Modelle:")
        for m in sorted(others):
            print(f"  {m}")
    print(f"\nModellordner: {models_dir()}")
    print("Jedes Whisper-Modell von Hugging Face lässt sich konvertieren und dann per --model nutzen.")
    return 0


def cmd_convert_model(args) -> int:
    from .transcription.models import ModelError, convert

    print(f"Konvertiere {args.model_id} – Download und Umwandlung können einige Minuten dauern …")
    try:
        target = convert(args.model_id, force=args.force)
    except ModelError as e:
        print(e)
        return 1
    print(f"Fertig: {target}\nNutzen mit: --model {args.model_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from .migration import migrate_if_needed
    from .settings import Settings
    from .transcription.models import RECOMMENDED

    if done := migrate_if_needed():
        print(f"Daten aus «Mitschrift» übernommen: {', '.join(done)}\n")

    parser = argparse.ArgumentParser(prog="verbalis", description="Gespräche aufnehmen und transkribieren.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("app", help="Oberfläche starten").set_defaults(func=cmd_app)
    sub.add_parser("devices", help="Mikrofone und Lautsprecher auflisten").set_defaults(func=cmd_devices)

    p = sub.add_parser("record", help="Mikrofon und Systemaudio als zwei Spuren aufnehmen")
    p.add_argument("--microphone", help="Index oder Namensteil (Standard: System-Standard)")
    p.add_argument("--speakers", help="Index oder Namensteil des Ausgabegeräts von Teams")
    p.add_argument("--output-dir", help="Zielordner (Standard: Aufnahmeordner aus den Einstellungen)")
    p.add_argument("--duration", type=float, help="Automatisch nach N Sekunden stoppen")
    p.add_argument("--consent", action="store_true", help="Einwilligung bereits eingeholt (keine Rückfrage)")
    p.set_defaults(func=cmd_record)

    def transcription_options(q):
        q.add_argument("folder", help="Aufnahmeordner mit me- und others-Spur")
        q.add_argument("--name", default="Ich", help="Name für die Mikrofonspur (Standard: Ich)")
        q.add_argument("--others", default="Gegenüber", help="Name für die Systemaudio-Spur")
        q.add_argument("--device", default="cpu", choices=["cpu", "cuda"], help="Rechnen auf CPU oder Nvidia-GPU")
        q.add_argument("--keywords", help="Namen/Fachbegriffe, z.B. \"tocco, Höngg\"")
        q.add_argument("--until", type=float, help="Nur die ersten N Sekunden transkribieren")
        q.add_argument("--beam", type=int, default=5, help="Suchbreite: 5 = genau (Standard), 1 = schneller")

    p = sub.add_parser("transcribe", help="Aufnahme transkribieren")
    transcription_options(p)
    p.add_argument("--model", default=Settings.load().model,
                   help="Modellname, HF-ID oder Ordner (Standard: Modell aus den Einstellungen)")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("compare", help="Mehrere Modelle auf derselben Aufnahme vergleichen")
    transcription_options(p)
    p.add_argument("--models", nargs="+", default=[m for m, _ in RECOMMENDED], help="Zu vergleichende Modelle")
    p.add_argument("--reference", help="Referenztext für die Fehlerquote, z.B. testdata/reference_standard_german.txt")
    p.set_defaults(func=cmd_compare, until=180)  # default: first 3 minutes, 0 = everything

    sub.add_parser("models", help="Empfohlene und konvertierte Modelle anzeigen").set_defaults(func=cmd_models)

    p = sub.add_parser("convert-model", help="Hugging-Face-Whisper-Modell für faster-whisper umwandeln")
    p.add_argument("model_id", help="z.B. Flix-AI/flix-swissgerman-full")
    p.add_argument("--force", action="store_true", help="Neu konvertieren, auch wenn schon vorhanden")
    p.set_defaults(func=cmd_convert_model)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
