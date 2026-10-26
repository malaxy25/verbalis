---
name: start
description: Sessionbeginn - zeigt den gespeicherten Stand, was offen ist und wo wir anfangen (Gegenstück zu /shutdown). Nur auf Aufruf von Andrea.
disable-model-invocation: true
---

# /start – Wo stehen wir?

Nur lesen und vorschlagen, nichts ändern, bis Andrea den Einstieg freigibt.

## Ablauf

1. **`BACKLOG.md`** im Projekt lesen: Abschnitt «Stand» und die offenen Punkte. Verweist er auf
   Detaildokumente (z. B. `auftraege/<name>/auftrag.md`), deren offene Punkte dort lesen.
   Fehlt `BACKLOG.md`: sagen und anbieten, es mit `/shutdown`-Vorlage aus Git-Log, TODOs und Doku anzulegen.
2. **Git:** Branch, `git status --short`, ungepushte Commits (`git log @{u}..` – ohne Upstream: sagen),
   die letzten 5 Commits.
3. **Startcheck** aus dem Backlog ausführen, wenn er nur liest (z. B. `py -3 fusion.py ping`).
   Schlägt er fehl: sagen, was Andrea starten muss.
4. **Melden**, kurz (max. ca. 15 Zeilen):
   - **Stand:** 1–2 Zeilen
   - **Offen:** die wichtigsten Punkte nach Prio, mit Verweis
   - **Vorschlag:** womit wir anfangen und warum (ein klarer Vorschlag, keine Liste von Optionen)
   - **Fragen an Andrea** aus dem Backlog, falls noch offen
   - **Achtung:** uncommittete Änderungen, ungepushte Commits, fehlgeschlagener Startcheck
5. Auf Andreas Antwort warten.
