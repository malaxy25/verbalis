# Mitschrift

Lokale App, die Gespräche aufnimmt (eigenes Mikrofon **und** Systemaudio, also
alle Teilnehmenden eines Teams-Calls) und danach ein Transkript erstellt –
Hochdeutsch und Schweizerdeutsch. Alles läuft lokal, nichts verlässt den Rechner.

**Stand: Schritt 1 – Aufnahme-Spike.** Zwei Spuren werden synchron als WAV gespeichert.

## Architektur (Ziel)

```
Frontend (HTML/JS in pywebview-Fenster)
        │  lokale API (FastAPI)
Backend (Python)
 ├─ audio/          Aufnahme: Mikrofon + Loopback als zwei Spuren   ← jetzt
 ├─ transcription/  austauschbare Backends (faster-whisper, transformers, …)
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

## Testplan für den Spike

1. `mitschrift geraete` – erscheinen Headset und Lautsprecher?
2. Kurzer Test ohne Teams: YouTube-Video abspielen und reden. Bewegen sich beide Pegel?
3. Echter Teams-Call (mit Einwilligung!), 2–3 Minuten:
   - Beide Spuren in Audacity nebeneinander öffnen: Ist die Gegenüber-Spur gut verständlich?
   - Sind die Spuren synchron? (Wer auf wen antwortet, sollte zeitlich passen.)
   - Ohne Headset: Wie stark hört man die anderen auch auf `ich.wav` (Echo)?
4. Dasselbe unter Ubuntu.
5. `aufgefuellte_stille_s` in `meta.json` anschauen: Sollte bei 0 oder sehr klein sein.

## Rechtliches

Gespräche ohne Einwilligung aller Teilnehmenden aufzunehmen, ist in der
Schweiz strafbar (StGB Art. 179ter). Die App fragt deshalb vor jeder Aufnahme
nach der Einwilligung und vermerkt sie in `meta.json`. Aufnahmen enthalten
Personendaten und sind über `.gitignore` vom Repo ausgeschlossen.

## Tests

```bash
pytest
```
