# Changelog

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
