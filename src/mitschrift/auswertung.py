"""Fehlerquote (WER, Word Error Rate) eines Transkripts gegen eine Referenz.

WER = (ersetzte + fehlende + zusätzliche Wörter) / Wörter der Referenz.

Vorsicht bei Schweizerdeutsch: Die Modelle *übersetzen* ins Hochdeutsche.
Eine korrekte, aber anders formulierte Übersetzung («Karotten» statt
«Rüebli») zählt hier als Fehler. Die WER taugt deshalb vor allem zum
Vergleichen von Modellen untereinander, nicht als absolute Note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def normalisieren(text: str) -> list[str]:
    """Kleinschreibung, Satzzeichen weg, Zifferngruppen zusammenziehen.

    "25'300" / "25.300" / "25 300" → "25300", "079 123 45 67" → "0791234567",
    damit Schreibweisen von Zahlen nicht als Fehler zählen.
    """
    t = text.lower().replace("ß", "ss")
    t = re.sub(r"(?<=\d)[\s'’.,](?=\d)", "", t)
    t = re.sub(r"[^\w\s]|_", " ", t)
    return t.split()


@dataclass
class Fehlerquote:
    wer: float
    ersetzt: int
    fehlend: int
    zusaetzlich: int
    referenz_woerter: int

    def __str__(self) -> str:
        return (
            f"{self.wer:.1%} (ersetzt {self.ersetzt}, fehlend {self.fehlend}, "
            f"zusätzlich {self.zusaetzlich} bei {self.referenz_woerter} Wörtern)"
        )


def fehlerquote(referenz: str, hypothese: str) -> Fehlerquote:
    ref, hyp = normalisieren(referenz), normalisieren(hypothese)
    n, m = len(ref), len(hyp)
    # d[i][j] = (kosten, ersetzt, fehlend, zusätzlich) für ref[:i] vs. hyp[:j]
    d = [[(j, 0, 0, j) for j in range(m + 1)]]
    for i in range(1, n + 1):
        zeile = [(i, 0, i, 0)]
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                zeile.append(d[i - 1][j - 1])
                continue
            k, e, f, z = d[i - 1][j - 1]
            ersetzen = (k + 1, e + 1, f, z)
            k, e, f, z = d[i - 1][j]
            loeschen = (k + 1, e, f + 1, z)
            k, e, f, z = zeile[j - 1]
            einfuegen = (k + 1, e, f, z + 1)
            zeile.append(min(ersetzen, loeschen, einfuegen))
        d.append(zeile)
    kosten, e, f, z = d[n][m]
    return Fehlerquote(wer=kosten / max(n, 1), ersetzt=e, fehlend=f, zusaetzlich=z, referenz_woerter=n)
