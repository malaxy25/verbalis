---
name: start
description: Sessionbeginn - zeigt den gespeicherten Stand, was offen ist und wo wir anfangen (Gegenstück zu /shutdown). Nur auf Aufruf von Andrea.
disable-model-invocation: true
---

# /start – Wo stehen wir?

Nur lesen und vorschlagen, nichts ändern, bis Andrea den Einstieg freigibt – einzige Ausnahme:
der Fast-Forward-Pull in Schritt 1.

## Ablauf

1. **Pull zuerst** (auf einem anderen Rechner kann weitergearbeitet worden sein): `git fetch`, dann
   - Arbeitsverzeichnis sauber und nur hinter `@{u}` → `git pull --ff-only`, Anzahl geholter Commits melden.
   - Uncommittete Änderungen oder Branch weicht ab (ahead *und* behind) → **nicht** pullen, kein Merge/Rebase,
     unter «Achtung» melden und Andrea fragen.
   - Kein Upstream oder `fetch` schlägt fehl (offline) → sagen und mit dem lokalen Stand weitermachen.
   Erst danach das Backlog lesen, sonst ist der Stand veraltet.
2. **`BACKLOG.md`** im Projekt lesen: Abschnitt «Stand» und die offenen Punkte. Verweist er auf
   Detaildokumente (z. B. `auftraege/<name>/auftrag.md`), deren offene Punkte dort lesen.
   Fehlt `BACKLOG.md`: sagen und anbieten, es mit `/shutdown`-Vorlage aus Git-Log, TODOs und Doku anzulegen.
3. **Git:** Branch, `git status --short`, ungepushte Commits (`git log @{u}..` – ohne Upstream: sagen),
   die letzten 5 Commits.
4. **Startcheck** aus dem Backlog ausführen, wenn er nur liest (z. B. `py -3 fusion.py ping`).
   Schlägt er fehl: sagen, was Andrea starten muss.
5. **Melden**, kurz (max. ca. 15 Zeilen):
   - **Stand:** 1–2 Zeilen
   - **Offen:** die wichtigsten Punkte nach Prio, mit Verweis
   - **Vorschlag:** womit wir anfangen und warum (ein klarer Vorschlag, keine Liste von Optionen)
   - **Fragen an Andrea** aus dem Backlog, falls noch offen
   - **Achtung:** Pull nicht möglich, uncommittete Änderungen, ungepushte Commits, fehlgeschlagener Startcheck
6. Auf Andreas Antwort warten.
