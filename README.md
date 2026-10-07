# Mitschrift

[![Tests](https://github.com/malaxy25/mitschrift/actions/workflows/tests.yml/badge.svg)](https://github.com/malaxy25/mitschrift/actions/workflows/tests.yml)

Lokale App, die Gespräche aufnimmt (eigenes Mikrofon **und** Systemaudio, also
alle Teilnehmenden eines Teams-Calls) und danach ein Transkript erstellt –
Hochdeutsch und Schweizerdeutsch. Alles läuft lokal, nichts verlässt den Rechner.

**Stand: Schritt 2 – Aufnahme und Transkription** per Kommandozeile. Noch ohne Oberfläche und Sprechererkennung.

## Architektur (Ziel)

```
Frontend (HTML/JS in pywebview-Fenster)
        │  lokale API (FastAPI)
Backend (Python)
 ├─ audio/          Aufnahme: Mikrofon + Loopback als zwei Spuren   ✓
 ├─ transcription/  austauschbare Backends (faster-whisper)          ✓
 ├─ transkript.py   Spuren zusammenführen, Markdown/JSON            ✓
 └─ diarization/    Sprechererkennung (pyannote), Namen vergeben
```

Die zwei Spuren sind bewusst getrennt: `ich.wav` (Mikrofon) und
`gegenueber.wav` (Systemaudio). Damit ist «Ich vs. die anderen» ohne
Sprechererkennung klar, und pyannote muss nur noch die Remote-Teilnehmenden
auseinanderhalten.

## Einrichtung

Python 3.11 oder neuer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Ubuntu:   source .venv/bin/activate
pip install -e ".[dev]"
```

Ubuntu: Es braucht PipeWire mit `pipewire-pulse` (Standard bei Ubuntu) bzw.
`libpulse0`. Windows: nichts Zusätzliches.

## Bedienung

```bash
mitschrift geraete                       # Mikrofone und Lautsprecher anzeigen
mitschrift aufnehmen                     # Standardgeräte, Ctrl+C beendet
mitschrift aufnehmen --lautsprecher jabra --mikrofon jabra
mitschrift aufnehmen --dauer 30          # Testaufnahme 30 s
```

Ergebnis in `aufnahmen/JJJJ-MM-TT_HHMMSS/`: `ich.wav`, `gegenueber.wav`, `meta.json`.

**Wichtig:** Als `--lautsprecher` das Gerät wählen, auf dem Teams den Ton
ausgibt (Teams → Einstellungen → Geräte). Ist das nicht das Standardgerät,
bleibt die Gegenüber-Spur sonst stumm.

## Transkription

```bash
mitschrift transkribieren aufnahmen/2026-10-07_143000 --name Andrea
mitschrift transkribieren … --modell large-v3 --stichworte "tocco, Höngg"
```

Ergebnis: `transkript.md` (lesbar) und `transkript.json` (für die spätere App)
im Aufnahmeordner. Standardmodell ist `large-v3-turbo`, gerechnet wird auf der CPU.

## Modelle vergleichen

```bash
mitschrift modelle                                   # Übersicht mit Status
pip install -e ".[konvertieren]"                     # einmalig, gross (torch)
mitschrift modell-konvertieren Flix-AI/flix-swissgerman-full
mitschrift modell-konvertieren nizarmichaud/whisper-large-v3-turbo-swissgerman
mitschrift vergleichen aufnahmen/2026-10-07_143000   # erste 3 min, alle empfohlenen
```

`vergleich.md` zeigt Lade- und Rechenzeit pro Modell, daneben liegt pro Modell
ein `vergleich_<modell>.md` zum Lesen. `--bis 0` vergleicht die ganze Aufnahme.

Jedes Whisper-Modell von Hugging Face lässt sich so konvertieren und danach mit
`--modell <hf-id>` nutzen. Konvertierte Modelle liegen in `~/.mitschrift/modelle/`
(änderbar über die Umgebungsvariable `MITSCHRIFT_HOME`).

Hinweis: Alle Modelle schreiben Schweizerdeutsch als **Hochdeutsch** auf.
Das ist für Protokolle meist gewünscht, aber es ist eine Übersetzung, kein Wortlaut.

## Testplan Aufnahme

1. `mitschrift geraete` – erscheinen Headset und Lautsprecher?
2. Kurzer Test ohne Teams: YouTube-Video abspielen und reden. Bewegen sich beide Pegel?
3. Echter Teams-Call (mit Einwilligung!), 2–3 Minuten:
   - Beide Spuren in Audacity nebeneinander öffnen: Ist die Gegenüber-Spur gut verständlich?
   - Sind die Spuren synchron? (Wer auf wen antwortet, sollte zeitlich passen.)
   - Ohne Headset: Wie stark hört man die anderen auch auf `ich.wav` (Echo)?
4. Dasselbe unter Ubuntu.
5. `aufgefuellte_stille_s` in `meta.json` anschauen: Sollte bei 0 oder sehr klein sein.

## Testplan Transkription

1. `mitschrift transkribieren` auf einer kurzen Aufnahme: Stimmt die Reihenfolge Ich/Gegenüber?
2. `mitschrift vergleichen` auf einem Call mit viel Schweizerdeutsch.
3. Pro Modell beurteilen: Inhalt richtig? Namen und Fachbegriffe? Erfundene Sätze in Pausen?
4. Echtzeitfaktor notieren: 0.5× heisst, eine Stunde Call braucht 30 Minuten.

## Rechtliches

Gespräche ohne Einwilligung aller Teilnehmenden aufzunehmen, ist in der
Schweiz strafbar (StGB Art. 179ter). Die App fragt deshalb vor jeder Aufnahme
nach der Einwilligung und vermerkt sie in `meta.json`. Aufnahmen enthalten
Personendaten und sind über `.gitignore` vom Repo ausgeschlossen (Ordner `aufnahmen/`, alle `.wav` sowie Transkripte).

## Tests

```bash
pytest
```
