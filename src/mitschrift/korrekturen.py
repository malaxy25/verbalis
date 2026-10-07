"""Korrekturliste: wiederkehrende Erkennungsfehler automatisch ersetzen.

Aufbau: Jedes Ziel (richtige Schreibweise) ist eindeutig und sammelt seine
Fehlvarianten:

    tocco   ← Toko, Tokko
    Limmat  ← Limetnah, Limet nah

Eine Variante gehört immer zu genau einem Ziel. Wird sie später zu einem
anderen Ziel korrigiert, gilt die neuere Korrektur.

Die Liste entsteht aus Korrekturen im Transkript: `vorschlaege()` vergleicht
den Text vor und nach der Bearbeitung und liefert die ersetzten Wörter.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .transcription.modelle import mitschrift_home

WORT = re.compile(r"\w+(?:[-'’]\w+)*|[.,;:!?…]")  # Satzzeichen als Grenze im Vergleich
SATZZEICHEN = set(".,;:!?…")
MAX_WOERTER = 3  # längere Änderungen sind Umformulierungen, keine Erkennungsfehler
MIN_AEHNLICHKEIT = 0.6


def _schluessel(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass
class Korrekturliste:
    regeln: dict[str, list[str]] = field(default_factory=dict)  # Ziel → Varianten

    # ------------------------------------------------------------ Speichern

    @staticmethod
    def pfad() -> Path:
        return mitschrift_home() / "korrekturen.json"

    @classmethod
    def laden(cls) -> "Korrekturliste":
        try:
            daten = json.loads(cls.pfad().read_text(encoding="utf-8"))
            return cls({str(z): [str(v) for v in vs] for z, vs in daten.get("regeln", {}).items()})
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            return cls()

    def speichern(self) -> None:
        self.pfad().parent.mkdir(parents=True, exist_ok=True)
        self.pfad().write_text(json.dumps({"regeln": self.regeln}, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------ Abfragen

    def ziel_von(self, variante: str) -> str | None:
        k = _schluessel(variante)
        for ziel, varianten in self.regeln.items():
            if any(_schluessel(v) == k for v in varianten):
                return ziel
        return None

    def _ziel_schluessel(self, ziel: str) -> str | None:
        """Vorhandenes Ziel mit gleicher Schreibweise (ohne Gross/Klein) finden."""
        k = _schluessel(ziel)
        return next((z for z in self.regeln if _schluessel(z) == k), None)

    def einordnen(self, variante: str, ziel: str) -> dict:
        """Was würde `hinzufuegen` bewirken? Für die Vorschau in der Oberfläche."""
        bisher = self.ziel_von(variante)
        vorhandenes_ziel = self._ziel_schluessel(ziel)
        if bisher is not None and _schluessel(bisher) == _schluessel(ziel):
            art = "bekannt"
        elif bisher is not None:
            art = "ersetzt"
        elif vorhandenes_ziel is not None:
            art = "ergaenzt"
        else:
            art = "neu"
        return {"variante": variante, "ziel": vorhandenes_ziel or ziel, "art": art, "bisher": bisher}

    def als_liste(self) -> list[dict]:
        return [{"ziel": z, "varianten": sorted(vs, key=str.lower)}
                for z, vs in sorted(self.regeln.items(), key=lambda e: e[0].lower())]

    def ziele(self) -> list[str]:
        return list(self.regeln)

    # ------------------------------------------------------------ Ändern

    def hinzufuegen(self, variante: str, ziel: str) -> dict:
        variante, ziel = " ".join(variante.split()), " ".join(ziel.split())
        if not variante or not ziel or _schluessel(variante) == _schluessel(ziel):
            return {"variante": variante, "ziel": ziel, "art": "ignoriert", "bisher": None}
        info = self.einordnen(variante, ziel)
        if info["art"] == "ersetzt":
            self.entfernen(info["bisher"], variante)
        ziel = self._ziel_schluessel(ziel) or ziel
        varianten = self.regeln.setdefault(ziel, [])
        if not any(_schluessel(v) == _schluessel(variante) for v in varianten):
            varianten.append(variante)
        return info

    def entfernen(self, ziel: str, variante: str | None = None) -> None:
        if ziel not in self.regeln:
            return
        if variante is None:
            del self.regeln[ziel]
            return
        k = _schluessel(variante)
        self.regeln[ziel] = [v for v in self.regeln[ziel] if _schluessel(v) != k]
        if not self.regeln[ziel]:
            del self.regeln[ziel]

    # ------------------------------------------------------------ Anwenden

    def anwenden(self, text: str) -> tuple[str, int]:
        """Alle Varianten als ganze Wörter ersetzen. Gibt (text, anzahl) zurück."""
        paare = [(v, z) for z, vs in self.regeln.items() for v in vs]
        if not paare:
            return text, 0
        # Längere Varianten zuerst, damit «Limet nah» vor «Limet» greift
        paare.sort(key=lambda p: len(p[0]), reverse=True)
        ziel_fuer = {_schluessel(v): z for v, z in paare}
        muster = "|".join(r"\s+".join(map(re.escape, v.split())) for v, _ in paare)
        regex = re.compile(rf"(?<!\w)(?:{muster})(?!\w)", re.IGNORECASE)
        anzahl = 0

        def ersetzen(treffer: re.Match) -> str:
            nonlocal anzahl
            anzahl += 1
            return ziel_fuer[_schluessel(treffer.group(0))]

        return regex.sub(ersetzen, text), anzahl


def vorschlaege(alt: str, neu: str) -> list[tuple[str, str]]:
    """Wörter, die bei einer Bearbeitung ersetzt wurden, als (variante, ziel).

    Nur kurze Ersetzungen (bis 3 Wörter, nicht über Satzzeichen hinweg) –
    eingefügte, gelöschte oder umformulierte Passagen ergeben keine Regel,
    ein weitgehend neu geschriebener Absatz gar keine. Reine Änderungen der
    Gross-/Kleinschreibung auch nicht.
    """
    a = [m.group(0) for m in WORT.finditer(alt)]
    b = [m.group(0) for m in WORT.finditer(neu)]
    vergleich = difflib.SequenceMatcher(a=[w.lower() for w in a], b=[w.lower() for w in b], autojunk=False)
    if vergleich.ratio() < MIN_AEHNLICHKEIT:
        return []  # weitgehend neu geschrieben – keine einzelnen Erkennungsfehler
    ergebnis: list[tuple[str, str]] = []
    for art, i1, i2, j1, j2 in vergleich.get_opcodes():
        if art != "replace" or i2 - i1 > MAX_WOERTER or j2 - j1 > MAX_WOERTER:
            continue
        if SATZZEICHEN & {*a[i1:i2], *b[j1:j2]}:
            continue
        variante, ziel = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if _schluessel(variante) != _schluessel(ziel) and (variante, ziel) not in ergebnis:
            ergebnis.append((variante, ziel))
    return ergebnis
