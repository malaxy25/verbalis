"""Segmente beider Spuren zu einem Gesprächsverlauf zusammenführen.

Die Spuren sind zeitlich synchron (siehe Recorder), daher reicht es,
alle Segmente nach Startzeit zu sortieren. Aufeinanderfolgende Segmente
derselben Person fassen wir zu einem Absatz zusammen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from .transcription.base import Segment

MAX_PAUSE_IM_ABSATZ_S = 2.0


def zusammenfuehren(spuren: dict[str, list[Segment]]) -> list[Segment]:
    alle = [replace(s, sprecher=name) for name, segmente in spuren.items() for s in segmente]
    alle.sort(key=lambda s: (s.start, s.ende))

    absaetze: list[Segment] = []
    for s in alle:
        letzter = absaetze[-1] if absaetze else None
        if letzter and letzter.sprecher == s.sprecher and s.start - letzter.ende <= MAX_PAUSE_IM_ABSATZ_S:
            absaetze[-1] = replace(letzter, ende=max(letzter.ende, s.ende), text=f"{letzter.text} {s.text}")
        else:
            absaetze.append(s)
    return absaetze


def _zeit(sekunden: float) -> str:
    h, rest = divmod(int(sekunden), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def als_markdown(absaetze: list[Segment], titel: str, kopf: dict[str, str]) -> str:
    zeilen = [f"# {titel}", ""]
    zeilen += [f"- **{k}:** {v}" for k, v in kopf.items()]
    zeilen.append("")
    for a in absaetze:
        zeilen.append(f"**[{_zeit(a.start)}] {a.sprecher}:** {a.text}")
        zeilen.append("")
    return "\n".join(zeilen)


def speichern(ordner: Path, dateiname: str, absaetze: list[Segment], titel: str, kopf: dict[str, str]) -> Path:
    md = ordner / f"{dateiname}.md"
    md.write_text(als_markdown(absaetze, titel, kopf), encoding="utf-8")
    (ordner / f"{dateiname}.json").write_text(
        json.dumps({"kopf": kopf, "segmente": [asdict(a) for a in absaetze]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return md
