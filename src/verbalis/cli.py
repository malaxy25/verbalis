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
import subprocess
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
    n = 1
    while folder.exists():              # never write into an existing recording
        n += 1
        folder = base / f"{start:%Y-%m-%d_%H%M%S}_{n}"

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
            tracks = {s.name: s for s in rec.status()}
            me, others = tracks["me"], tracks.get("others", tracks["me"])
            mm, ss = divmod(int(elapsed), 60)
            sys.stdout.write(
                f"\r● {mm:02d}:{ss:02d}   Mikrofon {_level_bar(me.level_rms)}"
                f"   Systemton {_level_bar(others.level_rms)}  "
            )
            sys.stdout.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        ended = rec.stop()
    print("\n")

    from .pipeline import COMPLETE, INCOMPLETE, STOP_TIMEOUT
    state = COMPLETE if ended and not rec.errors else (STOP_TIMEOUT if not ended else INCOMPLETE)
    problem = None if state == COMPLETE else (
        "Eine Spur liess sich nicht rechtzeitig beenden." if not ended
        else "Gerätefehler: " + "; ".join(str(e) or type(e).__name__ for e in rec.errors))
    meta = write_meta(
        folder, start, rec.active_seconds(), rec.samplerate, consent_time,
        {"me": devices.microphone.name, "others": devices.loopback.name}, rec.status(), state, problem,
    )
    if problem:
        print(f"Achtung: {problem} Das Audio bis dahin ist gesichert.")
        return 2
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


def cmd_audio_test(args) -> int:
    """Open the microphone and the others' audio one after the other and report what arrives.

    Prints only numbers – nothing is recorded or saved. For devices that deliver nothing
    (e.g. the first tests on a Mac).
    """
    import threading

    from .audio import devices
    from .audio.recorder import SAMPLERATE, MeterTrack
    from .service import _db

    try:
        selection = devices.select(args.microphone, args.speakers)
    except Exception as e:
        print(f"Geräte konnten nicht gewählt werden: {e}")
        return 1
    problems = 0
    for track, label, device in (("me", "Mikrofon", selection.microphone),
                                 ("others", "Systemton", selection.loopback)):
        print(f"{label}: «{getattr(device, 'name', '?')}» – {args.seconds:.0f} s lang lesen …")
        stop = threading.Event()
        meter = MeterTrack(track, device, stop)
        started = time.monotonic()
        meter.start()
        loudest = -90.0
        while time.monotonic() - started < args.seconds and (meter.is_alive() or not meter.status.error):
            time.sleep(0.1)
            loudest = max(loudest, _db(meter.status.level_rms))
            if not meter.is_alive():
                break
        stop.set()
        meter.join(3)
        seconds = meter.status.written_frames / SAMPLERATE
        if meter.status.error:
            result = f"FEHLER: {meter.status.error}"
        elif seconds == 0:
            result = "KEINE DATEN – das Gerät liefert nichts (Berechtigung oder Gerät prüfen)"
        else:
            result = f"OK – {seconds:.1f} s Audio erhalten, lautester Pegel {loudest:.0f} dB"
            if loudest <= -89:
                result += " (nur Stille)"
        if meter.is_alive():
            result += "; hängt beim Beenden"
        problems += result.startswith(("FEHLER", "KEINE")) or meter.is_alive()
        print(f"  {result}\n")
    print("Alles in Ordnung." if not problems else f"{problems} Gerät(e) mit Problemen.")
    return 1 if problems else 0


def cmd_speakers_test(args) -> int:
    """How many speakers diarization finds per threshold – only numbers, no content (to tune THRESHOLD)."""
    from . import diarization
    from .pipeline import audio_file
    from .transcription.faster import WHISPER_SAMPLERATE, load_audio

    folder = Path(args.folder)
    path = audio_file(folder, args.track)
    if path is None:
        print(f"In {folder} gibt es keine Audiodatei für die Spur «{args.track}».")
        return 1
    audio = load_audio(path, args.until)
    diarization.ensure_models()
    print(f"Spur «{args.track}»: {len(audio) / WHISPER_SAMPLERATE / 60:.1f} min Audio. "
          "Es werden nur Zahlen ausgegeben, kein Inhalt.\n")
    embed = None
    for threshold in args.thresholds:
        raw = diarization.find_turns(audio, threshold=threshold, refine_turns=False)
        refined = raw
        if len({t[2] for t in raw}) > 1:
            embed = embed or diarization.embedder(audio)
            refined = diarization.refine(raw, embed)
        talk: dict[int, float] = {}
        for start, end, speaker in refined:
            talk[speaker] = talk.get(speaker, 0.0) + end - start
        times = sorted(talk.values(), reverse=True)
        shown = ", ".join(_minutes(t) for t in times[:12]) + (" …" if len(times) > 12 else "")
        print(f"Schwelle {threshold:.2f}: {len({t[2] for t in raw}):3d} Sprecher roh, {len(times):3d} bereinigt"
              f" – Redezeit: {shown}")
    print(f"\nAktuell eingestellt: Schwelle {diarization.THRESHOLD:.2f}. Höher = weniger Sprecher.")
    return 0


def _minutes(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


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
    from .evaluation import combined, error_rate, load_reference
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
            if per_track:
                # overall rate from the tracks: the merged order of overlapping speech would count as errors
                rates, lines = [], []
                for track, display in names.items():
                    ref_text = reference.tracks.get(track, "")
                    hyp_text = " ".join(p.text for p in paragraphs
                                        if (p.track == track if p.track else p.speaker == display))
                    track_rate = error_rate(ref_text, hyp_text) if ref_text.strip() else None
                    cell = f"{track_rate.wer:.1%}" if track_rate else "–"
                    if track_rate:
                        rates.append(track_rate)
                    track_cells += f" {cell} |"
                    lines.append(f"  {display}: {cell}")
                rate = combined(rates)
            else:
                rate = error_rate(reference.text, " ".join(p.text for p in paragraphs))
                lines = []
            wer = f"{rate.wer:.1%}"
            print(f"  Fehlerquote: {rate}")
            for line in lines:
                print(line)
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
        if sys.platform in ("win32", "darwin"):  # on Linux it needs a running PulseAudio
            from .audio.devices import soundcard_module
            soundcard_module()   # Verbalis' own entry point, not just the import (0.7.19 failed on macOS there)

    check("Audio komprimieren und lesen", audio_roundtrip)
    check("Stillefilter (Silero VAD)", silence_filter)
    check("Modell-Laufzeit (CTranslate2)", model_runtime)
    check("Oberfläche (index.html, Icon)", user_interface)
    check("Fenster (pywebview)", window_library)
    check("Audiogeräte (soundcard)", audio_devices_library)

    def certificates():
        import os
        if sys.platform == "darwin":   # see verbalis/__init__.py: the Mac app's Python has no certificates
            path = os.environ.get("SSL_CERT_FILE", "")
            assert path and os.path.exists(path), f"Zertifikatsliste fehlt ({path or 'SSL_CERT_FILE leer'})"

    check("Zertifikate für HTTPS", certificates)
    check("Rechtschreibung (spylls)", lambda: importlib.import_module("spylls.hunspell"))

    def system_audio_helper():
        from .audio.mac_tap import helper_path
        helper = helper_path()
        assert helper is not None, "verbalis-audiotap fehlt"
        out = subprocess.run([str(helper), "--version"], capture_output=True, text=True, timeout=10)
        assert out.returncode == 0 and "verbalis-audiotap" in out.stdout, out.stderr

    if sys.platform == "darwin":
        check("Systemton-Hilfsprogramm (macOS)", system_audio_helper)

    def speaker_diarization():
        """Both ONNX runtimes in one process, in the app's order: silence filter first, then diarization.

        With VERBALIS_SELFTEST_DIARIZATION=1 (set in the release workflow) the real models are
        downloaded and run – this catches a clash between faster-whisper's onnxruntime and the
        one bundled with sherpa-onnx on Windows before anybody installs the release.
        """
        import os

        import numpy as np
        importlib.import_module("sherpa_onnx")
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        from . import diarization

        noise = np.random.default_rng(0).normal(0, 0.05, 16_000 * 5).astype(np.float32)
        get_speech_timestamps(noise, VadOptions())
        if os.environ.get("VERBALIS_SELFTEST_DIARIZATION") == "1":
            import soundfile as sf

            diarization.ensure_models()
            diarization.find_turns(noise)
            with tempfile.TemporaryDirectory() as tmp:   # also in its own process, as the app runs it
                sf.write(Path(tmp) / "others.wav", noise, 16_000)
                diarization.turns_for_file(Path(tmp) / "others.wav")

    check("Sprechererkennung (sherpa-onnx)", speaker_diarization)

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

    p = sub.add_parser("audio-test", help="Prüfen, ob Mikrofon und Systemton Audio liefern (nichts wird gespeichert)")
    p.add_argument("--microphone", help="Mikrofon (Namensteil), Standard: wie in der App")
    p.add_argument("--speakers", help="Systemton: Ausgabegerät (Namensteil), Standard: wie in der App")
    p.add_argument("--seconds", type=float, default=4.0, help="Wie lange pro Gerät (Standard: 4)")
    p.set_defaults(func=cmd_audio_test)

    p = sub.add_parser("speakers-test", help="Sprechererkennung mit verschiedenen Schwellen testen (nur Zahlen)")
    p.add_argument("folder", help="Aufnahmeordner")
    p.add_argument("--track", default="others", choices=["me", "others"], help="Spur (Standard: others)")
    p.add_argument("--thresholds", nargs="+", type=float, default=[0.6, 0.7, 0.8, 0.9],
                   help="Schwellen zum Vergleichen (Standard: 0.6 0.7 0.8 0.9)")
    p.add_argument("--until", type=float, help="Nur die ersten N Sekunden")
    p.set_defaults(func=cmd_speakers_test)

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
