# Mitschrift

[![Tests](https://github.com/malaxy25/mitschrift/actions/workflows/tests.yml/badge.svg)](https://github.com/malaxy25/mitschrift/actions/workflows/tests.yml)

Lokale App, die Gespräche aufnimmt (eigenes Mikrofon **und** Systemaudio, also
alle Teilnehmenden eines Teams-Calls) und danach ein Transkript erstellt –
Hochdeutsch und Schweizerdeutsch. Alles läuft lokal, nichts verlässt den Rechner.

**Stand 0.6.0:** Oberfläche für Aufnahme, Transkription und Verlauf. Sprechererkennung folgt.

```bash
mitschrift app
```

## Architektur (Ziel)

```
Oberfläche (HTML/JS in pywebview-Fenster)      app.py, ui/index.html   ✓
        │  JavaScript ruft Python direkt auf
Dienst: Aufnahme, Warteschlange, Verlauf        dienst.py               ✓
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

## Start per Doppelklick (Windows)

Einmalig im Repo ausführen, mit aktivierter `.venv`:

```powershell
pip install -e ".[dev]"
.\werkzeuge\verknuepfung-erstellen.ps1
```

Danach gibt es «Mitschrift» auf dem Desktop und im Startmenü. Die Verknüpfung
startet `.venv\Scripts\mitschrift-app.exe` ohne Konsolenfenster und zeigt auf
das Repo – Updates wirken sofort. Fehler landen in `~/.mitschrift/protokoll.txt`.

## Oberfläche

`mitschrift app` oder die Verknüpfung öffnet das Fenster:

- **Aufnahme:** Mikrofon und Tonausgabe von Teams wählen, Zustimmung aller
  Teilnehmenden bestätigen, mit dem roten Knopf starten und beenden.
- **Transkript:** entsteht nach dem Beenden automatisch im Hintergrund.
  Fortschritt und Restdauer in der Ansicht, Status in der Liste links. Das
  Modell bleibt geladen, die zweite Transkription startet deshalb schneller.
- **Pausieren:** Transkriptionen lassen sich pausieren und fortsetzen. Während
  einer Aufnahme pausieren sie automatisch, damit die CPU frei bleibt.
- **Korrigieren:** Absatz im Transkript anklicken, ändern, speichern. Die App
  schlägt die geänderten Wörter für die Korrekturliste vor (z.B. «Toko» →
  «tocco»); angehakte Vorschläge gelten ab dann für alle Transkripte.
- **Audio aufbewahren:** Nach der Aufnahme wird das Audio verlustfrei auf
  16 kHz FLAC komprimiert (eine Stunde ≈ 100 MB). Es wird nach einer Frist
  (Standard 3 Tage) und/oder über einer Speichergrenze automatisch gelöscht,
  älteste zuerst. Transkripte bleiben, Aufnahmen ohne Transkript sind geschützt.
- **Einstellungen:** dein Name, Bezeichnung der anderen, Modell, Tempo
  (genau/schnell), Stichworte, Korrekturliste, Audio-Aufbewahrung und Aufnahmeordner.

Aufnahmen landen standardmässig in `~/.mitschrift/aufnahmen` (änderbar in den
Einstellungen) – App und Kommandozeile nutzen denselben Ordner.

Unter Ubuntu braucht pywebview zusätzlich GTK oder Qt, z.B.
`sudo apt install python3-gi gir1.2-webkit2-4.1` oder `pip install pywebview[qt]`.

## Kommandozeile

```bash
mitschrift geraete                       # Mikrofone und Lautsprecher anzeigen
mitschrift aufnehmen                     # Standardgeräte, Ctrl+C beendet
mitschrift aufnehmen --lautsprecher jabra --mikrofon jabra
mitschrift aufnehmen --dauer 30          # Testaufnahme 30 s
```

Ergebnis in `~/.mitschrift/aufnahmen/JJJJ-MM-TT_HHMMSS/`: `ich.flac`, `gegenueber.flac`, `meta.json`.
Während der Aufnahme wird als WAV geschrieben (absturzsicher), danach komprimiert.

**Wichtig:** Als `--lautsprecher` das Gerät wählen, auf dem Teams den Ton
ausgibt (Teams → Einstellungen → Geräte). Ist das nicht das Standardgerät,
bleibt die Gegenüber-Spur sonst stumm.

## Transkription

```bash
mitschrift transkribieren aufnahmen/2026-10-07_143000 --name Andrea
mitschrift transkribieren … --modell large-v3 --stichworte "tocco, Höngg"
```

Ergebnis: `transkript.md` (lesbar) und `transkript.json` (für die spätere App)
im Aufnahmeordner. Standardmodell ist das aus den Einstellungen (Flix), gerechnet wird auf der CPU.
`--beam 1` ist etwa doppelt so schnell, aber etwas ungenauer.

## Modelle vergleichen

```bash
mitschrift modelle                                   # Übersicht mit Status
pip install -e ".[konvertieren]"                     # einmalig, gross (torch)
mitschrift modell-konvertieren Flix-AI/flix-swissgerman-full
mitschrift vergleichen aufnahmen/2026-10-07_143000   # erste 3 min, alle empfohlenen
```

Mit Referenztext berechnet `vergleichen` zusätzlich die Wortfehlerquote (WER):

```bash
mitschrift vergleichen aufnahmen/… --referenz testdaten/referenz_hochdeutsch.txt
```

Der passende Vorlesetext liegt in `testdaten/vorlesetext_zuerich.md`. Weil die
Modelle Schweizerdeutsch übersetzen, zählen auch korrekte Umformulierungen als
Fehler – die WER eignet sich zum Vergleichen der Modelle, nicht als absolute Note.

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
