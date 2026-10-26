---
name: shutdown
description: Sessionende - speichert Stand, Entscheide, offene Punkte und Erfahrungen der Session so, dass /start sie wiederfindet. Nur auf Aufruf von Andrea.
disable-model-invocation: true
---

# /shutdown – Session sauber abschliessen

Ziel: Die nächste Session (mit `/start`) weiss ohne diesen Chat, wo wir stehen. Nichts doppelt speichern,
CLAUDE.md klein halten.

## Wohin gehört was

| Was | Wohin | Regel |
|---|---|---|
| Stand, nächster Schritt, offene Fragen an Andrea | `BACKLOG.md` → Abschnitt «Stand» ganz oben | **überschreiben**, nicht anhängen; max. ca. 15 Zeilen |
| Offene Aufgaben, Ideen | `BACKLOG.md` → Liste darunter | Erledigtes **löschen** (steht in Git-Log / Releases / CHANGELOG) |
| Entscheide und Details zu einer bestimmten Sache | deren eigenes Dokument (z. B. `auftraege/<name>/auftrag.md`, `docs/…`) | im Backlog nur ein Verweis |
| Dauerhafte Regeln und Erfahrungen, die künftige Arbeit ändern | Projekt-`CLAUDE.md`, passender Abschnitt | eine Zeile pro Erfahrung, Budget siehe unten |
| Persönliches, projektübergreifend (Arbeitsweise, Vorlieben) | Auto-Memory | selten; nichts, was im Repo steht |

Nicht speichern: was Code oder Git-Log schon sagen, Zwischenschritte, Sackgassen ohne Lehre.

## Ablauf

1. **Session durchgehen:** Was wurde gemacht, entschieden, verworfen (mit Grund)? Was ist offen, was blockiert?
   Welche Erfahrung würde beim nächsten Mal Zeit sparen?
2. **Arbeitsstand prüfen:** `git status`, nicht committete Änderungen und ungepushte Commits auflisten.
3. **`BACKLOG.md` nachführen** – bestehende Datei immer zuerst lesen und ergänzen, nie überschreiben.
   Fehlt sie: anlegen (Vorlage unten). Hat das Projekt schon eine eigene
   Struktur oder Sprache (z. B. Klaxon, Verbalis), diese beibehalten und nur den Abschnitt «Stand» oben pflegen.
4. **Detaildokumente** der bearbeiteten Sache nachführen (Entscheide, Masse, offene Fragen).
5. **CLAUDE.md – nur wenn es eine echte, wiederverwendbare Erfahrung gibt.** Budget: **max. 150 Zeilen**.
   - Vorher prüfen, ob es schon drinsteht → dann schärfen statt ergänzen.
   - Über dem Budget: ähnliche Punkte zusammenfassen, Veraltetes löschen, Detailwissen zu einem Thema nach
     `docs/erfahrungen-<thema>.md` auslagern und in CLAUDE.md nur eine Zeile «Bei <Thema>: `docs/…` lesen».
6. **Committen** (lokal), Betreff ohne Versionsnummer, aussagekräftig. **Nicht pushen**, ausser Andrea sagt es
   in dieser Session ausdrücklich oder die Projekt-CLAUDE.md erlaubt es – bei Web-Projekten löst ein Push ein
   Release aus.
7. **Kurz melden** (max. 10 Zeilen): was wo gespeichert ist, was ungepusht/uncommittet bleibt, nächster Schritt.

## Vorlage `BACKLOG.md`

```markdown
# Backlog <Projekt>

## Stand (<Datum>)

- **Zuletzt:** <1–3 Zeilen, was in der letzten Session passiert ist>
- **Nächster Schritt:** <konkret, womit /start beginnt>
- **Offene Fragen an Andrea:** <oder «keine»>
- **Voraussetzungen / Startcheck:** <z. B. Fusion mit Add-in starten, `py -3 fusion.py ping`>

## Offen

1. **<Titel>** – <1–2 Zeilen, Verweis auf Detaildokument> (Prio hoch/mittel/niedrig)

## Ideen / später

- …
```
