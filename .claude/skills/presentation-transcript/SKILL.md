---
name: presentation-transcript
description: Präsentationsprotokoll aus Verbalis-Transkript + Teams-Video (+ PowerPoint) – pro Folie, was gezeigt und was gesagt wurde, mit Bildern. Nur auf Aufruf von Andrea.
disable-model-invocation: true
argument-hint: <Aufnahme-ID oder -Ordner> <Teams-Video.mp4> [<Präsentation.pptx>]
---

# /presentation-transcript – Präsentation als Protokoll

Ergebnis: ein Markdown-Dokument, das sich wie eine gute Mitschrift liest – pro Folie bzw. Vorführung das Bild,
die Kernaussagen, was mündlich dazukam, Fragen und Antworten. Für Leute, die nicht dabei waren, und zum
Nachschlagen. Kein Wortprotokoll.

## Eingaben

Aus den Argumenten; fehlt etwas, kurz nachfragen (nicht raten):

1. **Verbalis-Aufnahme** – ID (`2026-10-28_100000`) oder Ordner unter `~\.verbalis\recordings\`. Muss
   transkribiert sein; Sprecher idealerweise benannt. **Datenschutz:** Nur diesen einen Ordner lesen, den Andrea
   genannt hat – keine anderen Aufnahmen öffnen (siehe CLAUDE.md).
2. **Teams-Video** (MP4) – liefert, wann welche Folie zu sehen war. Optional, aber ohne Video ist die Zuordnung
   nur inhaltlich (siehe unten).
3. **PowerPoint** (.pptx) – liefert sauberen Folientext und Sprechernotizen. Optional.

## Ablauf

1. **Vorbereiten** (aus dem Repo, mit der venv):
   ```
   .venv\Scripts\python tools\presentation.py <Aufnahmeordner> --video <mp4> --pptx <pptx>
   ```
   Schreibt nach `<Aufnahmeordner>\presentation\`: `scene_NNN.png` (ein Bild pro Szene), `overview_NN.png`
   (12 Szenen pro Bild, 4 × 3 zeilenweise), `slides.json`, `timeline.md` (pro Szene das Gesagte),
   `scenes.json` (inkl. Zeitversatz). Dauert bei einer Stunde Video einige Minuten.
   - **Versatz prüfen:** Das Skript meldet «Versatz … (Übereinstimmung x)». Unter 0.3 ist er unsicher: an einer
     Stelle prüfen, ob das Gesagte zum Bild passt (z. B. «nächste Folie» kurz vor einem Szenenwechsel); sonst
     `--offset <Sekunden>` von Hand setzen und neu laufen lassen.
   - **Zu viele / zu wenige Szenen:** `--threshold` (Standard 0.12) höher = weniger Szenen, tiefer = mehr.
2. **Szenen den Folien zuordnen:** die `overview_*.png` ansehen und mit `slides.json` vergleichen; nur bei
   Unklarheit das einzelne `scene_NNN.png` öffnen. Jede Szene ist eines von:
   - **Folie N** (Folientext stimmt überein; Animationsschritte derselben Folie zusammenfassen),
   - **Vorführung** (Anwendung, Browser, Code – kurz beschreiben, was zu sehen ist),
   - **Sonstiges** (nur Kameras, Desktop, Pause) – weglassen, Gesagtes der Nachbarszene zuschlagen.
   Mehrere Szenen hintereinander mit derselben Folie werden ein Abschnitt; eine Folie, die später nochmals
   gezeigt wird, bekommt einen zweiten Abschnitt («Folie 4 – nochmals»).
3. **Ohne Video:** Folien rein inhaltlich zuordnen (Folientext ↔ Transkript, in Reihenfolge der Präsentation);
   im Dokument vermerken «Zuordnung ohne Video – Folienwechsel geschätzt».
4. **Protokoll schreiben** nach der Vorlage unten, nach `<Aufnahmeordner>\presentation\presentation.md`.
   Bilder relativ einbinden (`![Folie 3](scene_007.png)`), damit der Ordner als Ganzes weitergegeben werden kann.
5. **Melden** (max. 8 Zeilen): Pfad, Anzahl Abschnitte, Versatz und wie sicher, was unsicher blieb.

## Regeln für den Text

- Deutsch, Schweizer Schreibweise (immer «ss», nie «ß»), kein Komma vor «und».
- **Folie und Gesagtes zusammenführen, nicht doppeln:** Was auf der Folie steht, nur kurz; Gewicht auf das, was
  mündlich erklärt, ergänzt oder relativiert wurde.
- **Nichts erfinden.** Unklares im Transkript (Erkennungsfehler, abgebrochene Sätze) sinngemäss glätten, aber
  nichts dazudichten; Unsicheres mit 🔶 markieren. Fachbegriffe und Namen wie auf den Folien schreiben.
- **Fragen aus dem Publikum** mit Fragesteller und Antwort festhalten; offen gebliebene als offen markieren.
- **Aufgaben / Abmachungen** nur, wenn sie wirklich vereinbart wurden – am Schluss sammeln.
- Smalltalk, Technikprobleme («hört ihr mich?»), Privates weglassen.
- Zeiten als Video-Zeit `h:mm:ss`, damit man im Teams-Video nachspringen kann.

## Vorlage

```markdown
# <Titel der Präsentation>

**Datum:** <TT.MM.JJJJ> · **Präsentiert von:** <Name> · **Teilnehmende:** <Namen>
**Quellen:** Verbalis-Transkript, Teams-Aufzeichnung<, PowerPoint «<Dateiname>»>

## Überblick
<3–5 Sätze: worum es ging, wichtigste Aussagen, Ergebnis>

## Folie 1 – <Folientitel> (0:00:00)
![Folie 1](scene_001.png)

- <Kernaussage>
- <was mündlich dazukam>

> **Frage (<Name>):** <Frage>
> **Antwort (<Name>):** <Antwort>

## Vorführung – <was gezeigt wurde> (0:12:40)
![Vorführung](scene_014.png)

<Schritte bzw. was zu sehen war, knapp>

## Offene Fragen und Aufgaben
- **Aufgabe:** <…> *(Verantwortlich · Termin)*
- **Offen:** <…>
```
