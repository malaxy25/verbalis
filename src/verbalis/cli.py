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
    from .evaluation import error_rate, load_reference
    from .pipeline import header
    from .transcript import save
    from .transcription.faster import FasterWhisperTranscriber
    from .transcription.models import ModelError, slug

    folder = Path(args.folder)
    _check_folder(folder)
    names = {"me": args.name, "others": args.others}
    reference = load_reference(args.reference, folder, args.until) if args.reference else None
    per_track = bool(reference and reference.tracks)
    if reference and reference.edited is False:
        print("Achtung: Das Referenz-Transkript wurde nicht korrigiert. Die Fehlerquote zeigt dann nur, "
              "wie ähnlich die Modelle dem Modell sind, das es erstellt hat.\n")
    rows = []

    for model in args.models:
        print(f"\n=== {model} ===")
        t = time.monotonic()
        try:
            tr = FasterWhisperTranscriber(model, device=args.device, keywords=args.keywords, beam_size=args.beam)
        except ModelError as e:
            print(e)
            rows.append(f"| {model} | – | – | – | – |{' – | – |' if per_track else ''} Fehler beim Laden |")
            continue
        load_time = time.monotonic() - t
        paragraphs, compute, duration = _transcribe_folder(folder, tr, names, args.until)
        filename = f"comparison_{slug(model)}"
        save(folder, filename, paragraphs, f"Vergleich: {model}", header(folder, model, compute, duration))
        words = sum(len(p.text.split()) for p in paragraphs)
        wer = "–"
        track_cells = ""
        if reference is not None:
            rate = error_rate(reference.text, " ".join(p.text for p in paragraphs))
            wer = f"{rate.wer:.1%}"
            print(f"  Fehlerquote: {rate}")
            if per_track:
                for track, display in names.items():
                    ref_text = reference.tracks.get(track, "")
                    hyp_text = " ".join(p.text for p in paragraphs if p.speaker == display)
                    cell = f"{error_rate(ref_text, hyp_text).wer:.1%}" if ref_text.strip() else "–"
                    track_cells += f" {cell} |"
                    print(f"  {display}: {cell}")
        rows.append(
            f"| {model} | {load_time:.0f} s | {compute:.0f} s | {compute / max(duration, 1e-9):.2f}× "
            f"| {wer} |{track_cells} [{filename}.md]({filename}.md), {words} Wörter |"
        )
        del tr  # free memory before loading the next model

    report = folder / "comparison.md"
    report.write_text(
        "# Modellvergleich\n\n"
        f"Ausschnitt: {'erste ' + str(int(args.until)) + ' s' if args.until else 'ganze Aufnahme'}\n\n"
        + (f"Referenz: {reference.source} – WER = Wortfehlerquote, tiefer ist besser. "
           "Übersetzungsvarianten zählen als Fehler, also nur relativ vergleichen.\n\n" if reference else "")
        + ("**Achtung:** Das Referenz-Transkript wurde nicht korrigiert.\n\n"
           if reference and reference.edited is False else "")
        + (f"| Modell | Laden | Rechnen | Echtzeitfaktor | WER | WER {args.name} | WER {args.others} | Ergebnis |\n"
           "|---|---|---|---|---|---|---|---|\n" if per_track else
           "| Modell | Laden | Rechnen | Echtzeitfaktor | WER | Ergebnis |\n|---|---|---|---|---|---|\n")
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    print(f"\nÜbersicht: {report}")
    return 0


def cmd_models(_args) -> int:
    from .transcription.models import RECOMMENDED, converted_models, models_dir

    from .transcription.models import SIZE_GB, is_local

    converted = set(converted_models())
    print("Empfohlene Modelle:")
    for model, description in RECOMMENDED:
        try:
            local = is_local(model)
        except Exception:
            local = False
        size = f", ca. {SIZE_GB[model]} GB" if model in SIZE_GB else ""
        status = "auf diesem PC" if local else f"wird bei Bedarf heruntergeladen{size}"
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


def cmd_selftest(_args) -> int:
    """Check that all bundled parts work – used by the release build in CI."""
    import importlib
    import tempfile

    import numpy as np

    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"OK      {name}")
        except Exception as e:  # report every part, don't stop at the first
            print(f"FEHLER  {name}: {e!r}")
            failures.append(name)

    def audio_roundtrip():
        import soundfile as sf

        from .pipeline import audio_file, compress_audio
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            t = np.arange(48000) / 48000
            for track in ("me", "others"):
                sf.write(folder / f"{track}.wav", (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), 48000)
            assert compress_audio(folder) == 2
            data, sr = sf.read(audio_file(folder, "me"))
            assert sr == 16000 and len(data) > 15000

    def silence_filter():
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        assert get_speech_timestamps(np.zeros(32000, dtype=np.float32), VadOptions()) == []

    def model_runtime():
        import ctranslate2
        ctranslate2.get_cuda_device_count()

    def user_interface():
        from .app import ICON, UI
        assert UI.exists() and ICON.exists(), f"{UI} / {ICON} fehlen"

    def window_library():
        importlib.import_module("webview")

    def audio_devices_library():
        if sys.platform == "win32":  # on Linux it needs a running PulseAudio
            importlib.import_module("soundcard")

    check("Audio komprimieren und lesen", audio_roundtrip)
    check("Stillefilter (Silero VAD)", silence_filter)
    check("Modell-Laufzeit (CTranslate2)", model_runtime)
    check("Oberfläche (index.html, Icon)", user_interface)
    check("Fenster (pywebview)", window_library)
    check("Audiogeräte (soundcard)", audio_devices_library)
    check("Rechtschreibung (spylls)", lambda: importlib.import_module("spylls.hunspell"))

    def release_notes():
        from .updates import changelog_path, changes_between
        assert changelog_path() is not None, "CHANGELOG.md fehlt"
        assert changes_between("0.0.0"), "keine Abschnitte im CHANGELOG"

    check("Versionshinweise (CHANGELOG)", release_notes)
    print("\nAlles in Ordnung." if not failures else f"\n{len(failures)} Teil(e) fehlerhaft.")
    return 1 if failures else 0


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
    p.add_argument("--reference", help="Referenz für die Fehlerquote: «transcript» (das in der App korrigierte "
                                        "Transkript der Aufnahme), eine transcript.json oder ein Text wie "
                                        "testdata/reference_standard_german.txt")
    p.set_defaults(func=cmd_compare, until=180)  # default: first 3 minutes, 0 = everything

    sub.add_parser("models", help="Empfohlene und konvertierte Modelle anzeigen").set_defaults(func=cmd_models)

    sub.add_parser("selftest", help=argparse.SUPPRESS).set_defaults(func=cmd_selftest)

    p = sub.add_parser("convert-model", help="Hugging-Face-Whisper-Modell für faster-whisper umwandeln")
    p.add_argument("model_id", help="z.B. Flix-AI/flix-swissgerman-full")
    p.add_argument("--force", action="store_true", help="Neu konvertieren, auch wenn schon vorhanden")
    p.set_defaults(func=cmd_convert_model)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
