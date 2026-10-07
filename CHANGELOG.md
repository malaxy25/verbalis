# Changelog

## 0.6.0 – 2026-10-07
- Audio wird nach der Aufnahme auf 16 kHz FLAC komprimiert (verlustfrei, rund 85 % kleiner,
  eine Stunde ≈ 100 MB statt ≈ 700 MB); auch alte WAV-Aufnahmen werden nachträglich umgewandelt
- Aufbewahrung in den Einstellungen: Audio nach N Tagen löschen (Standard 3) und/oder höchstens
  N MB insgesamt (älteste zuerst). Transkripte bleiben immer, Aufnahmen ohne Transkript sind geschützt.
- Aufräumen beim Start, nach jeder Transkription und stündlich
- Transkriptansicht zeigt Grösse und Löschtermin des Audios, Knopf «Audio löschen»
- Ohne Audio kein «Neu transkribieren» mehr

## 0.5.1 – 2026-10-07
- Fenster öffnet nie höher als der Bildschirm (berücksichtigt Skalierung, Taskleiste und Titelleiste)
- Zuletzt genutzte Fenstergrösse wird gemerkt

## 0.5.0 – 2026-10-07
- Transkript direkt in der App korrigieren (Absatz anklicken); die unbearbeitete Fassung bleibt als
  `transkript_original.json` erhalten
- Korrekturliste: Aus Korrekturen entstehen Vorschläge (z.B. «Toko» → «tocco»), die man gezielt merkt.
  Ziel eindeutig, Varianten gesammelt. Wird nach jeder Transkription angewendet, die Ziele fliessen
  zusätzlich als Stichworte ins Modell. Verwaltung in den Einstellungen.
- «Neu transkribieren» bei korrigierten Transkripten erst nach Bestätigung
- Start per Doppelklick: `mitschrift-app.exe` ohne Konsolenfenster, Skript
  `werkzeuge/verknuepfung-erstellen.ps1` für Desktop und Startmenü, eigenes Icon
- Fehlerprotokoll in `~/.mitschrift/protokoll.txt`; App lässt sich unter Windows nur einmal öffnen

## 0.4.0 – 2026-10-07
- Transkription pausieren und fortsetzen (hält nach dem nächsten Textabschnitt an)
- Automatische Pause, solange eine Aufnahme läuft – die CPU bleibt frei für den Call
- Restdauer: anfangs aus dem Tempo früherer Transkriptionen geschätzt, danach aus dem Fortschritt
- Pausen zählen nicht mehr zur ausgewiesenen Rechenzeit
- Einstellungen: echte Auswahlliste für Modelle, eigenes Modell über «Anderes Modell …»

## 0.3.0 – 2026-10-07
- Oberfläche (`mitschrift app`): Aufnahme mit Pegelspuren, Zustimmung pro Aufnahme,
  automatische Transkription im Hintergrund, Verlauf, Transkriptansicht, Einstellungen
- Einstellungen in `~/.mitschrift/einstellungen.json`; Standardmodell Flix-AI/flix-swissgerman-full
- Aufnahmen standardmässig in `~/.mitschrift/aufnahmen` (auch für die Kommandozeile)
- Tempo wählbar: `--beam` bzw. «Genau/Schnell» in den Einstellungen
- Zurückgezogenes Modell nizarmichaud/… aus der Empfehlungsliste entfernt
- Konvertierung prüft vorab, ob das Repo Gewichte enthält (verständliche Meldung statt Traceback)
- Hinweise von Hugging Face (Symlinks, Info-Meldungen) ausgeblendet

## 0.2.1 – 2026-10-07
- Vorlesetext auf Züritüütsch und hochdeutsche Referenz in `testdaten/`
- `vergleichen --referenz`: Wortfehlerquote (WER) pro Modell
- Changelog eingeführt

## 0.2.0 – 2026-10-07
- Transkription mit faster-whisper, Stillefilter gegen Halluzinationen
- Spuren zu Gesprächsverlauf zusammenführen (Markdown + JSON)
- Modellvergleich, Modellübersicht, Konvertierung von Hugging-Face-Modellen
- Audio direkt mit soundfile laden (PyAV 19 ist inkompatibel mit faster-whisper)
- GitHub Action (Windows/Ubuntu), MIT-Lizenz, `.gitattributes`

## 0.1.0 – 2026-10-07
- Zwei-Spur-Aufnahme: Mikrofon und Systemaudio (Loopback), synchron
- Kommandozeile `geraete` und `aufnehmen` mit Pegelanzeige und Einwilligung
